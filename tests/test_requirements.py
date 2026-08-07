from pathlib import Path


def test_runtime_dependencies_are_intentional() -> None:
    requirements = _runtime_requirements()

    assert requirements == {
        "APScheduler",
        "PyYAML",
        "croniter",
        "fastapi",
        "httpx",
        "itsdangerous",
        "uvicorn",
    }


def test_web_scheduler_dependencies_are_declared() -> None:
    requirements = _read("requirements.txt")
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
    requirements = _read("requirements.txt")

    assert "pandas" not in requirements.lower()


def test_httpx2_is_not_a_runtime_dependency() -> None:
    requirements = _read("requirements.txt")

    assert "httpx2" not in requirements.lower()


def test_dev_requirements_include_runtime_and_test_client_dependencies() -> None:
    requirements = _read("requirements-dev.txt")

    assert "-r requirements.txt" in requirements
    assert "httpx2==2.9.1" in requirements
    for package in (
        "pytest==8.3.3",
        "pytest-cov==5.0.0",
        "freezegun==1.5.1",
        "pytz==2024.2",
        "vcrpy==6.0.2",
        "coveralls==4.0.1",
    ):
        assert package in requirements


def test_ci_installs_dev_requirements_for_unit_tests() -> None:
    workflow = _read(".github/workflows/main-unit-testing.yaml")

    assert "python -m pip install -r requirements-dev.txt" in workflow
    assert "python -m pip install -r requirements.txt" not in workflow


def test_readme_documents_dev_requirements_for_tests() -> None:
    readme = _read("README.md")

    assert "python -m pip install -r requirements-dev.txt" in readme


def test_apscheduler_uses_current_stable_3_x_release() -> None:
    requirements = _read("requirements.txt")

    assert "APScheduler==3.11.3" in requirements


def test_croniter_uses_current_stable_release() -> None:
    requirements = _read("requirements.txt")

    assert "croniter==6.2.4" in requirements


def test_fastapi_uses_current_stable_release() -> None:
    requirements = _read("requirements.txt")

    assert "fastapi==0.141.1" in requirements


def test_uvicorn_uses_current_stable_release() -> None:
    requirements = _read("requirements.txt")

    assert "uvicorn==0.52.1" in requirements


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _runtime_requirements() -> set[str]:
    requirements = _read("requirements.txt")
    packages = set()
    for line in requirements.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        packages.add(stripped.split("==", maxsplit=1)[0])
    return packages
