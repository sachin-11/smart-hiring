import { create } from "zustand"

interface AuthState {
  accessToken: string | null
  recruiterEmail: string | null
  setAuth: (accessToken: string | null, recruiterEmail: string | null) => void
}

/**
 * A synchronous mirror of the NextAuth session's access token. NextAuth's
 * `useSession()` is React-only (a hook), but the axios interceptor in lib/api.ts
 * runs outside the component tree and needs imperative access — this store is kept
 * in sync by <AuthSync> (see app/providers.tsx), which is mounted once at the root.
 */
export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  recruiterEmail: null,
  setAuth: (accessToken, recruiterEmail) => set({ accessToken, recruiterEmail }),
}))
