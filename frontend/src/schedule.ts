import { CronExpressionParser } from 'cron-parser'
import cronstrue from 'cronstrue'

export const MINUTE_PRESET_VALUES = [5, 10, 15, 20, 30] as const
export const HOUR_PRESET_VALUES = [1, 2, 3, 4, 6, 8, 12, 24] as const

const WEEKDAY_NAMES = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'] as const

export function buildDailyCron(hour: number, minute: number): string {
  assertHour(hour)
  assertMinute(minute)
  return `${minute} ${hour} * * *`
}

export function buildWeeklyCron(
  dayName: string,
  hour: number,
  minute: number,
): string {
  assertHour(hour)
  assertMinute(minute)
  const normalizedDay = dayName.toLowerCase()
  if (!isWeekdayName(normalizedDay)) {
    throw new Error('Unsupported weekday.')
  }
  return `${minute} ${hour} * * ${normalizedDay}`
}

export function buildMonthlyCron(day: number, hour: number, minute: number): string {
  assertHour(hour)
  assertMinute(minute)
  if (!Number.isInteger(day) || day < 1 || day > 28) {
    throw new Error('Monthly schedules support days 1 through 28.')
  }
  return `${minute} ${hour} ${day} * *`
}

export function buildEveryMinutesCron(minutes: number): string {
  if (!includesNumber(MINUTE_PRESET_VALUES, minutes)) {
    throw new Error('Unsupported minute preset.')
  }
  return `*/${minutes} * * * *`
}

export function buildEveryHoursCron(hours: number): string {
  if (!includesNumber(HOUR_PRESET_VALUES, hours)) {
    throw new Error('Unsupported hour preset.')
  }
  return `0 */${hours} * * *`
}

export function validateCron(cron: string): string | null {
  const fields = cron.trim().split(/\s+/).filter(Boolean)
  if (fields.length !== 5) {
    return 'Cron expression must have exactly five fields.'
  }
  if (fields.some((field) => field.includes('?'))) {
    return 'Cron expression must use Unix cron syntax.'
  }

  try {
    CronExpressionParser.parse(cron)
  } catch (error) {
    return error instanceof Error ? error.message : 'Invalid cron expression.'
  }
  return null
}

export function describeCron(cron: string): string {
  const validationError = validateCron(cron)
  if (validationError !== null) {
    throw new Error(validationError)
  }
  return cronstrue.toString(cron, {
    throwExceptionOnParseError: true,
  })
}

export function previewNextRuns(
  cron: string,
  timezone: string,
  count = 3,
  now?: string,
): string[] {
  const validationError = validateCron(cron)
  if (validationError !== null) {
    throw new Error(validationError)
  }
  const interval = CronExpressionParser.parse(cron, {
    currentDate: now,
    tz: timezone,
  })
  return interval.take(count).map((date) => {
    const serialized = date.toJSON()
    if (serialized === null) {
      throw new Error('Could not serialize next run time.')
    }
    return serialized
  })
}

export function cronRunsMoreFrequentlyThan(
  cron: string,
  timezone: string,
  minIntervalMinutes: number,
): boolean {
  if (minIntervalMinutes <= 0) {
    return false
  }
  const [first, second] = previewNextRuns(cron, timezone, 2)
  if (first === undefined || second === undefined) {
    return false
  }
  const deltaMinutes = (Date.parse(second) - Date.parse(first)) / 60_000
  return deltaMinutes < minIntervalMinutes
}

function assertHour(hour: number): void {
  if (!Number.isInteger(hour) || hour < 0 || hour > 23) {
    throw new Error('Hour must be between 0 and 23.')
  }
}

function assertMinute(minute: number): void {
  if (!Number.isInteger(minute) || minute < 0 || minute > 59) {
    throw new Error('Minute must be between 0 and 59.')
  }
}

function includesNumber(values: readonly number[], value: number): boolean {
  return values.includes(value)
}

function isWeekdayName(value: string): value is typeof WEEKDAY_NAMES[number] {
  return WEEKDAY_NAMES.some((weekday) => weekday === value)
}
