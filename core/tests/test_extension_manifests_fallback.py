"""An extension app that declares no spec.manifests must not fall back to manifests/ (Z-01)."""
from pathlib import Path

import pytest
from onemind_core.catalog import AppEntry


def entry(tmp_path: Path, spec: dict) -> AppEntry:
    (tmp_path / "manifests").mkdir(exist_ok=True)
    return AppEntry(id="x", dir=tmp_path, manifest={"spec": spec})


def test_extension_app_without_manifests_refuses_fallback(tmp_path):
    with pytest.raises(ValueError, match="no spec.manifests"):
        entry(tmp_path, {"extensions": {"settings": {"schema": "s.json"}}}).manifests_dir


def test_ordinary_app_keeps_default_and_declared_paths(tmp_path):
    assert entry(tmp_path, {}).manifests_dir == (tmp_path / "manifests").resolve()
    assert entry(tmp_path, {"extensions": {}, "manifests": "manifests/"}).manifests_dir == (tmp_path / "manifests").resolve()
