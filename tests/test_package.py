"""Scaffold gate: the package layout from PLAN §3 is importable."""

import importlib

import pytest

MODULES = [
    "claims_rag",
    "claims_rag.config",
    "claims_rag.components",
    "claims_rag.app",
]


@pytest.mark.parametrize("name", MODULES)
def test_module_importable(name: str) -> None:
    importlib.import_module(name)


def test_package_exposes_version() -> None:
    import claims_rag

    assert claims_rag.__version__ == "0.1.0"
