"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Mic, Square } from "lucide-react"

import { Button } from "@/components/ui/button"
import WaveformVisualizer from "@/components/WaveformVisualizer"
import type { InterviewWsServerMessage } from "@/types/interview"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1"
const WS_BASE_URL = API_BASE_URL.replace(/^http/, "ws")

const MAX_RECONNECT_ATTEMPTS = 3
const RECONNECT_BASE_DELAY_MS = 1000

type VoiceState = "idle" | "connecting" | "listening" | "processing" | "reconnecting"

interface VoiceRecorderProps {
  sessionId: string
  disabled?: boolean
  onTranscript: (text: string) => void
  onResult: (result: Extract<InterviewWsServerMessage, { type: "result" }>) => void
  onAudioChunk: (audio: ArrayBuffer) => void
  onAudioStart?: (chunkCount: number) => void
  onAudioEnd?: () => void
  onNudge?: () => void
  /** Barge-in hook: called right before the mic starts, so the parent can stop
   * whatever AI audio is currently playing instead of talking over it. */
  onBeforeRecording?: () => void
  onError: (message: string) => void
}

export default function VoiceRecorder({
  sessionId,
  disabled,
  onTranscript,
  onResult,
  onAudioChunk,
  onAudioStart,
  onAudioEnd,
  onNudge,
  onBeforeRecording,
  onError,
}: VoiceRecorderProps) {
  const [state, setState] = useState<VoiceState>("idle")
  const [elapsedMs, setElapsedMs] = useState(0)

  const wsRef = useRef<WebSocket | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const workletRef = useRef<AudioWorkletNode | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const [analyserForVisual, setAnalyserForVisual] = useState<AnalyserNode | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const intentionalCloseRef = useRef(false)
  const reconnectAttemptsRef = useRef(0)
  const wasRecordingRef = useRef(false)

  const stopMic = useCallback(() => {
    workletRef.current?.disconnect()
    workletRef.current?.port.close()
    analyserRef.current?.disconnect()
    workletRef.current = null
    analyserRef.current = null
    setAnalyserForVisual(null)
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    audioCtxRef.current?.close().catch(() => {})
    audioCtxRef.current = null
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const handleSocketMessage = useCallback(
    (event: MessageEvent) => {
      if (event.data instanceof ArrayBuffer) {
        onAudioChunk(event.data)
        return
      }
      const message = JSON.parse(event.data) as InterviewWsServerMessage
      if (message.type === "transcript") {
        setState("processing")
        stopMic()
        onTranscript(message.text)
      } else if (message.type === "result") {
        onResult(message)
        if (!message.complete) setState("idle")
      } else if (message.type === "audio_start") {
        onAudioStart?.(message.chunk_count)
      } else if (message.type === "audio_end") {
        onAudioEnd?.()
      } else if (message.type === "nudge") {
        onNudge?.()
      } else if (message.type === "error") {
        onError(message.detail)
        setState("idle")
      }
    },
    [onAudioChunk, onAudioStart, onAudioEnd, onNudge, onTranscript, onResult, onError, stopMic]
  )

  const connectSocket = useCallback((): Promise<WebSocket> => {
    return new Promise((resolve, reject) => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        resolve(wsRef.current)
        return
      }
      intentionalCloseRef.current = false
      const ws = new WebSocket(`${WS_BASE_URL}/ws/interview/${sessionId}`)
      ws.binaryType = "arraybuffer"

      ws.onopen = () => {
        reconnectAttemptsRef.current = 0
        resolve(ws)
      }
      ws.onerror = () => reject(new Error("Voice connection failed"))
      ws.onclose = () => {
        wsRef.current = null
        if (intentionalCloseRef.current || !wasRecordingRef.current) return

        // Unexpected drop mid-session (network blip, server restart) — the
        // interview's actual state lives in Redis server-side, so a fresh
        // socket to the same session_id just resumes; only the transport needs
        // re-establishing. Give up after a few tries rather than looping forever.
        if (reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
          onError("Lost connection to the interview. Please check your network and try again.")
          setState("idle")
          return
        }
        reconnectAttemptsRef.current += 1
        setState("reconnecting")
        setTimeout(
          () => {
            connectSocket()
              .then((reconnected) => {
                reconnected.onmessage = handleSocketMessage
                setState((s) => (s === "reconnecting" ? "listening" : s))
              })
              .catch(() => {
                onError("Lost connection to the interview. Please check your network and try again.")
                setState("idle")
              })
          },
          RECONNECT_BASE_DELAY_MS * 2 ** (reconnectAttemptsRef.current - 1)
        )
      }
      ws.onmessage = handleSocketMessage

      wsRef.current = ws
    })
  }, [sessionId, handleSocketMessage, onError])

  const startRecording = useCallback(async () => {
    try {
      onBeforeRecording?.()
      setState("connecting")
      wasRecordingRef.current = true
      await connectSocket()

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      })
      streamRef.current = stream

      // If the mic device disappears mid-recording (unplugged, OS revokes
      // permission), the stream otherwise just goes quiet with no signal to the
      // user — surface it explicitly instead of hanging in "listening" forever.
      const [track] = stream.getAudioTracks()
      track.onended = () => {
        if (streamRef.current !== stream) return // already stopped intentionally
        stopMic()
        setState("idle")
        onError("Microphone disconnected. Please check your device and try again.")
      }

      const audioCtx = new AudioContext()
      audioCtxRef.current = audioCtx
      // Safari suspends new AudioContexts until explicitly resumed, even from
      // within a user-gesture-triggered handler.
      if (audioCtx.state === "suspended") {
        await audioCtx.resume()
      }

      await audioCtx.audioWorklet.addModule("/audio-processor.worklet.js")
      const source = audioCtx.createMediaStreamSource(stream)

      const analyser = audioCtx.createAnalyser()
      analyser.fftSize = 2048
      source.connect(analyser)
      analyserRef.current = analyser
      setAnalyserForVisual(analyser)

      const worklet = new AudioWorkletNode(audioCtx, "pcm-recorder-processor")
      workletRef.current = worklet
      worklet.port.onmessage = (e: MessageEvent<ArrayBuffer>) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(e.data)
        }
      }
      source.connect(worklet)

      setElapsedMs(0)
      timerRef.current = setInterval(() => setElapsedMs((ms) => ms + 200), 200)
      setState("listening")
    } catch (err) {
      wasRecordingRef.current = false
      stopMic()
      setState("idle")
      onError(err instanceof Error ? err.message : "Could not access microphone")
    }
  }, [connectSocket, onBeforeRecording, onError, stopMic])

  const cancelRecording = useCallback(() => {
    wasRecordingRef.current = false
    intentionalCloseRef.current = true
    stopMic()
    wsRef.current?.close()
    setState("idle")
  }, [stopMic])

  useEffect(() => {
    return () => {
      wasRecordingRef.current = false
      intentionalCloseRef.current = true
      stopMic()
      wsRef.current?.close()
    }
  }, [stopMic])

  const seconds = (elapsedMs / 1000).toFixed(1)

  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border p-4">
      <WaveformVisualizer analyser={analyserForVisual} active={state === "listening"} className="w-full" />

      <div className="flex items-center gap-3">
        {state === "idle" && (
          <Button onClick={startRecording} disabled={disabled} size="lg" className="gap-2">
            <Mic /> Start speaking
          </Button>
        )}
        {state === "connecting" && (
          <Button disabled size="lg" className="gap-2">
            Connecting…
          </Button>
        )}
        {state === "reconnecting" && (
          <Button disabled size="lg" variant="outline" className="gap-2">
            Reconnecting…
          </Button>
        )}
        {state === "listening" && (
          <Button onClick={cancelRecording} variant="destructive" size="lg" className="gap-2">
            <Square /> Listening… {seconds}s (auto-submits on silence)
          </Button>
        )}
        {state === "processing" && (
          <Button disabled size="lg" className="gap-2">
            Processing your answer…
          </Button>
        )}
      </div>
    </div>
  )
}
