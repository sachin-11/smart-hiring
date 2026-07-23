import type { NextAuthOptions } from "next-auth"
import CredentialsProvider from "next-auth/providers/credentials"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1"

interface BackendTokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  recruiter: { id: string; email: string; full_name: string | null }
}

// Matches backend JWT_ACCESS_TOKEN_TTL_MINUTES (app/core/config.py) — used to decide
// when the JWT callback below should proactively refresh, without needing to decode
// the token's own `exp` claim on every request.
const ACCESS_TOKEN_TTL_MS = 30 * 60 * 1000

async function refreshAccessToken(refreshToken: string) {
  const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
  if (!response.ok) throw new Error("Refresh request failed")
  return (await response.json()) as BackendTokenResponse
}

export const authOptions: NextAuthOptions = {
  session: { strategy: "jwt" },
  secret: process.env.NEXTAUTH_SECRET,
  pages: { signIn: "/login" },
  providers: [
    CredentialsProvider({
      name: "Credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) return null

        const response = await fetch(`${API_BASE_URL}/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: credentials.email, password: credentials.password }),
        })
        if (!response.ok) return null

        const data = (await response.json()) as BackendTokenResponse
        return {
          id: data.recruiter.id,
          email: data.recruiter.email,
          name: data.recruiter.full_name,
          accessToken: data.access_token,
          refreshToken: data.refresh_token,
          accessTokenExpires: Date.now() + ACCESS_TOKEN_TTL_MS,
        }
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user }) {
      // Initial sign-in: `user` is what `authorize()` returned above.
      if (user) {
        return {
          ...token,
          accessToken: user.accessToken,
          refreshToken: user.refreshToken,
          accessTokenExpires: user.accessTokenExpires,
        }
      }

      if (Date.now() < (token.accessTokenExpires as number)) {
        return token
      }

      // Access token expired — rotate it via the backend's single-use refresh
      // token flow (see routes/auth.py). If this fails, mark the session so the
      // client can force a sign-out rather than silently keep a dead session.
      try {
        const refreshed = await refreshAccessToken(token.refreshToken as string)
        return {
          ...token,
          accessToken: refreshed.access_token,
          refreshToken: refreshed.refresh_token,
          accessTokenExpires: Date.now() + ACCESS_TOKEN_TTL_MS,
        }
      } catch {
        return { ...token, error: "RefreshAccessTokenError" as const }
      }
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken as string
      session.error = token.error as string | undefined
      if (session.user) {
        session.user.id = token.sub as string
      }
      return session
    },
  },
}
