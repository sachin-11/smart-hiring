"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"

import DashboardShell from "@/components/layout/DashboardShell"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { api } from "@/lib/api"
import { extractErrorMessage } from "@/lib/errors"
import type { ReportDetailResponse } from "@/types/report"

export default function ReportGeneratePage() {
  const router = useRouter()
  const [sessionId, setSessionId] = useState("")
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const generateReport = async () => {
    setGenerating(true)
    setError(null)
    try {
      const { data } = await api.post<ReportDetailResponse>("/report/generate", {
        session_id: sessionId,
      })
      router.push(`/report/${data.report_id}`)
    } catch (err) {
      setError(extractErrorMessage(err, "Failed to generate the report."))
      setGenerating(false)
    }
  }

  return (
    <DashboardShell>
    <main className="mx-auto flex max-w-lg flex-col gap-6">
      <h1 className="text-2xl font-bold">Generate Feedback Report</h1>

      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="session-id">Interview Session ID</Label>
          <Input
            id="session-id"
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value)}
            placeholder="uuid of a completed interview session"
          />
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button
          onClick={generateReport}
          disabled={!sessionId || generating}
          className="mt-1 self-start"
        >
          {generating ? "Generating…" : "Generate Report"}
        </Button>
      </div>
    </main>
    </DashboardShell>
  )
}
