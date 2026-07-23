"use client"

import { useEffect, useRef } from "react"

interface WaveformVisualizerProps {
  analyser: AnalyserNode | null
  active: boolean
  className?: string
}

export default function WaveformVisualizer({ analyser, active, className }: WaveformVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const frameRef = useRef<number | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    if (!active || !analyser) {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      return
    }

    const bufferLength = analyser.fftSize
    const dataArray = new Uint8Array(bufferLength)

    const draw = () => {
      frameRef.current = requestAnimationFrame(draw)
      analyser.getByteTimeDomainData(dataArray)

      const { width, height } = canvas
      ctx.clearRect(0, 0, width, height)
      ctx.lineWidth = 2
      ctx.strokeStyle = "hsl(var(--primary, 222 47% 40%))"
      ctx.beginPath()

      const sliceWidth = width / bufferLength
      let x = 0
      for (let i = 0; i < bufferLength; i++) {
        const v = dataArray[i] / 128.0
        const y = (v * height) / 2
        if (i === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
        x += sliceWidth
      }
      ctx.lineTo(width, height / 2)
      ctx.stroke()
    }

    draw()
    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current)
    }
  }, [analyser, active])

  return <canvas ref={canvasRef} width={400} height={64} className={className} />
}
