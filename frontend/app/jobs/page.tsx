"use client"

import Link from "next/link"
import { useState, type MouseEvent } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus, Trash2, Users } from "lucide-react"

import DashboardShell from "@/components/layout/DashboardShell"
import { Badge } from "@/components/ui/badge"
import { buttonVariants } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { api } from "@/lib/api"
import { extractErrorMessage } from "@/lib/errors"
import { useJobStore } from "@/lib/store/job"
import { cn } from "@/lib/utils"
import type { JobDeleteResponse, JobListResponse, JobStatus } from "@/types/job"

const STATUS_STYLES: Record<JobStatus, string> = {
  draft: "bg-muted text-muted-foreground",
  open: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  paused: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  closed: "bg-muted text-muted-foreground",
}

export default function JobsPage() {
  const setCurrentJob = useJobStore((s) => s.setCurrentJob)
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ["jobs"],
    queryFn: async () => (await api.get<JobListResponse>("/jobs")).data,
  })

  const [deleteTarget, setDeleteTarget] = useState<{ id: string; title: string } | null>(null)
  const [message, setMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null)

  const deleteMutation = useMutation({
    mutationFn: async (jobId: string) => (await api.delete<JobDeleteResponse>(`/jobs/${jobId}`)).data,
    onSuccess: () => {
      setMessage({ kind: "success", text: `Deleted "${deleteTarget?.title}".` })
      setDeleteTarget(null)
      queryClient.invalidateQueries({ queryKey: ["jobs"] })
    },
    onError: (err) => {
      setMessage({ kind: "error", text: extractErrorMessage(err, "Failed to delete job.") })
      setDeleteTarget(null)
    },
  })

  const handleDelete = (e: MouseEvent, jobId: string, title: string) => {
    e.preventDefault()
    e.stopPropagation()
    setMessage(null)
    setDeleteTarget({ id: jobId, title })
  }

  const jobs = data?.jobs ?? []

  return (
    <DashboardShell>
      <div className="flex flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Jobs</h1>
          <Link href="/jobs/new" className={cn(buttonVariants(), "gap-1.5")}>
            <Plus className="size-4" /> Create JD
          </Link>
        </div>
        {message && (
          <p className={`text-sm ${message.kind === "error" ? "text-destructive" : "text-muted-foreground"}`}>
            {message.text}
          </p>
        )}

        {isLoading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Card key={i}>
                <CardHeader>
                  <div className="flex items-start justify-between gap-2">
                    <Skeleton className="h-5 w-32" />
                    <Skeleton className="h-5 w-14 rounded-full" />
                  </div>
                </CardHeader>
                <CardContent className="flex flex-col gap-2">
                  <Skeleton className="h-4 w-24" />
                  <div className="flex items-center justify-between">
                    <Skeleton className="h-4 w-20" />
                    <Skeleton className="h-4 w-16" />
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : jobs.length === 0 ? (
          <p className="text-sm text-muted-foreground">No jobs posted yet.</p>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {jobs.map((job) => (
              <Link
                key={job.id}
                href={`/jobs/${job.id}/matches`}
                onClick={() => setCurrentJob(job.id, job.title)}
              >
                <Card className="group relative h-full transition-colors hover:border-primary">
                  <button
                    type="button"
                    aria-label={`Delete ${job.title}`}
                    onClick={(e) => handleDelete(e, job.id, job.title)}
                    className="absolute right-2 top-2 z-10 rounded-md p-1.5 text-muted-foreground opacity-0 transition-opacity hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
                  >
                    <Trash2 className="size-4" />
                  </button>
                  <CardHeader>
                    <div className="flex items-start justify-between gap-2 pr-7">
                      <CardTitle className="text-base">{job.title}</CardTitle>
                      <Badge className={STATUS_STYLES[job.status]} variant="outline">
                        {job.status}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-2 text-sm">
                    {job.department && <p className="text-muted-foreground">{job.department}</p>}
                    <div className="flex items-center justify-between">
                      <span className="flex items-center gap-1.5 text-muted-foreground">
                        <Users className="size-4" /> {job.applicant_count} applicant{job.applicant_count === 1 ? "" : "s"}
                      </span>
                      {job.top_match_score != null && (
                        <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                          {job.top_match_score.toFixed(1)}% top match
                        </span>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title={`Delete "${deleteTarget?.title ?? ""}"?`}
        description="This also removes its applications, interviews, and reports. This cannot be undone."
        loading={deleteMutation.isPending}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
      />
    </DashboardShell>
  )
}
