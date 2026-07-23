"""Shared config store tests."""

from datetime import datetime, timezone

import pytest
import yaml

from krakendca.config_store import (
    REDACTED_SECRET,
    ConfigValidationError,
    fingerprint_config,
    get_cli_dca_pairs,
    load_config,
    merge_redacted_config,
    redact_config,
    save_config,
    validate_config,
)


def valid_config() -> dict:
    return {
        "api": {
            "public_key": "FILE_PUBLIC_KEY",
            "private_key": "FILE_PRIVATE_KEY",
        },
        "dca_pairs": [
            {
                "pair": "XETHZEUR",
                "delay": 1,
                "amount": 15,
            }
        ],
    }


def test_loads_legacy_delay_config() -> None:
    config = validate_config(load_config("config-sample.yaml"))

    assert config["api"]["public_key"] == "KRAKEN_API_PUBLIC_KEY"
    assert config["api"]["private_key"] == "KRAKEN_API_PRIVATE_KEY"
    assert len(config["dca_pairs"]) == 2
    assert config["dca_pairs"][0]["delay"] == 1
    assert config["dca_pairs"][0]["amount"] == 15.0


def test_loads_schedule_config_fixture() -> None:
    config = validate_config(load_config("tests/fixtures/config_schedule.yaml"))

    assert config["dca_pairs"][0]["schedule"] == {
        "enabled": True,
        "cron": "0 9 * * *",
        "timezone": "Europe/Prague",
    }
    assert config["dca_pairs"][0]["min_order_interval_minutes"] == 30
    assert config["dca_pairs"][1]["schedule"] == {"enabled": False}


def test_rejects_duplicate_pair_names() -> None:
    config = valid_config()
    config["dca_pairs"].append(
        {"pair": "XETHZEUR", "delay": 3, "amount": 20}
    )

    with pytest.raises(ConfigValidationError) as exc_info:
        validate_config(config)

    assert "Duplicate DCA pair specified." in str(exc_info.value)
    assert exc_info.value.fields == {
        "dca_pairs.1.pair": "Duplicate DCA pair specified."
    }


def test_rejects_invalid_cron_with_field_path() -> None:
    config = valid_config()
    config["dca_pairs"][0].pop("delay")
    config["dca_pairs"][0]["schedule"] = {
        "enabled": True,
        "cron": "not cron",
        "timezone": "UTC",
    }

    with pytest.raises(ConfigValidationError) as exc_info:
        validate_config(config)

    assert "cron must use exactly five fields." in str(exc_info.value)
    assert exc_info.value.fields == {
        "dca_pairs.0.schedule.cron": "cron must use exactly five fields."
    }


def test_disabled_schedule_takes_precedence_over_delay() -> None:
    config = valid_config()
    config["dca_pairs"][0]["schedule"] = {"enabled": False}

    normalized = validate_config(config)

    assert normalized["dca_pairs"][0]["delay"] == 1
    assert normalized["dca_pairs"][0]["schedule"] == {"enabled": False}
    assert get_cli_dca_pairs(normalized) == []


def test_disabled_schedule_accepts_invalid_legacy_delay_as_metadata() -> None:
    config = valid_config()
    config["dca_pairs"][0]["delay"] = "bad"
    config["dca_pairs"][0]["schedule"] = {"enabled": False}

    normalized = validate_config(config)

    assert normalized["dca_pairs"][0]["delay"] == "bad"
    assert normalized["dca_pairs"][0]["schedule"] == {"enabled": False}
    assert get_cli_dca_pairs(normalized) == []


def test_enabled_schedule_accepts_invalid_legacy_delay_as_metadata() -> None:
    config = valid_config()
    config["dca_pairs"][0]["delay"] = "bad"
    config["dca_pairs"][0]["schedule"] = {
        "enabled": True,
        "cron": "0 9 * * *",
        "timezone": "UTC",
    }

    normalized = validate_config(config)

    assert normalized["dca_pairs"][0]["delay"] == "bad"
    assert normalized["dca_pairs"][0]["schedule"] == {
        "enabled": True,
        "cron": "0 9 * * *",
        "timezone": "UTC",
    }
    with pytest.raises(ConfigValidationError) as exc_info:
        get_cli_dca_pairs(normalized)
    assert "Cron schedules require web mode." in str(exc_info.value)


@pytest.mark.parametrize("minutes", [0, 525600])
def test_min_order_interval_accepts_bounds(minutes: int) -> None:
    config = valid_config()
    config["dca_pairs"][0]["min_order_interval_minutes"] = minutes

    normalized = validate_config(config)

    assert normalized["dca_pairs"][0]["min_order_interval_minutes"] == minutes


@pytest.mark.parametrize("minutes", [-1, 1.5, "30", 525601])
def test_min_order_interval_rejects_invalid_values(minutes: object) -> None:
    config = valid_config()
    config["dca_pairs"][0]["min_order_interval_minutes"] = minutes

    with pytest.raises(ConfigValidationError) as exc_info:
        validate_config(config)

    assert exc_info.value.fields == {
        "dca_pairs.0.min_order_interval_minutes": (
            "min_order_interval_minutes must be an integer from 0 through "
            "525600."
        )
    }


def test_min_order_interval_defaults_to_30() -> None:
    config = validate_config(valid_config())

    assert config["dca_pairs"][0]["min_order_interval_minutes"] == 30


def test_redacts_file_credentials_and_returns_secret_metadata() -> None:
    result = redact_config(validate_config(valid_config()))

    assert result["config"]["api"] == {
        "public_key": REDACTED_SECRET,
        "private_key": REDACTED_SECRET,
    }
    assert result["secrets"] == {
        "public_key": {"configured": True, "source": "file"},
        "private_key": {"configured": True, "source": "file"},
    }


def test_preserves_redacted_credentials_on_save(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(valid_config()), encoding="utf-8")
    submitted = redact_config(load_config(str(path)))["config"]
    submitted["dca_pairs"][0]["amount"] = 25

    save_config(str(path), submitted)
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert saved["api"]["public_key"] == "FILE_PUBLIC_KEY"
    assert saved["api"]["private_key"] == "FILE_PRIVATE_KEY"
    assert saved["dca_pairs"][0]["amount"] == 25.0
    assert REDACTED_SECRET not in path.read_text(encoding="utf-8")


def test_replaces_redacted_credentials_when_new_strings_are_submitted(
    tmp_path,
) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(valid_config()), encoding="utf-8")
    submitted = redact_config(load_config(str(path)))["config"]
    submitted["api"]["public_key"] = "NEW_PUBLIC_KEY"
    submitted["api"]["private_key"] = "NEW_PRIVATE_KEY"

    save_config(str(path), submitted)
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert saved["api"]["public_key"] == "NEW_PUBLIC_KEY"
    assert saved["api"]["private_key"] == "NEW_PRIVATE_KEY"


def test_partial_submission_preserves_omitted_existing_file_credentials() -> None:
    existing = valid_config()
    submitted = {
        "api": {"public_key": "NEW_PUBLIC_KEY"},
        "dca_pairs": existing["dca_pairs"],
    }

    merged = merge_redacted_config(submitted, existing)

    assert merged["api"]["public_key"] == "NEW_PUBLIC_KEY"
    assert merged["api"]["private_key"] == "FILE_PRIVATE_KEY"


def test_partial_save_preserves_omitted_existing_file_credentials(
    tmp_path,
) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(valid_config()), encoding="utf-8")
    submitted = {
        "api": {"public_key": "NEW_PUBLIC_KEY"},
        "dca_pairs": valid_config()["dca_pairs"],
    }

    save_config(
        str(path),
        submitted,
        {"KRAKEN_API_PRIVATE_KEY": "ENV_PRIVATE_KEY"},
    )
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert saved["api"]["public_key"] == "NEW_PUBLIC_KEY"
    assert saved["api"]["private_key"] == "FILE_PRIVATE_KEY"


def test_env_secret_metadata_shape() -> None:
    config = {
        "dca_pairs": [{"pair": "XETHZEUR", "delay": 1, "amount": 15}]
    }

    result = redact_config(
        validate_config(
            config,
            {
                "KRAKEN_API_PUBLIC_KEY": "ENV_PUBLIC",
                "KRAKEN_API_PRIVATE_KEY": "ENV_PRIVATE",
            },
        ),
        {
            "KRAKEN_API_PUBLIC_KEY": "ENV_PUBLIC",
            "KRAKEN_API_PRIVATE_KEY": "ENV_PRIVATE",
        },
    )

    assert result["config"]["api"] == {
        "public_key": None,
        "private_key": None,
    }
    assert result["secrets"] == {
        "public_key": {"configured": True, "source": "env"},
        "private_key": {"configured": True, "source": "env"},
    }


def test_null_credentials_are_omitted_on_save_and_may_use_env(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(valid_config()), encoding="utf-8")
    submitted = valid_config()
    submitted["api"] = {"public_key": None, "private_key": None}

    save_config(
        str(path),
        submitted,
        {
            "KRAKEN_API_PUBLIC_KEY": "ENV_PUBLIC",
            "KRAKEN_API_PRIVATE_KEY": "ENV_PRIVATE",
        },
    )
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert "api" not in saved or saved["api"] == {}
    assert validate_config(
        saved,
        {
            "KRAKEN_API_PUBLIC_KEY": "ENV_PUBLIC",
            "KRAKEN_API_PRIVATE_KEY": "ENV_PRIVATE",
        },
    )


def test_explicit_null_credential_omits_that_key_when_env_exists(
    tmp_path,
) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(valid_config()), encoding="utf-8")
    submitted = {
        "api": {"public_key": None},
        "dca_pairs": valid_config()["dca_pairs"],
    }

    save_config(
        str(path),
        submitted,
        {"KRAKEN_API_PUBLIC_KEY": "ENV_PUBLIC"},
    )
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert "public_key" not in saved["api"]
    assert saved["api"]["private_key"] == "FILE_PRIVATE_KEY"


def test_atomic_save_creates_timestamped_backup(tmp_path, monkeypatch) -> None:
    import krakendca.config_store as config_store

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(config_store, "datetime", FrozenDatetime)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(valid_config()), encoding="utf-8")

    save_config(str(path), valid_config())

    assert (tmp_path / "config.yaml.bak.20260721T120000Z").exists()


def test_backup_retention_keeps_only_10_newest(tmp_path, monkeypatch) -> None:
    import krakendca.config_store as config_store

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(config_store, "datetime", FrozenDatetime)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(valid_config()), encoding="utf-8")
    for day in range(1, 13):
        (tmp_path / f"config.yaml.bak.202607{day:02d}T120000Z").write_text(
            "backup",
            encoding="utf-8",
        )

    save_config(str(path), valid_config())

    backups = sorted(tmp_path.glob("config.yaml.bak.*"))
    assert len(backups) == 10
    assert [backup.name for backup in backups] == [
        "config.yaml.bak.20260704T120000Z",
        "config.yaml.bak.20260705T120000Z",
        "config.yaml.bak.20260706T120000Z",
        "config.yaml.bak.20260707T120000Z",
        "config.yaml.bak.20260708T120000Z",
        "config.yaml.bak.20260709T120000Z",
        "config.yaml.bak.20260710T120000Z",
        "config.yaml.bak.20260711T120000Z",
        "config.yaml.bak.20260712T120000Z",
        "config.yaml.bak.20260721T120000Z",
    ]


def test_fingerprint_redacts_secret_values() -> None:
    config_one = valid_config()
    config_two = valid_config()
    config_two["api"] = {
        "public_key": "DIFFERENT_PUBLIC",
        "private_key": "DIFFERENT_PRIVATE",
    }

    assert fingerprint_config(config_one) == fingerprint_config(config_two)


def test_fingerprint_uses_canonical_normalized_defaults() -> None:
    implicit = valid_config()
    explicit = valid_config()
    explicit["dca_pairs"][0]["min_order_interval_minutes"] = 30

    assert fingerprint_config(implicit) == fingerprint_config(explicit)


def test_fingerprint_includes_credential_source_and_presence() -> None:
    env = {
        "KRAKEN_API_PUBLIC_KEY": "ENV_PUBLIC",
        "KRAKEN_API_PRIVATE_KEY": "ENV_PRIVATE",
    }
    file_config = valid_config()
    env_config = valid_config()
    env_config.pop("api")

    assert fingerprint_config(file_config, env) != fingerprint_config(
        env_config, env
    )


def test_fingerprint_does_not_change_when_only_secret_values_change() -> None:
    config_one = valid_config()
    config_two = valid_config()
    config_two["api"] = {
        "public_key": "ROTATED_PUBLIC",
        "private_key": "ROTATED_PRIVATE",
    }

    assert fingerprint_config(config_one) == fingerprint_config(config_two)


def test_empty_string_credentials_are_invalid() -> None:
    config = valid_config()
    config["api"]["public_key"] = ""

    with pytest.raises(ConfigValidationError) as exc_info:
        validate_config(
            config,
            {
                "KRAKEN_API_PUBLIC_KEY": "ENV_PUBLIC",
                "KRAKEN_API_PRIVATE_KEY": "ENV_PRIVATE",
            },
        )

    assert exc_info.value.fields == {
        "api.public_key": "Please provide your Kraken API public key."
    }


def test_redact_config_redacts_credentials_without_validating_pairs() -> None:
    config = valid_config()
    config["dca_pairs"][0]["delay"] = "bad"
    config["dca_pairs"][0].pop("amount")

    result = redact_config(config)

    assert result["config"]["api"] == {
        "public_key": REDACTED_SECRET,
        "private_key": REDACTED_SECRET,
    }
    assert result["config"]["dca_pairs"] == config["dca_pairs"]
    assert result["secrets"] == {
        "public_key": {"configured": True, "source": "file"},
        "private_key": {"configured": True, "source": "file"},
    }


def test_redact_config_does_not_leak_empty_string_credentials() -> None:
    config = valid_config()
    config["api"]["public_key"] = ""

    result = redact_config(config)

    assert result["config"]["api"]["public_key"] is None
    assert result["config"]["api"]["private_key"] == REDACTED_SECRET
    assert result["secrets"]["public_key"] == {
        "configured": False,
        "source": None,
    }
    assert result["secrets"]["private_key"] == {
        "configured": True,
        "source": "file",
    }

    with pytest.raises(ConfigValidationError):
        validate_config(config)


def test_merge_redacted_config_preserves_replaces_and_omits_credentials() -> None:
    existing = valid_config()
    submitted = valid_config()
    submitted["api"] = {
        "public_key": REDACTED_SECRET,
        "private_key": "NEW_PRIVATE",
    }

    merged = merge_redacted_config(submitted, existing)

    assert merged["api"]["public_key"] == "FILE_PUBLIC_KEY"
    assert merged["api"]["private_key"] == "NEW_PRIVATE"

    submitted["api"] = {"public_key": None}
    merged = merge_redacted_config(submitted, existing)

    assert "public_key" not in merged.get("api", {})
    assert merged["api"]["private_key"] == "FILE_PRIVATE_KEY"
