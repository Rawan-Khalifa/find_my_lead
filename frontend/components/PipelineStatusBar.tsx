"use client"

import { useState } from "react"
import { Play, Loader2, MapPin, Ruler } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { RoofIcon } from "./RoofIcon"
import { timeSince } from "@/lib/api"
import type { PipelineStatus } from "@/lib/types"

interface PipelineStatusBarProps {
  status: PipelineStatus | null
  totalLeads: number
  onRunPipeline: (zipCode: string, distance: number) => Promise<void>
  isRunning: boolean
  runStage: "idle" | "scraping" | "enriching" | "done"
}

export function PipelineStatusBar({
  status,
  totalLeads,
  onRunPipeline,
  isRunning,
  runStage,
}: PipelineStatusBarProps) {
  const [isTriggering, setIsTriggering] = useState(false)
  const [zipCode, setZipCode] = useState(status?.zip_code || "10013")
  const [distance, setDistance] = useState(25)

  const handleRunClick = async () => {
    if (!zipCode.match(/^\d{5}$/)) return
    setIsTriggering(true)
    try {
      await onRunPipeline(zipCode, distance)
    } finally {
      setIsTriggering(false)
    }
  }

  const getButtonContent = () => {
    if (isTriggering || isRunning) {
      switch (runStage) {
        case "scraping":
          return (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>🔄 Scraping GAF...</span>
            </>
          )
        case "enriching":
          return (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>✨ Enriching leads...</span>
            </>
          )
        case "done":
          return (
            <>
              <span>✅ Done</span>
            </>
          )
        default:
          return (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Running...</span>
            </>
          )
      }
    }
    return (
      <>
        <Play className="h-4 w-4" />
        <span>Run Pipeline</span>
      </>
    )
  }

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        {/* Left: Brand */}
        <div className="flex items-center gap-3">
          <RoofIcon className="h-8 w-8" />
          <div>
            <h1 className="text-lg font-bold text-foreground">FindMyLead</h1>
            <p className="text-xs text-muted-foreground">Roofing Sales Intelligence</p>
          </div>
        </div>

        {/* Center: Status */}
        <div className="hidden items-center gap-2 text-sm text-muted-foreground md:flex">
          {isRunning ? (
            <div className="flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-amber" />
              </span>
              <span className="animate-status-pulse">Pipeline running...</span>
            </div>
          ) : (
            <>
              {status?.completed_at && (
                <span>Last refreshed {timeSince(status.completed_at)}</span>
              )}
              <span className="text-border">·</span>
              <span className="font-medium text-foreground">{totalLeads} leads</span>
              <span>in pipeline</span>
            </>
          )}
        </div>

        {/* Right: Target inputs + Run Button */}
        <div className="flex items-center gap-2">
          <div className="hidden items-center gap-1.5 sm:flex">
            <div className="relative">
              <MapPin className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={zipCode}
                onChange={(e) => setZipCode(e.target.value.replace(/\D/g, "").slice(0, 5))}
                placeholder="ZIP"
                disabled={isTriggering || isRunning}
                className="h-9 w-[100px] pl-7 bg-background border-border text-sm font-mono"
              />
            </div>
            <div className="relative">
              <Ruler className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                type="number"
                value={distance}
                onChange={(e) => setDistance(Math.max(1, Math.min(100, Number(e.target.value))))}
                disabled={isTriggering || isRunning}
                className="h-9 w-[80px] pl-7 bg-background border-border text-sm font-mono"
              />
            </div>
            <span className="text-xs text-muted-foreground">mi</span>
          </div>
          <Button
            onClick={handleRunClick}
            disabled={isTriggering || isRunning || !zipCode.match(/^\d{5}$/)}
            className="gap-2 bg-amber text-amber-950 hover:bg-amber/90"
          >
            {getButtonContent()}
          </Button>
        </div>
      </div>
    </header>
  )
}
