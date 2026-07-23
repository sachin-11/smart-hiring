"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Mic, Square } from "lucide-react"

import { Button } from "@/components/ui/button"
import WaveformVisualizer from "@/components/WaveformVisualizer"
import { downsampleTo16k, floatTo16BitPCM } from "@/lib/pcm"
import type { InterviewWsServerMessage } from "@/types/interview"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1"
const WS_BASE_URL = API_BASE_URL.replace(/^http/, "ws")

type VoiceState = "idle" | "connecting" | "listening" | "processing"

interface VoiceRecorderProps {
  sessionId: string
  disabled?: boolean
  onTranscript: (text: string) => void
  onResult: (result: Extract<InterviewWsServerMessage, { type: "result" }>) => void
  onAudio: (audio: ArrayBuffer) => void
  onError: (message: string) => void
}

export default function VoiceRecorder({
  sessionId,
  disabled,
  onTranscript,
  onResult,
  onAudio,
  onError,
}: VoiceRecorderProps) {
  const [state, setState] = useState<VoiceState>("idle")
  const [elapsedMs, setElapsedMs] = useState(0)

  const wsRef = useRef<WebSocket | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const [analyserForVisual, setAnalyserForVisual] = useState<AnalyserNode | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const expectingAudioRef = useRef(false)

  const stopMic = useCallback(() => {
    processorRef.current?.disconnect()
    analyserRef.current?.disconnect()
    processorRef.current = null
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

  const ensureSocket = useCallback((): Promise<WebSocket> => {
    return new Promise((resolve, reject) => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        resolve(wsRef.current)
        return
      }
      const ws = new WebSocket(`${WS_BASE_URL}/ws/interview/${sessionId}`)
      ws.binaryType = "arraybuffer"

      ws.onopen = () => resolve(ws)
      ws.onerror = () => reject(new Error("Voice connection failed"))
      ws.onclose = () => {
        wsRef.current = null
      }
      ws.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
          expectingAudioRef.current = false
          onAudio(event.data)
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
          expectingAudioRef.current = true
        } else if (message.type === "error") {
          onError(message.detail)
          setState("idle")
        }
      }

      wsRef.current = ws
    })
  }, [sessionId, onTranscript, onResult, onAudio, onError, stopMic])

  const startRecording = useCallback(async () => {
    try {
      setState("connecting")
      await ensureSocket()

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      // ScriptProcessorNode is deprecated in favor of AudioWorklet, but it needs no
      // separate worklet module file to serve and is supported everywhere we target.
      const audioCtx = new AudioContext()
      audioCtxRef.current = audioCtx
      const source = audioCtx.createMediaStreamSource(stream)

      const analyser = audioCtx.createAnalyser()
      analyser.fftSize = 2048
      source.connect(analyser)
      analyserRef.current = analyser
      setAnalyserForVisual(analyser)

      const processor = audioCtx.createScriptProcessor(4096, 1, 1)
      processorRef.current = processor
      source.connect(processor)
      const silentGain = audioCtx.createGain()
      silentGain.gain.value = 0
      processor.connect(silentGain)
      silentGain.connect(audioCtx.destination)

      processor.onaudioprocess = (e) => {
        const input = e.inputBuffer.getChannelData(0)
        const downsampled = downsampleTo16k(input, audioCtx.sampleRate)
        const pcm16 = floatTo16BitPCM(downsampled)
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(pcm16)
        }
      }

      setElapsedMs(0)
      timerRef.current = setInterval(() => setElapsedMs((ms) => ms + 200), 200)
      setState("listening")
    } catch (err) {
      stopMic()
      setState("idle")
      onError(err instanceof Error ? err.message : "Could not access microphone")
    }
  }, [ensureSocket, onError, stopMic])

  const cancelRecording = useCallback(() => {
    stopMic()
    setState("idle")
  }, [stopMic])

  useEffect(() => {
    return () => {
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
