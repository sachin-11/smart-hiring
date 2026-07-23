"use client"

import { useState } from "react"
import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { HiringState, PipelineEvent, StepStatus } from "@/types/pipeline"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1"

const DISPLAY_STEPS = [
  { key: "parse_resume", label: "Parsing" },
  { key: "analyze_jd", label: "Analyzing" },
  { key: "match_candidates", label: "Matching" },
  { key: "generate_questions", label: "Generating Qs" },
  { key: "report", label: "Report" },
] as const

function nextNodeAfter(step: string, matchScore: number): string | null {
  switch (step) {
    case "parse_resume":
      return "analyze_jd"
    case "analyze_jd":
      return "match_candidates"
    case "match_candidates":
      return matchScore > 0.7 ? "generate_questions" : "create_rejection_report"
    case "generate_questions":
      return "create_report"
    default:
      return null
  }
}

function StepIcon({ status }: { status: StepStatus }) {
  if (status === "done") return <CheckCircle2 className="h-5 w-5 text-emerald-500" />
  if (status === "error") return <XCircle className="h-5 w-5 text-red-500" />
  if (status === "running") return <Loader2 className="h-5 w-5 animate-spin text-primary" />
  return <Circle className="h-5 w-5 text-muted-foreground" />
}

interface PipelineProgressProps {
  candidateId: string
  jobId: string
}

export default function PipelineProgress({ candidateId, jobId }: PipelineProgressProps) {
  const [statuses, setStatuses] = useState<Record<string, StepStatus>>({})
  const [isRunning, setIsRunning] = useState(false)
  const [finalState, setFinalState] = useState<HiringState | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleEvent = (step: string, state: HiringState) => {
    if (step === "__end__") {
      setFinalState(state)
      setIsRunning(false)
      return
    }
    if (step === "error_handler") {
      return
    }

    const hasError = state.errors.length > 0
    setStatuses((prev) => {
      const next: Record<string, StepStatus> = { ...prev, [step]: hasError ? "error" : "done" }
      if (!hasError) {
        const upcoming = nextNodeAfter(step, state.match_score)
        if (upcoming) next[upcoming] = "running"
      }
      return next
    })
  }

  const runPipeline = async () => {
    setIsRunning(true)
    setStatuses({ parse_resume: "running" })
    setFinalState(null)
    setError(null)

    try {
      const response = await fetch(`${API_BASE_URL}/pipeline/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ candidate_id: candidateId, job_id: jobId }),
      })
      if (!response.ok || !response.body) {
        throw new Error(`Pipeline request failed (${response.status})`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const chunks = buffer.split("\n\n")
        buffer = chunks.pop() ?? ""
        for (const chunk of chunks) {
          const line = chunk.trim()
          if (!line.startsWith("data:")) continue
          const jsonStr = line.slice(5).trim()
          if (!jsonStr) continue
          const event: PipelineEvent = JSON.parse(jsonStr)
          handleEvent(event.step, event.state)
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pipeline failed")
      setIsRunning(false)
    }
  }

  const reportStatus: StepStatus =
    statuses["create_report"] ?? statuses["create_rejection_report"] ?? statuses["report"] ?? "pending"

  return (
    <Card className="w-full max-w-lg">
      <CardHeader>
        <CardTitle>Hiring Pipeline</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <ol className="flex flex-col gap-3">
          {DISPLAY_STEPS.map((step) => {
            const status = step.key === "report" ? reportStatus : (statuses[step.key] ?? "pending")
            return (
              <li key={step.key} className="flex items-center gap-3">
                <StepIcon status={status} />
                <span className={status === "pending" ? "text-muted-foreground" : ""}>{step.label}</span>
              </li>
            )
          })}
        </ol>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <Button onClick={runPipeline} disabled={isRunning}>
          {isRunning ? "Running..." : "Run Pipeline"}
        </Button>

        {finalState && (
          <div className="flex flex-col gap-2 border-t pt-4 text-sm">
            <p>
              Match score: <span className="font-semibold">{(finalState.match_score * 100).toFixed(1)}%</span>
            </p>
            {finalState.interview_questions.length > 0 && (
              <p>{finalState.interview_questions.length} interview questions generated</p>
            )}
            {finalState.report.recommendation && (
              <p>
                Recommendation: <span className="font-semibold">{finalState.report.recommendation}</span>
              </p>
            )}
            {finalState.errors.length > 0 && (
              <p className="text-destructive">{finalState.errors.join("; ")}</p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
