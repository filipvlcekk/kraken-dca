import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ProfitLossChart from '../components/ProfitLossChart.vue'

describe('ProfitLossChart', () => {
  it('renders an accessible SVG chart for completed buys', () => {
    const wrapper = mount(ProfitLossChart, {
      props: {
        points: [
          {
            date: '2026-07-20T10:00:00',
            pair: 'XETHZEUR',
            txid: 'A',
            spent: '20.05',
            volume: '0.01',
            cumulative_spent: '20.05',
            cumulative_volume: '0.01',
          },
          {
            date: '2026-07-21T10:00:00',
            pair: 'XETHZEUR',
            txid: 'B',
            spent: '40.10',
            volume: '0.02',
            cumulative_spent: '60.15',
            cumulative_volume: '0.03',
          },
        ],
        estimatedValue: '75.00',
      },
    })

    expect(wrapper.find('svg[role="img"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Buying history and estimate')
    expect(wrapper.text()).toContain('Money spent')
    expect(wrapper.text()).toContain('Worth now')
  })

  it('renders an empty state without chart points', () => {
    const wrapper = mount(ProfitLossChart, {
      props: {
        points: [],
        estimatedValue: null,
      },
    })

    expect(wrapper.text()).toContain('No completed orders yet')
  })
})
