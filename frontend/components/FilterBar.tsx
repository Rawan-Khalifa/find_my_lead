"use client"

import { Search, X } from "lucide-react"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Button } from "@/components/ui/button"
import { Slider } from "@/components/ui/slider"
import { Badge } from "@/components/ui/badge"
import type { LeadFilters, GafTier, PipelineStage } from "@/lib/types"

interface FilterBarProps {
  filters: LeadFilters
  onFiltersChange: (filters: LeadFilters) => void
}

const tiers: Array<{ value: GafTier | "all"; label: string }> = [
  { value: "all", label: "All Tiers" },
  { value: "Master Elite", label: "Master Elite" },
  { value: "Certified Plus", label: "Certified Plus" },
  { value: "Certified", label: "Certified" },
  { value: "Registered", label: "Registered" },
]

const stages: Array<{ value: PipelineStage | "all"; label: string }> = [
  { value: "all", label: "All Stages" },
  { value: "new", label: "New" },
  { value: "contacted", label: "Contacted" },
  { value: "qualified", label: "Qualified" },
  { value: "customer", label: "Customer" },
  { value: "disqualified", label: "Disqualified" },
]

function countActiveFilters(filters: LeadFilters): number {
  let count = 0
  if (filters.search) count++
  if (filters.tier !== "all") count++
  if (filters.stage !== "all") count++
  if (filters.minScore > 0) count++
  if (filters.city) count++
  return count
}

export function FilterBar({ filters, onFiltersChange }: FilterBarProps) {
  const activeCount = countActiveFilters(filters)

  const updateFilter = <K extends keyof LeadFilters>(
    key: K,
    value: LeadFilters[K]
  ) => {
    onFiltersChange({ ...filters, [key]: value })
  }

  const clearFilters = () => {
    onFiltersChange({
      search: "",
      tier: "all",
      stage: "all",
      minScore: 0,
      city: "",
    })
  }

  return (
    <div className="border-b border-border bg-surface/50 py-4">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex flex-wrap items-center gap-3">
          {/* Search */}
          <div className="relative flex-1 min-w-[200px] max-w-xs">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search contractors..."
              value={filters.search}
              onChange={(e) => updateFilter("search", e.target.value)}
              className="pl-9 bg-background border-border"
            />
          </div>

          {/* Tier Dropdown */}
          <Select
            value={filters.tier}
            onValueChange={(value) => updateFilter("tier", value as GafTier | "all")}
          >
            <SelectTrigger className="w-[160px] bg-background border-border">
              <SelectValue placeholder="All Tiers" />
            </SelectTrigger>
            <SelectContent className="bg-card border-border">
              {tiers.map((tier) => (
                <SelectItem key={tier.value} value={tier.value}>
                  {tier.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Stage Dropdown */}
          <Select
            value={filters.stage}
            onValueChange={(value) =>
              updateFilter("stage", value as PipelineStage | "all")
            }
          >
            <SelectTrigger className="w-[150px] bg-background border-border">
              <SelectValue placeholder="All Stages" />
            </SelectTrigger>
            <SelectContent className="bg-card border-border">
              {stages.map((stage) => (
                <SelectItem key={stage.value} value={stage.value}>
                  {stage.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Min Score Slider */}
          <div className="flex items-center gap-3 rounded-md border border-border bg-background px-3 py-2">
            <span className="text-xs text-muted-foreground whitespace-nowrap">
              Min Score
            </span>
            <Slider
              value={[filters.minScore]}
              onValueChange={([value]) => updateFilter("minScore", value)}
              max={100}
              step={5}
              className="w-24"
            />
            <span className="text-sm font-medium w-8 text-right text-foreground">
              {filters.minScore}
            </span>
          </div>

          {/* City Input */}
          <Input
            placeholder="City..."
            value={filters.city}
            onChange={(e) => updateFilter("city", e.target.value)}
            className="w-[120px] bg-background border-border"
          />

          {/* Active Filters Count & Clear */}
          <div className="flex items-center gap-2 ml-auto">
            {activeCount > 0 && (
              <>
                <Badge
                  variant="secondary"
                  className="bg-amber/20 text-amber border-none"
                >
                  {activeCount} filter{activeCount !== 1 && "s"} active
                </Badge>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={clearFilters}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <X className="h-4 w-4 mr-1" />
                  Clear all
                </Button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
