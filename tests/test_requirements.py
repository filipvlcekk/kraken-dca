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
