"""Schedule validation tests."""

import pytest

from krakendca.schedule import (
    HOUR_PRESET_VALUES,
    MINUTE_PRESET_VALUES,
    build_daily_cron,
    build_every_hours_cron,
    build_every_minutes_cron,
    build_monthly_cron,
    build_weekly_cron,
    next_run_times,
    normalize_cron_day_of_week,
    validate_schedule,
)


def test_validate_schedule_accepts_valid_five_field_cron() -> None:
    schedule = validate_schedule(
        {"enabled": True, "cron": "0 9 * * *", "timezone": "UTC"}
    )

    assert schedule == {
        "enabled": True,
        "cron": "0 9 * * *",
        "timezone": "UTC",
    }


@pytest.mark.parametrize(
    "cron",
    [
        "0 0 9 * * *",
        "0 0 9 * * * *",
        "0 9 ? * mon",
    ],
)
def test_validate_schedule_rejects_non_unix_cron(cron: str) -> None:
    with pytest.raises(ValueError):
        validate_schedule({"enabled": True, "cron": cron, "timezone": "UTC"})


def test_validate_schedule_rejects_enabled_schedule_without_cron() -> None:
    with pytest.raises(ValueError):
        validate_schedule({"enabled": True, "timezone": "UTC"})


def test_validate_schedule_rejects_invalid_timezone() -> None:
    with pytest.raises(ValueError):
        validate_schedule(
            {"enabled": True, "cron": "0 9 * * *", "timezone": "Mars/Base"}
        )


def test_validate_schedule_defaults_timezone_to_utc() -> None:
    schedule = validate_schedule({"enabled": True, "cron": "0 9 * * *"})

    assert schedule["timezone"] == "UTC"


@pytest.mark.parametrize(
    ("cron", "expected"),
    [
        ("0 9 * * 0", "0 9 * * sun"),
        ("0 9 * * 7", "0 9 * * sun"),
        ("0 9 * * 1", "0 9 * * mon"),
        ("0 9 * * 2", "0 9 * * tue"),
        ("0 9 * * 3", "0 9 * * wed"),
        ("0 9 * * 4", "0 9 * * thu"),
        ("0 9 * * 5", "0 9 * * fri"),
        ("0 9 * * 6", "0 9 * * sat"),
        ("0 9 * * 1,3,5", "0 9 * * mon,wed,fri"),
        ("0 9 * * 1-5", "0 9 * * mon-fri"),
    ],
)
def test_normalize_cron_day_of_week_numeric_tokens(
    cron: str, expected: str
) -> None:
    assert normalize_cron_day_of_week(cron) == expected


@pytest.mark.parametrize("day_name", ["sun", "mon", "tue", "wed", "thu", "fri", "sat"])
def test_normalize_cron_day_of_week_accepts_weekday_names(day_name: str) -> None:
    assert normalize_cron_day_of_week(f"0 9 * * {day_name.upper()}") == (
        f"0 9 * * {day_name}"
    )


def test_validate_schedule_treats_omitted_enabled_as_enabled() -> None:
    schedule = validate_schedule({"cron": "0 9 * * *", "timezone": "UTC"})

    assert schedule["enabled"] is True


def test_validate_schedule_allows_disabled_schedule_without_cron_or_timezone() -> None:
    schedule = validate_schedule({"enabled": False})

    assert schedule == {"enabled": False}


def test_validate_schedule_rejects_disabled_schedule_with_invalid_cron() -> None:
    with pytest.raises(ValueError):
        validate_schedule(
            {"enabled": False, "cron": "0 0 9 * * *", "timezone": "UTC"}
        )


@pytest.mark.parametrize("cron", ["", 0, []])
def test_validate_schedule_rejects_disabled_schedule_with_invalid_falsey_cron(
    cron: object,
) -> None:
    with pytest.raises(ValueError):
        validate_schedule({"enabled": False, "cron": cron, "timezone": "UTC"})


def test_validate_schedule_rejects_disabled_schedule_with_invalid_timezone() -> None:
    with pytest.raises(ValueError):
        validate_schedule(
            {"enabled": False, "cron": "0 9 * * *", "timezone": "Mars/Base"}
        )


@pytest.mark.parametrize("timezone", [None, "", 0, []])
def test_validate_schedule_rejects_disabled_schedule_with_invalid_falsey_timezone(
    timezone: object,
) -> None:
    with pytest.raises(ValueError):
        validate_schedule(
            {"enabled": False, "cron": "0 9 * * *", "timezone": timezone}
        )


def test_preset_values_are_exact() -> None:
    assert MINUTE_PRESET_VALUES == (5, 10, 15, 20, 30)
    assert HOUR_PRESET_VALUES == (1, 2, 3, 4, 6, 8, 12, 24)


@pytest.mark.parametrize("day", [29, 30, 31])
def test_build_monthly_cron_rejects_days_after_28(day: int) -> None:
    with pytest.raises(ValueError, match="day"):
        build_monthly_cron(day=day, hour=9, minute=0)


def test_cron_builder_helpers() -> None:
    assert build_daily_cron(9, 0) == "0 9 * * *"
    assert build_weekly_cron("mon", 9, 0) == "0 9 * * mon"
    assert build_monthly_cron(day=28, hour=9, minute=0) == "0 9 28 * *"
    assert build_every_minutes_cron(15) == "*/15 * * * *"
    assert build_every_hours_cron(6) == "0 */6 * * *"


def test_next_run_times_returns_prague_timezone_aware_iso_timestamps() -> None:
    runs = next_run_times(
        "0 9 * * *", "Europe/Prague", now="2026-07-21T06:00:00Z"
    )

    assert runs[0] == "2026-07-21T09:00:00+02:00"
    assert len(runs) == 3


def test_next_run_times_returns_utc_timezone_aware_iso_timestamps() -> None:
    runs = next_run_times("0 9 * * *", "UTC", now="2026-07-21T06:00:00Z")

    assert runs[0] == "2026-07-21T09:00:00+00:00"
    assert len(runs) == 3
