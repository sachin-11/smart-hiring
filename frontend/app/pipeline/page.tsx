"use client"

import { useState } from "react"

import DashboardShell from "@/components/layout/DashboardShell"
import PipelineProgress from "@/components/PipelineProgress"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export default function PipelinePage() {
  const [candidateId, setCandidateId] = useState("")
  const [jobId, setJobId] = useState("")
  const [activeIds, setActiveIds] = useState<{ candidateId: string; jobId: string } | null>(null)

  return (
    <DashboardShell>
    <main className="mx-auto flex max-w-lg flex-col gap-6">
      <h1 className="text-2xl font-bold">Run Hiring Pipeline</h1>

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
        <button
          type="button"
          onClick={() => setActiveIds({ candidateId, jobId })}
          disabled={!candidateId || !jobId}
          className="mt-1 self-start rounded-md border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
        >
          Load
        </button>
      </div>

      {activeIds && <PipelineProgress candidateId={activeIds.candidateId} jobId={activeIds.jobId} />}
    </main>
    </DashboardShell>
  )
}
