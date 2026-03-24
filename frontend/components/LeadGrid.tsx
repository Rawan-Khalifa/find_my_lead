"use client"

import { Inbox } from "lucide-react"
import { Button } from "@/components/ui/button"
import { LeadCard } from "./LeadCard"
import type { ContractorListItem, PipelineStage } from "@/lib/types"

interface LeadGridProps {
  leads: ContractorListItem[]
  isLoading: boolean
  error: string | null
  onStageChange: (id: string, stage: PipelineStage) => void
  onViewDetail: (id: string) => void
  onClearFilters: () => void
}

function SkeletonCard() {
  return (
    <div className="rounded-lg border border-border bg-card p-5 animate-pulse">
      <div className="flex items-start justify-between mb-4">
        <div className="h-11 w-11 rounded-full bg-muted" />
        <div className="h-6 w-24 rounded-full bg-muted" />
      </div>
      <div className="h-5 w-3/4 rounded bg-muted mb-2" />
      <div className="h-4 w-1/2 rounded bg-muted mb-3" />
      <div className="h-4 w-1/3 rounded bg-muted mb-3" />
      <div className="h-6 w-32 rounded-full bg-muted mb-4" />
      <div className="h-4 w-1/3 rounded bg-muted mb-4" />
      <div className="pt-3 border-t border-border flex items-center gap-3">
        <div className="h-8 flex-1 rounded bg-muted" />
        <div className="h-8 w-24 rounded bg-muted" />
      </div>
    </div>
  )
}

export function LeadGrid({
  leads,
  isLoading,
  error,
  onStageChange,
  onViewDetail,
  onClearFilters,
}: LeadGridProps) {
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <div className="rounded-full bg-destructive/10 p-4 mb-4">
          <svg
            className="h-8 w-8 text-destructive"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
        </div>
        <h3 className="text-lg font-semibold text-foreground mb-2">
          Could not connect to API at localhost:8000
        </h3>
        <p className="text-sm text-muted-foreground max-w-md">
          Make sure the backend is running:{" "}
          <code className="bg-muted px-2 py-0.5 rounded text-amber font-mono text-xs">
            uvicorn api.main:app --reload
          </code>
        </p>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    )
  }

  if (leads.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <div className="rounded-full bg-muted p-4 mb-4">
          <Inbox className="h-8 w-8 text-muted-foreground" />
        </div>
        <h3 className="text-lg font-semibold text-foreground mb-2">
          No leads match your filters
        </h3>
        <p className="text-sm text-muted-foreground mb-4">
          Try adjusting your search criteria or clear all filters.
        </p>
        <Button
          variant="outline"
          onClick={onClearFilters}
          className="border-border text-foreground hover:bg-amber/10 hover:text-amber hover:border-amber"
        >
          Clear filters
        </Button>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {leads.map((lead, index) => (
        <LeadCard
          key={lead.id}
          lead={lead}
          onStageChange={onStageChange}
          onViewDetail={onViewDetail}
          animationDelay={index * 50}
        />
      ))}
    </div>
  )
}
