"""TOML config loading → BuildConfig dataclass."""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class ScriptEntry:
    name: str
    enabled: bool
    font: str
    unicode_ranges: list[str]
    url: str = ""            # download URL
    charset_file: str | None = None
    scale: bool = True       # scale glyphs to match target cap ratio
    weights: list[str] = field(default_factory=list)  # available weights; empty = all


@dataclass
class MetricsConfig:
    """Target vertical metrics. All default to 0 (keep source font's native values)."""
    ascender: int = 0
    descender: int = 0
    target_cap_ratio: float = 0.0


@dataclass
class MergeConfig:
    drop_tables: list[str]
    keep_features: list[str] = field(default_factory=list)


@dataclass
class BuildConfig:
    name: str
    style: str
    output: str
    cache_dir: Path
    output_dir: str
    scripts: list[ScriptEntry]
    merge: MergeConfig
    metrics: MetricsConfig
    copyright: str = ""
    designer: str = ""
    weight_values: dict[str, int] = field(default_factory=dict)

    @property
    def weights(self) -> list[str]:
        return list(self.weight_values.keys())


def _parse_script(raw: dict) -> ScriptEntry:
    return ScriptEntry(
        name=raw["name"],
        enabled=raw.get("enabled", True),
        font=raw["font"],
        unicode_ranges=raw.get("unicode_ranges", []),
        url=raw["url"],
        charset_file=raw.get("charset_file"),
        scale=raw.get("scale", True),
        weights=raw.get("weights", []),
    )


def load_config(path: Path) -> BuildConfig:
    """Load a TOML config file and return a BuildConfig."""
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    font = raw["font"]
    scripts_raw = raw.get("scripts", [])
    merge_raw = raw.get("merge", {})

    weight_values = font.get("weight_values", {})
    first_weight = next(iter(weight_values), "Regular")

    config = BuildConfig(
        name=font.get("name", "OpFont"),
        style=font.get("style", first_weight),
        output=font.get("output", f"{font.get('name', 'OpFont')}-{first_weight}.otf"),
        cache_dir=Path(font.get("cache_dir", "./cache")),
        output_dir=font.get("output_dir", "dist"),
        scripts=[_parse_script(s) for s in scripts_raw],
        merge=MergeConfig(
            drop_tables=merge_raw.get("drop_tables", []),
            keep_features=merge_raw.get("keep_features", []),
        ),
        metrics=MetricsConfig(
            ascender=font.get("ascender", 0),
            descender=font.get("descender", 0),
            target_cap_ratio=font.get("target_cap_ratio", 0.0),
        ),
        copyright=font.get("copyright", ""),
        designer=font.get("designer", ""),
        weight_values=weight_values,
    )

    log.debug("Loaded config: %d scripts", len(config.scripts))
    return config


