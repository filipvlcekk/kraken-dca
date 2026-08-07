"""Docker runtime and web UI packaging tests."""

from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_builds_frontend_and_runs_web_app() -> None:
    dockerfile = _read("Dockerfile")

    assert re.search(
        r"(?im)^FROM\s+node:[^\n]+\s+AS\s+frontend-build$",
        dockerfile,
    )
    assert "npm --prefix frontend ci" in dockerfile
    assert "npm --prefix frontend run build" in dockerfile
    assert re.search(
        r"(?m)^COPY\s+--from=frontend-build\s+"
        r"--chown=krakendca:krakendca\s+"
        r"/app/frontend/dist/\s+/app/frontend/$",
        dockerfile,
    )
    assert "EXPOSE 8080" in dockerfile
    assert (
        'CMD ["uvicorn", "krakendca.web.app:app", "--host", "0.0.0.0", '
        '"--port", "8080", "--workers", "1"]'
    ) in dockerfile


def test_dockerfile_final_runtime_excludes_cron_node_and_baked_config() -> None:
    dockerfile = _read("Dockerfile")
    final_stage = _final_stage(dockerfile)
    lower_final_stage = final_stage.lower()

    assert "apt-get install --yes --no-install-recommends cron" not in lower_final_stage
    assert "crontab" not in lower_final_stage
    assert 'CMD ["cron", "-f"]' not in final_stage
    assert "node" not in lower_final_stage
    assert "config-sample.yaml /app/config.yaml" not in dockerfile
    assert "touch /app/orders.csv" in final_stage
    assert "USER krakendca" in final_stage


def test_dockerfile_final_runtime_supports_coolify_healthchecks() -> None:
    final_stage = _final_stage(_read("Dockerfile"))

    assert "apt-get install --yes --no-install-recommends curl" in final_stage
    assert "rm -rf /var/lib/apt/lists/*" in final_stage


def test_dockerfile_final_runtime_installs_only_runtime_requirements() -> None:
    final_stage = _final_stage(_read("Dockerfile"))

    assert "requirements.txt" in final_stage
    assert "requirements-dev.txt" not in final_stage


def test_readme_documents_docker_web_ui_runtime() -> None:
    readme = _read("README.md")

    for required in (
        "WEB_UI_PASSWORD",
        "WEB_UI_SESSION_SECRET",
        "WEB_UI_COOKIE_SECURE",
        "-p 8080:8080",
        "writable `config.yaml`",
        "writable `orders.csv`",
        "schedule:",
        "min_order_interval_minutes",
        "legacy `delay`",
        "Manual run",
        "scheduler reload",
    ):
        assert required in readme

    assert "read-only" in readme
    assert "legacy CLI/cron mode" in readme


def test_sample_config_includes_schedule_modes() -> None:
    sample = yaml.safe_load(_read("config-sample.yaml"))
    pairs = sample["dca_pairs"]

    cron_pair = next(
        pair
        for pair in pairs
        if (pair.get("schedule") or {}).get("enabled") is True
    )
    assert cron_pair["schedule"]["cron"].count(" ") == 4
    assert cron_pair["schedule"]["timezone"] == "Europe/Prague"
    assert cron_pair["min_order_interval_minutes"] == 30

    disabled_pair = next(
        pair
        for pair in pairs
        if (pair.get("schedule") or {}).get("enabled") is False
    )
    assert disabled_pair["schedule"] == {"enabled": False}

    assert any("delay" in pair and "schedule" not in pair for pair in pairs)


def test_config_fixture_matches_sample_config() -> None:
    assert _read("tests/fixtures/config.yaml") == _read("config-sample.yaml")


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _final_stage(dockerfile: str) -> str:
    starts = [match.start() for match in re.finditer(r"(?im)^FROM\s+", dockerfile)]
    return dockerfile[starts[-1]:]
