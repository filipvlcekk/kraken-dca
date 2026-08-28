"""Shared configuration loading, validation, and persistence helpers."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from krakendca.schedule import validate_schedule

REDACTED_SECRET = "__KRADCA_SECRET_REDACTED__"

_PUBLIC_ENV_VAR = "KRAKEN_API_PUBLIC_KEY"
_PRIVATE_ENV_VAR = "KRAKEN_API_PRIVATE_KEY"
_MIN_ORDER_INTERVAL_DEFAULT = 30
_MIN_ORDER_INTERVAL_MAX = 525600
_CLI_SCHEDULE_ERROR = "Cron schedules require web mode."
_ORDERS_FILEPATH_ERROR = (
    "orders_filepath must be a relative CSV filename without directories."
)


class ConfigValidationError(ValueError):
    """Configuration validation error with field-path details."""

    def __init__(self, message: str, fields: dict[str, str]) -> None:
        super().__init__(message)
        self.fields = fields


def load_config(path: str) -> dict:
    """Load YAML config from path, returning an empty dict for empty YAML."""
    try:
        with open(path, "r", encoding="utf-8") as stream:
            return yaml.load(stream, Loader=yaml.SafeLoader) or {}
    except UnicodeDecodeError as exc:
        raise yaml.YAMLError("Config YAML is malformed.") from exc


def validate_config(config: dict, env: dict | None = None) -> dict:
    """Validate config and return a normalized copy with defaults applied."""
    env_values = _env(env)
    source = config or {}
    normalized: dict = {}
    fields: dict[str, str] = {}

    api = source.get("api") or {}
    if not isinstance(api, dict):
        api = {}
    normalized["api"] = _validate_api(api, env_values, fields)
    if "orders_filepath" in source:
        _validate_orders_filepath(
            source.get("orders_filepath"),
            "orders_filepath",
            normalized,
            fields,
        )

    dca_pairs = source.get("dca_pairs")
    if not dca_pairs or type(dca_pairs) is not list:
        fields["dca_pairs"] = "No DCA pairs specified."
        _raise_first(fields)

    normalized_pairs = []
    seen_pairs = set()
    for index, dca_pair in enumerate(dca_pairs):
        normalized_pair = _validate_pair(
            dca_pair,
            index,
            seen_pairs,
            fields,
        )
        normalized_pairs.append(normalized_pair)
    normalized["dca_pairs"] = normalized_pairs

    if fields:
        _raise_first(fields)
    return normalized


def redact_config(config: dict, env: dict | None = None) -> dict:
    """Return a redacted config plus secret metadata for API responses."""
    env_values = _env(env)
    source = config or {}
    redacted = copy.deepcopy(source)
    redacted_api = {}
    secrets = {}
    api = source.get("api") or {}
    if not isinstance(api, dict):
        api = {}

    for key, env_var in (
        ("public_key", _PUBLIC_ENV_VAR),
        ("private_key", _PRIVATE_ENV_VAR),
    ):
        file_value = api.get(key)
        if isinstance(file_value, str) and file_value:
            redacted_api[key] = REDACTED_SECRET
            secrets[key] = {"configured": True, "source": "file"}
        elif file_value == "":
            redacted_api[key] = None
            secrets[key] = {"configured": False, "source": None}
        elif env_values.get(env_var):
            redacted_api[key] = None
            secrets[key] = {"configured": True, "source": "env"}
        else:
            redacted_api[key] = None
            secrets[key] = {"configured": False, "source": None}

    redacted["api"] = redacted_api
    return {"config": redacted, "secrets": secrets}


def merge_redacted_config(
    submitted: dict,
    existing: dict,
    env: dict | None = None,
) -> dict:
    """Merge submitted config with existing file secrets for redacted values."""
    del env
    merged = copy.deepcopy(submitted or {})
    submitted_api = (submitted or {}).get("api") or {}
    existing_api = (existing or {}).get("api") or {}

    api: dict = {}
    for key in ("public_key", "private_key"):
        if key not in submitted_api:
            existing_value = existing_api.get(key)
            if existing_value is not None:
                api[key] = existing_value
            continue

        value = submitted_api.get(key)
        if value == REDACTED_SECRET:
            existing_value = existing_api.get(key)
            if existing_value is not None:
                api[key] = existing_value
        elif value is None:
            continue
        else:
            api[key] = value

    if api:
        merged["api"] = api
    else:
        merged.pop("api", None)
    return merged


def save_config(path: str, submitted: dict, env: dict | None = None) -> dict:
    """Merge, validate, and atomically save config YAML with backup retention."""
    config_path = Path(path)
    existing = load_config(path) if config_path.exists() else {}
    merged = merge_redacted_config(submitted, existing, env)
    normalized = validate_config(merged, env)
    writable_config = _config_for_yaml(normalized)

    config_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            delete=False,
            dir=str(config_path.parent),
            encoding="utf-8",
        ) as temp_file:
            temp_path = temp_file.name
            yaml.safe_dump(writable_config, temp_file, sort_keys=False)

        if config_path.exists():
            backup_path = _backup_path(config_path)
            shutil.copy2(config_path, backup_path)
            _prune_backups(config_path)

        try:
            os.replace(temp_path, config_path)
        except OSError:
            if not config_path.exists():
                raise
            _write_config_in_place(config_path, temp_path)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

    return normalized


def fingerprint_config(config: dict, env: dict | None = None) -> str:
    """Return a stable fingerprint for normalized config and secret metadata."""
    redacted = redact_config(validate_config(config, env), env)
    canonical = json.dumps(redacted, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _write_config_in_place(config_path: Path, temp_path: str) -> None:
    with open(temp_path, "r", encoding="utf-8") as source:
        with config_path.open("w", encoding="utf-8") as target:
            shutil.copyfileobj(source, target)


def get_cli_dca_pairs(config: dict) -> list[dict]:
    """Return pairs executable by the legacy CLI path."""
    cli_pairs = []
    for index, dca_pair in enumerate(config.get("dca_pairs") or []):
        schedule = dca_pair.get("schedule")
        if schedule is not None:
            if schedule.get("enabled", True):
                raise ConfigValidationError(
                    _CLI_SCHEDULE_ERROR,
                    {f"dca_pairs.{index}.schedule": _CLI_SCHEDULE_ERROR},
                )
            continue
        cli_pairs.append(dca_pair)
    return cli_pairs


def _validate_api(
    api: dict,
    env_values: dict,
    fields: dict[str, str],
) -> dict:
    normalized_api = {
        "public_key": api.get("public_key"),
        "private_key": api.get("private_key"),
    }

    _validate_api_key(
        "public_key",
        _PUBLIC_ENV_VAR,
        "Please provide your Kraken API public key.",
        api,
        env_values,
        fields,
    )
    _validate_api_key(
        "private_key",
        _PRIVATE_ENV_VAR,
        "Please provide your Kraken API private key.",
        api,
        env_values,
        fields,
    )
    return normalized_api


def _validate_api_key(
    key: str,
    env_var: str,
    message: str,
    api: dict,
    env_values: dict,
    fields: dict[str, str],
) -> None:
    file_value = api.get(key)
    if file_value == "":
        fields[f"api.{key}"] = message
        return
    if file_value is None and not env_values.get(env_var):
        fields[f"api.{key}"] = message


def _validate_pair(
    dca_pair: object,
    index: int,
    seen_pairs: set,
    fields: dict[str, str],
) -> dict:
    if not isinstance(dca_pair, dict):
        fields[f"dca_pairs.{index}.pair"] = (
            "Please provide the pair to dollar cost average."
        )
        return {}

    normalized_pair: dict = {}
    pair_name = dca_pair.get("pair")
    if pair_name is None or pair_name == "":
        fields[f"dca_pairs.{index}.pair"] = (
            "Please provide the pair to dollar cost average."
        )
    elif not isinstance(pair_name, str):
        fields[f"dca_pairs.{index}.pair"] = "Pair must be a non-empty string."
    elif pair_name in seen_pairs:
        fields[f"dca_pairs.{index}.pair"] = "Duplicate DCA pair specified."
    else:
        seen_pairs.add(pair_name)
        normalized_pair["pair"] = pair_name

    if "schedule" in dca_pair:
        if "delay" in dca_pair:
            normalized_pair["delay"] = dca_pair.get("delay")
        _validate_pair_schedule(
            dca_pair.get("schedule"),
            index,
            normalized_pair,
            fields,
        )
    elif "delay" in dca_pair:
        _validate_delay(dca_pair.get("delay"), index, normalized_pair, fields)
    else:
        fields[f"dca_pairs.{index}.delay"] = (
            "Please set the DCA days delay as a number > 0."
        )

    _validate_amount(dca_pair, index, normalized_pair, fields)
    _validate_min_order_interval(dca_pair, index, normalized_pair, fields)
    _validate_limit_factor(dca_pair, index, normalized_pair, fields)
    _validate_max_price(dca_pair, index, normalized_pair, fields)
    _validate_ignore_differing_orders(dca_pair, index, normalized_pair, fields)
    if "orders_filepath" in dca_pair:
        _validate_orders_filepath(
            dca_pair.get("orders_filepath"),
            f"dca_pairs.{index}.orders_filepath",
            normalized_pair,
            fields,
        )
    return normalized_pair


def _validate_delay(
    delay: object,
    index: int,
    normalized_pair: dict,
    fields: dict[str, str],
) -> None:
    if not delay or type(delay) is not int or delay <= 0:
        fields[f"dca_pairs.{index}.delay"] = (
            "Please set the DCA days delay as a number > 0."
        )
        return
    normalized_pair["delay"] = delay


def _validate_pair_schedule(
    schedule: object,
    index: int,
    normalized_pair: dict,
    fields: dict[str, str],
) -> None:
    if not isinstance(schedule, dict):
        fields[f"dca_pairs.{index}.schedule"] = "schedule must be a mapping."
        return

    try:
        normalized_pair["schedule"] = validate_schedule(schedule)
    except ValueError as exc:
        message = str(exc)
        field = "schedule"
        if message.startswith("cron "):
            field = "schedule.cron"
        elif message.startswith("timezone "):
            field = "schedule.timezone"
        elif message.startswith("enabled "):
            field = "schedule.enabled"
        fields[f"dca_pairs.{index}.{field}"] = message


def _validate_amount(
    dca_pair: dict,
    index: int,
    normalized_pair: dict,
    fields: dict[str, str],
) -> None:
    try:
        amount = float(dca_pair.get("amount"))
    except (TypeError, ValueError):
        fields[f"dca_pairs.{index}.amount"] = (
            "Please provide an amount > 0 to DCA."
        )
        return

    if not amount or type(amount) is not float or amount <= 0:
        fields[f"dca_pairs.{index}.amount"] = (
            "Please provide an amount > 0 to DCA."
        )
        return
    normalized_pair["amount"] = amount


def _validate_min_order_interval(
    dca_pair: dict,
    index: int,
    normalized_pair: dict,
    fields: dict[str, str],
) -> None:
    minutes = dca_pair.get(
        "min_order_interval_minutes",
        _MIN_ORDER_INTERVAL_DEFAULT,
    )
    if (
        type(minutes) is not int
        or minutes < 0
        or minutes > _MIN_ORDER_INTERVAL_MAX
    ):
        fields[f"dca_pairs.{index}.min_order_interval_minutes"] = (
            "min_order_interval_minutes must be an integer from 0 through "
            "525600."
        )
        return
    normalized_pair["min_order_interval_minutes"] = minutes


def _validate_limit_factor(
    dca_pair: dict,
    index: int,
    normalized_pair: dict,
    fields: dict[str, str],
) -> None:
    if dca_pair.get("limit_factor"):
        try:
            limit_factor = float(dca_pair.get("limit_factor"))
            if len(str(limit_factor).split(".")[1]) > 5:
                raise ValueError
            normalized_pair["limit_factor"] = limit_factor
        except (IndexError, TypeError, ValueError):
            fields[f"dca_pairs.{index}.limit_factor"] = (
                "limit_factor option must be a number up to 5 digits."
            )


def _validate_max_price(
    dca_pair: dict,
    index: int,
    normalized_pair: dict,
    fields: dict[str, str],
) -> None:
    if dca_pair.get("max_price"):
        try:
            normalized_pair["max_price"] = float(dca_pair.get("max_price"))
        except (TypeError, ValueError):
            fields[f"dca_pairs.{index}.max_price"] = (
                "max_price must be a number."
            )


def _validate_ignore_differing_orders(
    dca_pair: dict,
    index: int,
    normalized_pair: dict,
    fields: dict[str, str],
) -> None:
    if dca_pair.get("ignore_differing_orders"):
        if not isinstance(dca_pair.get("ignore_differing_orders"), bool):
            fields[f"dca_pairs.{index}.ignore_differing_orders"] = (
                "ignore_differing_orders must be a boolean."
            )
            return
        normalized_pair["ignore_differing_orders"] = dca_pair.get(
            "ignore_differing_orders"
        )


def _validate_orders_filepath(
    value: object,
    field: str,
    normalized: dict,
    fields: dict[str, str],
) -> None:
    if not isinstance(value, str):
        fields[field] = _ORDERS_FILEPATH_ERROR
        return

    filename = value.strip()
    path = Path(filename)
    if (
        not filename
        or filename != value
        or "\\" in filename
        or path.is_absolute()
        or path.name != filename
        or path.suffix.lower() != ".csv"
    ):
        fields[field] = _ORDERS_FILEPATH_ERROR
        return

    normalized["orders_filepath"] = filename


def _config_for_yaml(config: dict) -> dict:
    writable = copy.deepcopy(config)
    api = writable.get("api") or {}
    for key in ("public_key", "private_key"):
        if api.get(key) is None:
            api.pop(key, None)
    if api:
        writable["api"] = api
    else:
        writable.pop("api", None)
    return writable


def _backup_path(config_path: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return config_path.with_name(f"{config_path.name}.bak.{timestamp}")


def _prune_backups(config_path: Path) -> None:
    backups = sorted(config_path.parent.glob(f"{config_path.name}.bak.*"))
    for backup in backups[:-10]:
        backup.unlink()


def _raise_first(fields: dict[str, str]) -> None:
    message = next(iter(fields.values()))
    raise ConfigValidationError(message, fields)


def _env(env: dict | None) -> dict:
    return os.environ if env is None else env
