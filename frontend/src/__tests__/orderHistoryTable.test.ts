import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import OrderHistoryTable from '../components/OrderHistoryTable.vue'

describe('OrderHistoryTable', () => {
  it('renders newest completed orders and expandable details', async () => {
    const wrapper = mount(OrderHistoryTable, {
      props: {
        entries: [
          {
            date: '2026-07-21T10:00:00',
            pair: 'XETHZEUR',
            type: 'buy',
            order_type: 'limit',
            o_flags: 'fciq',
            pair_price: '2000',
            volume: '0.02',
            price: '40',
            fee: '0.10',
            total_price: '40.10',
            txid: 'NEWER',
            description: 'buy 0.02 XETHZEUR @ limit 2000',
          },
        ],
      },
    })

    expect(wrapper.text()).toContain('Completed order history')
    expect(wrapper.text()).toContain('XETHZEUR')
    expect(wrapper.text()).toContain('40.10')

    await wrapper.get('button[aria-label="Show order NEWER details"]').trigger('click')

    expect(wrapper.text()).toContain('Transaction id')
    expect(wrapper.text()).toContain('NEWER')
    expect(wrapper.text()).toContain('Exchange fee')
  })

  it('renders an empty state', () => {
    const wrapper = mount(OrderHistoryTable, {
      props: {
        entries: [],
      },
    })

    expect(wrapper.text()).toContain('No completed orders yet')
  })
})
