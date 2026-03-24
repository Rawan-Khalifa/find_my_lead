"use client"

import { useState } from "react"
import {
  X,
  MapPin,
  Phone,
  Globe,
  Ruler,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  Search,
  Sparkles,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ScoreBadge } from "./ScoreBadge"
import { TierBadge } from "./TierBadge"
import { StagePicker } from "./StagePicker"
import { OutreachBadge } from "./OutreachBadge"
import { formatPhone, formatDistance } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { ContractorDetail, PipelineStage } from "@/lib/types"

interface LeadDetailPanelProps {
  lead: ContractorDetail | null
  isLoading: boolean
  onClose: () => void
  onStageChange: (id: string, stage: PipelineStage) => void
}

function CollapsibleSection({
  title,
  icon,
  children,
  defaultOpen = true,
}: {
  title: string
  icon: React.ReactNode
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen)

  return (
    <div className="border-b border-border pb-4 mb-4 last:border-0 last:pb-0 last:mb-0">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-between w-full text-left group"
      >
        <div className="flex items-center gap-2 text-sm font-medium text-foreground">
          {icon}
          {title}
        </div>
        {isOpen ? (
          <ChevronUp className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        )}
      </button>
      {isOpen && <div className="mt-3">{children}</div>}
    </div>
  )
}

export function LeadDetailPanel({
  lead,
  isLoading,
  onClose,
  onStageChange,
}: LeadDetailPanelProps) {
  const [isUpdating, setIsUpdating] = useState(false)

  const handleStageChange = async (stage: PipelineStage) => {
    if (!lead) return
    setIsUpdating(true)
    try {
      await onStageChange(lead.id, stage)
    } finally {
      setIsUpdating(false)
    }
  }

  if (!lead && !isLoading) return null

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 z-40"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <div className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-md bg-surface border-l-4 border-l-amber overflow-y-auto animate-slide-in-right">
        {isLoading ? (
          <div className="p-6 animate-pulse">
            <div className="h-8 w-3/4 bg-muted rounded mb-4" />
            <div className="flex gap-2 mb-6">
              <div className="h-11 w-11 rounded-full bg-muted" />
              <div className="h-6 w-24 rounded-full bg-muted" />
            </div>
            <div className="space-y-4">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-16 rounded bg-muted" />
              ))}
            </div>
          </div>
        ) : lead ? (
          <div className="flex flex-col h-full">
            {/* Header */}
            <div className="p-6 border-b border-border">
              <div className="flex items-start justify-between mb-4">
                <h2 className="text-xl font-bold text-foreground pr-8 text-balance">
                  {lead.name}
                </h2>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={onClose}
                  className="absolute top-4 right-4 text-muted-foreground hover:text-foreground"
                >
                  <X className="h-5 w-5" />
                </Button>
              </div>
              <div className="flex items-center gap-3">
                <ScoreBadge score={lead.opportunity_score} size="lg" />
                <TierBadge tier={lead.gaf_tier} />
              </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-6">
              {/* Contact Info */}
              <div className="grid grid-cols-2 gap-3 mb-6">
                {lead.address && (
                  <a
                    href={`https://maps.google.com/?q=${encodeURIComponent(lead.address)}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-start gap-2 p-3 rounded-lg bg-muted/50 hover:bg-muted transition-colors"
                  >
                    <MapPin className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
                    <span className="text-sm text-foreground">{lead.address}</span>
                  </a>
                )}
                {lead.phone && (
                  <a
                    href={`tel:${lead.phone}`}
                    className="flex items-center gap-2 p-3 rounded-lg bg-muted/50 hover:bg-muted transition-colors"
                  >
                    <Phone className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm text-foreground">
                      {formatPhone(lead.phone)}
                    </span>
                  </a>
                )}
                {lead.website && (
                  <a
                    href={lead.website}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 p-3 rounded-lg bg-muted/50 hover:bg-muted transition-colors"
                  >
                    <Globe className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm text-foreground truncate">Website</span>
                  </a>
                )}
                {lead.distance_miles != null && (
                  <div className="flex items-center gap-2 p-3 rounded-lg bg-muted/50">
                    <Ruler className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm text-foreground">
                      {formatDistance(lead.distance_miles)}
                    </span>
                  </div>
                )}
              </div>

              {lead.enrichment && (
                <>
                  {/* Score Reasoning */}
                  <CollapsibleSection
                    title="Why this score?"
                    icon={<span>🎯</span>}
                    defaultOpen={false}
                  >
                    <p className="text-sm text-muted-foreground bg-muted/30 p-3 rounded-lg">
                      {lead.enrichment.score_reasoning}
                    </p>
                  </CollapsibleSection>

                  {/* AI Sales Brief */}
                  <div className="mb-6">
                    <div className="flex items-center gap-2 mb-4">
                      <Sparkles className="h-5 w-5 text-amber" />
                      <h3 className="text-base font-semibold text-foreground">
                        AI Sales Brief
                      </h3>
                      <Badge
                        variant="outline"
                        className="text-xs text-muted-foreground border-border"
                      >
                        {lead.enrichment.model_version}
                      </Badge>
                    </div>

                    {/* Talking Points */}
                    <div className="mb-4">
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                        Talking Points
                      </p>
                      <div className="space-y-2">
                        {lead.enrichment.talking_points.map((point, i) => (
                          <div
                            key={i}
                            className="flex items-start gap-3 p-3 bg-muted/30 rounded-lg border-l-2 border-l-amber"
                          >
                            <span className="flex items-center justify-center h-5 w-5 rounded-full bg-amber text-amber-950 text-xs font-bold shrink-0">
                              {i + 1}
                            </span>
                            <p className="text-sm text-foreground">{point}</p>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Product Needs */}
                    <div className="mb-4">
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                        Likely Product Needs
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {lead.enrichment.likely_product_needs.map((product, i) => (
                          <Badge
                            key={i}
                            variant="secondary"
                            className="bg-amber/10 text-amber border border-amber/20"
                          >
                            {product}
                          </Badge>
                        ))}
                      </div>
                    </div>

                    {/* Outreach Angle */}
                    <div>
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                        Outreach Angle
                      </p>
                      <OutreachBadge angle={lead.enrichment.outreach_angle} />
                    </div>
                  </div>

                  {/* Risk Flags */}
                  {(lead.enrichment.risk_flags?.length ?? 0) > 0 && (
                    <div className="mb-6 p-4 rounded-lg bg-red/10 border border-red/20">
                      <div className="flex items-center gap-2 mb-2">
                        <AlertTriangle className="h-4 w-4 text-red" />
                        <span className="text-sm font-medium text-red">
                          Risk Flags
                        </span>
                      </div>
                      <ul className="space-y-1">
                        {lead.enrichment.risk_flags.map((flag, i) => (
                          <li key={i} className="text-sm text-red/80 flex items-start gap-2">
                            <span className="text-red">•</span>
                            {flag}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Web Research */}
                  <CollapsibleSection
                    title="Web Research"
                    icon={<Search className="h-4 w-4" />}
                    defaultOpen={false}
                  >
                    <div className="space-y-2">
                      <p className="text-sm text-muted-foreground">
                        {lead.enrichment.web_research_summary}
                      </p>
                      <Badge
                        variant="outline"
                        className="text-xs text-muted-foreground border-border"
                      >
                        Powered by Perplexity
                      </Badge>
                    </div>
                  </CollapsibleSection>
                </>
              )}

              {!lead.enrichment && (
                <div className="text-center py-8">
                  <p className="text-muted-foreground text-sm">
                    Enrichment data not yet available for this lead.
                  </p>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="p-6 border-t border-border bg-background">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                Update Pipeline Stage
              </p>
              <StagePicker
                currentStage={lead.pipeline_stage}
                onStageChange={handleStageChange}
                disabled={isUpdating}
                className="w-full"
              />
            </div>
          </div>
        ) : null}
      </div>
    </>
  )
}
