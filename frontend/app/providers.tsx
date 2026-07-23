"use client"

import { useEffect, useState } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { SessionProvider, useSession } from "next-auth/react"

import { useAuthStore } from "@/lib/store/auth"

function AuthSync() {
  const { data: session } = useSession()
  const setAuth = useAuthStore((s) => s.setAuth)

  useEffect(() => {
    setAuth(session?.accessToken ?? null, session?.user?.email ?? null)
  }, [session, setAuth])

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
