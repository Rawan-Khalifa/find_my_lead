// API Types for FindMyLead
// Field nullability matches the Python backend schemas exactly (api/schemas.py)

export type GafTier = "Master Elite" | "Certified Plus" | "Certified" | "Registered" | "Unknown"
export type PipelineStage = "new" | "contacted" | "qualified" | "customer" | "disqualified"
export type OutreachAngle = "new_relationship" | "upsell" | "reactivation"

export interface ContractorListItem {
  id: string
  name: string
  city: string | null
  state: string | null
  phone: string | null
  gaf_tier: GafTier
  distance_miles: number | null
  rating: number | null
  reviews_count: number | null
  pipeline_stage: PipelineStage
  opportunity_score: number | null
  outreach_angle: string | null
  has_enrichment: boolean
}

export interface ContractorEnrichment {
  opportunity_score: number | null
  score_reasoning: string | null
  talking_points: string[]
  likely_product_needs: string[]
  outreach_angle: string | null
  risk_flags: string[]
  web_research_summary: string | null
  qualifier_bonus: number | null
  model_version: string | null
  prompt_version: string | null
  created_at: string | null
}

export interface ContractorDetail extends ContractorListItem {
  address: string | null
  zip_code: string | null
  website: string | null
  specialties: string[]
  gaf_profile_url: string | null
  scraped_at: string | null
  enrichment: ContractorEnrichment | null
}

export interface LeadsResponse {
  total: number
  page: number
  page_size: number
  results: ContractorListItem[]
}

export interface PipelineStatus {
  run_id: string | null
  status: string | null
  contractors_scraped: number | null
  contractors_new: number | null
  enrichments_created: number | null
  enrichments_failed: number | null
  started_at: string | null
  completed_at: string | null
  zip_code: string | null
}

export interface PipelineRunResponse {
  run_id: string
  status: string
  message: string
}

export interface LeadFilters {
  search: string
  tier: GafTier | "all"
  stage: PipelineStage | "all"
  minScore: number
  city: string
}
