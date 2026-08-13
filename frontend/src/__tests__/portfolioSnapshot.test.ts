import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import PortfolioSnapshot from '../components/PortfolioSnapshot.vue'

describe('PortfolioSnapshot', () => {
  it('renders household-readable money labels', () => {
    const wrapper = mount(PortfolioSnapshot, {
      props: {
        portfolio: {
          trade_count: 3,
          total_spent: '90.23',
          total_price: '90',
          total_fees: '0.23',
          estimated_value: '105.00',
          estimated_pl: '14.77',
        },
        valuation: {
          status: 'live',
          message: null,
        },
      },
    })

    expect(wrapper.text()).toContain('You spent')
    expect(wrapper.text()).toContain('You bought')
    expect(wrapper.text()).toContain('Worth now')
    expect(wrapper.text()).toContain('Estimated gain/loss')
    expect(wrapper.text()).toContain('+14.77')
  })

  it('explains unavailable live estimates', () => {
    const wrapper = mount(PortfolioSnapshot, {
      props: {
        portfolio: {
          trade_count: 0,
          total_spent: '0',
          total_price: '0',
          total_fees: '0',
          estimated_value: null,
          estimated_pl: null,
        },
        valuation: {
          status: 'unavailable',
          message: 'Live Kraken price unavailable.',
        },
      },
    })

    expect(wrapper.text()).toContain('Live Kraken price unavailable.')
    expect(wrapper.text()).toContain('No live estimate')
  })
})
