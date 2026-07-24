"use client"

import { useState } from "react"
import Link from "next/link"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { api } from "@/lib/api"
import { extractErrorMessage } from "@/lib/errors"

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)

  const submit = async () => {
    setSubmitting(true)
    setError(null)
    try {
      await api.post("/auth/forgot-password", { email })
      setSent(true)
    } catch (err) {
      setError(extractErrorMessage(err, "Something went wrong. Please try again."))
    } finally {
      setSubmitting(false)
    }
  }

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
            <CardTitle>Reset your password</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {sent ? (
              <p className="text-sm text-muted-foreground">
                If an account exists for <span className="font-medium text-foreground">{email}</span>, we&apos;ve
                sent a password reset link to it. The link expires in 1 hour.
              </p>
            ) : (
              <>
                <p className="text-sm text-muted-foreground">
                  Enter your account email and we&apos;ll send you a link to reset your password.
                </p>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="email">Email</Label>
                  <Input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && email && !submitting && submit()}
                  />
                </div>

                {error && <p className="text-sm text-destructive">{error}</p>}

                <Button onClick={submit} disabled={!email || submitting}>
                  {submitting ? "Sending…" : "Send reset link"}
                </Button>
              </>
            )}

            <Link href="/login" className="text-sm text-muted-foreground underline-offset-4 hover:underline">
              Back to log in
            </Link>
          </CardContent>
        </Card>
      </div>
    </main>
  )
}
