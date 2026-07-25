"use client"

import { useCallback, useEffect, useState } from "react"
import { AlertTriangle, Play, RefreshCw } from "lucide-react"
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"

import DashboardShell from "@/components/layout/DashboardShell"
import { Badge } from "@/components/ui/badge"
import { LoadingState } from "@/components/ui/spinner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { api } from "@/lib/api"
import { extractErrorMessage } from "@/lib/errors"
import type { AnalyticsDashboardResponse, DriftRunResponse, JudgeRunResponse, RagasRunResponse } from "@/types/analytics"

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
}

function StatCard({ label, value, sub, danger }: { label: string; value: string; sub?: string; danger?: boolean }) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-1 p-4">
        <span className="text-sm text-muted-foreground">{label}</span>
        <span className={`text-2xl font-bold ${danger ? "text-destructive" : ""}`}>{value}</span>
        {sub && <span className="text-xs text-muted-foreground">{sub}</span>}
      </CardContent>
    </Card>
  )
}

export default function AnalyticsPage() {
  const [data, setData] = useState<AnalyticsDashboardResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [runningRagas, setRunningRagas] = useState(false)
  const [runningDrift, setRunningDrift] = useState(false)
  const [runningJudge, setRunningJudge] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [lastAction, setLastAction] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const { data } = await api.get<AnalyticsDashboardResponse>("/analytics/dashboard")
      setData(data)
      setError(null)
    } catch (err) {
      setError(extractErrorMessage(err, "Failed to load analytics."))
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const runRagas = async () => {
    setRunningRagas(true)
    setActionError(null)
    setLastAction(null)
    try {
      const { data } = await api.post<RagasRunResponse>("/mlops/ragas/run", null, {
        params: { sample_size: 5 },
        timeout: 300_000,
      })
      setLastAction(
        `RAGAS run complete: faithfulness=${data.avg_faithfulness.toFixed(2)}, ${data.sample_size} samples${data.alert_triggered ? " — ALERT" : ""}`
      )
      await load()
    } catch (err) {
      setActionError(extractErrorMessage(err, "RAGAS run failed."))
    } finally {
      setRunningRagas(false)
    }
  }

  const runDrift = async () => {
    setRunningDrift(true)
    setActionError(null)
    setLastAction(null)
    try {
      const { data } = await api.post<DriftRunResponse>("/mlops/drift/run", null, { timeout: 120_000 })
      setLastAction(
        `Drift check complete: PSI=${data.psi_score.toFixed(3)} (threshold ${data.psi_threshold})${data.alert_triggered ? " — ALERT" : ""}`
      )
      await load()
    } catch (err) {
      setActionError(extractErrorMessage(err, "Drift check failed."))
    } finally {
      setRunningDrift(false)
    }
  }

  const runJudge = async () => {
    setRunningJudge(true)
    setActionError(null)
    setLastAction(null)
    try {
      const { data } = await api.post<JudgeRunResponse>("/mlops/judge/run", null, {
        params: { sample_size: 5 },
        timeout: 300_000,
      })
      setLastAction(
        `LLM-judge run complete: ${(data.agreement_rate * 100).toFixed(0)}% agreement with the live scorer, ${data.sample_size} samples${data.alert_triggered ? " — ALERT" : ""}`
      )
    } catch (err) {
      setActionError(extractErrorMessage(err, "LLM-judge run failed."))
    } finally {
      setRunningJudge(false)
    }
  }

  if (error) {
    return (
      <DashboardShell>
        <main className="mx-auto flex max-w-5xl items-center justify-center">
          <p className="text-destructive">{error}</p>
        </main>
      </DashboardShell>
    )
  }

  if (!data) {
    return (
      <DashboardShell>
        <main className="mx-auto flex max-w-5xl items-center justify-center">
          <LoadingState label="Loading analytics…" />
        </main>
      </DashboardShell>
    )
  }

  const alerts = [
    ...data.recent_drift_reports
      .filter((d) => d.alert_triggered)
      .map((d) => ({
        key: `drift-${d.id}`,
        created_at: d.created_at,
        label: "Embedding drift",
        detail: `PSI=${d.psi_score.toFixed(3)} (baseline=${d.baseline_size}, current=${d.current_size})`,
      })),
    ...data.recent_ragas_alerts.map((r) => ({
      key: `ragas-${r.run_id}`,
      created_at: r.created_at,
      label: "RAGAS faithfulness",
      detail: `avg faithfulness=${r.avg_faithfulness.toFixed(2)} (below 0.75 threshold)`,
    })),
  ].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())

  return (
    <DashboardShell>
    <main className="mx-auto flex max-w-5xl flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold">MLOps Analytics</h1>
        <div className="flex gap-2">
          <Button variant="outline" onClick={runDrift} disabled={runningDrift} className="gap-1.5">
            <Play className="size-4" /> {runningDrift ? "Running…" : "Run Drift Check"}
          </Button>
          <Button variant="outline" onClick={runRagas} disabled={runningRagas} className="gap-1.5">
            <Play className="size-4" /> {runningRagas ? "Running…" : "Run RAGAS Eval"}
          </Button>
          <Button variant="outline" onClick={runJudge} disabled={runningJudge} className="gap-1.5">
            <Play className="size-4" /> {runningJudge ? "Running…" : "Run LLM Judge"}
          </Button>
          <Button variant="ghost" size="icon" onClick={load} aria-label="Refresh">
            <RefreshCw className="size-4" />
          </Button>
        </div>
      </div>
      {(lastAction || actionError) && (
        <p className={`text-sm ${actionError ? "text-destructive" : "text-muted-foreground"}`}>
          {actionError ?? lastAction}
        </p>
      )}

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard label="Pipeline Runs" value={String(data.total_pipeline_runs)} />
        <StatCard
          label="Avg Match Score"
          value={data.avg_match_score !== null ? `${data.avg_match_score.toFixed(1)}%` : "—"}
        />
        <StatCard label="Total LLM Cost" value={`$${data.total_llm_cost_usd.toFixed(4)}`} />
        <StatCard
          label="Today's LLM Spend"
          value={`$${data.daily_llm_cost_usd.toFixed(4)}`}
          sub={data.daily_llm_budget_usd > 0 ? `of $${data.daily_llm_budget_usd.toFixed(2)} daily cap` : "no daily cap set"}
          danger={data.daily_llm_budget_usd > 0 && data.daily_llm_cost_usd >= data.daily_llm_budget_usd}
        />
        <StatCard
          label="Cost per Hire"
          value={data.cost_per_hire_usd !== null ? `$${data.cost_per_hire_usd.toFixed(2)}` : "—"}
          sub={`${data.hired_count} hired`}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>RAGAS Score Trend</CardTitle>
        </CardHeader>
        <CardContent className="h-72">
          {data.ragas_trend.length === 0 ? (
            <p className="text-sm text-muted-foreground">No RAGAS evaluation runs yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.ragas_trend.map((p) => ({ ...p, time: formatTime(p.created_at) }))}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="time" tick={{ fontSize: 11 }} />
                <YAxis domain={[0, 1]} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="avg_faithfulness" name="Faithfulness" stroke="#059669" strokeWidth={2} />
                <Line type="monotone" dataKey="avg_answer_relevancy" name="Answer Relevancy" stroke="#4f46e5" strokeWidth={2} />
                <Line type="monotone" dataKey="avg_context_precision" name="Context Precision" stroke="#d97706" strokeWidth={2} />
                <Line type="monotone" dataKey="avg_context_recall" name="Context Recall" stroke="#dc2626" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recent Alerts</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {alerts.length === 0 ? (
            <p className="text-sm text-muted-foreground">No alerts — RAGAS faithfulness and embedding drift are within thresholds.</p>
          ) : (
            alerts.map((a) => (
              <div key={a.key} className="flex items-center justify-between gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-3">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="size-4 shrink-0 text-destructive" />
                  <div>
                    <Badge variant="destructive" className="mb-1">{a.label}</Badge>
                    <p className="text-sm">{a.detail}</p>
                  </div>
                </div>
                <span className="whitespace-nowrap text-xs text-muted-foreground">{formatTime(a.created_at)}</span>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </main>
    </DashboardShell>
  )
}
