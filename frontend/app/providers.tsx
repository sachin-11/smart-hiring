"use client"

import { useEffect, useState } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { SessionProvider, useSession } from "next-auth/react"

import { useAuthStore } from "@/lib/store/auth"

function AuthSync() {
  const { data: session, status } = useSession()
  const setAuth = useAuthStore((s) => s.setAuth)

  useEffect(() => {
    // On a hard reload, useSession() starts in "loading" (re-fetching
    // /api/auth/session) with session still undefined — don't clobber the
    // token that lib/store/auth.ts already persisted from before the reload
    // with a premature null. Only write once NextAuth has a definitive answer.
    if (status === "loading") return
    setAuth(session?.accessToken ?? null, session?.user?.email ?? null)
  }, [session, status, setAuth])

  return null
}

export default function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient({ defaultOptions: { queries: { staleTime: 30_000 } } }))

  return (
    <SessionProvider>
      <QueryClientProvider client={queryClient}>
        <AuthSync />
        {children}
      </QueryClientProvider>
    </SessionProvider>
  )
}
