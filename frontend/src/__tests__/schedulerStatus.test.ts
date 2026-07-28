import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import type { SchedulerStatus as SchedulerStatusData } from '../api'
import SchedulerStatus from '../components/SchedulerStatus.vue'

const status: SchedulerStatusData = {
  running: true,
  config_applied: true,
  saved_config_fingerprint: 'saved',
  active_config_fingerprint: 'active',
  reload_error: null,
  last_reload_at: '2026-07-21T08:00:00Z',
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
    {
      id: 'XETHZEUR',
      pair: 'XETHZEUR',
      mode: 'legacy-delay',
      enabled: false,
      cron: null,
      timezone: 'UTC',
      next_run_at: null,
      running: true,
    },
  ],
}

describe('SchedulerStatus', () => {
  it('renders running state, job count, and next run details', () => {
    const wrapper = mount(SchedulerStatus, {
      props: {
        status,
        onReload: vi.fn(),
      },
    })

    expect(wrapper.text()).toContain('Scheduler running')
    expect(wrapper.text()).toContain('2 jobs')
    expect(wrapper.text()).toContain('XXBTZEUR')
    expect(wrapper.text()).toContain('0 9 * * *')
    expect(wrapper.text()).toContain('Europe/Prague')
    expect(wrapper.text()).toContain('2026-07-22T07:00:00Z')
    expect(wrapper.text()).toContain('XETHZEUR')
    expect(wrapper.text()).toContain('manual run active')
  })

  it('renders config mismatch, reload errors, and retry action', async () => {
    const onReload = vi.fn()
    const wrapper = mount(SchedulerStatus, {
      props: {
        status: {
          ...status,
          running: false,
          config_applied: false,
          reload_error: 'Invalid cron expression.',
          jobs: [],
        },
        onReload,
      },
    })

    expect(wrapper.text()).toContain('Scheduler stopped')
    expect(wrapper.text()).toContain('Config mismatch')
    expect(wrapper.text()).toContain('Invalid cron expression.')

    await wrapper.get('button[aria-label="Reload scheduler"]').trigger('click')

    expect(onReload).toHaveBeenCalledOnce()
  })
})
