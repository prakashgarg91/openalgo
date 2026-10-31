// api/research.ts
// Cross-market linkage study for the Research page.
//
// Base is `/research/api`, session-cookie authenticated. `webClient` rewrites an axios
// error's message to the server's own explanation, so callers show `error.message` as it is.

import { webClient } from './client'

export type LinkStatus = 'verified' | 'weak' | 'flipped' | 'not_selected'

export interface ResearchNode {
  id: string
  label: string
  group: string
  kind: 'driver' | 'target'
  note?: string
}

export interface ResearchLink {
  source: string
  target: string
  status: LinkStatus
  beta_disc: number
  t_disc: number
  beta_ver: number | null
  t_ver: number | null
}

export interface JointModelRow {
  target: string
  r2_full: number
  r2_baseline: number
  rank_corr_full: number
  rank_corr_baseline: number
}

export interface RangeModelRow {
  model: string
  r2_out: number
  rank_corr: number
}

export interface RangeCalibration {
  group: number
  days: number
  mean_range_pct: number
}

export interface LinkageData {
  generated: string
  meta: {
    days: number
    pairs_tried: number
    selected: number
    verified: number
    flipped: number
    chance_mean: number
    chance_p95: number
    discovery: string
    verification: string
  }
  groups: { id: string; label: string }[]
  nodes: ResearchNode[]
  links: ResearchLink[]
  joint_model: JointModelRow[]
  range_model: {
    models: RangeModelRow[]
    calibration: RangeCalibration[]
    top_to_bottom: number
  }
}

export const researchQueryKeys = {
  linkage: () => ['research', 'linkage'] as const,
}

export async function fetchLinkage(): Promise<LinkageData> {
  const response = await webClient.get<{ data: LinkageData }>('/research/api/linkage')
  return response.data.data
}
