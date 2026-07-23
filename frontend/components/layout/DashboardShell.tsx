"use client"

import { useRouter } from "next/navigation"
import { useSession } from "next-auth/react"

import Breadcrumbs from "@/components/layout/Breadcrumbs"
import Header from "@/components/layout/Header"
import Sidebar from "@/components/layout/Sidebar"

export default function DashboardShell({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const { status } = useSession({
    required: true,
    onUnauthenticated: () => router.push("/login"),
  })

  if (status !== "authenticated") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">Loading…</p>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex flex-1 flex-col">
        <Header />
        <Breadcrumbs />
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  )
}
