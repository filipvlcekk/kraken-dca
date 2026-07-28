import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { DcaPairConfig } from '../api'
import PairEditor from '../components/PairEditor.vue'
import type { ManualRunState } from '../schedulerStore'

const pairConfig: DcaPairConfig = {
  pair: 'XXBTZEUR',
  amount: 15,
  limit_factor: 1.02,
  max_price: 42_000,
  ignore_differing_orders: true,
  min_order_interval_minutes: 30,
  schedule: {
    enabled: true,
    cron: '0 9 * * *',
    timezone: 'UTC',
  },
}

describe('PairEditor', () => {
  it('renders pair fields, validation errors, and emits pair updates', async () => {
    const wrapper = mount(PairEditor, {
      props: {
        pairConfig,
        fieldErrors: {
          pair: 'Pair is required.',
          amount: 'Amount must be positive.',
        },
        manualRunState: null,
      },
    })

    expect(wrapper.get<HTMLInputElement>('input[aria-label="Pair name"]').element.value).toBe('XXBTZEUR')
    expect(wrapper.get<HTMLInputElement>('input[aria-label="Amount"]').element.value).toBe('15')
    expect(wrapper.get<HTMLInputElement>('input[aria-label="Limit factor"]').element.value).toBe('1.02')
    expect(wrapper.get<HTMLInputElement>('input[aria-label="Max price"]').element.value).toBe('42000')
    expect(wrapper.get<HTMLInputElement>('input[aria-label="Ignore differing orders"]').element.checked).toBe(true)
    expect(wrapper.text()).toContain('Pair is required.')
    expect(wrapper.text()).toContain('Amount must be positive.')

    await wrapper.get('input[aria-label="Pair name"]').setValue('XETHZEUR')

    expect(lastEmission(wrapper.emitted('update:pairConfig'))).toEqual([
      {
        ...pairConfig,
        pair: 'XETHZEUR',
      },
    ])
  })

  it('emits schedule, min interval, manual run, and remove actions', async () => {
    const wrapper = mount(PairEditor, {
      props: {
        pairConfig,
        fieldErrors: {},
        manualRunState: {
          status: 'completed',
          message: 'Manual run completed.',
          orderTxid: 'ORDER-1',
        },
      },
    })

    await wrapper.get('select[aria-label="Schedule preset"]').setValue('every-15-minutes')
    expect(lastEmission(wrapper.emitted('update:pairConfig'))).toEqual([
      {
        ...pairConfig,
        schedule: {
          enabled: true,
          cron: '*/15 * * * *',
          timezone: 'UTC',
        },
      },
    ])

    await wrapper.get('input[aria-label="Minimum order interval minutes"]').setValue(45)
    expect(lastEmission(wrapper.emitted('update:pairConfig'))).toEqual([
      {
        ...pairConfig,
        min_order_interval_minutes: 45,
      },
    ])

    await wrapper.get('button[aria-label="Run XXBTZEUR now"]').trigger('click')
    await wrapper.get('button[aria-label="Remove XXBTZEUR"]').trigger('click')

    expect(wrapper.emitted('run-now')).toEqual([[]])
    expect(wrapper.emitted('remove')).toEqual([[]])
    expect(wrapper.text()).toContain('Manual run completed.')
    expect(wrapper.text()).toContain('ORDER-1')
  })

  it.each([
    [{ status: 'skipped', message: 'Skipped by safety interval.' }, 'Skipped by safety interval.'],
    [{ status: 'running-conflict', message: 'Another run is active.' }, 'Another run is active.'],
    [{ status: 'failed', message: 'Kraken API failed.' }, 'Kraken API failed.'],
  ] satisfies Array<[ManualRunState, string]>)('renders manual run state %s', (manualRunState, text) => {
    const wrapper = mount(PairEditor, {
      props: {
        pairConfig,
        fieldErrors: {},
        manualRunState,
      },
    })

    expect(wrapper.text()).toContain(text)
  })
})

function lastEmission(events: unknown[][] | undefined): unknown[] | undefined {
  return events?.[events.length - 1]
}
