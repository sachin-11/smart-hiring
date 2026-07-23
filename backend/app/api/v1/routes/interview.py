import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketState

from app.agents import interview_agent
from app.core.database import get_db
from app.models.interview import Interview
from app.schemas.interview import (
    InterviewAnswerResponse,
    InterviewStartRequest,
    InterviewStartResponse,
    InterviewTranscriptResponse,
    QAExchange,
)
from app.services import s3_service, voice_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/interview", tags=["interview"])
# Registered without the "/interview" prefix so the socket lives at the spec'd
# /ws/interview/{session_id} path rather than /interview/ws/interview/{session_id}.
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
async def start_interview(payload: InterviewStartRequest) -> InterviewStartResponse:
    try:
        result = await interview_agent.start_interview(payload.candidate_id, payload.job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    audio_url = await _synthesize_and_upload(result["session_id"], result["question"])
    return InterviewStartResponse(**result, audio_url=audio_url)


@router.post("/answer", response_model=InterviewAnswerResponse)
async def submit_answer(
    session_id: uuid.UUID = Form(...),
    answer_text: str | None = Form(default=None),
    audio_file: UploadFile | None = File(default=None),
) -> InterviewAnswerResponse:
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
async def get_transcript(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> InterviewTranscriptResponse:
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


@ws_router.websocket("/ws/interview/{session_id}")
async def interview_voice_stream(websocket: WebSocket, session_id: uuid.UUID) -> None:
    """Real-time voice turn-taking: client streams raw PCM16LE mono 16kHz audio
    frames as binary WS messages; the server runs WebRTC VAD to detect when the
    candidate stops talking, transcribes the utterance, runs it through the
    interview agent, and pushes back the next question as JSON + synthesized audio."""
    await websocket.accept()
    vad = voice_service.VoiceActivityDetector()

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            if (data := message.get("bytes")) is not None:
                utterance_ready = vad.push(data)
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

                if result["question"]:
                    try:
                        audio = await voice_service.synthesize_speech(result["question"])
                        await websocket.send_json({"type": "audio_start"})
                        await websocket.send_bytes(audio)
                    except Exception:
                        logger.exception("TTS failed mid-stream for session=%s", session_id)

            elif (text := message.get("text")) is not None:
                # Control messages from the client (e.g. {"type": "ping"}) are accepted but ignored for now.
                logger.debug("Received text control message on interview WS: %s", text)

    except WebSocketDisconnect:
        logger.info("Interview WS disconnected for session=%s", session_id)
    finally:
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close()
