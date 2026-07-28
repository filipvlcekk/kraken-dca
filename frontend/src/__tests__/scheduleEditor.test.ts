import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ScheduleEditor from '../components/ScheduleEditor.vue'

describe('ScheduleEditor', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders enabled toggle, summary, timezone-aware preview, and field errors', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-21T06:00:00Z'))

    const wrapper = mount(ScheduleEditor, {
      props: {
        schedule: {
          enabled: true,
          cron: '0 9 * * *',
          timezone: 'Europe/Prague',
        },
        minOrderIntervalMinutes: 30,
        fieldErrors: {
          cron: 'Cron is invalid.',
        },
      },
    })

    expect(wrapper.get<HTMLInputElement>('input[aria-label="Enable scheduled DCA"]').element.checked).toBe(true)
    expect(wrapper.text()).toContain('Every day at 09:00 AM')
    expect(wrapper.text()).toContain('Europe/Prague')
    expect(wrapper.text()).toContain('2026-07-21T09:00:00.000+02:00')
    expect(wrapper.text()).toContain('Cron is invalid.')
  })

  it('emits preset, advanced cron, timezone, enabled, and safety interval changes', async () => {
    const wrapper = mount(ScheduleEditor, {
      props: {
        schedule: {
          enabled: true,
          cron: '0 9 * * *',
          timezone: 'UTC',
        },
        minOrderIntervalMinutes: 30,
        fieldErrors: {},
      },
    })

    await wrapper.get('select[aria-label="Schedule preset"]').setValue('every-15-minutes')
    expect(lastEmission(wrapper.emitted('update:schedule'))).toEqual([
      {
        enabled: true,
        cron: '*/15 * * * *',
        timezone: 'UTC',
      },
    ])

    await wrapper.get('button[aria-label="Use advanced cron"]').trigger('click')
    await wrapper.get('input[aria-label="Cron expression"]').setValue('0 */6 * * *')
    expect(lastEmission(wrapper.emitted('update:schedule'))).toEqual([
      {
        enabled: true,
        cron: '0 */6 * * *',
        timezone: 'UTC',
      },
    ])

    await wrapper.get('select[aria-label="Timezone"]').setValue('Europe/Prague')
    expect(lastEmission(wrapper.emitted('update:schedule'))).toEqual([
      {
        enabled: true,
        cron: '0 9 * * *',
        timezone: 'Europe/Prague',
      },
    ])

    await wrapper.get('input[aria-label="Enable scheduled DCA"]').setValue(false)
    expect(lastEmission(wrapper.emitted('update:schedule'))).toEqual([
      {
        enabled: false,
        cron: '0 9 * * *',
        timezone: 'UTC',
      },
    ])

    await wrapper.get('input[aria-label="Minimum order interval minutes"]').setValue(45)
    expect(lastEmission(wrapper.emitted('update:minOrderIntervalMinutes'))).toEqual([45])
  })

  it('warns when cron is more frequent than the minimum order interval', () => {
    const wrapper = mount(ScheduleEditor, {
      props: {
        schedule: {
          enabled: true,
          cron: '*/15 * * * *',
          timezone: 'UTC',
        },
        minOrderIntervalMinutes: 30,
        fieldErrors: {},
      },
    })

    expect(wrapper.text()).toContain('Runs more often than the 30 minute safety interval.')
  })
})

function lastEmission(events: unknown[][] | undefined): unknown[] | undefined {
  return events?.[events.length - 1]
}
