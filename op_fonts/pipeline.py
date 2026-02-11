"""Build pipeline orchestrator: download → subset → merge → rename."""

from __future__ import annotations

import copy
import logging
import shutil
import tempfile
from pathlib import Path

from .charsets import load_charset_file
from .config import BuildConfig
from .download import ensure_font, get_download_plan
from .merge import merge_fonts
from .naming import rename_font
from .subset import parse_unicode_ranges, subset_font

log = logging.getLogger(__name__)



def _resolve_codepoints(script, config: BuildConfig) -> list[int]:
    """Resolve the full codepoint list for a script entry.

    If charset_file is set, load codepoints from it and merge with unicode_ranges
    (so CJK ideographs come from the charset, but punctuation/fullwidth ranges
    are still included from unicode_ranges).
    """
    if script.charset_file:
        charset_path = Path(script.charset_file)
        if not charset_path.is_absolute():
            # Resolve relative to config's cache dir parent (project root)
            charset_path = config.cache_dir.parent / charset_path
        charset_cps = set(load_charset_file(charset_path))
        log.info(
            "%s: loaded %d codepoints from charset file %s",
            script.name, len(charset_cps), charset_path,
        )
        # Merge with unicode_ranges (for punctuation, fullwidth, etc.)
        if script.unicode_ranges:
            range_cps = set(parse_unicode_ranges(script.unicode_ranges))
            charset_cps |= range_cps
        return sorted(charset_cps)
    return parse_unicode_ranges(script.unicode_ranges)


def dry_run(config: BuildConfig) -> None:
    """Print the build plan without executing anything."""
    enabled = [s for s in config.scripts if s.enabled]
    print(f"Output: {config.output}")
    print(f"Cache: {config.cache_dir}")
    print(f"\nEnabled scripts ({len(enabled)}):")
    for s in enabled:
        cps = _resolve_codepoints(s, config)
        charset_tag = f" [charset: {s.charset_file}]" if s.charset_file else ""
        print(f"  {s.name}: {s.font} → {len(cps)} codepoints{charset_tag}")

    print(f"\nDownload plan:")
    for name, url, cached in get_download_plan(config):
        status = "cached" if cached.exists() else "download"
        print(f"  [{status}] {name}")
        print(f"    {url}")

    print(f"\nMerge order (first = baseline metrics):")
    for i, s in enumerate(enabled):
        print(f"  {i + 1}. {s.font} ({s.name})")
    print(f"\nDrop tables: {config.merge.drop_tables}")
    print(f"Final name: {config.name} {config.style}")


def build(config: BuildConfig) -> Path:
    """Execute the full build pipeline. Returns the path to the output font."""
    enabled = [s for s in config.scripts if s.enabled]
    if not enabled:
        raise RuntimeError("No scripts enabled — nothing to build")

    log.info("Building %s (%d scripts)", config.output, len(enabled))

    # 1. Download
    log.info("Step 1/5: Downloading fonts...")
    font_paths: dict[str, Path] = {}
    for script in enabled:
        font_paths[script.name] = ensure_font(config.cache_dir, script.font, script.url)

    # 2. Subset (dedup: later scripts only get codepoints not already covered)
    log.info("Step 2/5: Subsetting fonts...")
    work_dir = Path(tempfile.mkdtemp(prefix="op_fonts_"))
    subset_entries: list[tuple[Path, bool]] = []  # (path, should_scale)
    covered_cps: set[int] = set()

    for script in enabled:
        src = font_paths[script.name]
        out = work_dir / f"subset_{script.name}.otf"
        codepoints = _resolve_codepoints(script, config)
        if covered_cps:
            codepoints = [cp for cp in codepoints if cp not in covered_cps]
        if not codepoints:
            log.info("Skipping %s: all codepoints already covered", script.name)
            continue
        try:
            subset_font(src, codepoints=codepoints, output_path=out)
            # Track actual cmap (font may not have all requested codepoints)
            from fontTools.ttLib import TTFont
            font = TTFont(out)
            covered_cps.update(font.getBestCmap().keys())
            font.close()
            subset_entries.append((out, script.scale))
        except ValueError as exc:
            log.warning("Skipping %s: %s", script.name, exc)

    if not subset_entries:
        raise RuntimeError("All subsets were empty — nothing to merge")

    # Scale each subset to match target cap-height ratio.
    # If not set, auto-detect from first script (base font).
    subset_paths = [p for p, _ in subset_entries]
    target_ratio = config.metrics.target_cap_ratio
    if target_ratio <= 0:
        target_ratio = _get_cap_ratio(subset_paths[0])
    if target_ratio > 0:
        log.info("Target cap ratio: %.3f", target_ratio)
        for sp, should_scale in subset_entries:
            if should_scale:
                _scale_to_target(sp, target_ratio)
            else:
                log.info("Skipping scale for %s (scale = false)", sp.name)

    # 3. Merge
    log.info("Step 3/5: Merging %d subset fonts...", len(subset_paths))
    out_dir = Path(config.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / config.output
    merge_fonts(subset_paths, output_path, drop_tables=config.merge.drop_tables)

    # 4. Prune unused GSUB/GPOS features and unreferenced glyphs
    if config.merge.keep_features:
        _prune_features(output_path, config.merge.keep_features)

    # 5. Rename, fix metrics & subroutinize
    log.info("Step 5/5: Setting font metadata...")
    rename_font(output_path, config.name, config.style, copyright=config.copyright, designer=config.designer)
    _fix_metrics(output_path, config.metrics)
    _subroutinize(output_path)

    # Clean up temp dir
    shutil.rmtree(work_dir, ignore_errors=True)

    final_size = output_path.stat().st_size
    log.info(
        "Done! %s — %.1f KB (%d glyphs)",
        output_path,
        final_size / 1024,
        _count_glyphs(output_path),
    )
    return output_path



def _prune_features(font_path: Path, keep_features: list[str]) -> None:
    """Remove GSUB/GPOS features not in keep list, then prune unreferenced glyphs.

    Uses fontTools subsetter to re-subset the merged font, keeping only the
    codepoints already in the cmap and the specified layout features. This
    drops alternate glyphs (stylistic sets, CJK variants, etc.) that aren't
    needed for a car UI.
    """
    from fontTools.ttLib import TTFont
    from fontTools.subset import Subsetter, Options

    font = TTFont(font_path)
    cmap = font.getBestCmap()
    before_glyphs = len(font.getGlyphOrder())

    opts = Options()
    opts.layout_features = keep_features
    opts.notdef_outline = True
    opts.name_legacy = True
    opts.glyph_names = False
    opts.drop_tables += ["DSIG", "meta"]

    subsetter = Subsetter(options=opts)
    subsetter.populate(unicodes=list(cmap.keys()))
    subsetter.subset(font)

    after_glyphs = len(font.getGlyphOrder())
    font.save(str(font_path))
    font.close()

    before_size = font_path.stat().st_size  # saved size
    log.info(
        "Step 4/5: Pruned features → kept %s, glyphs %d → %d (removed %d)",
        keep_features, before_glyphs, after_glyphs, before_glyphs - after_glyphs,
    )


def _get_cap_ratio(font_path: Path) -> float:
    """Read a font's cap-height / UPM ratio."""
    from fontTools.ttLib import TTFont
    font = TTFont(font_path)
    upm = font["head"].unitsPerEm
    cap = font["OS/2"].sCapHeight if font["OS/2"].sCapHeight else 0
    font.close()
    return cap / upm if upm and cap > 0 else 0.0


def _scale_to_target(font_path: Path, target_cap_ratio: float) -> None:
    """Scale all glyphs in a font so its cap-height ratio matches the target.

    Each source font may have a different cap-height ratio, so this must run
    per-subset *before* merging to get uniform visual size across mixed sources.
    """
    from fontTools.ttLib import TTFont

    font = TTFont(font_path)
    upm = font["head"].unitsPerEm
    source_cap = font["OS/2"].sCapHeight if font["OS/2"].sCapHeight else 0
    if source_cap <= 0:
        font.close()
        return

    source_ratio = source_cap / upm
    scale = target_cap_ratio / source_ratio
    if abs(scale - 1.0) < 0.001:
        font.close()
        return

    log.info("Scaling %s by %.3f (cap ratio %.3f → %.3f)", font_path.name, scale, source_ratio, target_cap_ratio)

    if "CFF " in font:
        from fontTools.pens.t2CharStringPen import T2CharStringPen
        from fontTools.pens.transformPen import TransformPen

        cff = font["CFF "]
        td = cff.cff.topDictIndex[0]
        cs = td.CharStrings
        hmtx = font["hmtx"]

        for gname in list(cs.keys()):
            old_cs = cs[gname]
            old_cs.decompile()
            width = hmtx.metrics[gname][0] if gname in hmtx.metrics else 0
            pen = T2CharStringPen(width=round(width * scale), glyphSet=None)
            tpen = TransformPen(pen, (scale, 0, 0, scale, 0, 0))
            old_cs.draw(tpen)
            new_cs = pen.getCharString()
            new_cs.private = old_cs.private
            new_cs.globalSubrs = old_cs.globalSubrs
            cs[gname] = new_cs

        for gname in hmtx.metrics:
            width, lsb = hmtx.metrics[gname]
            hmtx.metrics[gname] = (round(width * scale), round(lsb * scale))

    os2 = font["OS/2"]
    os2.sxHeight = round(os2.sxHeight * scale) if os2.sxHeight else 0
    os2.sCapHeight = round(os2.sCapHeight * scale) if os2.sCapHeight else 0

    font.save(str(font_path))
    font.close()


def _fix_metrics(font_path: Path, metrics) -> None:
    """Set vertical metrics on the merged font. Skips if ascender/descender are 0."""
    if metrics.ascender == 0 and metrics.descender == 0:
        return

    from fontTools.ttLib import TTFont

    font = TTFont(font_path)

    ascender = metrics.ascender
    descender = metrics.descender

    os2 = font["OS/2"]
    os2.sTypoAscender = ascender
    os2.sTypoDescender = descender
    os2.sTypoLineGap = 0
    os2.usWinAscent = ascender
    os2.usWinDescent = abs(descender)

    hhea = font["hhea"]
    hhea.ascent = ascender
    hhea.descent = descender
    hhea.lineGap = 0

    font.save(str(font_path))
    font.close()
    log.info("Fixed metrics: ascender=%d, descender=%d", ascender, descender)




def _subroutinize(font_path: Path) -> None:
    """Re-subroutinize CFF outlines for smaller file size."""
    from fontTools.ttLib import TTFont
    font = TTFont(font_path)
    if "CFF " not in font:
        font.close()
        return
    try:
        import cffsubr
        before = font_path.stat().st_size
        cffsubr.subroutinize(font)
        font.save(str(font_path))
        after = font_path.stat().st_size
        log.info("Subroutinized: %.1f KB → %.1f KB (%.0f%% smaller)",
                 before / 1024, after / 1024, (before - after) / before * 100)
    except ImportError:
        log.debug("cffsubr not installed, skipping subroutinization")
    font.close()


def _count_glyphs(font_path: Path) -> int:
    from fontTools.ttLib import TTFont
    font = TTFont(font_path)
    count = len(font.getGlyphOrder())
    font.close()
    return count


def build_all(config: BuildConfig) -> list[Path]:
    """Build all weight variants defined in config."""
    if not config.weights:
        return [build(config)]

    outputs = []
    for weight in config.weights:
        log.info("=== Building weight: %s ===", weight)
        cfg = copy.deepcopy(config)
        cfg.style = weight
        cfg.output = f"{config.name}-{weight}.otf"
        # Replace "Regular" in font names/URLs for this weight.
        # Scripts with explicit weights only swap if the weight is available.
        for script in cfg.scripts:
            if not script.weights or weight in script.weights:
                script.font = script.font.replace("Regular", weight)
                script.url = script.url.replace("Regular", weight)
        outputs.append(build(cfg))
    return outputs
