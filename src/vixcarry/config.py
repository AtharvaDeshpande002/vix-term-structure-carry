"""Read config.yaml once and resolve its relative paths against the repository root.

Why: every script, the notebook and the tests must see the same parameters, and nothing may depend on the
folder the user happens to run Python from.
"""
from __future__ import annotations

import pathlib
from typing import Any

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]  # src/vixcarry/config.py -> repo root


def load_config(path: str | pathlib.Path | None = None) -> dict[str, Any]:
    """Return config.yaml as a dict, with every entry under `paths` turned into an absolute pathlib.Path."""
    p = pathlib.Path(path) if path else ROOT / "config.yaml"
    cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
    cfg["paths"] = {k: (ROOT / v) for k, v in cfg["paths"].items()}
    return cfg
