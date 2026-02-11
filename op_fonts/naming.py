"""Font name table editor — sets family/style/version metadata."""

from __future__ import annotations

import logging
from pathlib import Path

from fontTools.ttLib import TTFont

log = logging.getLogger(__name__)


def rename_font(
    font_path: Path,
    family_name: str,
    style_name: str,
    version: str = "1.000",
    copyright: str = "",
    designer: str = "",
) -> None:
    """Rewrite the name table to use the given family/style names."""
    font = TTFont(font_path)
    name_table = font["name"]

    full_name = f"{family_name}-{style_name}"
    ps_name = full_name.replace(" ", "")
    unique_id = f"{version};{ps_name}"
    version_str = f"Version {version}"

    entries = {
        1: family_name,
        2: style_name,
        3: unique_id,
        4: f"{family_name} {style_name}",
        5: version_str,
        6: ps_name,
    }

    if copyright:
        entries[0] = copyright
    if designer:
        entries[9] = designer

    for name_id, value in entries.items():
        name_table.setName(value, name_id, 3, 1, 0x0409)  # Windows, Unicode BMP, English
        name_table.setName(value, name_id, 1, 0, 0)        # Mac, Roman, English

    font.save(str(font_path))
    font.close()

    log.info("Renamed font: %s → %s %s", font_path.name, family_name, style_name)
