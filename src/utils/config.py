"""Load the YAML configuration used by generation and analytics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_CONFIG = PROJECT_ROOT / "config" / "config.example.yaml"
LOCAL_CONFIG = PROJECT_ROOT / "config" / "config.yaml"


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load local config when present, otherwise the committed example file."""
    config_path = path or (LOCAL_CONFIG if LOCAL_CONFIG.exists() else EXAMPLE_CONFIG)
    with config_path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError(f"Configuration at {config_path} must be a mapping.")
    config["_config_path"] = str(config_path)
    config["_project_root"] = str(PROJECT_ROOT)
    return config


def project_path(config: dict[str, Any], key: str) -> Path:
    """Resolve a configured relative path against the repository root."""
    root = Path(config["_project_root"])
    return root / config["paths"][key]


def validate_risk_weights(weights: dict[str, float], tolerance: float = 1e-9) -> None:
    """Raise if weights are negative or do not sum to 1."""
    if any(float(value) < 0 for value in weights.values()):
        raise ValueError("Risk weights must be non-negative.")
    total = sum(float(value) for value in weights.values())
    if abs(total - 1.0) > tolerance:
        raise ValueError(f"Risk weights must sum to 1. Current sum is {total:.6f}.")
