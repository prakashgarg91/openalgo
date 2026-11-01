import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { CostData, StructuresData } from '@/api/research'
import { OptionTestsPanel } from './OptionTestsPanel'

const cost: CostData = {
  rows: [
    {
      rule: 'Always sell calls',
      sel_pre_cost: 68086,
      sel_conservative: -21582,
      sel_realistic: 16970,
      sel_realistic_2x: -34147,
      sel_drawdown: 57148,
      held_pre_cost: 27982,
      held_conservative: -9858,
      held_realistic: 7611,
      held_realistic_2x: -12760,
      held_drawdown: 36175,
      cost_per_trade_realistic: 157,
      cost_per_trade_conservative: 275,
    },
  ],
}

describe('OptionTestsPanel cost card', () => {
  it('shows both periods under both cost models, with signs', () => {
    render(<OptionTestsPanel cost={cost} />)
    expect(screen.getByText(/Does a realistic cost model change it/)).toBeTruthy()
    expect(screen.getByText('First two thirds')).toBeTruthy()
    expect(screen.getByText('Last third')).toBeTruthy()
    expect(screen.getByText('Rs 16,970')).toBeTruthy()
    expect(screen.getByText('-Rs 34,147')).toBeTruthy()
    expect(screen.getByText('-Rs 12,760')).toBeTruthy()
  })

  it('renders nothing for a result that is not there yet', () => {
    render(<OptionTestsPanel />)
    expect(screen.queryByText(/realistic cost model/)).toBeNull()
  })
})

const structures: StructuresData = {
  rows: [
    {
      name: 'S3',
      label: 'Weekly call spread, 250 wide',
      candidate: true,
      passed: false,
      failed: ['drawdown', 'bootstrap'],
      sel_trades: 67,
      sel_pre_cost: 70732,
      sel_realistic: 60033,
      sel_realistic_2x: 49335,
      sel_drawdown: 31881,
      held_trades: 30,
      held_pre_cost: 77873,
      held_realistic: 73189,
      held_realistic_2x: 68504,
      held_drawdown: 26723,
      held_worst_day: -13352,
    },
    {
      name: 'S2',
      label: 'Weekly iron condor',
      candidate: false,
      passed: false,
      failed: [],
      sel_trades: 68,
      sel_pre_cost: 339,
      sel_realistic: -19873,
      sel_realistic_2x: -40084,
      sel_drawdown: 57776,
      held_trades: 30,
      held_pre_cost: 16068,
      held_realistic: 7273,
      held_realistic_2x: -1523,
      held_drawdown: 32968,
      held_worst_day: -22165,
    },
  ],
}

const narrowRow: StructuresData['rows'][number] = {
  name: 'S3n',
  label: 'Weekly call spread, 100 wide',
  candidate: true,
  passed: false,
  failed: ['bootstrap'],
  sel_trades: 68,
  sel_pre_cost: 46590,
  sel_realistic: 35380,
  sel_realistic_2x: 24171,
  sel_drawdown: 15013,
  held_trades: 30,
  held_pre_cost: 40362,
  held_realistic: 35530,
  held_realistic_2x: 30697,
  held_drawdown: 13425,
  held_worst_day: -6916,
}

describe('OptionTestsPanel structures card', () => {
  it('distinguishes a drawdown failure from a statistical one', () => {
    render(<OptionTestsPanel structures={{ rows: [narrowRow] }} />)
    expect(screen.getByText('Within the loss limit, not proven')).toBeTruthy()
  })

  it('says why each structure did not pass', () => {
    render(<OptionTestsPanel structures={structures} />)
    expect(screen.getByText('Weekly call spread, 250 wide')).toBeTruthy()
    expect(screen.getByText('Too much drawdown, not proven')).toBeTruthy()
    expect(screen.getByText('Lost money, dropped')).toBeTruthy()
    expect(screen.getByText('Rs 60,033')).toBeTruthy()
    expect(screen.getByText('-Rs 40,084')).toBeTruthy()
  })
})
