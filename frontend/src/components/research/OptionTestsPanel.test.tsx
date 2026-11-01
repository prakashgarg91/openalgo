import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { CostData } from '@/api/research'
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
