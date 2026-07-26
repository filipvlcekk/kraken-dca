import { describe, expect, it } from 'vitest'

import {
  HOUR_PRESET_VALUES,
  MINUTE_PRESET_VALUES,
  buildDailyCron,
  buildEveryHoursCron,
  buildEveryMinutesCron,
  buildMonthlyCron,
  buildWeeklyCron,
  cronRunsMoreFrequentlyThan,
  describeCron,
  previewNextRuns,
  validateCron,
} from '../schedule'

describe('schedule helpers', () => {
  it('exposes the backend-supported preset values', () => {
    expect(MINUTE_PRESET_VALUES).toEqual([5, 10, 15, 20, 30])
    expect(HOUR_PRESET_VALUES).toEqual([1, 2, 3, 4, 6, 8, 12, 24])
  })

  it('builds cron expressions for supported presets', () => {
    expect(buildDailyCron(9, 0)).toBe('0 9 * * *')
    expect(buildWeeklyCron('MON', 9, 0)).toBe('0 9 * * mon')
    expect(buildEveryMinutesCron(15)).toBe('*/15 * * * *')
    expect(buildEveryHoursCron(6)).toBe('0 */6 * * *')
    expect(buildMonthlyCron(28, 9, 0)).toBe('0 9 28 * *')
  })

  it('rejects unsupported preset values and non-Unix cron syntax', () => {
    expect(() => buildMonthlyCron(29, 9, 0)).toThrow('Monthly schedules support days 1 through 28.')
    expect(() => buildEveryMinutesCron(7)).toThrow('Unsupported minute preset.')
    expect(() => buildEveryHoursCron(5)).toThrow('Unsupported hour preset.')
    expect(validateCron('0 0 9 * * *')).toBe('Cron expression must have exactly five fields.')
    expect(validateCron('0 9 ? * mon')).toBe('Cron expression must use Unix cron syntax.')
    expect(validateCron('0 9 * * mon')).toBeNull()
  })

  it('renders a human-readable schedule summary', () => {
    expect(describeCron('0 9 * * mon').toLowerCase()).toContain('monday')
  })

  it('renders timezone-aware next-run previews', () => {
    const pragueRuns = previewNextRuns(
      '0 9 * * *',
      'Europe/Prague',
      3,
      '2026-07-21T06:00:00Z',
    )
    const utcRuns = previewNextRuns(
      '0 9 * * *',
      'UTC',
      3,
      '2026-07-21T06:00:00Z',
    )

    expect(pragueRuns).toHaveLength(3)
    expect(pragueRuns[0]).toBe('2026-07-21T09:00:00.000+02:00')
    expect(utcRuns[0]).toBe('2026-07-21T09:00:00.000Z')
    expect(pragueRuns[0]).not.toBe(utcRuns[0])
  })

  it('detects cron schedules more frequent than the configured safety interval', () => {
    expect(cronRunsMoreFrequentlyThan('*/15 * * * *', 'UTC', 30)).toBe(true)
    expect(cronRunsMoreFrequentlyThan('0 */6 * * *', 'UTC', 30)).toBe(false)
    expect(cronRunsMoreFrequentlyThan('*/15 * * * *', 'UTC', 0)).toBe(false)
  })
})
