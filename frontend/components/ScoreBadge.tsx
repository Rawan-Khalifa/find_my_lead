"use client"

import { cn } from "@/lib/utils"

interface ScoreBadgeProps {
  score: number | null
  size?: "sm" | "md" | "lg"
  className?: string
}

function getScoreColor(score: number): string {
  if (score >= 80) return "bg-amber text-amber-950"
  if (score >= 60) return "bg-blue text-white"
  if (score >= 40) return "bg-slate text-white"
  return "bg-gray text-white"
}

function getScoreRingColor(score: number): string {
  if (score >= 80) return "ring-amber/30"
  if (score >= 60) return "ring-blue/30"
  if (score >= 40) return "ring-slate/30"
  return "ring-gray/30"
}

export function ScoreBadge({ score, size = "md", className }: ScoreBadgeProps) {
  const safeScore = score ?? 0
  const isHot = safeScore >= 85
  const isHighScore = safeScore >= 80

  const sizeClasses = {
    sm: "h-8 w-8 text-xs",
    md: "h-11 w-11 text-sm",
    lg: "h-14 w-14 text-base",
  }

  return (
    <div className={cn("flex items-center gap-1.5", className)}>
      <div
        className={cn(
          "flex items-center justify-center rounded-full font-bold ring-2",
          sizeClasses[size],
          getScoreColor(safeScore),
          getScoreRingColor(safeScore),
          isHighScore && "animate-pulse-ring"
        )}
      >
        {score != null ? score : "—"}
      </div>
      {isHot && <span className="text-lg">🔥</span>}
    </div>
  )
}
