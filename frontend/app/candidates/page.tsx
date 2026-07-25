"use client"

import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Mail, Star, Trash2 } from "lucide-react"

import DashboardShell from "@/components/layout/DashboardShell"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { api } from "@/lib/api"
import { extractErrorMessage } from "@/lib/errors"
import { useJobStore } from "@/lib/store/job"
import type { CandidateDeleteResponse, CandidateListResponse, CandidateStatus } from "@/types/candidate"

const STATUS_OPTIONS: CandidateStatus[] = ["new", "screening", "interviewing", "offered", "hired", "rejected"]

function scoreColor(score: number | null): string {
  if (score === null) return "text-muted-foreground"
  if (score >= 80) return "text-emerald-600 dark:text-emerald-400"
  if (score >= 60) return "text-amber-600 dark:text-amber-400"
  return "text-red-600 dark:text-red-400"
}

export default function CandidatesPage() {
  const queryClient = useQueryClient()
  const currentJobId = useJobStore((s) => s.currentJobId)

  const [status, setStatus] = useState<CandidateStatus | "">("")
  const [skill, setSkill] = useState("")
  const [minScore, setMinScore] = useState("")
  const [maxScore, setMaxScore] = useState("")
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [actionMessage, setActionMessage] = useState<string | null>(null)

  const filters = { status: status || undefined, skill: skill || undefined, min_score: minScore ? Number(minScore) : undefined, max_score: maxScore ? Number(maxScore) : undefined }

  const { data, isLoading } = useQuery({
    queryKey: ["candidates", filters],
    queryFn: async () => (await api.get<CandidateListResponse>("/candidates", { params: filters })).data,
  })

  const shortlistMutation = useMutation({
    mutationFn: async (candidateIds: string[]) =>
      (await api.post("/candidates/bulk-shortlist", { candidate_ids: candidateIds })).data as { affected: number },
    onSuccess: (result) => {
      setActionMessage(`Shortlisted ${result.affected} candidate(s).`)
      setSelected(new Set())
      queryClient.invalidateQueries({ queryKey: ["candidates"] })
    },
    onError: () => setActionMessage("Failed to shortlist — are you logged in?"),
  })

  const emailMutation = useMutation({
    mutationFn: async (candidateIds: string[]) => {
      if (!currentJobId) throw new Error("Pick a job on the Jobs page first (used to compose the email).")
      return (await api.post("/candidates/bulk-email", { candidate_ids: candidateIds, job_id: currentJobId })).data as {
        affected: number
      }
    },
    onSuccess: (result) => {
      setActionMessage(`Queued emails for ${result.affected} candidate(s).`)
      setSelected(new Set())
    },
    onError: (err) => setActionMessage(err instanceof Error ? err.message : "Failed to send emails."),
  })

  const [deleteTarget, setDeleteTarget] = useState<string[] | null>(null)

  const deleteMutation = useMutation({
    mutationFn: async (candidateIds: string[]) => {
      const results = await Promise.all(
        candidateIds.map((id) => api.delete<CandidateDeleteResponse>(`/candidates/${id}`))
      )
      return results.length
    },
    onSuccess: (count) => {
      setActionMessage(`Deleted ${count} candidate(s).`)
      setSelected(new Set())
      setDeleteTarget(null)
      queryClient.invalidateQueries({ queryKey: ["candidates"] })
    },
    onError: (err) => {
      setActionMessage(extractErrorMessage(err, "Failed to delete candidate(s)."))
      setDeleteTarget(null)
    },
  })

  const handleDelete = (candidateIds: string[]) => {
    setActionMessage(null)
    setDeleteTarget(candidateIds)
  }

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const candidates = data?.candidates ?? []

  return (
    <DashboardShell>
      <div className="flex flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Candidates</h1>
          {selected.size > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">{selected.size} selected</span>
              <Button size="sm" variant="outline" className="gap-1.5" onClick={() => shortlistMutation.mutate(Array.from(selected))}>
                <Star className="size-4" /> Shortlist
              </Button>
              <Button size="sm" variant="outline" className="gap-1.5" onClick={() => emailMutation.mutate(Array.from(selected))}>
                <Mail className="size-4" /> Send Email
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5 text-destructive hover:bg-destructive/10 hover:text-destructive"
                onClick={() => handleDelete(Array.from(selected))}
              >
                <Trash2 className="size-4" /> Delete
              </Button>
            </div>
          )}
        </div>
        {actionMessage && <p className="text-sm text-muted-foreground">{actionMessage}</p>}

        <Card>
          <CardContent className="flex flex-wrap items-end gap-3 p-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="filter-status">Status</Label>
              <select
                id="filter-status"
                value={status}
                onChange={(e) => setStatus(e.target.value as CandidateStatus | "")}
                className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
              >
                <option value="">Any</option>
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="filter-skill">Skill</Label>
              <Input id="filter-skill" value={skill} onChange={(e) => setSkill(e.target.value)} placeholder="e.g. Python" className="w-40" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="filter-min">Min score</Label>
              <Input id="filter-min" type="number" min={0} max={100} value={minScore} onChange={(e) => setMinScore(e.target.value)} className="w-24" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="filter-max">Max score</Label>
              <Input id="filter-max" type="number" min={0} max={100} value={maxScore} onChange={(e) => setMaxScore(e.target.value)} className="w-24" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="flex flex-col gap-4 p-4">
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} className="flex items-center gap-4">
                    <Skeleton className="size-4 shrink-0" />
                    <div className="flex flex-1 flex-col gap-1.5">
                      <Skeleton className="h-4 w-40" />
                      <Skeleton className="h-3 w-56" />
                    </div>
                    <Skeleton className="h-4 w-24" />
                    <Skeleton className="h-4 w-16" />
                    <Skeleton className="h-5 w-20 rounded-full" />
                  </div>
                ))}
              </div>
            ) : candidates.length === 0 ? (
              <p className="p-6 text-sm text-muted-foreground">No candidates match these filters.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="w-10 p-3"></th>
                    <th className="p-3 font-medium">Name</th>
                    <th className="p-3 font-medium">Applied JD</th>
                    <th className="p-3 font-medium">Match Score</th>
                    <th className="p-3 font-medium">Status</th>
                    <th className="w-10 p-3"></th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.map((c) => (
                    <tr key={c.id} className="border-b last:border-0">
                      <td className="p-3">
                        <input type="checkbox" checked={selected.has(c.id)} onChange={() => toggle(c.id)} />
                      </td>
                      <td className="p-3">
                        <p className="font-medium">{c.full_name ?? "Unknown"}</p>
                        <p className="text-xs text-muted-foreground">{c.email ?? "no email on file"}</p>
                      </td>
                      <td className="p-3">{c.applied_job_title ?? "—"}</td>
                      <td className={`p-3 font-semibold ${scoreColor(c.match_score)}`}>
                        {c.match_score != null ? `${c.match_score.toFixed(1)}%` : "—"}
                      </td>
                      <td className="p-3">
                        <Badge variant="secondary">{c.status}</Badge>
                      </td>
                      <td className="p-3">
                        <button
                          type="button"
                          aria-label={`Delete ${c.full_name ?? "candidate"}`}
                          onClick={() => handleDelete([c.id])}
                          className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                        >
                          <Trash2 className="size-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title={deleteTarget && deleteTarget.length === 1 ? "Delete this candidate?" : `Delete ${deleteTarget?.length ?? 0} candidates?`}
        description="This also removes their interviews and reports. This cannot be undone."
        loading={deleteMutation.isPending}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget)}
      />
    </DashboardShell>
  )
}
