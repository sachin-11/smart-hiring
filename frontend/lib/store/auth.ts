import { create } from "zustand"
import { createJSONStorage, persist } from "zustand/middleware"

interface AuthState {
  accessToken: string | null
  recruiterEmail: string | null
  setAuth: (accessToken: string | null, recruiterEmail: string | null) => void
}

/**
 * A synchronous mirror of the NextAuth session's access token. NextAuth's
 * `useSession()` is React-only (a hook) and resolves asynchronously (it re-fetches
 * `/api/auth/session` on every full page load), but the axios interceptor in
 * lib/api.ts runs outside the component tree and needs imperative access — this
 * store is kept in sync by <AuthSync> (see app/providers.tsx), which is mounted
 * once at the root.
 *
 * Persisted to sessionStorage so a hard reload doesn't leave a window where pages
 * that fetch data immediately on mount (most of them — the useQuery call typically
 * sits above <DashboardShell> in the component, not gated by its auth check) fire
 * their first request with no token and get a 401 before AuthSync's effect has
 * re-synced it from the freshly-refetched session. This doesn't change what's
 * exposed to client JS — the token is already readable via useSession() either way.
 */
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      recruiterEmail: null,
      setAuth: (accessToken, recruiterEmail) => set({ accessToken, recruiterEmail }),
    }),
    {
      name: "auth-token-mirror",
      storage: createJSONStorage(() => sessionStorage),
    }
  )
)
