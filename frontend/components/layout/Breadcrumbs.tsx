"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { ChevronRight } from "lucide-react"

function toTitle(segment: string): string {
  const decoded = decodeURIComponent(segment)
  // Route params (UUIDs) aren't human-readable — show a short, honest placeholder.
  if (/^[0-9a-f-]{20,}$/i.test(decoded)) return "Detail"
  return decoded.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
}

export default function Breadcrumbs() {
  const pathname = usePathname() ?? "/"
  const segments = pathname.split("/").filter(Boolean)

  return (
    <nav className="flex items-center gap-1.5 px-6 pt-4 text-sm text-muted-foreground print:hidden">
      <Link href="/dashboard" className="hover:text-foreground">
        Home
      </Link>
      {segments.map((segment, i) => {
        const href = "/" + segments.slice(0, i + 1).join("/")
        const isLast = i === segments.length - 1
        return (
          <span key={href} className="flex items-center gap-1.5">
            <ChevronRight className="size-3.5" />
            {isLast ? (
              <span className="text-foreground">{toTitle(segment)}</span>
            ) : (
              <Link href={href} className="hover:text-foreground">
                {toTitle(segment)}
              </Link>
            )}
          </span>
        )
      })}
    </nav>
  )
}
