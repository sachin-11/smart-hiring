"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { signIn } from "next-auth/react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { api } from "@/lib/api"
import { extractErrorMessage } from "@/lib/errors"

export default function LoginPage() {
  const router = useRouter()
  const [mode, setMode] = useState<"login" | "register">("login")

  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [fullName, setFullName] = useState("")

  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    setSubmitting(true)
    setError(null)
    try {
      if (mode === "register") {
        await api.post("/auth/register", { email, password, full_name: fullName || undefined })
      }

      const result = await signIn("credentials", { email, password, redirect: false })
      if (result?.error) {
        setError(mode === "register" ? "Account created, but sign-in failed — try logging in." : "Incorrect email or password.")
        setSubmitting(false)
        return
      }
      router.push("/dashboard")
    } catch (err) {
      setError(extractErrorMessage(err, "Something went wrong. Please try again."))
      setSubmitting(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>{mode === "login" ? "Recruiter Login" : "Create Recruiter Account"}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {mode === "register" && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="full-name">Full name</Label>
              <Input id="full-name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
            </div>
          )}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
            {mode === "register" && <p className="text-xs text-muted-foreground">At least 8 characters.</p>}
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <Button onClick={submit} disabled={!email || !password || submitting}>
            {submitting ? "Please wait…" : mode === "login" ? "Log In" : "Create Account"}
          </Button>

          <button
            type="button"
            onClick={() => {
              setMode((m) => (m === "login" ? "register" : "login"))
              setError(null)
            }}
            className="text-sm text-muted-foreground underline-offset-4 hover:underline"
          >
            {mode === "login" ? "Don't have an account? Register" : "Already have an account? Log in"}
          </button>
        </CardContent>
      </Card>
    </main>
  )
}
