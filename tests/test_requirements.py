from pathlib import Path


def test_web_scheduler_dependencies_are_declared() -> None:
    requirements = Path("requirements.txt").read_text()
    for package in (
        "APScheduler==",
        "croniter==",
        "fastapi==",
        "httpx==",
        "itsdangerous==",
        "uvicorn==",
    ):
        assert package in requirements


def test_pandas_is_not_a_runtime_dependency() -> None:
    requirements = Path("requirements.txt").read_text()

    assert "pandas" not in requirements.lower()


def test_apscheduler_uses_current_stable_3_x_release() -> None:
    requirements = Path("requirements.txt").read_text()

    assert "APScheduler==3.11.3" in requirements


def test_croniter_uses_current_stable_release() -> None:
    requirements = Path("requirements.txt").read_text()

    assert "croniter==6.2.4" in requirements
