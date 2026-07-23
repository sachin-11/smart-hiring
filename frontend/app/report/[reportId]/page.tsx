"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import { AlertTriangle, ChevronDown, ChevronUp, Download, Mail } from "lucide-react"
import { Cell, Pie, PieChart, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer } from "recharts"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { api } from "@/lib/api"
import { extractErrorMessage } from "@/lib/errors"
import type {
  ProficiencyLevel,
  Recommendation,
  ReportDetailResponse,
  ReportPdfResponse,
  ReportShareResponse,
} from "@/types/report"

const RECOMMENDATION_STYLES: Record<Recommendation, string> = {
  "Strongly Hire": "bg-emerald-600 text-white",
  Hire: "bg-lime-600 text-white",
  Hold: "bg-amber-500 text-white",
  Reject: "bg-red-600 text-white",
}

const PROFICIENCY_SCORE: Record<ProficiencyLevel, number> = {
  Beginner: 1,
  Intermediate: 2,
  Advanced: 3,
  Expert: 4,
}

function scoreColor(score: number): string {
  if (score >= 8) return "#059669"
  if (score >= 6) return "#65a30d"
  if (score >= 4) return "#d97706"
  return "#dc2626"
}

function ExpandableSection({ title, score, defaultOpen = false, children }: { title: string; score: number; defaultOpen?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <Card className="print:break-inside-avoid">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between p-4 text-left"
      >
        <span className="font-semibold">
          {title} <span className="text-muted-foreground font-normal">— {score.toFixed(1)}/10</span>
        </span>
        <span className="print:hidden">{open ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}</span>
      </button>
      <CardContent className={`pt-0 ${open ? "block" : "hidden"} print:!block`}>{children}</CardContent>
    </Card>
  )
}

export default function ReportPage() {
  const params = useParams<{ reportId: string }>()
  const reportId = params.reportId

  const [data, setData] = useState<ReportDetailResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [pdfUrl, setPdfUrl] = useState<string | null>(null)
  const [downloadError, setDownloadError] = useState<string | null>(null)

  const [showShareForm, setShowShareForm] = useState(false)
  const [shareEmail, setShareEmail] = useState("")
  const [shareMessage, setShareMessage] = useState("")
  const [sharing, setSharing] = useState(false)
  const [shareResult, setShareResult] = useState<{ ok: boolean; text: string } | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .get<ReportDetailResponse>(`/report/${reportId}`)
      .then(({ data }) => {
        if (!cancelled) setData(data)
      })
      .catch((err) => {
        if (cancelled) return
        setError(extractErrorMessage(err, "Failed to load report."))
      })

    // Pre-fetch the presigned PDF URL so the Download button can call window.open()
    // synchronously inside the click's user-gesture context — fetching it only on
    // click would open the tab after an await, which real browsers popup-block.
    api
      .get<ReportPdfResponse>(`/report/${reportId}/pdf`)
      .then(({ data }) => {
        if (!cancelled) setPdfUrl(data.pdf_url)
      })
      .catch((err) => {
        if (cancelled) return
        setDownloadError(extractErrorMessage(err, "PDF is not available."))
      })

    return () => {
      cancelled = true
    }
  }, [reportId])

  const downloadPdf = () => {
    if (pdfUrl) window.open(pdfUrl, "_blank")
  }

  const sendShare = async () => {
    if (!shareEmail.trim()) return
    setSharing(true)
    setShareResult(null)
    try {
      const { data } = await api.post<ReportShareResponse>(`/report/${reportId}/share`, {
        to_email: shareEmail.trim(),
        message: shareMessage.trim() || undefined,
      })
      setShareResult({ ok: true, text: data.detail })
    } catch (err) {
      setShareResult({ ok: false, text: extractErrorMessage(err, "Failed to send email.") })
    } finally {
      setSharing(false)
    }
  }

  if (error) {
    return (
      <main className="mx-auto flex min-h-screen max-w-4xl items-center justify-center p-8">
        <p className="text-destructive">{error}</p>
      </main>
    )
  }

  if (!data) {
    return (
      <main className="mx-auto flex min-h-screen max-w-4xl items-center justify-center p-8">
        <p className="text-muted-foreground">Loading report…</p>
      </main>
    )
  }

  const { report } = data
  const donutColor = scoreColor(report.overall_score)
  const donutData = [
    { value: report.overall_score },
    { value: Math.max(0, 10 - report.overall_score) },
  ]
  const radarData = report.skill_breakdown.map((s) => ({
    skill: s.skill,
    value: PROFICIENCY_SCORE[s.proficiency_level],
  }))

  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col gap-6 p-8 print:p-0">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">{data.candidate_name ?? "Candidate"} — Scorecard</h1>
          <p className="text-sm text-muted-foreground">{data.job_title ?? "Role"}</p>
        </div>
        <div className="flex gap-2 print:hidden">
          <Button variant="outline" onClick={() => setShowShareForm((s) => !s)} className="gap-1.5">
            <Mail className="size-4" /> Share via Email
          </Button>
          <Button onClick={downloadPdf} disabled={!pdfUrl} className="gap-1.5">
            <Download className="size-4" /> {pdfUrl ? "Download PDF" : "Preparing…"}
          </Button>
        </div>
      </div>
      {downloadError && <p className="text-sm text-destructive print:hidden">{downloadError}</p>}

      {showShareForm && (
        <Card className="print:hidden">
          <CardContent className="flex flex-col gap-3 pt-6">
            <Input
              type="email"
              placeholder="candidate@company.com"
              value={shareEmail}
              onChange={(e) => setShareEmail(e.target.value)}
            />
            <Textarea
              placeholder="Optional note…"
              rows={2}
              value={shareMessage}
              onChange={(e) => setShareMessage(e.target.value)}
            />
            <Button onClick={sendShare} disabled={!shareEmail.trim() || sharing} className="self-start">
              {sharing ? "Sending…" : "Send"}
            </Button>
            {shareResult && (
              <p className={`text-sm ${shareResult.ok ? "text-emerald-600" : "text-destructive"}`}>{shareResult.text}</p>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="flex flex-col items-center gap-4 pt-6 sm:flex-row sm:justify-between">
          <div className="relative h-40 w-40 shrink-0">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={donutData} dataKey="value" innerRadius={55} outerRadius={75} startAngle={90} endAngle={-270} stroke="none">
                  <Cell fill={donutColor} />
                  <Cell fill="#e5e7eb" />
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-3xl font-bold">{report.overall_score.toFixed(1)}</span>
              <span className="text-xs text-muted-foreground">/ 10</span>
            </div>
          </div>

          <div className="flex flex-1 flex-col items-center gap-2 sm:items-end">
            <Badge className={`${RECOMMENDATION_STYLES[report.recommendation]} px-4 py-1.5 text-base`}>
              {report.recommendation}
            </Badge>
            {report.red_flags.length > 0 && (
              <div className="flex flex-col gap-1 text-right">
                {report.red_flags.map((flag, i) => (
                  <span key={i} className="flex items-center gap-1.5 text-sm text-red-600">
                    <AlertTriangle className="size-3.5 shrink-0" /> {flag}
                  </span>
                ))}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {radarData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Skill Breakdown</CardTitle>
          </CardHeader>
          <CardContent className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radarData}>
                <PolarGrid />
                <PolarAngleAxis dataKey="skill" tick={{ fontSize: 12 }} />
                <PolarRadiusAxis domain={[0, 4]} tick={false} axisLine={false} />
                <Radar dataKey="value" stroke="#4f46e5" fill="#4f46e5" fillOpacity={0.4} />
              </RadarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      <div className="flex flex-col gap-4">
        <ExpandableSection title="Technical Assessment" score={report.technical_assessment.score} defaultOpen>
          <p className="text-sm text-muted-foreground">{report.technical_assessment.comments}</p>
          {report.technical_assessment.strengths.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {report.technical_assessment.strengths.map((s, i) => (
                <Badge key={i} variant="secondary">{s}</Badge>
              ))}
            </div>
          )}
          {report.technical_assessment.gaps.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {report.technical_assessment.gaps.map((g, i) => (
                <Badge key={i} variant="outline" className="text-muted-foreground">gap: {g}</Badge>
              ))}
            </div>
          )}
        </ExpandableSection>

        <ExpandableSection title="Communication Assessment" score={report.communication_assessment.score}>
          <p className="text-sm"><span className="font-medium">Clarity: </span><span className="text-muted-foreground">{report.communication_assessment.clarity}</span></p>
          <p className="mt-1 text-sm"><span className="font-medium">Articulation: </span><span className="text-muted-foreground">{report.communication_assessment.articulation}</span></p>
        </ExpandableSection>

        <ExpandableSection title="Culture Fit" score={report.culture_fit.score}>
          <p className="text-sm text-muted-foreground">{report.culture_fit.comments}</p>
        </ExpandableSection>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Interview Highlights</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          <p><span className="font-medium text-emerald-600">Best moment: </span>{report.interview_highlights.best_answer}</p>
          <p><span className="font-medium text-amber-600">Concern: </span>{report.interview_highlights.concern_answer}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Suggested Next Steps</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">{report.suggested_next_steps}</p>
        </CardContent>
      </Card>
    </main>
  )
}
