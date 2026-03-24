"use client"

import { cn } from "@/lib/utils"
interface OutreachBadgeProps {
  angle: string | null
  className?: string
}

function getOutreachStyles(angle: string | null): { bg: string; emoji: string; label: string } {
  switch (angle) {
    case "new_relationship":
      return { bg: "bg-blue/20 text-blue border border-blue/30", emoji: "🤝", label: "New Relationship" }
    case "upsell":
      return { bg: "bg-amber/20 text-amber border border-amber/30", emoji: "📈", label: "Upsell Opportunity" }
    case "reactivation":
      return { bg: "bg-purple/20 text-purple border border-purple/30", emoji: "🔄", label: "Reactivation" }
    default:
      return { bg: "bg-gray/20 text-muted-foreground", emoji: "", label: "Unknown" }
  }
}

export function OutreachBadge({ angle, className }: OutreachBadgeProps) {
  const styles = getOutreachStyles(angle)

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium",
        styles.bg,
        className
      )}
    >
      <span>{styles.emoji}</span>
      <span>{styles.label}</span>
    </span>
  )
}
