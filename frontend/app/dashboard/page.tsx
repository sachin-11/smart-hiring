"use client"

import Link from "next/link"
import { useQuery } from "@tanstack/react-query"
import { Briefcase, FileText, TrendingUp, Upload, Users } from "lucide-react"

import DashboardShell from "@/components/layout/DashboardShell"
import { buttonVariants } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { api } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { ActivityItem, DashboardActivityResponse, DashboardStats } from "@/types/dashboard"

function StatCard({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-4">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Icon className="size-5" />
        </div>
        <div>
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="text-xl font-bold">{value}</p>
        </div>
      </CardContent>
    </Card>
  )
}

function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diffMs / 60000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

function ActivityRow({ item }: { item: ActivityItem }) {
  return (
    <li className="flex items-center justify-between gap-4 py-2 text-sm">
      <span>{item.description}</span>
      <span className="whitespace-nowrap text-xs text-muted-foreground">{timeAgo(item.timestamp)}</span>
    </li>
  )
}

export default function DashboardPage() {
  const statsQuery = useQuery({
    queryKey: ["dashboard", "stats"],
    queryFn: async () => (await api.get<DashboardStats>("/dashboard/stats")).data,
  })
  const activityQuery = useQuery({
    queryKey: ["dashboard", "activity"],
    queryFn: async () => (await api.get<DashboardActivityResponse>("/dashboard/activity")).data,
  })

  const stats = statsQuery.data

  return (
    <DashboardShell>
      <div className="flex flex-col gap-6">
        <h1 className="text-2xl font-bold">Dashboard</h1>

        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard icon={Users} label="Total Candidates" value={stats ? String(stats.total_candidates) : "—"} />
          <StatCard icon={Briefcase} label="Active JDs" value={stats ? String(stats.active_jds) : "—"} />
          <StatCard
            icon={TrendingUp}
            label="Avg Match Score"
            value={stats?.avg_match_score != null ? `${stats.avg_match_score.toFixed(1)}%` : "—"}
          />
          <StatCard
            icon={FileText}
            label="Interviews Scheduled"
            value={stats ? String(stats.interviews_scheduled) : "—"}
          />
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>Recent Pipeline Activity</CardTitle>
            </CardHeader>
            <CardContent>
              {activityQuery.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
              {activityQuery.data?.items.length === 0 && (
                <p className="text-sm text-muted-foreground">No activity yet.</p>
              )}
              <ul className="divide-y">
                {activityQuery.data?.items.map((item) => (
                  <ActivityRow key={item.id} item={item} />
                ))}
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Quick Actions</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              <Link href="/upload" className={cn(buttonVariants({ variant: "outline" }), "justify-start gap-2")}>
                <Upload className="size-4" /> Upload Resume
              </Link>
              <Link href="/jobs/new" className={cn(buttonVariants({ variant: "outline" }), "justify-start gap-2")}>
                <Briefcase className="size-4" /> Create JD
              </Link>
              <Link href="/jobs" className={cn(buttonVariants({ variant: "outline" }), "justify-start gap-2")}>
                <FileText className="size-4" /> View Reports
              </Link>
            </CardContent>
          </Card>
        </div>
      </div>
    </DashboardShell>
  )
}
