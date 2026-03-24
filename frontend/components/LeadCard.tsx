"use client"

import { useState } from "react"
import { Phone, Star, ArrowRight } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { ScoreBadge } from "./ScoreBadge"
import { TierBadge } from "./TierBadge"
import { StagePicker } from "./StagePicker"
import { OutreachBadge } from "./OutreachBadge"
import { formatPhone, formatDistance } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { ContractorListItem, PipelineStage } from "@/lib/types"

interface LeadCardProps {
  lead: ContractorListItem
  onStageChange: (id: string, stage: PipelineStage) => void
  onViewDetail: (id: string) => void
  animationDelay?: number
}

export function LeadCard({
  lead,
  onStageChange,
  onViewDetail,
  animationDelay = 0,
}: LeadCardProps) {
  const [isUpdating, setIsUpdating] = useState(false)

  const handleStageChange = async (stage: PipelineStage) => {
    setIsUpdating(true)
    try {
      await onStageChange(lead.id, stage)
    } finally {
      setIsUpdating(false)
    }
  }

  return (
    <Card
      className={cn(
        "group relative overflow-hidden border-border bg-card p-5 transition-all duration-200",
        "hover:border-amber/50 hover:shadow-lg hover:shadow-amber/5 hover:-translate-y-0.5",
        "animate-fade-up"
      )}
      style={{ animationDelay: `${animationDelay}ms` }}
    >
      {/* Header: Score & Tier */}
      <div className="flex items-start justify-between mb-4">
        <ScoreBadge score={lead.opportunity_score} />
        <TierBadge tier={lead.gaf_tier} />
      </div>

      {/* Name & Location */}
      <h3 className="text-lg font-semibold text-foreground mb-1 text-balance">
        {lead.name}
      </h3>
      <p className="text-sm text-muted-foreground mb-3">
        {[lead.city, lead.state].filter(Boolean).join(", ")}
        {lead.distance_miles != null && ` · ${formatDistance(lead.distance_miles)} away`}
      </p>

      {/* Rating */}
      {lead.rating != null && (
        <div className="flex items-center gap-1 text-sm mb-3">
          <Star className="h-4 w-4 fill-amber text-amber" />
          <span className="font-medium text-foreground">{lead.rating.toFixed(1)}</span>
          <span className="text-muted-foreground">
            ({lead.reviews_count ?? 0} review{lead.reviews_count !== 1 && "s"})
          </span>
        </div>
      )}

      {/* Outreach Angle */}
      <div className="mb-4">
        {lead.has_enrichment ? (
          <OutreachBadge angle={lead.outreach_angle} />
        ) : (
          <span className="text-xs text-muted-foreground italic">
            Enrichment pending...
          </span>
        )}
      </div>

      {/* Phone */}
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <a
              href={lead.phone ? `tel:${lead.phone}` : undefined}
              className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-amber transition-colors mb-4"
            >
              <Phone className="h-3.5 w-3.5" />
              {lead.phone ? formatPhone(lead.phone) : "No phone"}
            </a>
          </TooltipTrigger>
          <TooltipContent
            side="top"
            className="bg-card border-border text-foreground"
          >
            <p>Ready to call?</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      {/* Footer: Stage & View Button */}
      <div className="flex items-center gap-3 pt-3 border-t border-border">
        <StagePicker
          currentStage={lead.pipeline_stage}
          onStageChange={handleStageChange}
          disabled={isUpdating}
          size="sm"
          className="flex-1"
        />
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onViewDetail(lead.id)}
          className="text-muted-foreground hover:text-amber hover:bg-amber/10"
        >
          View Brief
          <ArrowRight className="h-4 w-4 ml-1" />
        </Button>
      </div>
    </Card>
  )
}
