"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Check, Copy } from "lucide-react"

import DashboardShell from "@/components/layout/DashboardShell"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { api } from "@/lib/api"
import { extractErrorMessage } from "@/lib/errors"
import type { InterviewStartResponse } from "@/types/interview"

interface StartedInterview {
  sessionId: string
  accessUrl: string
}

export default function InterviewStartPage() {
  const router = useRouter()
  const [candidateId, setCandidateId] = useState("")
  const [jobId, setJobId] = useState("")
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [started, setStarted] = useState<StartedInterview | null>(null)
  const [copied, setCopied] = useState(false)

  const startInterview = async () => {
    setStarting(true)
    setError(null)
    try {
      const { data } = await api.post<InterviewStartResponse>("/interview/start", {
        candidate_id: candidateId,
        job_id: jobId,
      })
      // The interview room page loads its state from GET /transcript, which
      // has no audio field — hand off the first question's already-synthesized
      // audio via sessionStorage so it still gets played once there, instead
      // of silently dropping it on this navigation.
      if (data.audio_url) {
        sessionStorage.setItem(`interview-first-audio:${data.session_id}`, data.audio_url)
      }
      setStarted({ sessionId: data.session_id, accessUrl: data.access_url })
    } catch (err) {
      setError(extractErrorMessage(err, "Failed to start the interview."))
    } finally {
      setStarting(false)
    }
  }

  const copyLink = async () => {
    if (!started) return
    await navigator.clipboard.writeText(started.accessUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (started) {
    return (
      <DashboardShell>
        <main className="mx-auto flex max-w-lg flex-col gap-6">
          <h1 className="text-2xl font-bold">Interview Created</h1>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Share this link with the candidate</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <p className="text-sm text-muted-foreground">
                This link lets the candidate take the interview themselves — no recruiter account
                needed. It expires in a few hours.
              </p>
              <div className="flex gap-2">
                <Input readOnly value={started.accessUrl} className="font-mono text-xs" />
                <Button variant="outline" onClick={copyLink} className="shrink-0 gap-1.5">
                  {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
                  {copied ? "Copied" : "Copy"}
                </Button>
              </div>
              <Button onClick={() => router.push(`/interview/${started.sessionId}`)} className="self-start">
                Continue to Interview Room →
              </Button>
            </CardContent>
          </Card>
        </main>
      </DashboardShell>
    )
  }

  return (
    <DashboardShell>
    <main className="mx-auto flex max-w-lg flex-col gap-6">
      <h1 className="text-2xl font-bold">Start AI Interview</h1>

      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="candidate-id">Candidate ID</Label>
          <Input
            id="candidate-id"
            value={candidateId}
            onChange={(e) => setCandidateId(e.target.value)}
            placeholder="uuid of a candidate with a parsed resume"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="job-id">Job ID</Label>
          <Input
            id="job-id"
            value={jobId}
            onChange={(e) => setJobId(e.target.value)}
            placeholder="uuid of a job"
          />
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button
          onClick={startInterview}
          disabled={!candidateId || !jobId || starting}
          className="mt-1 self-start"
        >
          {starting ? "Starting…" : "Start Interview"}
        </Button>
      </div>
    </main>
    </DashboardShell>
  )
}
