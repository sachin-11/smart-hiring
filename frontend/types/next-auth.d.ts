import type { DefaultSession, DefaultUser } from "next-auth"
import type { DefaultJWT } from "next-auth/jwt"

declare module "next-auth" {
  interface User extends DefaultUser {
    accessToken: string
    refreshToken: string
    accessTokenExpires: number
  }

  interface Session extends DefaultSession {
    accessToken?: string
    error?: string
    user?: DefaultSession["user"] & { id: string }
  }
}

declare module "next-auth/jwt" {
  interface JWT extends DefaultJWT {
    accessToken?: string
    refreshToken?: string
    accessTokenExpires?: number
    error?: string
  }
}
