"use client"

import { LogOut, Menu } from "lucide-react"
import { signOut, useSession } from "next-auth/react"

import { Button } from "@/components/ui/button"
import { useUiStore } from "@/lib/store/ui"

export default function Header() {
  const { data: session } = useSession()
  const toggleSidebar = useUiStore((s) => s.toggleSidebar)

  const initial = (session?.user?.name || session?.user?.email || "?").charAt(0).toUpperCase()

  return (
    <header className="flex h-14 items-center border-b bg-background px-6 print:hidden">
      <Button variant="ghost" size="icon" onClick={toggleSidebar} aria-label="Toggle menu" className="lg:hidden">
        <Menu className="size-5" />
      </Button>
      <div className="ml-auto flex items-center gap-3">
        {session?.user?.email && (
          <div className="flex items-center gap-2">
            <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-semibold text-accent-foreground">
              {initial}
            </span>
            <span className="text-sm text-muted-foreground">{session.user.name || session.user.email}</span>
          </div>
        )}
        <Button variant="ghost" size="icon" onClick={() => signOut({ callbackUrl: "/login" })} aria-label="Sign out">
          <LogOut className="size-4" />
        </Button>
      </div>
    </header>
  )
}
