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
  account?: AccountResult
}

export interface AccountResult {
  lots: number
  message?: string
  capital?: number
  max_daily_loss?: number
  worst_case_per_trade?: number
  days_traded?: number
  final_equity?: number
  return_pct?: number
  worst_day?: number
  best_day?: number
  max_drawdown?: number
  max_drawdown_pct?: number
  lowest_equity?: number
  ruined?: boolean
  within_daily_cap?: boolean
  cap_breaches?: { date: string; loss: number }[]
  curve?: [string, number][]
}

export interface LabRequest {
  algo_id: string
  model: LabModel
  gated: boolean
  start?: string
  account?: { capital: number; max_daily_loss: number }
}

export const algoQueryKeys = {
  all: ['algos'] as const,
  catalogue: () => [...algoQueryKeys.all, 'catalogue'] as const,
  regime: () => [...algoQueryKeys.all, 'regime'] as const,
  coverage: () => [...algoQueryKeys.all, 'coverage'] as const,
  readiness: () => [...algoQueryKeys.all, 'readiness'] as const,
  registry: () => [...algoQueryKeys.all, 'registry'] as const,
  forward: () => [...algoQueryKeys.all, 'forward'] as const,
  ideaTracker: () => [...algoQueryKeys.all, 'idea-tracker'] as const,
  reconciliation: () => [...algoQueryKeys.all, 'reconciliation'] as const,
  picker: (margins = false) => [...algoQueryKeys.all, 'picker', margins] as const,
  picks: () => [...algoQueryKeys.all, 'picks'] as const,
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

export interface WaitingProposal {
  checked_on: string
  verdict: string
  trials: number
  proposal: { name: string; why: string } | null
}

export async function fetchProposal(customId: number): Promise<WaitingProposal | null> {
  const response = await webClient.get<{ data: WaitingProposal | null }>(
    `${BASE}/builder/custom/${customId}/proposal`
  )
  return response.data.data
}

export interface EventDay {
  date: string
  label: string
}

export async function fetchEventDays(): Promise<EventDay[]> {
  const response = await webClient.get<{ data: EventDay[] }>(`${BASE}/events`)
  return response.data.data
}

export async function addEventDay(date: string, label: string): Promise<EventDay[]> {
  const response = await webClient.post<{ data: EventDay[] }>(`${BASE}/events`, { date, label })
  return response.data.data
}

export async function removeEventDay(date: string): Promise<EventDay[]> {
  const response = await webClient.delete<{ data: EventDay[] }>(`${BASE}/events/${date}`)
  return response.data.data
}

export interface UniverseStats {
  cagr: number
  total: number
  max_drawdown: number
  worst_day: number
  days: number
}

export interface UniverseResult {
  kind: 'universe'
  data_from: string
  data_to: string
  trials: number
  segments: Record<'train' | 'validate' | 'test', [string, string]>
  lost_to_cash_on_test: number
  baselines: Record<'buy_and_hold' | 'cash', Record<'train' | 'validate' | 'test', UniverseStats>>
  winner: { name: string; stats: Record<'train' | 'validate' | 'test', UniverseStats> }
  rules: {
    name: string
    family: string
    train_cagr: number
    validate_cagr: number
    test_cagr: number
    test_excess_over_cash: number
  }[]
  verdict: {
    edge_shown: boolean
    beats_cash: boolean
    beats_buy_and_hold: boolean
    lowers_risk_like_buy_and_hold: boolean
    within_daily_cap: boolean
    headline: string
    reasons: string[]
  }
  today?: {
    as_of: string | null
    lookback_days?: number
    returns: Record<string, number>
    would_hold: Record<string, number>
    nifty_above_200_day_average?: boolean | null
    headline: string
    note?: string
  }
  account: AccountResult
  caveats: string[]
}

export async function startUniverseSearch(account: {
  capital: number
  max_daily_loss: number
}): Promise<string> {
  const response = await webClient.post<{ job_id: string }>(`${BASE}/universe/search`, { account })
  return response.data.job_id
}

export interface RegistrationRow {
  id: string
  name: string
  created_at: string
  slot: string
  trial_numbers: [number, number]
  pass_bar: number
  status: string
  intact: boolean
  needs_post_mortem?: boolean
}

export interface RegistryView {
  trial_count: number
  pass_bar: number
  next_free_month: string
  months_used: Record<string, string>
  fields: Record<string, string>
  registrations: RegistrationRow[]
}

export type RegistrationDraft = Record<string, unknown>

export async function fetchRegistry(): Promise<RegistryView> {
  const response = await webClient.get<{ data: RegistryView }>(`${BASE}/registry`)
  return response.data.data
}

export async function registerIdea(draft: RegistrationDraft): Promise<RegistrationRow> {
  const response = await webClient.post<{ data: RegistrationRow }>(`${BASE}/registry`, draft)
  return response.data.data
}

export interface ForwardRow {
  name: string
  state: string
  verdict: string | null
  completed: number
  trades_to_go: number | null
  net: number | null
}

export async function fetchForwardTests(): Promise<ForwardRow[]> {
  const response = await webClient.get<{ data: ForwardRow[] }>(`${BASE}/forward`)
  return response.data.data
}

export interface TrackedIdea {
  id: string
  name: string
  registered: string
  slot: string
  trial_numbers: [number, number]
  stage: string
  failed_gates: string[]
  why_it_might_work: string
  how_it_fails: string
  intact: boolean
}

export interface IdeaTracker {
  trial_count: number
  pass_bar: number
  standard_errors_needed: number
  next_free_month: string
  ideas: TrackedIdea[]
  stage_counts: Record<string, number>
  lessons: { gate: string; ideas_missed: number }[]
  forward_tests: ForwardRow[]
  live_gate: 'locked'
  rules: string[]
}

export async function fetchIdeaTracker(): Promise<IdeaTracker> {
  const response = await webClient.get<{ data: IdeaTracker }>(`${BASE}/idea-tracker`)
  return response.data.data
}

export async function savePostMortem(id: string, text: string): Promise<void> {
  await webClient.post(`${BASE}/registry/${id}/post-mortem`, { text })
}

export interface ReconciliationRow {
  expiry: string
  ledger_credit: number
  bot_credit: number
  entry_shortfall: number
  exit_shortfall: number | null
  flagged: boolean
}

export interface Reconciliation {
  rows: ReconciliationRow[]
  weeks: number
  mean_entry_shortfall: number | null
  flag_points: number
}

export async function fetchReconciliation(): Promise<Reconciliation> {
  const response = await webClient.get<{ data: Reconciliation }>(`${BASE}/reconciliation`)
  return response.data.data
}

export type PickerRow = {
  id: string
  name: string
  direction: string
  priced: boolean
  evidence: string
  blocked_because: string[]
  score?: number
  capital_required?: number | null
  capital_source?: string
  components?: Record<string, number>
  stats?: {
    max_loss: number | null
    unbounded_loss: boolean
    max_profit: number | null
    net_credit: number
    breakevens: number[]
  }
  costs?: { charges: number; spread: number; total: number }
  history?: PickerHistory | null
  scenarios?: { multiple: number; label: string; nifty: number; pnl: number }[] | null
}

export type PickerHistory = {
  available: boolean
  reason?: string
  trades?: number
  mean?: number
  median?: number
  win_rate?: number
  worst?: number
  p05?: number
  mean_lower?: number
  older_mean?: number | null
  recent_mean?: number
  note?: string
  today_bucket?: {
    bucket: string | null
    note?: string
    trades?: number
    mean?: number
    win_rate?: number
    worst?: number
  }
}

export type PickerView = {
  header: {
    disclaimer: string
    notes: string[]
    confidence: number
    expected_move: { fifteen_minutes: number | null; day: number | null }
    capital: number
    daily_cap: number
    lot: number
    spot: number
    dte: number
    expiry?: string
    margins_from_broker?: number
    vix?: number | null
    regime?: { label: string; bias: string; reasons: string[] } | null
    history_note?: string | null
    research?: {
      expected_gap: {
        gap_pct: number | null
        links: { label: string; move_pct: number; coefficient: number; implied_gap_pct: number }[]
      }
      skill: Record<string, { r2: number; usable: boolean; note: string }>
    }
  }
  ranked: PickerRow[]
  blocked: PickerRow[]
}

export async function fetchPicker(margins = false): Promise<PickerView> {
  const response = await webClient.get<{ data: PickerView }>(`${BASE}/picker`, {
    params: { margins: margins ? '1' : '0' },
  })
  return response.data.data
}

export type TrackedPick = {
  id: string
  template_id: string
  name: string
  fit: number
  expiry: string
  lot: number
  status: 'open' | 'closed'
  opened: string
  closed: string | null
  pnl: number | null
  unrealized: number | null
  capital_required?: number | null
  max_loss?: number | null
  legs: { kind: string; strike: number; side: string; qty: number; price: number }[]
  conditions?: {
    spot?: number
    vix?: number | null
    dte?: number
    regime?: string | null
    expected_gap_pct?: number | null
  }
}

export type PickSummary = {
  open: number
  closed: number
  wins: number
  win_rate: number | null
  average_pnl: number | null
  worst: number | null
  best: number | null
  total: number
  correlation: number | null
  verdict: string
}

export type PicksView = { picks: TrackedPick[]; summary: PickSummary }

export async function fetchPicks(): Promise<PicksView> {
  const response = await webClient.get<{ data: PicksView }>(`${BASE}/picks`)
  return response.data.data
}

export async function trackPick(templateId: string): Promise<TrackedPick> {
  const response = await webClient.post<{ data: TrackedPick }>(`${BASE}/picks`, {
    template_id: templateId,
  })
  return response.data.data
}

export async function closePick(id: string, pnl?: number): Promise<TrackedPick> {
  const response = await webClient.post<{ data: TrackedPick }>(
    `${BASE}/picks/${id}/close`,
    pnl === undefined ? {} : { pnl }
  )
  return response.data.data
}
