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
