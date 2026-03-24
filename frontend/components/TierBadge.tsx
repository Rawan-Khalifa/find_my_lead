"use client"

import { cn } from "@/lib/utils"
import type { GafTier } from "@/lib/types"

interface TierBadgeProps {
  tier: GafTier
  className?: string
}

function getTierStyles(tier: GafTier): string {
  switch (tier) {
    case "Master Elite":
      return "bg-amber text-amber-950 font-semibold"
    case "Certified Plus":
      return "bg-blue text-white"
    case "Certified":
      return "bg-green text-white"
    case "Registered":
      return "bg-slate text-white"
    default:
      return "bg-gray text-white"
  }
}

function getTierPrefix(tier: GafTier): string {
  return tier === "Master Elite" ? "⭐ " : ""
}

export function TierBadge({ tier, className }: TierBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        getTierStyles(tier),
        className
      )}
    >
      {getTierPrefix(tier)}
      {tier}
    </span>
  )
}
