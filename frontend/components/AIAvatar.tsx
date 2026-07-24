"use client"

import { useEffect, useRef } from "react"
import { Bot } from "lucide-react"

import { cn } from "@/lib/utils"

interface AIAvatarProps {
  /** The AI's own playback audio graph — null while nothing is set up yet. */
  analyser: AnalyserNode | null
  /** True while AI audio is actually playing (drives the reactive glow/scale). */
  speaking: boolean
  className?: string
}

/** A circular avatar that pulses and glows in real time with the AI's own
 * speech amplitude — the audio-output counterpart to WaveformVisualizer,
 * which does the same for the candidate's mic input. */
export default function AIAvatar({ analyser, speaking, className }: AIAvatarProps) {
  const coreRef = useRef<HTMLDivElement>(null)
  const ring1Ref = useRef<HTMLDivElement>(null)
  const ring2Ref = useRef<HTMLDivElement>(null)
  const frameRef = useRef<number | null>(null)

  useEffect(() => {
    const core = coreRef.current
    const ring1 = ring1Ref.current
    const ring2 = ring2Ref.current
    if (!core || !ring1 || !ring2) return

    if (!speaking || !analyser) {
      core.style.transform = "scale(1)"
      core.style.boxShadow = "0 0 0 rgba(99, 102, 241, 0)"
      ring1.style.transform = "scale(1)"
      ring1.style.opacity = "0"
      ring2.style.transform = "scale(1)"
      ring2.style.opacity = "0"
      return
    }

    const dataArray = new Uint8Array(analyser.fftSize)

    const draw = () => {
      frameRef.current = requestAnimationFrame(draw)
      analyser.getByteTimeDomainData(dataArray)

      let sumSquares = 0
      for (let i = 0; i < dataArray.length; i++) {
        const normalized = (dataArray[i] - 128) / 128
        sumSquares += normalized * normalized
      }
      const volume = Math.sqrt(sumSquares / dataArray.length) // ~0 (silence) to ~0.4 (loud speech)

      const coreScale = 1 + Math.min(volume * 2.2, 0.35)
      const glowAlpha = Math.min(volume * 2.5, 0.55)
      core.style.transform = `scale(${coreScale})`
      core.style.boxShadow = `0 0 ${20 + volume * 60}px rgba(99, 102, 241, ${glowAlpha})`

      const ringScale = 1 + Math.min(volume * 3.5, 0.9)
      ring1.style.transform = `scale(${ringScale})`
      ring1.style.opacity = String(Math.min(volume * 1.8, 0.5))
      ring2.style.transform = `scale(${1 + Math.min(volume * 5, 1.4)})`
      ring2.style.opacity = String(Math.min(volume * 1.2, 0.3))
    }

    draw()
    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current)
    }
  }, [analyser, speaking])

  return (
    <div className={cn("relative flex items-center justify-center", className)}>
      <div
        ref={ring2Ref}
        className="absolute size-24 rounded-full bg-primary/20 opacity-0 transition-[transform,opacity] duration-100 ease-out"
      />
      <div
        ref={ring1Ref}
        className="absolute size-24 rounded-full bg-primary/30 opacity-0 transition-[transform,opacity] duration-100 ease-out"
      />
      <div
        ref={coreRef}
        className={cn(
          "relative flex size-24 items-center justify-center rounded-full bg-gradient-to-br from-primary to-violet-500 text-primary-foreground transition-[transform,box-shadow] duration-100 ease-out",
          !speaking && "animate-pulse"
        )}
      >
        <Bot className="size-10" />
      </div>
    </div>
  )
}
