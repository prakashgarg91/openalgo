// api/algos.ts
// Regime algo catalogue: Zen, Mirror Zen and friends.
//
// Base is `/algos/api`, session-cookie authenticated. `webClient` carries the
// CSRF token on writes and rewrites an axios error's message to the server's own
// explanation, so callers read `error.message` and show it as it is.

import { webClient } from './client'

const BASE = '/algos/api'

export type RegimeLabel = 'calm' | 'trending' | 'volatile' | 'event'
export type Bias = 'bullish' | 'bearish' | 'neutral'
export type AlgoMode = 'sandbox' | 'live'

export interface Regime {
  label: RegimeLabel
  bias: Bias
  score: number
  confidence: number
  reasons: string[]
  missing: string[]
}

export interface Plan {
  algo_id: string
  action: 'trade' | 'skip'
  reason: string
  lots: number
  max_loss_inr: number | null
  side: string | null
}

export interface Decision {
  id: number
  decided_at: string
  action: 'trade' | 'skip' | 'error'
  regime_label: string | null
  bias: string | null
  side: string | null
  lots: number | null
  max_loss_inr: number | null
  reason: string
}

export interface TrackRecord {
  runs: number
  wins: number
  net_pnl: number
  worst_run: number
  available: boolean
}

export interface LiveGate {
  allowed: boolean
  needed_runs: number
  reason: string
  record: TrackRecord
}

export interface Deployment {
  id: number
  algo_id: string
  strategy_id: number
  capital: number
  active: boolean
  mode: AlgoMode
  live_enabled: boolean
  position_open: boolean
  max_loss_ceiling_inr: number | null
  recent_decisions: Decision[]
  live_gate: LiveGate
}

export interface AlgoItem {
  id: string
  name: string
  summary: string
  risk: 'low' | 'medium' | 'high'
  allowed_regimes: RegimeLabel[]
  overnight: boolean
  entry_time: string
  status: 'tested' | 'experimental'
  evidence: string
  deployment: Deployment | null
}

export interface Coverage {
  regimes: Record<RegimeLabel, string[]>
  stands_aside_on: RegimeLabel[]
}

export const algoQueryKeys = {
  all: ['algos'] as const,
  catalogue: () => [...algoQueryKeys.all, 'catalogue'] as const,
  regime: () => [...algoQueryKeys.all, 'regime'] as const,
  coverage: () => [...algoQueryKeys.all, 'coverage'] as const,
}

export async function fetchCatalogue(): Promise<AlgoItem[]> {
  const response = await webClient.get<{ data: AlgoItem[] }>(`${BASE}/catalogue`)
  return response.data.data
}

export async function fetchRegime(): Promise<Regime> {
  const response = await webClient.get<{ data: Regime }>(`${BASE}/regime`)
  return response.data.data
}

export async function fetchCoverage(): Promise<Coverage> {
  const response = await webClient.get<{ data: Coverage }>(`${BASE}/coverage`)
  return response.data.data
}

export async function previewAlgo(
  algoId: string,
  capital: number
): Promise<{ regime: Regime; plan: Plan }> {
  const response = await webClient.post<{ data: { regime: Regime; plan: Plan } }>(
    `${BASE}/preview`,
    { algo_id: algoId, capital }
  )
  return response.data.data
}

export async function deployAlgo(algoId: string, capital: number): Promise<Deployment> {
  const response = await webClient.post<{ data: Deployment }>(`${BASE}/deployments`, {
    algo_id: algoId,
    capital,
  })
  return response.data.data
}

export async function setAlgoActive(id: number, active: boolean): Promise<Deployment> {
  const response = await webClient.post<{ data: Deployment }>(`${BASE}/deployments/${id}/active`, {
    active,
  })
  return response.data.data
}

export async function setAlgoLive(
  id: number,
  enabled: boolean,
  confirmMaxLoss?: number
): Promise<Deployment> {
  const response = await webClient.post<{ data: Deployment }>(`${BASE}/deployments/${id}/live`, {
    enabled,
    confirm_max_loss: confirmMaxLoss,
  })
  return response.data.data
}

export async function checkAlgoNow(id: number): Promise<{ action: string; reason: string }> {
  const response = await webClient.post<{ data: { action: string; reason: string } }>(
    `${BASE}/deployments/${id}/run-now`
  )
  return response.data.data
}

export async function removeAlgo(id: number): Promise<void> {
  await webClient.delete(`${BASE}/deployments/${id}`)
}
