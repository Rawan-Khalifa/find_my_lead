import type {
  LeadsResponse,
  ContractorDetail,
  PipelineStatus,
  PipelineRunResponse,
  LeadFilters,
  PipelineStage,
} from "./types"

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export async function fetchLeads(
  filters: LeadFilters,
  page = 1,
  pageSize = 20
): Promise<LeadsResponse> {
  const params = new URLSearchParams()
  params.set("page", page.toString())
  params.set("page_size", pageSize.toString())
  params.set("sort_by", "opportunity_score")
  params.set("sort_order", "desc")

  if (filters.tier !== "all") {
    params.set("tier", filters.tier)
  }
  if (filters.stage !== "all") {
    params.set("stage", filters.stage)
  }
  if (filters.minScore > 0) {
    params.set("min_score", filters.minScore.toString())
  }
  if (filters.city) {
    params.set("city", filters.city)
  }

  const response = await fetch(`${API_BASE}/leads?${params.toString()}`)
  if (!response.ok) {
    throw new Error(`Failed to fetch leads: ${response.statusText}`)
  }
  return response.json()
}

export async function fetchLeadDetail(id: string): Promise<ContractorDetail> {
  const response = await fetch(`${API_BASE}/leads/${id}`)
  if (!response.ok) {
    throw new Error(`Failed to fetch lead detail: ${response.statusText}`)
  }
  return response.json()
}

export async function updateLeadStage(
  id: string,
  stage: PipelineStage
): Promise<void> {
  const response = await fetch(`${API_BASE}/leads/${id}/stage`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stage }),
  })
  if (!response.ok) {
    throw new Error(`Failed to update stage: ${response.statusText}`)
  }
}

export async function triggerPipelineRun(
  zipCode = "10013",
  distance = 25
): Promise<PipelineRunResponse> {
  const response = await fetch(`${API_BASE}/pipeline/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ zip_code: zipCode, distance }),
  })
  if (!response.ok) {
    throw new Error(`Failed to trigger pipeline: ${response.statusText}`)
  }
  return response.json()
}

export async function fetchPipelineStatus(): Promise<PipelineStatus> {
  const response = await fetch(`${API_BASE}/pipeline/status`)
  if (!response.ok) {
    throw new Error(`Failed to fetch pipeline status: ${response.statusText}`)
  }
  return response.json()
}

// Utility functions
export function formatPhone(digits: string | null): string {
  if (!digits) return ""
  if (digits.length !== 10) return digits
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`
}

export function formatDistance(miles: number | null): string {
  if (miles == null) return "— mi"
  return `${miles.toFixed(1)} mi`
}

export function timeSince(isoString: string): string {
  if (!isoString) return "Unknown"
  const date = new Date(isoString)
  const now = new Date()
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000)

  if (seconds < 60) return "just now"
  if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60)
    return `${minutes} minute${minutes === 1 ? "" : "s"} ago`
  }
  if (seconds < 86400) {
    const hours = Math.floor(seconds / 3600)
    return `${hours} hour${hours === 1 ? "" : "s"} ago`
  }
  const days = Math.floor(seconds / 86400)
  return `${days} day${days === 1 ? "" : "s"} ago`
}
