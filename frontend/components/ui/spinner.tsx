import { Loader2 } from "lucide-react"

import { cn } from "@/lib/utils"

const SIZES = {
  sm: "size-4",
  default: "size-6",
  lg: "size-8",
} as const

function Spinner({ size = "default", className }: { size?: keyof typeof SIZES; className?: string }) {
  return <Loader2 className={cn(SIZES[size], "animate-spin text-primary", className)} />
}

function LoadingState({ label, className }: { label?: string; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-3 py-12", className)}>
      <Spinner size="lg" />
      {label && <p className="text-sm text-muted-foreground">{label}</p>}
    </div>
  )
}

export { Spinner, LoadingState }
