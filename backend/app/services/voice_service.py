import io
import logging
import re

import webrtcvad

from app.services.embedding_service import get_openai_client

logger = logging.getLogger(__name__)

WHISPER_MODEL = "whisper-1"
TTS_MODEL = "tts-1"
TTS_VOICE = "alloy"

# VAD operates on 16-bit mono PCM at one of 8000/16000/32000/48000 Hz.
VAD_SAMPLE_RATE = 16000
VAD_FRAME_MS = 30
VAD_FRAME_BYTES = int(VAD_SAMPLE_RATE * (VAD_FRAME_MS / 1000)) * 2  # 16-bit samples
VAD_AGGRESSIVENESS = 2
SILENCE_FRAMES_TO_END_UTTERANCE = 27  # ~800ms of trailing silence


async def transcribe_audio(data: bytes, filename: str = "answer.webm") -> str:
    """STT via OpenAI Whisper. Accepts any container Whisper supports
    (webm/mp3/wav/m4a/...) — no client-side transcoding required."""
    client = get_openai_client()
    response = await client.audio.transcriptions.create(
        model=WHISPER_MODEL,
        file=(filename, io.BytesIO(data)),
    )
    return response.text


async def synthesize_speech(text: str, voice: str = TTS_VOICE) -> bytes:
    """TTS via OpenAI TTS. Returns raw mp3 bytes."""
    client = get_openai_client()
    response = await client.audio.speech.create(model=TTS_MODEL, voice=voice, input=text)
    return await response.aread()


def split_into_speech_chunks(text: str) -> list[str]:
    """Splits a response into sentence-ish chunks so the caller can synthesize
    and send them one at a time — the candidate hears the first sentence while
    later ones are still being generated, instead of silence for the whole
    response followed by one long clip."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    return sentences or [text]


class VoiceActivityDetector:
    """Wraps webrtcvad frame-by-frame speech detection plus trailing-silence
    tracking, so a caller streaming raw PCM chunks over a WebSocket can tell
    when the candidate has stopped talking without waiting for a client signal."""

    def __init__(self, aggressiveness: int = VAD_AGGRESSIVENESS) -> None:
        self._vad = webrtcvad.Vad(aggressiveness)
        self._buffer = b""
        self._speech_buffer = b""
        self._consecutive_silence = 0
        self._has_heard_speech = False

    @property
    def has_heard_speech(self) -> bool:
        """True once any speech has been detected in the current utterance —
        lets a caller distinguish "candidate is silently thinking" (frames
        still arriving, no speech yet) from genuine idle for timeout purposes."""
        return self._has_heard_speech

    def _frames(self) -> list[bytes]:
        frames = []
        while len(self._buffer) >= VAD_FRAME_BYTES:
            frames.append(self._buffer[:VAD_FRAME_BYTES])
            self._buffer = self._buffer[VAD_FRAME_BYTES:]
        return frames

    def push(self, pcm_chunk: bytes) -> bool:
        """Feeds raw PCM16LE mono audio at VAD_SAMPLE_RATE. Returns True once
        enough trailing silence has followed detected speech to end the utterance."""
        self._buffer += pcm_chunk

        for frame in self._frames():
            is_speech = self._vad.is_speech(frame, VAD_SAMPLE_RATE)
            if is_speech:
                self._has_heard_speech = True
                self._consecutive_silence = 0
                self._speech_buffer += frame
            else:
                self._speech_buffer += frame
                if self._has_heard_speech:
                    self._consecutive_silence += 1
                    if self._consecutive_silence >= SILENCE_FRAMES_TO_END_UTTERANCE:
                        return True
        return False

    def take_utterance(self) -> bytes:
        """Returns the buffered speech-containing PCM and resets state for the next utterance."""
        audio = self._speech_buffer
        self._speech_buffer = b""
        self._consecutive_silence = 0
        self._has_heard_speech = False
        return audio


def pcm_to_wav(pcm_data: bytes, sample_rate: int = VAD_SAMPLE_RATE, channels: int = 1, sample_width: int = 2) -> bytes:
    """Wraps raw PCM16LE bytes in a minimal WAV container so Whisper can read it."""
    import struct

    byte_rate = sample_rate * channels * sample_width
    block_align = channels * sample_width
    data_size = len(pcm_data)

    header = b"RIFF" + struct.pack("<I", 36 + data_size) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, channels, sample_rate, byte_rate, block_align, sample_width * 8)
    header += b"data" + struct.pack("<I", data_size)
    return header + pcm_data
