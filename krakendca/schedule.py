"""Cron schedule validation and preset helpers."""

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter


MINUTE_PRESET_VALUES = (5, 10, 15, 20, 30)
HOUR_PRESET_VALUES = (1, 2, 3, 4, 6, 8, 12, 24)

_DAY_NAMES = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")
_DAY_NUMBERS = {
    "0": "sun",
    "1": "mon",
    "2": "tue",
    "3": "wed",
    "4": "thu",
    "5": "fri",
    "6": "sat",
    "7": "sun",
}


def validate_schedule(schedule: dict) -> dict:
    """Validate a schedule dictionary and return normalized schedule values."""
    enabled = schedule.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be a boolean.")

    has_cron = "cron" in schedule
    has_timezone = "timezone" in schedule
    cron = schedule.get("cron")
    timezone = schedule.get("timezone")
    normalized = {"enabled": enabled}

    if enabled and not has_cron:
        raise ValueError("cron is required for enabled schedules.")

    if has_cron:
        normalized["cron"] = _validate_cron(cron)

    if enabled and not has_timezone:
        timezone = "UTC"
        has_timezone = True

    if has_timezone:
        normalized["timezone"] = _validate_timezone(timezone)

    return normalized


def normalize_cron_day_of_week(cron: str) -> str:
    """Normalize Unix numeric day-of-week cron tokens to lowercase names."""
    fields = _split_cron_fields(cron)
    fields[4] = _normalize_day_of_week_field(fields[4])
    return " ".join(fields)


def next_run_times(
    cron: str, timezone: str, count: int = 3, now: str | None = None
) -> list[str]:
    """Return the next run times for cron in the requested timezone."""
    normalized_cron = _validate_cron(cron)
    tz = ZoneInfo(_validate_timezone(timezone))
    base_time = _parse_now(now).astimezone(tz)
    iterator = croniter(normalized_cron, base_time)

    runs = []
    for _ in range(count):
        run = iterator.get_next(datetime)
        if run.tzinfo is None:
            run = run.replace(tzinfo=tz)
        runs.append(run.isoformat())
    return runs


def build_daily_cron(hour: int, minute: int) -> str:
    """Build a daily cron expression."""
    _validate_hour(hour)
    _validate_minute(minute)
    return f"{minute} {hour} * * *"


def build_weekly_cron(day_name: str, hour: int, minute: int) -> str:
    """Build a weekly cron expression."""
    normalized_day = _normalize_day_name(day_name)
    _validate_hour(hour)
    _validate_minute(minute)
    return f"{minute} {hour} * * {normalized_day}"


def build_monthly_cron(day: int, hour: int, minute: int) -> str:
    """Build a monthly cron expression for days 1 through 28."""
    if not isinstance(day, int) or not 1 <= day <= 28:
        raise ValueError("day must be an integer from 1 through 28.")
    _validate_hour(hour)
    _validate_minute(minute)
    return f"{minute} {hour} {day} * *"


def build_every_minutes_cron(minutes: int) -> str:
    """Build an every-N-minutes cron expression for supported presets."""
    if minutes not in MINUTE_PRESET_VALUES:
        raise ValueError("minutes must be one of the supported preset values.")
    return f"*/{minutes} * * * *"


def build_every_hours_cron(hours: int) -> str:
    """Build an every-N-hours cron expression for supported presets."""
    if hours not in HOUR_PRESET_VALUES:
        raise ValueError("hours must be one of the supported preset values.")
    return f"0 */{hours} * * *"


def _validate_cron(cron: str) -> str:
    if not isinstance(cron, str):
        raise ValueError("cron must be a string.")
    if "?" in cron:
        raise ValueError("cron must use standard five-field Unix format.")

    normalized = normalize_cron_day_of_week(cron)
    if not croniter.is_valid(normalized):
        raise ValueError("cron must be a valid five-field Unix expression.")
    return normalized


def _split_cron_fields(cron: str) -> list[str]:
    fields = cron.split()
    if len(fields) != 5:
        raise ValueError("cron must use exactly five fields.")
    return fields


def _validate_timezone(timezone: str) -> str:
    if not isinstance(timezone, str):
        raise ValueError("timezone must be an IANA timezone name.")
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("timezone must be a valid IANA timezone name.") from exc
    return timezone


def _normalize_day_of_week_field(day_of_week: str) -> str:
    return ",".join(
        _normalize_day_of_week_part(part)
        for part in day_of_week.lower().split(",")
    )


def _normalize_day_of_week_part(part: str) -> str:
    if "/" in part:
        base, step = part.split("/", 1)
        if not step.isdigit():
            raise ValueError("cron day of week step must be numeric.")
        if _is_numeric_sunday_alias_range(base):
            raise ValueError(
                "cron day of week step is not supported for Sunday alias ranges."
            )
        return f"{_normalize_day_of_week_part(base)}/{step}"

    if "-" in part:
        start, end = part.split("-", 1)
        if _is_numeric_sunday_alias_range(part):
            return ",".join(_expand_numeric_day_range(start, end))
        return (
            f"{_normalize_day_of_week_token(start)}-"
            f"{_normalize_day_of_week_token(end)}"
        )

    return _normalize_day_of_week_token(part)


def _normalize_day_of_week_token(token: str) -> str:
    if token == "*":
        return token
    if token in _DAY_NUMBERS:
        return _DAY_NUMBERS[token]
    return _normalize_day_name(token)


def _is_numeric_sunday_alias_range(part: str) -> bool:
    if "-" not in part:
        return False
    start, end = part.split("-", 1)
    return start.isdigit() and end.isdigit() and (start == "0" or end == "7")


def _expand_numeric_day_range(start: str, end: str) -> list[str]:
    day_numbers = list(range(int(start), int(end) + 1))
    day_names = []
    for day_number in day_numbers:
        day_name = _DAY_NUMBERS[str(day_number)]
        if day_name not in day_names:
            day_names.append(day_name)
    return day_names


def _normalize_day_name(day_name: str) -> str:
    if not isinstance(day_name, str):
        raise ValueError("day_name must be a weekday name.")
    normalized = day_name.lower()
    if normalized not in _DAY_NAMES:
        raise ValueError("day_name must be one of sun, mon, tue, wed, thu, fri, sat.")
    return normalized


def _validate_hour(hour: int) -> None:
    if not isinstance(hour, int) or not 0 <= hour <= 23:
        raise ValueError("hour must be an integer from 0 through 23.")


def _validate_minute(minute: int) -> None:
    if not isinstance(minute, int) or not 0 <= minute <= 59:
        raise ValueError("minute must be an integer from 0 through 59.")


def _parse_now(now: str | None) -> datetime:
    if now is None:
        return datetime.now(tz=ZoneInfo("UTC"))

    value = now
    if value.endswith("Z"):
        value = f"{value[:-1]}+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ZoneInfo("UTC"))
    return parsed
