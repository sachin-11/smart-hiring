import asyncio
import logging
import time
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketState

from app.agents import interview_agent
from app.core import security
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import (
    get_current_recruiter,
    interview_token_matches,
    recruiter_from_credentials,
    require_recruiter_or_interview_access,
)
from app.core.rate_limit import limiter
from app.models.interview import Interview
from app.models.recruiter import Recruiter
from app.schemas.interview import (
    InterviewAnswerResponse,
    InterviewDeleteResponse,
    InterviewStartRequest,
    InterviewStartResponse,
    InterviewStopResponse,
    InterviewTranscriptResponse,
    QAExchange,
)
from app.services import s3_service, voice_service

logger = logging.getLogger(__name__)

# NOT router-level auth here (unlike every other resource) — interview
# endpoints are the one place a non-recruiter (the candidate) legitimately
# needs access, via a magic-link token scoped to their own session_id rather
# than a recruiter login. Each endpoint below picks the right check for its
# own shape: /start is recruiter-only (starting an interview for arbitrary
# candidate_id/job_id isn't something a candidate should be able to do),
# /answer and /transcript accept either a recruiter OR a matching token.
router = APIRouter(prefix="/interview", tags=["interview"])
_bearer_scheme = HTTPBearer(auto_error=False)
# Registered without the "/interview" prefix so the socket lives at the spec'd
# /ws/interview/{session_id} path rather than /interview/ws/interview/{session_id}.
# NOTE: unauthenticated — browsers can't attach an Authorization header to a
# WebSocket handshake. It relies on session_id being an unguessable UUID; add
# a query-param token check here if that's ever not a strong enough guarantee.
ws_router = APIRouter(tags=["interview"])


async def _synthesize_and_upload(session_id: uuid.UUID, text: str) -> str | None:
    """Best-effort TTS: a synthesis/upload failure shouldn't block the interview
    from continuing in text mode, so this logs and returns None instead of raising."""
    try:
        audio = await voice_service.synthesize_speech(text)
        key, _ = await s3_service.upload_interview_audio(
            session_id, f"q_{uuid.uuid4().hex[:8]}.mp3", audio, "audio/mpeg"
        )
        # The bucket is private (same as resumes) — a raw object URL 403s, so
        # hand back a presigned URL the browser can actually play.
        return s3_service.generate_presigned_url(key)
    except Exception:
        logger.exception("TTS synthesis/upload failed for session=%s", session_id)
        return None


@router.post("/start", response_model=InterviewStartResponse)
@limiter.limit(settings.RATE_LIMIT_LLM_ENDPOINTS)
async def start_interview(
    request: Request,
    payload: InterviewStartRequest,
    _recruiter: Recruiter = Depends(get_current_recruiter),
) -> InterviewStartResponse:
    try:
        result = await interview_agent.start_interview(payload.candidate_id, payload.job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    audio_url = await _synthesize_and_upload(result["session_id"], result["question"])
    access_token = security.create_interview_access_token(result["session_id"])
    access_url = f"{settings.FRONTEND_URL}/interview/{result['session_id']}?token={access_token}"
    return InterviewStartResponse(**result, audio_url=audio_url, access_token=access_token, access_url=access_url)


@router.post("/answer", response_model=InterviewAnswerResponse)
async def submit_answer(
    session_id: uuid.UUID = Form(...),
    answer_text: str | None = Form(default=None),
    audio_file: UploadFile | None = File(default=None),
    token: str | None = Form(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> InterviewAnswerResponse:
    recruiter = await recruiter_from_credentials(credentials, db)
    if recruiter is None and not interview_token_matches(token, session_id):
        raise HTTPException(status_code=401, detail="Not authenticated")

    if audio_file is not None:
        data = await audio_file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Uploaded audio file is empty")
        answer_text = await voice_service.transcribe_audio(data, audio_file.filename or "answer.webm")
    elif not answer_text:
        raise HTTPException(status_code=400, detail="Provide either answer_text or audio_file")

    try:
        result = await interview_agent.submit_answer(session_id, answer_text)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    audio_url = None
    if not result["complete"] and result["question"]:
        audio_url = await _synthesize_and_upload(session_id, result["question"])

    return InterviewAnswerResponse(**result, audio_url=audio_url)


@router.get("/{session_id}/transcript", response_model=InterviewTranscriptResponse)
async def get_transcript(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _access: None = Depends(require_recruiter_or_interview_access),
) -> InterviewTranscriptResponse:
    live = await interview_agent.get_live_transcript(session_id)
    if live is not None:
        return InterviewTranscriptResponse(
            session_id=session_id,
            candidate_id=uuid.UUID(live["candidate_id"]),
            job_id=uuid.UUID(live["job_id"]),
            status=live["status"],
            exchanges=[QAExchange(**ex) for ex in live["exchanges"]],
            question_index=live["question_index"],
            total_questions=live["total_questions"],
            average_score=None,
        )

    interview = await db.get(Interview, session_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview session not found")

    exchanges_raw = (interview.ai_feedback or {}).get("exchanges", [])
    non_follow_up_count = sum(1 for ex in exchanges_raw if not ex.get("is_follow_up"))
    return InterviewTranscriptResponse(
        session_id=session_id,
        candidate_id=interview.candidate_id,
        job_id=interview.job_id,
        status=interview.status,
        question_index=non_follow_up_count,
        total_questions=non_follow_up_count,
        exchanges=[QAExchange(**ex) for ex in exchanges_raw],
        average_score=interview.ai_score,
    )


@router.post("/{session_id}/stop", response_model=InterviewStopResponse)
async def stop_interview(
    session_id: uuid.UUID,
    _recruiter: Recruiter = Depends(get_current_recruiter),
) -> InterviewStopResponse:
    """Recruiter-only: ends an in-progress interview early, keeping whatever
    was answered so far and marking it CANCELLED instead of COMPLETED."""
    try:
        result = await interview_agent.stop_interview(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return InterviewStopResponse(**result)


@router.delete("/{session_id}", response_model=InterviewDeleteResponse)
async def delete_interview(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _recruiter: Recruiter = Depends(get_current_recruiter),
) -> InterviewDeleteResponse:
    """Recruiter-only: permanently deletes a single interview record (and its
    report, via FK cascade) without touching the candidate or the rest of
    their history. Interview audio is only reachable by S3 key prefix, so
    it's cleaned up here rather than relying on any DB-side tracking."""
    interview = await db.get(Interview, session_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")

    s3_objects_deleted = await s3_service.delete_prefix(s3_service.build_interview_prefix(session_id))

    await db.delete(interview)
    await db.commit()

    return InterviewDeleteResponse(session_id=session_id, s3_objects_deleted=s3_objects_deleted)


async def _stream_question_audio(websocket: WebSocket, session_id: uuid.UUID, question: str) -> None:
    """Synthesizes and sends the next question sentence-by-sentence instead of
    as one clip — the candidate hears the first sentence while later ones are
    still being generated, instead of silence for the whole response."""
    chunks = voice_service.split_into_speech_chunks(question)
    try:
        await websocket.send_json({"type": "audio_start", "chunk_count": len(chunks)})
        for chunk_text in chunks:
            audio = await voice_service.synthesize_speech(chunk_text)
            await websocket.send_bytes(audio)
    except Exception:
        logger.exception("TTS failed mid-stream for session=%s", session_id)
    finally:
        await websocket.send_json({"type": "audio_end"})


@ws_router.websocket("/ws/interview/{session_id}")
async def interview_voice_stream(websocket: WebSocket, session_id: uuid.UUID) -> None:
    """Real-time voice turn-taking: client streams raw PCM16LE mono 16kHz audio
    frames as binary WS messages; the server runs WebRTC VAD to detect when the
    candidate stops talking, transcribes the utterance, runs it through the
    interview agent, and pushes back the next question as JSON + synthesized audio.

    Session state itself lives in Redis (see interview_agent), so a client that
    loses this connection and opens a fresh one to the same session_id resumes
    correctly — the reconnect logic lives entirely on the frontend."""
    await websocket.accept()
    vad = voice_service.VoiceActivityDetector()

    # Idle handling: distinguishes "candidate is silently thinking" (frames still
    # arriving, no speech yet) from genuine no-response, since audio frames keep
    # streaming continuously while the mic is open regardless of whether the
    # candidate is actually talking.
    last_speech_at = time.monotonic()
    nudged = False

    try:
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=settings.INTERVIEW_WS_POLL_SECONDS)
            except asyncio.TimeoutError:
                idle_for = time.monotonic() - last_speech_at
                if idle_for >= settings.INTERVIEW_WS_TIMEOUT_SECONDS:
                    await websocket.send_json(
                        {"type": "error", "detail": "We didn't hear a response — please try again."}
                    )
                    break
                if idle_for >= settings.INTERVIEW_WS_NUDGE_SECONDS and not nudged:
                    nudged = True
                    await websocket.send_json({"type": "nudge"})
                continue

            if message.get("type") == "websocket.disconnect":
                break

            if (data := message.get("bytes")) is not None:
                utterance_ready = vad.push(data)
                if vad.has_heard_speech:
                    last_speech_at = time.monotonic()
                    nudged = False
                if not utterance_ready:
                    continue

                pcm = vad.take_utterance()
                if not pcm:
                    continue

                wav_bytes = voice_service.pcm_to_wav(pcm)
                try:
                    transcript = await voice_service.transcribe_audio(wav_bytes, "answer.wav")
                    if not transcript.strip():
                        continue

                    await websocket.send_json({"type": "transcript", "text": transcript})

                    result = await interview_agent.submit_answer(session_id, transcript)
                except ValueError as exc:
                    await websocket.send_json({"type": "error", "detail": str(exc)})
                    break
                except RuntimeError as exc:
                    await websocket.send_json({"type": "error", "detail": str(exc)})
                    continue

                await websocket.send_json(
                    {
                        "type": "result",
                        "score": result["score"],
                        "feedback": result["feedback"],
                        "is_follow_up": result["is_follow_up"],
                        "complete": result["complete"],
                        "question": result["question"],
                        "category": result["category"],
                        "question_index": result["question_index"],
                        "total_questions": result["total_questions"],
                    }
                )

                if result["complete"]:
                    break

                last_speech_at = time.monotonic()
                nudged = False

                if result["question"]:
                    await _stream_question_audio(websocket, session_id, result["question"])

            elif (text := message.get("text")) is not None:
                # Control messages from the client (e.g. {"type": "ping"}) are accepted but ignored for now.
                logger.debug("Received text control message on interview WS: %s", text)

    except WebSocketDisconnect:
        logger.info("Interview WS disconnected for session=%s", session_id)
    finally:
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close()
