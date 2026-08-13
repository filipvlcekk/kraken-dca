import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import PairStatusPanel from '../components/PairStatusPanel.vue'

describe('PairStatusPanel', () => {
  it('combines scheduler status and history in plain labels', () => {
    const wrapper = mount(PairStatusPanel, {
      props: {
        pairs: [
          {
            pair: 'XXBTZEUR',
            trade_count: 2,
            total_volume: '0.02',
            total_spent: '50.10',
            total_price: '50',
            total_fees: '0.10',
            average_buy_price: '2500',
            last_trade_at: '2026-07-21T08:00:00',
            last_trade_txid: 'TXID',
            current_price: '3000',
            estimated_value: '60',
            estimated_pl: '9.90',
          },
        ],
        jobs: [
          {
            id: 'XXBTZEUR',
            pair: 'XXBTZEUR',
            mode: 'cron',
            enabled: true,
            cron: '0 9 * * *',
            timezone: 'Europe/Prague',
            next_run_at: '2026-07-22T07:00:00Z',
            running: false,
          },
        ],
      },
    })

    expect(wrapper.text()).toContain('XXBTZEUR')
    expect(wrapper.text()).toContain('Active')
    expect(wrapper.text()).toContain('Buys completed')
    expect(wrapper.text()).toContain('Estimated gain/loss')
    expect(wrapper.text()).toContain('+9.90')
  })
})
