"use client"

import { cn } from "@/lib/utils"

interface RoofIconProps {
  className?: string
  animated?: boolean
}

export function RoofIcon({ className, animated = true }: RoofIconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn(
        "h-6 w-6",
        animated && "animate-roof",
        className
      )}
    >
      {/* Roof */}
      <path
        d="M3 12L12 4L21 12"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="text-amber"
      />
      {/* Chimney */}
      <rect
        x="16"
        y="6"
        width="3"
        height="4"
        fill="currentColor"
        className="text-amber/60"
      />
      {/* House body */}
      <path
        d="M5 12V20H19V12"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="text-muted-foreground"
      />
      {/* Door */}
      <rect
        x="10"
        y="14"
        width="4"
        height="6"
        fill="currentColor"
        className="text-amber/40"
      />
    </svg>
  )
}
