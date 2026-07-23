"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { api } from "@/lib/api"
import { extractErrorMessage } from "@/lib/errors"
import type { JobDetailResponse } from "@/types/job"
import type { MatchResponse, MatchResult } from "@/types/matching"

function scoreColor(score: number): string {
  if (score > 80) return "bg-emerald-500"
  if (score >= 60) return "bg-amber-500"
  return "bg-red-500"
}

function scoreTextColor(score: number): string {
  if (score > 80) return "text-emerald-600 dark:text-emerald-400"
  if (score >= 60) return "text-amber-600 dark:text-amber-400"
  return "text-red-600 dark:text-red-400"
}

export default function JobMatchesPage() {
  const params = useParams<{ id: string }>()
  const jobId = params.id

  const [job, setJob] = useState<JobDetailResponse | null>(null)
  const [results, setResults] = useState<MatchResult[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [threshold, setThreshold] = useState(0)

  useEffect(() => {
    let cancelled = false

    async function run() {
      try {
        // The first match request on a cold backend loads the cross-encoder
        // model (one-time cost), which can take significantly longer than
        // the client's default timeout.
        const [{ data: jobData }, { data: matchData }] = await Promise.all([
          api.get<JobDetailResponse>(`/jobs/${jobId}`),
          api.post<MatchResponse>(
            "/match",
            { jd_id: jobId, top_k: 10 },
            { timeout: 120_000 }
          ),
        ])
        if (cancelled) return
        setJob(jobData)
        setResults(matchData.results)
      } catch (err) {
        if (cancelled) return
        setError(extractErrorMessage(err, "Failed to compute matches."))
      }
    }

    run()
    return () => {
      cancelled = true
    }
  }, [jobId])

  const filteredResults = (results ?? []).filter((r) => r.match_score >= threshold)

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 p-8">
      <div>
        <h1 className="text-2xl font-bold">{job?.title ?? "Job Matches"}</h1>
        {job && (
          <p className="text-sm text-muted-foreground">
            {job.required_skills?.join(", ") || "No required skills listed"}
          </p>
        )}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {!error && results === null && (
        <div className="flex flex-col items-center gap-2 rounded-xl border p-12 text-center">
          <p className="font-medium">Computing matches…</p>
          <p className="text-sm text-muted-foreground">
            Running hybrid search and cross-encoder reranking — this can take up to a minute the
            first time.
          </p>
        </div>
      )}

      {results !== null && results.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No candidates with parsed resumes are available to match against yet.
        </p>
      )}

      {results !== null && results.length > 0 && (
        <>
          <div className="flex items-center gap-3">
            <label htmlFor="threshold" className="text-sm text-muted-foreground whitespace-nowrap">
              Min score: {threshold}%
            </label>
            <input
              id="threshold"
              type="range"
              min={0}
              max={100}
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
              className="w-full"
            />
          </div>

          <div className="flex flex-col gap-4">
            {filteredResults.map((r) => (
              <Card key={r.candidate_id}>
                <CardHeader>
                  <div className="flex items-center justify-between gap-4">
                    <CardTitle>{r.name ?? "Unknown candidate"}</CardTitle>
                    <span className={`text-lg font-bold ${scoreTextColor(r.match_score)}`}>
                      {r.match_score}%
                    </span>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className={`h-full ${scoreColor(r.match_score)}`}
                      style={{ width: `${Math.min(100, Math.max(0, r.match_score))}%` }}
                    />
                  </div>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  {r.skill_overlap.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {r.skill_overlap.map((skill) => (
                        <Badge key={skill} variant="secondary">
                          {skill}
                        </Badge>
                      ))}
                    </div>
                  )}
                  {r.missing_skills.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {r.missing_skills.map((skill) => (
                        <Badge key={skill} variant="outline" className="text-muted-foreground">
                          missing: {skill}
                        </Badge>
                      ))}
                    </div>
                  )}
                  <p className="text-sm text-muted-foreground">{r.explanation}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}
    </main>
  )
}
