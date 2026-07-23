"use client"

import Link from "next/link"
import { useQuery } from "@tanstack/react-query"
import { Plus, Users } from "lucide-react"

import DashboardShell from "@/components/layout/DashboardShell"
import { Badge } from "@/components/ui/badge"
import { buttonVariants } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { api } from "@/lib/api"
import { useJobStore } from "@/lib/store/job"
import { cn } from "@/lib/utils"
import type { JobListResponse, JobStatus } from "@/types/job"

const STATUS_STYLES: Record<JobStatus, string> = {
  draft: "bg-muted text-muted-foreground",
  open: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  paused: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  closed: "bg-muted text-muted-foreground",
}

export default function JobsPage() {
  const setCurrentJob = useJobStore((s) => s.setCurrentJob)

  const { data, isLoading } = useQuery({
    queryKey: ["jobs"],
    queryFn: async () => (await api.get<JobListResponse>("/jobs")).data,
  })

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

        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
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
                <Card className="h-full transition-colors hover:border-primary">
                  <CardHeader>
                    <div className="flex items-start justify-between gap-2">
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
    </DashboardShell>
  )
}
