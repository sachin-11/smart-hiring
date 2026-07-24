"use client"

import { Suspense, useState } from "react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { api } from "@/lib/api"
import { extractErrorMessage } from "@/lib/errors"

function ResetPasswordForm() {
  const router = useRouter()
  const token = useSearchParams().get("token")

  const [newPassword, setNewPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const submit = async () => {
    if (newPassword !== confirmPassword) {
      setError("Passwords don't match.")
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await api.post("/auth/reset-password", { token, new_password: newPassword })
      setDone(true)
      setTimeout(() => router.push("/login"), 2000)
    } catch (err) {
      setError(extractErrorMessage(err, "Failed to reset password. The link may have expired."))
    } finally {
      setSubmitting(false)
    }
  }

  if (!token) {
    return (
      <p className="text-sm text-destructive">
        This reset link is missing its token.{" "}
        <Link href="/forgot-password" className="underline underline-offset-4">
          Request a new one
        </Link>
        .
      </p>
    )
  }

  if (done) {
    return <p className="text-sm text-muted-foreground">Password updated — redirecting you to log in…</p>
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="new-password">New password</Label>
        <Input id="new-password" type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
        <p className="text-xs text-muted-foreground">At least 8 characters.</p>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="confirm-password">Confirm new password</Label>
        <Input
          id="confirm-password"
          type="password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && newPassword && confirmPassword && !submitting && submit()}
        />
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Button onClick={submit} disabled={!newPassword || !confirmPassword || submitting}>
        {submitting ? "Updating…" : "Update password"}
      </Button>
    </div>
  )
}

export default function ResetPasswordPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_top,_var(--tw-gradient-stops))] from-accent/60 via-background to-background p-8">
      <div className="flex w-full max-w-sm flex-col items-center gap-6">
        <div className="flex items-center gap-2">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary text-sm font-bold text-primary-foreground">
            S
          </span>
          <span className="text-lg font-semibold tracking-tight">Smart Hiring</span>
        </div>
        <Card className="w-full shadow-lg">
          <CardHeader>
            <CardTitle>Choose a new password</CardTitle>
          </CardHeader>
          <CardContent>
            <Suspense fallback={<p className="text-sm text-muted-foreground">Loading…</p>}>
              <ResetPasswordForm />
            </Suspense>
          </CardContent>
        </Card>
      </div>
    </main>
  )
}
