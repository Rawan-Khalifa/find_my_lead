"use client"

import { useState, useEffect, useCallback, useMemo } from "react"
import { Toaster, toast } from "sonner"
import { PipelineStatusBar } from "@/components/PipelineStatusBar"
import { FilterBar } from "@/components/FilterBar"
import { LeadGrid } from "@/components/LeadGrid"
import { LeadDetailPanel } from "@/components/LeadDetailPanel"
import { Confetti } from "@/components/Confetti"
import {
  fetchLeads,
  fetchLeadDetail,
  updateLeadStage,
  triggerPipelineRun,
  fetchPipelineStatus,
} from "@/lib/api"
import type {
  ContractorListItem,
  ContractorDetail,
  PipelineStatus,
  LeadFilters,
  PipelineStage,
} from "@/lib/types"

const DEFAULT_FILTERS: LeadFilters = {
  search: "",
  tier: "all",
  stage: "all",
  minScore: 0,
  city: "",
}

export default function Dashboard() {
  // State
  const [leads, setLeads] = useState<ContractorListItem[]>([])
  const [isLoadingLeads, setIsLoadingLeads] = useState(true)
  const [leadsError, setLeadsError] = useState<string | null>(null)
  const [filters, setFilters] = useState<LeadFilters>(DEFAULT_FILTERS)

  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus | null>(null)
  const [isPipelineRunning, setIsPipelineRunning] = useState(false)
  const [runStage, setRunStage] = useState<"idle" | "scraping" | "enriching" | "done">("idle")

  const [selectedLeadId, setSelectedLeadId] = useState<string | null>(null)
  const [selectedLead, setSelectedLead] = useState<ContractorDetail | null>(null)
  const [isLoadingDetail, setIsLoadingDetail] = useState(false)

  const [showConfetti, setShowConfetti] = useState(false)

  // Filter leads client-side for search
  const filteredLeads = useMemo(() => {
    if (!filters.search) return leads
    const searchLower = filters.search.toLowerCase()
    return leads.filter((lead) =>
      lead.name.toLowerCase().includes(searchLower)
    )
  }, [leads, filters.search])

  // Fetch leads
  const loadLeads = useCallback(async () => {
    setIsLoadingLeads(true)
    setLeadsError(null)
    try {
      const response = await fetchLeads(filters)
      setLeads(response.results)
    } catch (error) {
      setLeadsError(error instanceof Error ? error.message : "Failed to fetch leads")
      setLeads([])
    } finally {
      setIsLoadingLeads(false)
    }
  }, [filters])

  // Fetch pipeline status
  const loadPipelineStatus = useCallback(async () => {
    try {
      const status = await fetchPipelineStatus()
      setPipelineStatus(status)
      setIsPipelineRunning(status.status === "running")
    } catch {
      // Silently fail - API might not be running
    }
  }, [])

  // Initial load
  useEffect(() => {
    loadLeads()
    loadPipelineStatus()
  }, [loadLeads, loadPipelineStatus])

  // Poll pipeline status when running
  useEffect(() => {
    if (!isPipelineRunning) return

    const interval = setInterval(async () => {
      try {
        const status = await fetchPipelineStatus()
        setPipelineStatus(status)

        if (status.status === "completed") {
          setIsPipelineRunning(false)
          setRunStage("done")
          toast.success("Pipeline completed! Refreshing leads...")
          loadLeads()
          setTimeout(() => setRunStage("idle"), 2000)
        } else if (status.status === "failed") {
          setIsPipelineRunning(false)
          setRunStage("idle")
          toast.error("Pipeline run failed")
        }
      } catch {
        // Continue polling
      }
    }, 15000)

    return () => clearInterval(interval)
  }, [isPipelineRunning, loadLeads])

  // Refetch when filters change (except search which is client-side)
  useEffect(() => {
    const filtersWithoutSearch = { ...filters, search: "" }
    const defaultWithoutSearch = { ...DEFAULT_FILTERS, search: "" }
    if (JSON.stringify(filtersWithoutSearch) !== JSON.stringify(defaultWithoutSearch)) {
      loadLeads()
    }
  }, [filters.tier, filters.stage, filters.minScore, filters.city, loadLeads])

  // Handle run pipeline
  const handleRunPipeline = async (zipCode: string, distance: number) => {
    setRunStage("scraping")
    try {
      await triggerPipelineRun(zipCode, distance)
      setIsPipelineRunning(true)
      toast.info(`Pipeline started for ZIP ${zipCode} within ${distance} mi`)
      setTimeout(() => setRunStage("enriching"), 2000)
    } catch {
      setRunStage("idle")
      toast.error("Failed to start pipeline")
    }
  }

  // Handle stage change
  const handleStageChange = async (id: string, stage: PipelineStage) => {
    try {
      await updateLeadStage(id, stage)

      // Update local state
      setLeads((prev) =>
        prev.map((lead) =>
          lead.id === id ? { ...lead, pipeline_stage: stage } : lead
        )
      )

      if (selectedLead?.id === id) {
        setSelectedLead((prev) =>
          prev ? { ...prev, pipeline_stage: stage } : null
        )
      }

      // Show toast
      const stageLabels: Record<PipelineStage, string> = {
        new: "New",
        contacted: "Contacted",
        qualified: "Qualified",
        customer: "Customer",
        disqualified: "Disqualified",
      }
      toast.success(`Marked as ${stageLabels[stage]}`)

      // Confetti for customer!
      if (stage === "customer") {
        setShowConfetti(true)
      }
    } catch {
      toast.error("Failed to update stage")
    }
  }

  // Handle view detail
  const handleViewDetail = async (id: string) => {
    setSelectedLeadId(id)
    setIsLoadingDetail(true)
    try {
      const detail = await fetchLeadDetail(id)
      setSelectedLead(detail)
    } catch {
      toast.error("Failed to load lead details")
      setSelectedLeadId(null)
    } finally {
      setIsLoadingDetail(false)
    }
  }

  // Handle close detail
  const handleCloseDetail = () => {
    setSelectedLeadId(null)
    setSelectedLead(null)
  }

  // Handle clear filters
  const handleClearFilters = () => {
    setFilters(DEFAULT_FILTERS)
  }

  return (
    <div className="min-h-screen bg-background bg-dot-pattern">
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: {
            background: "var(--card)",
            color: "var(--foreground)",
            border: "1px solid var(--border)",
          },
        }}
      />

      <Confetti active={showConfetti} onComplete={() => setShowConfetti(false)} />

      <PipelineStatusBar
        status={pipelineStatus}
        totalLeads={leads.length}
        onRunPipeline={handleRunPipeline}
        isRunning={isPipelineRunning}
        runStage={runStage}
      />

      <FilterBar filters={filters} onFiltersChange={setFilters} />

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        {/* Results count */}
        {!isLoadingLeads && !leadsError && filteredLeads.length > 0 && (
          <p className="text-sm text-muted-foreground mb-4">
            Showing <span className="font-medium text-foreground">{filteredLeads.length}</span> leads
            {" · "}Sorted by opportunity score
          </p>
        )}

        <LeadGrid
          leads={filteredLeads}
          isLoading={isLoadingLeads}
          error={leadsError}
          onStageChange={handleStageChange}
          onViewDetail={handleViewDetail}
          onClearFilters={handleClearFilters}
        />
      </main>

      {selectedLeadId && (
        <LeadDetailPanel
          lead={selectedLead}
          isLoading={isLoadingDetail}
          onClose={handleCloseDetail}
          onStageChange={handleStageChange}
        />
      )}
    </div>
  )
}
