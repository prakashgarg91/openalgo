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

export interface DominoChain {
  driver: string
  driver_label: string
  middle: string
  middle_label: string
  end: string
  end_label: string
  stage1_beta: number
  stage1_t: number
  stage2_beta: number
  stage2_t: number
  carried: boolean
}

export interface DominoStage {
  tried: number
  selected: number
  verified: number
  chance_mean: number
}

export interface DominoStage2Pair {
  middle: string
  middle_label: string
  end: string
  end_label: string
  beta_disc: number
  t_disc: number
  beta_ver: number
  t_ver: number
  verified: boolean
}

export interface DominoData {
  stage1: DominoStage
  stage2: DominoStage
  chains: DominoChain[]
  stage2_pairs: DominoStage2Pair[]
}

export interface VrpRow {
  label: string
  days: number
  premium_pts: number
  payoff: number
  t: number
  positive: number
  worst: number
}

export interface VrpData {
  periods: VrpRow[]
  quintiles: (VrpRow & { group: number })[]
  top_minus_bottom: { payoff: number; t: number }
  forecast_r2: number
}

export interface HorizonData {
  pairs_tried: number
  selected: number
  verified: number
  chance_mean: number
  outcomes: { outcome: string; label: string; selected: number; verified: number }[]
  joint_model: { label: string; r2_full: number; r2_baseline: number }[]
  top_links: { input: string; outcome: string; beta_ver: number; t_ver: number }[]
}

export interface SpreadRow {
  rule: string
  gate: string
  sel_episodes: number
  sel_net: number
  sel_net_2x: number
  held_episodes: number
  held_net: number
  held_net_2x: number
  held_drawdown: number
}

export interface SpreadData {
  rows: SpreadRow[]
  qualified: number
  cells: number
  cells_lost_held: number
}

export interface MomentumData {
  sessions: number
  joint_r2: number
  pairs: {
    condition: string
    predictor: string
    beta_first: number
    t_first: number
    beta_second: number
    t_second: number
    verified: boolean
  }[]
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
  domino?: DominoData
  vrp?: VrpData
  horizon?: HorizonData
  spread?: SpreadData
  momentum?: MomentumData
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
