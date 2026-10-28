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
  missing_labels: string[]
  reliable: boolean
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

export type LabModel = 'standard' | 'conservative'

export interface LabMetrics {
  trades: number
  win_rate: number
  avg: number
  total: number
  max_drawdown: number
  profit_factor: number | null
  worst: number
  best: number
  avg_cost?: number
  avg_gross?: number
  break_even_cost?: number
}

export interface LabResult {
  algo_id: string
  algo_name: string
  model: { name: LabModel; label: string }
  gated: boolean
  start: string
  end: string
  days: number
  metrics: LabMetrics
  yearly: ({ year: number } & LabMetrics)[]
  curve: [string, number][]
  trades: { date: string; regime: string; side: string; pnl: number; cost: number }[]
  skipped: { reason: string; days: number }[]
  notes: string[]
  caveats: string[]
}

export interface LabRequest {
  algo_id: string
  model: LabModel
  gated: boolean
  start?: string
}

export const algoQueryKeys = {
  all: ['algos'] as const,
  catalogue: () => [...algoQueryKeys.all, 'catalogue'] as const,
  regime: () => [...algoQueryKeys.all, 'regime'] as const,
  coverage: () => [...algoQueryKeys.all, 'coverage'] as const,
  readiness: () => [...algoQueryKeys.all, 'readiness'] as const,
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

export async function runLab(request: LabRequest): Promise<LabResult> {
  const response = await webClient.post<{ data: LabResult }>(`${BASE}/lab/run`, request)
  return response.data.data
}

export interface ReadinessStep {
  id: string
  label: string
  state: 'done' | 'todo' | 'confirm'
  detail: string
  path: string | null
}

export interface Readiness {
  steps: ReadinessStep[]
  ready_for_sandbox: boolean
  ready_for_live: boolean
  next: string | null
}

export async function fetchReadiness(): Promise<Readiness> {
  const response = await webClient.get<{ data: Readiness }>(`${BASE}/readiness`)
  return response.data.data
}

export type BuilderFamily = 'condor' | 'bull_put' | 'bear_call'

export interface BuilderStats {
  trades: number
  win_rate: number
  avg: number
  total: number
  max_drawdown: number
  profit_factor: number | null
}

export interface BuilderCandidate {
  spec: Record<string, unknown>
  name: string
  train: BuilderStats
  validate: BuilderStats
  test?: BuilderStats
  curve?: [string, number][]
}

export interface BuilderResult {
  trials: number
  lost_on_test: number
  segments: Record<'train' | 'validate' | 'test', [string, string]>
  baseline_test: BuilderStats | null
  winner: BuilderCandidate | null
  shortlist: BuilderCandidate[]
  verdict: { edge_shown: boolean; headline: string; reasons: string[] }
  caveats: string[]
  proposal?: { name: string; why: string; spec: Record<string, unknown> } | null
}

export type BuilderJob =
  | { state: 'running'; progress: { done: number; total?: number } }
  | { state: 'done'; result: BuilderResult }
  | { state: 'failed'; message: string }

export interface BuilderRequest {
  families: BuilderFamily[]
  label_sets: string[][]
  custom_id?: number
}

export async function startBuilderSearch(request: BuilderRequest): Promise<string> {
  const response = await webClient.post<{ job_id: string }>(`${BASE}/builder/search`, request)
  return response.data.job_id
}

export async function fetchBuilderJob(jobId: string): Promise<BuilderJob> {
  const response = await webClient.get<{ data: BuilderJob }>(`${BASE}/builder/jobs/${jobId}`)
  return response.data.data
}

export async function saveBuiltAlgo(jobId: string, name: string): Promise<{ algo_id: string }> {
  const response = await webClient.post<{ data: { algo_id: string } }>(`${BASE}/builder/save`, {
    job_id: jobId,
    name,
  })
  return response.data.data
}

export async function deleteBuiltAlgo(customId: number): Promise<void> {
  await webClient.delete(`${BASE}/builder/custom/${customId}`)
}

export interface ChooserCell {
  trades: number
  total: number
  avg: number
  profit_factor: number | null
}

export interface ChooserRow {
  algo_id: string
  name: string
  eligible: boolean
  reasons: string[]
  evidence: ChooserCell
  check: ChooserCell
}

export interface ChooserToday {
  regime: Regime
  decision: { pick: string | null; headline: string; candidates: ChooserRow[] }
  table: { built_at: string | null; first: string; split: string; last: string } | null
}

export async function fetchChooserToday(): Promise<ChooserToday> {
  const response = await webClient.get<{ data: ChooserToday }>(`${BASE}/chooser/today`)
  return response.data.data
}

export async function rebuildChooser(): Promise<string> {
  const response = await webClient.post<{ job_id: string }>(`${BASE}/chooser/rebuild`)
  return response.data.job_id
}

export interface DebugStep {
  title: string
  status: 'pass' | 'stop' | 'info'
  detail: string
}

export interface DebugResult {
  algo_name: string
  verdict: string
  date?: string
  decided_at?: string
  steps: DebugStep[]
}

export async function debugDay(algoId: string, date: string): Promise<DebugResult> {
  const response = await webClient.post<{ data: DebugResult }>(`${BASE}/debug`, {
    algo_id: algoId,
    date,
  })
  return response.data.data
}

export async function fetchExplanations(deploymentId: number): Promise<DebugResult[]> {
  const response = await webClient.get<{ data: DebugResult[] }>(
    `${BASE}/deployments/${deploymentId}/explain`
  )
  return response.data.data
}
