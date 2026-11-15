#!/usr/bin/env python3
"""
TermVR Mono & TermVR Mono NF Reproducible Font Builder
======================================================
Synthesizes a strict 1:2 terminal grid font (1-cell = 600, 2-cell = 1200, UPM = 1000)
from pinned upstream sources:
  1. IBM Plex Mono (Base ASCII, Latin, Greek, Cyrillic, core operators)
  2. Programmatic Terminal Grid Glyphs (Box Drawing, Block Elements, Braille, Sextants, U+3000)
  3. IBM Plex Math + Core Prompt Symbols (Arrows, Math Operators, Misc Technical, Shapes, Dingbats)
  4. IBM Plex Sans Hebrew (Consonants normalized to 600 + zero-width Niqqud with GPOS MarkToBase)
  5. IBM Plex Sans KR (11,172 modern Hangul syllables + Jamo + KR symbols, normalized to 1200/600)
  6. IBM Plex Sans JP (Hiragana, Katakana, 14,800+ Kanji/Hanja, normalized to 1200/600)
  7. IBM Plex Sans TC (KS X 1001 Korean Hanja supplement + NFKD compatibility ideograph mapping)
  8. Symbols Nerd Font Mono (10,600+ developer icons & Powerline symbols normalized to 600)
"""

from __future__ import annotations

import argparse
import copy
import math
import sys
import time
import tomllib
import unicodedata
from pathlib import Path

from fontTools.misc.timeTools import timestampSinceEpoch
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont, newTable
from fontTools.ttLib.tables._g_l_y_f import Glyph

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.fetch_sources import fetch_all_sources, get_base_weight
from scripts.generate_terminal_glyphs import build_all_programmatic_glyphs

CONFIG_PATH = ROOT_DIR / "config" / "build_config.toml"
SOURCES_DIR = ROOT_DIR / "sources"
DIST_DIR = ROOT_DIR / "dist"

WEIGHT_CLASS_MAP = {
    "Thin": 100,
    "ExtraLight": 200,
    "Light": 300,
    "Regular": 400,
    "Text": 450,
    "Medium": 500,
    "SemiBold": 600,
    "Bold": 700,
}

# Core terminal prompt / power symbols always included even in non-NF TermVR Mono
CORE_PROMPT_UNICODES = {
    0x23FB,  # ⏻ Power symbol
    0x23FC,  # ⏼ Power on-off symbol
    0x23FD,  # ⏽ Power on symbol
    0x23FE,  # ⏾ Power sleep symbol
    0x2665,  # ♥ Black heart suit
    0x26A1,  # ⚡ High voltage sign
    0x276C,  # ❬ Medium left-pointing angle bracket ornament
    0x276D,  # ❭ Medium right-pointing angle bracket ornament
    0x276E,  # ❮ Heavy left-pointing angle quotation mark ornament
    0x276F,  # ❯ Heavy right-pointing angle quotation mark ornament (Starship / Pure prompt)
    0x2770,  # ❰ Heavy left-pointing angle bracket ornament
    0x2771,  # ❱ Heavy right-pointing angle bracket ornament
    0x2B58,  # ⭘ Heavy circle
}

# Fullwidth punctuation in KR/JP that need special positional tuning rather than generic centering
FULLWIDTH_OPEN_BRACKETS = {0x3008, 0x300A, 0x300C, 0x300E, 0x3010, 0x3014, 0x3016, 0x3018, 0x301A, 0xFF08, 0xFF3B, 0xFF5B, 0xFF5F}
FULLWIDTH_CLOSE_BRACKETS = {0x3009, 0x300B, 0x300D, 0x300F, 0x3011, 0x3015, 0x3017, 0x3019, 0x301B, 0xFF09, 0xFF3D, 0xFF5D, 0xFF60}
FULLWIDTH_CORNER_PUNCT = {0x3001, 0x3002, 0xFF0C, 0xFF0E}


def is_zero_width_codepoint(u: int) -> bool:
    """Return True if Unicode codepoint `u` has wcwidth == 0 in terminals."""
    if u == 0x0000:
        return True
    cat = unicodedata.category(chr(u))
    if cat in ("Mn", "Me", "Cf", "Zl", "Zp"):
        return True
    if 0x1160 <= u <= 0x11FF or 0xD7B0 <= u <= 0xD7FF:
        return True
    return False


def is_fullwidth_codepoint(u: int) -> bool:
    """Return True if Unicode codepoint `u` has East_Asian_Width W or F (wcwidth == 2)."""
    if is_zero_width_codepoint(u):
        return False
    # PUA icons (Nerd Fonts) are always 1-cell halfwidth in Mono terminal fonts
    if (0xE000 <= u <= 0xF8FF) or (0xF0000 <= u <= 0x10FFFF):
        return False
    return unicodedata.east_asian_width(chr(u)) in ("W", "F")


def get_target_cell_width(u: int, half_width: int = 600, full_width: int = 1200) -> int:
    if is_zero_width_codepoint(u):
        return 0
    if is_fullwidth_codepoint(u):
        return full_width
    return half_width


def get_ks_x_1001_hanja() -> set[int]:
    """Return the exact set of 4,888 Korean KS X 1001 Hanja codepoints."""
    hanja: set[int] = set()
    for row in range(0xCA, 0xFD + 1):
        for col in range(0xA1, 0xFE + 1):
            try:
                hanja.add(ord(bytes([row, col]).decode("euc_kr")))
            except UnicodeDecodeError:
                pass
    return hanja


class DecomposingTransformPen(TransformPen):
    """TransformPen that recursively decomposes composite glyph components into simple contours."""

    def __init__(self, outPen, transformation, glyphSet):
        super().__init__(outPen, transformation)
        self.glyphSet = glyphSet

    def addComponent(self, glyphName: str, transformation) -> None:
        if self.glyphSet and glyphName in self.glyphSet:
            sub_pen = DecomposingTransformPen(self, transformation, self.glyphSet)
            self.glyphSet[glyphName].draw(sub_pen)


def draw_transformed_glyph(
    glyph_set,
    src_gname: str,
    sx: float = 1.0,
    shx: float = 0.0,
    shy: float = 0.0,
    sy: float = 1.0,
    dx: float = 0.0,
    dy: float = 0.0,
) -> Glyph:
    """Flatten composite references and apply 2D affine transform (sx, shx, shy, sy, dx, dy)."""
    pen = TTGlyphPen(None)
    tpen = DecomposingTransformPen(pen, (sx, shy, shx, sy, dx, dy), glyph_set)
    glyph_set[src_gname].draw(tpen)
    g = pen.glyph()
    g.recalcBounds(None)
    return g


def get_glyph_bbox(src_tt: TTFont, gname: str) -> tuple[int, int, int, int] | None:
    glyf = src_tt["glyf"]
    g = glyf[gname]
    if g.numberOfContours == 0:
        return None
    g.recalcBounds(glyf)
    return (g.xMin, g.yMin, g.xMax, g.yMax)


def merge_hebrew_gpos_marks(
    base_tt: TTFont,
    heb_tt: TTFont,
    glyph_map: dict[str, str],
    transforms: dict[str, tuple[float, float, float, float, float]],
    glyph_order: list[str],
) -> None:
    """
    Transplant Hebrew MarkToBase (LookupType 4) subtables into base_tt['GPOS']
    with anchor coordinates transformed to match the normalized 600-unit cell outlines.
    """
    if "GPOS" not in base_tt or "GPOS" not in heb_tt:
        return

    glyph_id_map = {g: idx for idx, g in enumerate(glyph_order)}
    base_gpos = base_tt["GPOS"].table
    heb_gpos = heb_tt["GPOS"].table
    new_lookup_indices: list[int] = []

    # In IBMPlexSansHebrew, Lookups with MarkCoverage containing Hebrew Mn (uni05B0..uni05C7)
    for lookup in heb_gpos.LookupList.Lookup:
        if lookup.LookupType != 4:
            continue
        st = lookup.SubTable[0]
        if not any(m in glyph_map for m in st.MarkCoverage.glyphs):
            continue

        new_lookup = copy.deepcopy(lookup)
        new_st = new_lookup.SubTable[0]

        # Filter, transform, and sort marks by target glyph ID
        mark_entries = []
        for m_gname, m_rec in zip(new_st.MarkCoverage.glyphs, new_st.MarkArray.MarkRecord):
            if m_gname not in glyph_map:
                continue
            dst_m = glyph_map[m_gname]
            sx, shx, sy, dx, dy = transforms[m_gname]
            old_x = m_rec.MarkAnchor.XCoordinate
            old_y = m_rec.MarkAnchor.YCoordinate
            m_rec.MarkAnchor.XCoordinate = round(old_x * sx + old_y * shx + dx)
            m_rec.MarkAnchor.YCoordinate = round(old_y * sy + dy)
            mark_entries.append((glyph_id_map[dst_m], dst_m, m_rec))

        # Filter, transform, and sort bases by target glyph ID
        base_entries = []
        for b_gname, b_rec in zip(new_st.BaseCoverage.glyphs, new_st.BaseArray.BaseRecord):
            if b_gname not in glyph_map:
                continue
            dst_b = glyph_map[b_gname]
            sx, shx, sy, dx, dy = transforms[b_gname]
            for anchor in b_rec.BaseAnchor:
                if anchor is not None:
                    old_x = anchor.XCoordinate
                    old_y = anchor.YCoordinate
                    anchor.XCoordinate = round(old_x * sx + old_y * shx + dx)
                    anchor.YCoordinate = round(old_y * sy + dy)
            base_entries.append((glyph_id_map[dst_b], dst_b, b_rec))

        if not mark_entries or not base_entries:
            continue

        mark_entries.sort(key=lambda item: item[0])
        base_entries.sort(key=lambda item: item[0])

        new_st.MarkCoverage.glyphs = [item[1] for item in mark_entries]
        new_st.MarkArray.MarkRecord = [item[2] for item in mark_entries]
        new_st.MarkArray.MarkCount = len(mark_entries)
        new_st.BaseCoverage.glyphs = [item[1] for item in base_entries]
        new_st.BaseArray.BaseRecord = [item[2] for item in base_entries]
        new_st.BaseArray.BaseCount = len(base_entries)

        new_idx = len(base_gpos.LookupList.Lookup)
        base_gpos.LookupList.Lookup.append(new_lookup)
        base_gpos.LookupList.LookupCount = len(base_gpos.LookupList.Lookup)
        new_lookup_indices.append(new_idx)

    if not new_lookup_indices:
        return

    # Attach new lookup indices to 'mark' feature records
    mark_feat_indices: list[int] = []
    for f_idx, frec in enumerate(base_gpos.FeatureList.FeatureRecord):
        if frec.FeatureTag == "mark":
            for l_idx in new_lookup_indices:
                if l_idx not in frec.Feature.LookupListIndex:
                    frec.Feature.LookupListIndex.append(l_idx)
            frec.Feature.LookupCount = len(frec.Feature.LookupListIndex)
            mark_feat_indices.append(f_idx)

    # Ensure 'hebr' script tag is registered in GPOS ScriptList
    if mark_feat_indices and not any(s.ScriptTag == "hebr" for s in base_gpos.ScriptList.ScriptRecord):
        dflt_rec = next((s for s in base_gpos.ScriptList.ScriptRecord if s.ScriptTag == "DFLT"), None)
        if dflt_rec is not None:
            hebr_rec = copy.deepcopy(dflt_rec)
            hebr_rec.ScriptTag = "hebr"
            base_gpos.ScriptList.ScriptRecord.append(hebr_rec)
            base_gpos.ScriptList.ScriptCount = len(base_gpos.ScriptList.ScriptRecord)

    # Update GDEF GlyphClassDef (1 = Base, 3 = Mark)
    if "GDEF" in base_tt and base_tt["GDEF"].table.GlyphClassDef is not None:
        class_defs = base_tt["GDEF"].table.GlyphClassDef.classDefs
        heb_cmap = heb_tt.getBestCmap()
        for u, src_gname in heb_cmap.items():
            if src_gname in glyph_map:
                dst_gname = glyph_map[src_gname]
                class_defs[dst_gname] = 3 if is_zero_width_codepoint(u) else 1


def add_nfd_composition_gsub(
    base_tt: TTFont,
    cmap: dict[int, str],
    glyph_order: list[str],
) -> None:
    """
    Build OpenType GSUB `ccmp` LigatureSubst (LookupType 4) lookups so Unicode NFD
    sequences render identically to NFC without triggering OS font fallback:
      1. Hangul Conjoining Jamo: L + V + T -> LVT and L + V -> LV (all 11,172 syllables)
      2. Hybrid Hangul LV + T -> LVT (all 10,773 combinations)
      3. Japanese Kana + Combining Dakuten/Handakuten (U+3099/U+309A) -> Voiced Kana
      4. Latin / Greek / Cyrillic Base + Combining Mark(s) -> Precomposed NFC
    Attached to DFLT, hang, kana, hani, latn, cyrl, and grek script tags.
    """
    from fontTools.ttLib.tables import otTables

    if "GSUB" not in base_tt:
        return

    glyph_id_map = {g: i for i, g in enumerate(glyph_order)}
    gsub = base_tt["GSUB"].table

    def build_ligature_lookup(lig_map: dict[str, list[tuple[tuple[str, ...], str]]]) -> otTables.Lookup | None:
        if not lig_map:
            return None
        st = otTables.LigatureSubst()
        st.Format = 1
        st.ligatures = {}
        # Sort first-glyph keys by glyph ID for valid OpenType Coverage ordering
        for first_g in sorted(lig_map.keys(), key=lambda g: glyph_id_map[g]):
            entries = sorted(lig_map[first_g], key=lambda item: (-len(item[0]), item[0]))
            lig_objs = []
            for comps, target_g in entries:
                lig = otTables.Ligature()
                lig.Component = list(comps)
                lig.CompCount = len(comps) + 1
                lig.LigGlyph = target_g
                lig_objs.append(lig)
            st.ligatures[first_g] = lig_objs
        lookup = otTables.Lookup()
        lookup.LookupType = 4
        lookup.LookupFlag = 0
        lookup.SubTable = [st]
        lookup.SubTableCount = 1
        return lookup

    # 1. Hangul NFD: L (0x1100..0x1112) + V (0x1161..0x1175) [+ T (0x11A8..0x11C2)]
    hangul_lvt_map: dict[str, list[tuple[tuple[str, ...], str]]] = {}
    hangul_lv_t_map: dict[str, list[tuple[tuple[str, ...], str]]] = {}

    for l_idx in range(19):
        l_u = 0x1100 + l_idx
        if l_u not in cmap:
            continue
        l_g = cmap[l_u]
        l_entries: list[tuple[tuple[str, ...], str]] = []
        for v_idx in range(21):
            v_u = 0x1161 + v_idx
            if v_u not in cmap:
                continue
            v_g = cmap[v_u]
            lv_u = 0xAC00 + (l_idx * 21 + v_idx) * 28
            if lv_u not in cmap:
                continue
            lv_g = cmap[lv_u]
            # 3-component L + V + T -> LVT
            for t_idx in range(1, 28):
                t_u = 0x11A7 + t_idx
                lvt_u = lv_u + t_idx
                if t_u in cmap and lvt_u in cmap:
                    t_g = cmap[t_u]
                    lvt_g = cmap[lvt_u]
                    l_entries.append(((v_g, t_g), lvt_g))
                    hangul_lv_t_map.setdefault(lv_g, []).append(((t_g,), lvt_g))
            # 2-component L + V -> LV
            l_entries.append(((v_g,), lv_g))
        if l_entries:
            hangul_lvt_map[l_g] = l_entries

    # 2. Kana + Latin/Greek/Cyrillic canonical NFD -> NFC compositions
    general_nfd_map: dict[str, list[tuple[tuple[str, ...], str]]] = {}
    for u in sorted(cmap):
        # Skip Hangul syllables (handled above) and Hebrew Presentation Forms (handled by GPOS MarkToBase)
        if 0xAC00 <= u <= 0xD7A3 or 0xFB1D <= u <= 0xFB4F or u > 0xFFFF:
            continue
        nfd = unicodedata.normalize("NFD", chr(u))
        if len(nfd) < 2:
            continue
        if not all(ord(ch) in cmap for ch in nfd):
            continue
        first_g = cmap[ord(nfd[0])]
        comps = tuple(cmap[ord(ch)] for ch in nfd[1:])
        target_g = cmap[u]
        if first_g == target_g:
            continue
        general_nfd_map.setdefault(first_g, []).append((comps, target_g))

    new_lookup_indices: list[int] = []
    for lig_map in (hangul_lvt_map, hangul_lv_t_map, general_nfd_map):
        lk = build_ligature_lookup(lig_map)
        if lk is not None:
            idx = len(gsub.LookupList.Lookup)
            gsub.LookupList.Lookup.append(lk)
            gsub.LookupList.LookupCount = len(gsub.LookupList.Lookup)
            new_lookup_indices.append(idx)

    if not new_lookup_indices:
        return

    # Prepend NFD composition lookups to all existing 'ccmp' FeatureRecords
    ccmp_indices: list[int] = []
    for f_idx, frec in enumerate(gsub.FeatureList.FeatureRecord):
        if frec.FeatureTag == "ccmp":
            existing = [i for i in frec.Feature.LookupListIndex if i not in new_lookup_indices]
            frec.Feature.LookupListIndex = list(new_lookup_indices) + existing
            frec.Feature.LookupCount = len(frec.Feature.LookupListIndex)
            ccmp_indices.append(f_idx)

    # Ensure script records exist for DFLT, cyrl, grek, hang, hani, hebr, kana, latn
    if ccmp_indices:
        dflt_rec = next((s for s in gsub.ScriptList.ScriptRecord if s.ScriptTag == "DFLT"), None)
        if dflt_rec is not None:
            existing_scripts = {s.ScriptTag for s in gsub.ScriptList.ScriptRecord}
            for tag in ("grek", "hang", "hani", "hebr", "kana"):
                if tag not in existing_scripts:
                    new_sr = copy.deepcopy(dflt_rec)
                    new_sr.ScriptTag = tag
                    gsub.ScriptList.ScriptRecord.append(new_sr)
            gsub.ScriptList.ScriptRecord.sort(key=lambda s: s.ScriptTag)
            gsub.ScriptList.ScriptCount = len(gsub.ScriptList.ScriptRecord)

    # Register Hangul Jungseong/Jongseong & Kana/Greek combining marks in GDEF as Mark (3)
    if "GDEF" in base_tt and base_tt["GDEF"].table.GlyphClassDef is not None:
        class_defs = base_tt["GDEF"].table.GlyphClassDef.classDefs
        for u in range(0x1100, 0x1113):
            if u in cmap:
                class_defs[cmap[u]] = 1
        for u in list(range(0x1161, 0x1176)) + list(range(0x11A8, 0x11C3)) + [0x3099, 0x309A, 0x0342, 0x0345]:
            if u in cmap:
                class_defs[cmap[u]] = 3


def configure_name_table(
    tt: TTFont,
    family_name: str,
    style: str,
    version: str,
    copyright_str: str,
    license_url: str,
    vendor_url: str,
) -> None:
    """Populate clean OpenType `name` table entries complying with SIL OFL 1.1 & Windows/macOS rules."""
    name_table = newTable("name")
    name_table.names = []

    base_weight = get_base_weight(style)
    is_italic = "Italic" in style
    is_ribbi = base_weight in ("Regular", "Bold")

    # Display style with space before Italic for non-Regular weights (e.g. "Bold Italic", "SemiBold Italic")
    display_style = style.replace("Italic", " Italic").strip() if (is_italic and style != "Italic") else style

    if is_ribbi:
        win_family = family_name
        win_subfamily = display_style
    else:
        win_family = f"{family_name} {base_weight}"
        win_subfamily = "Italic" if is_italic else "Regular"

    ps_family = family_name.replace(" ", "")
    ps_style = style.replace(" ", "")
    postscript_name = f"{ps_family}-{ps_style}"
    full_name = f"{family_name} {display_style}"
    unique_id = f"{version};{vendor_url};{postscript_name}"
    version_str = f"Version {version}"

    ofl_short = (
        "This Font Software is licensed under the SIL Open Font License, Version 1.1. "
        "This license is available with a FAQ at: https://openfontlicense.org"
    )

    records = [
        (0, copyright_str),
        (1, win_family),
        (2, win_subfamily),
        (3, unique_id),
        (4, full_name),
        (5, version_str),
        (6, postscript_name),
        (8, "gfire-sigs"),
        (9, "Bold Monday, Sandoll Inc., Ryan L McIntyre, gfire-sigs"),
        (11, vendor_url),
        (13, ofl_short),
        (14, license_url),
    ]
    if not is_ribbi:
        records.append((16, family_name))
        records.append((17, display_style))

    for name_id, text in records:
        # Platform 3 (Windows), Encoding 1 (Unicode BMP), Lang 0x0409 (en-US)
        name_table.setName(text, name_id, 3, 1, 0x0409)
        # Platform 1 (Macintosh), Encoding 0 (Roman), Lang 0 (English)
        try:
            name_table.setName(text, name_id, 1, 0, 0)
        except Exception:
            pass

    tt["name"] = name_table


def configure_cmap_tables(tt: TTFont, cmap_dict: dict[int, str]) -> None:
    """Build Format 4 (BMP) and Format 12 (Full Unicode) cmap subtables."""
    from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

    cmap_table = newTable("cmap")
    cmap_table.tableVersion = 0

    bmp_map = {u: g for u, g in cmap_dict.items() if u <= 0xFFFF}

    # Format 4 for Windows BMP (3, 1) and Unicode BMP (0, 3)
    sub4_win = CmapSubtable.newSubtable(4)
    sub4_win.platformID = 3
    sub4_win.platEncID = 1
    sub4_win.language = 0
    sub4_win.cmap = bmp_map

    sub4_uni = CmapSubtable.newSubtable(4)
    sub4_uni.platformID = 0
    sub4_uni.platEncID = 3
    sub4_uni.language = 0
    sub4_uni.cmap = dict(bmp_map)

    # Format 12 for Windows UCS-4 (3, 10) and Unicode Full (0, 4)
    sub12_win = CmapSubtable.newSubtable(12)
    sub12_win.platformID = 3
    sub12_win.platEncID = 10
    sub12_win.language = 0
    sub12_win.cmap = dict(cmap_dict)

    sub12_uni = CmapSubtable.newSubtable(12)
    sub12_uni.platformID = 0
    sub12_uni.platEncID = 4
    sub12_uni.language = 0
    sub12_uni.cmap = dict(cmap_dict)

    cmap_table.tables = [sub4_win, sub4_uni, sub12_win, sub12_uni]
    tt["cmap"] = cmap_table


def set_style_flags(tt: TTFont, style: str, cfg: dict) -> None:
    """Synchronize head, hhea, OS/2, and post tables for strict terminal compatibility."""
    m = cfg["metrics"]
    p = cfg["project"]
    upm = int(m["upm"])
    half_width = int(m["half_width"])
    ascender = int(m["ascender"])
    descender = int(m["descender"])
    line_gap = int(m["line_gap"])
    cap_height = int(m["cap_height"])
    x_height = int(m["x_height"])

    base_weight = get_base_weight(style)
    is_bold = base_weight == "Bold"
    is_italic = "Italic" in style
    is_regular = style == "Regular"

    # 1. head table
    head = tt["head"]
    head.unitsPerEm = upm
    epoch_ts = timestampSinceEpoch(int(p["reproducible_timestamp"]))
    head.created = epoch_ts
    head.modified = epoch_ts
    mac_style = 0
    if is_bold:
        mac_style |= 1 << 0
    if is_italic:
        mac_style |= 1 << 1
    head.macStyle = mac_style

    # 2. hhea table
    hhea = tt["hhea"]
    hhea.ascent = ascender
    hhea.descent = descender
    hhea.lineGap = line_gap

    # 3. OS/2 table
    os2 = tt["OS/2"]
    os2.version = 4
    os2.xAvgCharWidth = half_width
    os2.usWeightClass = WEIGHT_CLASS_MAP.get(base_weight, 400)
    os2.usWidthClass = 5
    os2.fsType = 0  # Installable embedding allowed (OFL-1.1)
    os2.sTypoAscender = ascender
    os2.sTypoDescender = descender
    os2.sTypoLineGap = line_gap
    os2.usWinAscent = ascender
    os2.usWinDescent = abs(descender)
    os2.sxHeight = x_height
    os2.sCapHeight = cap_height
    os2.achVendID = p["vendor"][:4].ljust(4)

    # PANOSE: Monospaced Sans (bFamilyType=2, bProportion=9)
    os2.panose.bFamilyType = 2
    os2.panose.bProportion = 9

    # fsSelection bits: 0=ITALIC, 5=BOLD, 6=REGULAR, 7=USE_TYPO_METRICS
    fs_sel = 1 << 7  # Always enable USE_TYPO_METRICS
    if is_italic:
        fs_sel |= 1 << 0
    if is_bold:
        fs_sel |= 1 << 5
    if is_regular:
        fs_sel |= 1 << 6
    os2.fsSelection = fs_sel

    # Set OS/2 Unicode range & CodePage range bits (Latin, Greek, Cyrillic, Hebrew, Hangul, CJK, Symbols)
    os2.ulUnicodeRange1 = (
        (1 << 0)   # Basic Latin
        | (1 << 1) # Latin-1 Supplement
        | (1 << 2) # Latin Extended-A
        | (1 << 3) # Latin Extended-B
        | (1 << 7) # Greek and Coptic
        | (1 << 9) # Cyrillic
        | (1 << 11) # Hebrew
        | (1 << 28) # Hangul Jamo
    )
    os2.ulUnicodeRange2 = (
        (1 << 0)   # General Punctuation
        | (1 << 1) # Superscripts And Subscripts
        | (1 << 2) # Currency Symbols
        | (1 << 4) # Letterlike Symbols
        | (1 << 5) # Number Forms
        | (1 << 6) # Arrows
        | (1 << 7) # Mathematical Operators
        | (1 << 8) # Miscellaneous Technical
        | (1 << 9) # Control Pictures
        | (1 << 11) # Enclosed Alphanumerics
        | (1 << 12) # Box Drawing
        | (1 << 13) # Block Elements
        | (1 << 14) # Geometric Shapes
        | (1 << 15) # Miscellaneous Symbols
        | (1 << 16) # Dingbats
        | (1 << 17) # CJK Symbols And Punctuation
        | (1 << 18) # Hiragana
        | (1 << 19) # Katakana
        | (1 << 20) # Bopomofo / CJK
        | (1 << 21) # Hangul Compatibility Jamo
        | (1 << 23) # Enclosed CJK Letters And Months
        | (1 << 24) # CJK Compatibility
        | (1 << 26) # Hangul Syllables (bit 54)
        | (1 << 27) # CJK Unified Ideographs (bit 59 -> bit 27 of range2)
        | (1 << 28) # Private Use Area (bit 60)
    )
    os2.ulUnicodeRange3 = (
        (1 << 0)   # CJK Compatibility Ideographs
        | (1 << 1) # Alphabetic Presentation Forms (Hebrew)
        | (1 << 4) # Halfwidth And Fullwidth Forms
        | (1 << 18) # Braille Patterns
    )
    # CodePage bits: Latin1 (0), Latin2 (1), Cyrillic (2), Greek (3), Hebrew (5), JIS/Japan (17), Korean Wansung (19), Korean Johab (21)
    os2.ulCodePageRange1 = (
        (1 << 0) | (1 << 1) | (1 << 2) | (1 << 3) | (1 << 5) | (1 << 17) | (1 << 19) | (1 << 21)
    )

    # 4. post table
    post = tt["post"]
    post.formatType = 2.0
    post.isFixedPitch = 1
    post.italicAngle = float(m["italic_angle"]) if is_italic else 0.0
    post.underlinePosition = -125
    post.underlineThickness = 50
    post.extraNames = []
    post.mapping = {}

    # Remove BASE or DSIG if present to prevent renderer clipping / signature mismatch
    for tbl in ("BASE", "DSIG", "hdmx", "LTSH", "VDMX"):
        if tbl in tt:
            del tt[tbl]


def build_single_font(
    style: str,
    cfg: dict,
    include_nerd_fonts: bool = True,
    include_tc_supplement: bool = True,
    visualize_zenkaku_space: bool = True,
    strip_emoji_overrides: bool = True,
) -> TTFont:
    t0 = time.time()
    m = cfg["metrics"]
    sc = cfg["scaling"]
    p = cfg["project"]

    half_width = int(m["half_width"])
    full_width = int(m["full_width"])
    ascender = int(m["ascender"])
    descender = int(m["descender"])

    base_weight = get_base_weight(style)
    is_italic = "Italic" in style
    is_bold = base_weight == "Bold"

    cjk_skew = math.tan(math.radians(float(sc["cjk_italic_skew_deg"]))) if is_italic else 0.0
    heb_skew = math.tan(math.radians(float(sc["hebrew_italic_skew_deg"]))) if is_italic else 0.0

    # 1. Open base IBM Plex Mono
    mono_path = SOURCES_DIR / "plex-mono" / f"IBMPlexMono-{style}.ttf"
    base_tt = TTFont(mono_path)
    glyf_table = base_tt["glyf"]
    hmtx_table = base_tt["hmtx"]
    glyph_order: list[str] = list(base_tt.getGlyphOrder())
    used_glyph_names: set[str] = set(glyph_order)
    cmap: dict[int, str] = dict(base_tt.getBestCmap())

    def alloc_glyph_name(preferred: str) -> str:
        if preferred not in used_glyph_names:
            used_glyph_names.add(preferred)
            glyph_order.append(preferred)
            return preferred
        i = 1
        while f"{preferred}.{i}" in used_glyph_names:
            i += 1
        unique = f"{preferred}.{i}"
        used_glyph_names.add(unique)
        glyph_order.append(unique)
        return unique

    def set_glyph(u: int, gname_hint: str, glyph_obj: Glyph, adv_width: int) -> str:
        glyph_obj.recalcBounds(glyf_table)
        lsb = getattr(glyph_obj, "xMin", 0) if glyph_obj.numberOfContours != 0 else 0
        if u in cmap:
            existing_name = cmap[u]
            glyf_table[existing_name] = glyph_obj
            hmtx_table[existing_name] = (adv_width, lsb)
            return existing_name
        gname = alloc_glyph_name(gname_hint)
        glyf_table[gname] = glyph_obj
        hmtx_table[gname] = (adv_width, lsb)
        cmap[u] = gname
        return gname

    # Clean up IBM Plex Mono quirks
    if strip_emoji_overrides:
        for emoji_cp in (0x274C, 0x2705):
            cmap.pop(emoji_cp, None)
    # Remove internal Adobe PUA combining marks (U+F6D7, U+F6D8) from cmap so PUA is clean
    for pua_cp in (0xF6D7, 0xF6D8):
        cmap.pop(pua_cp, None)

    # 2. Inject Layer 2: Programmatic Terminal Grid Glyphs (Box Drawing, Block, Braille, Sextants, U+3000)
    prog_glyphs = build_all_programmatic_glyphs(
        half_width=half_width,
        full_width=full_width,
        ymin=descender,
        ymax=ascender,
        visualize_zenkaku_space=visualize_zenkaku_space,
    )
    for u, (gname_hint, g_obj, adv_w) in prog_glyphs.items():
        set_glyph(u, gname_hint, g_obj, adv_w)

    # 3. Inject Layer 3: IBM Plex Sans Hebrew (with GPOS MarkToBase preservation)
    heb_path = SOURCES_DIR / "plex-sans-hebrew" / f"IBMPlexSansHebrew-{base_weight}.ttf"
    heb_tt = TTFont(heb_path)
    heb_cmap = heb_tt.getBestCmap()
    heb_gset = heb_tt.getGlyphSet()
    heb_glyph_map: dict[str, str] = {}
    heb_transforms: dict[str, tuple[float, float, float, float, float]] = {}

    for u, src_gname in sorted(heb_cmap.items()):
        if not ((0x0590 <= u <= 0x05FF) or (0xFB1D <= u <= 0xFB4F) or u == 0x20AA):
            continue
        if u in cmap and u != 0x20AA:
            continue

        bb = get_glyph_bbox(heb_tt, src_gname)
        if is_zero_width_codepoint(u):
            # Zero-width Hebrew Niqqud / Cantillation mark:
            # Shift outline & GPOS MarkAnchor by -half_width/2 (-300) so both HarfBuzz GPOS
            # AND simple non-GPOS cell renderers center the vowel point on the preceding consonant!
            sx, sy = 1.0, 1.0
            shx = heb_skew
            dx = -half_width / 2.0
            dy = 0.0
            g_obj = draw_transformed_glyph(heb_gset, src_gname, sx=sx, shx=shx, sy=sy, dx=dx, dy=dy)
            dst_gname = set_glyph(u, f"heb_{src_gname}", g_obj, 0)
        else:
            # 1-cell Hebrew consonant / punctuation / New Sheqel sign
            max_w = half_width * float(sc["hebrew_max_fill_ratio"])  # 510
            sy = float(sc["hebrew_scale_y"])
            shx = heb_skew
            if bb is not None:
                gw = bb[2] - bb[0]
                g_cx = (bb[0] + bb[2]) / 2.0
                g_cy = (bb[1] + bb[3]) / 2.0
                sx = min(1.0, max_w / gw) if gw > 0 else 1.0
                dx = (half_width / 2.0) - (g_cx * sx + g_cy * shx)
                dy = 0.0
                g_obj = draw_transformed_glyph(heb_gset, src_gname, sx=sx, shx=shx, sy=sy, dx=dx, dy=dy)
            else:
                sx, dx, dy = 1.0, 0.0, 0.0
                g_obj = Glyph()
            dst_gname = set_glyph(u, f"heb_{src_gname}", g_obj, half_width)

        heb_glyph_map[src_gname] = dst_gname
        heb_transforms[src_gname] = (sx, shx, sy, dx, dy)

    merge_hebrew_gpos_marks(base_tt, heb_tt, heb_glyph_map, heb_transforms, glyph_order)

    # 4. Inject Layer 4: IBM Plex Math (Native Technical, Mathematical, Arrow, Geometric & Dingbat Symbols)
    math_path = SOURCES_DIR / "plex-math" / "IBMPlexMath-Regular.ttf"
    math_tt = TTFont(math_path)
    math_cmap = math_tt.getBestCmap()
    math_gset = math_tt.getGlyphSet()

    for u, src_gname in sorted(math_cmap.items()):
        if u in cmap:
            continue
        if strip_emoji_overrides and u in (0x274C, 0x2705):
            continue
        # Skip Math Alphanumeric Supplementary Plane (U+1D400..U+1D7FF) only if not needed?
        # Wait: keeping U+1D400..U+1D7FF adds double-struck/script math letters and we have plenty of glyph headroom!
        target_w = get_target_cell_width(u, half_width, full_width)
        bb = get_glyph_bbox(math_tt, src_gname)
        if target_w == 0:
            dx = -half_width / 2.0 if bb is not None and bb[0] >= -100 else 0.0
            g_obj = draw_transformed_glyph(math_gset, src_gname, sx=1.0, shx=cjk_skew, sy=1.0, dx=dx, dy=0.0)
            set_glyph(u, f"math_{u:04X}", g_obj, 0)
        else:
            if bb is not None:
                gw = bb[2] - bb[0]
                gh = bb[3] - bb[1]
                g_cx = (bb[0] + bb[2]) / 2.0
                g_cy = (bb[1] + bb[3]) / 2.0
                max_box_w = target_w - 84.0  # 516 for 1-cell, 1116 for 2-cell
                max_box_h = (ascender - descender) - 120.0  # 1020
                scale = 1.0
                if gw > max_box_w and gw > 0:
                    scale = min(scale, max_box_w / gw)
                if gh > max_box_h and gh > 0:
                    scale = min(scale, max_box_h / gh)
                # Slight weight boost when synthesizing Bold from Regular Math
                sx = scale * (1.03 if is_bold else 1.0)
                sy = scale * (1.02 if is_bold else 1.0)
                dx = (target_w / 2.0) - (g_cx * sx + g_cy * cjk_skew)
                dy = 0.0
                g_obj = draw_transformed_glyph(
                    math_gset, src_gname, sx=sx, shx=cjk_skew, sy=sy, dx=dx, dy=dy
                )
            else:
                g_obj = Glyph()
            set_glyph(u, f"math_{u:04X}", g_obj, target_w)

    # 5. Inject Layer 5: IBM Plex Sans KR (Hangul Syllables 11,172 + Jamo + KR Symbols)
    kr_path = SOURCES_DIR / "plex-sans-kr" / f"IBMPlexSansKR-{base_weight}.ttf"
    kr_tt = TTFont(kr_path)
    kr_cmap = kr_tt.getBestCmap()
    kr_gset = kr_tt.getGlyphSet()
    kr_hmtx = kr_tt["hmtx"]

    kr_sx = float(sc["kr_scale_x"])
    kr_sy = float(sc["kr_scale_y"])
    kr_dy = float(sc["kr_shift_y"])

    for u, src_gname in sorted(kr_cmap.items()):
        if u in cmap:
            continue
        # Exclude proportional Latin/Greek/Cyrillic below U+1100 (except currency U+20A9 Won)
        if u < 0x1100:
            continue
        if strip_emoji_overrides and u in (0x274C, 0x2705):
            continue

        target_w = get_target_cell_width(u, half_width, full_width)
        if target_w == 0:
            g_obj = draw_transformed_glyph(kr_gset, src_gname, sx=1.0, shx=cjk_skew, sy=1.0, dx=0.0, dy=0.0)
            set_glyph(u, f"kr_{u:04X}", g_obj, 0)
        elif target_w == full_width:
            # 2-cell Fullwidth Hangul / CJK symbol
            orig_w = kr_hmtx[src_gname][0] or 892
            g_cy = 330.0
            dx = (full_width - orig_w * kr_sx) / 2.0 - g_cy * cjk_skew
            g_obj = draw_transformed_glyph(
                kr_gset, src_gname, sx=kr_sx, shx=cjk_skew, sy=kr_sy, dx=dx, dy=kr_dy
            )
            set_glyph(u, f"kr_{u:04X}", g_obj, full_width)
        else:
            # 1-cell Halfwidth symbol from KR (e.g., U+20A9 Won sign or EAW=A symbol)
            bb = get_glyph_bbox(kr_tt, src_gname)
            if bb is not None:
                gw = bb[2] - bb[0]
                g_cx = (bb[0] + bb[2]) / 2.0
                g_cy = (bb[1] + bb[3]) / 2.0
                max_w = half_width - 84.0  # 516
                s = min(1.0, max_w / gw) if gw > 0 else 1.0
                dx = (half_width / 2.0) - (g_cx * s + g_cy * cjk_skew)
                g_obj = draw_transformed_glyph(
                    kr_gset, src_gname, sx=s, shx=cjk_skew, sy=min(1.0, s * 1.05), dx=dx, dy=0.0
                )
            else:
                g_obj = Glyph()
            set_glyph(u, f"kr_{u:04X}", g_obj, half_width)

    # Populate ALL 67 modern Hangul Conjoining Jamo (U+1100..U+1112, U+1161..U+1175, U+11A8..U+11C2)
    # as dedicated glyphs so NFD filenames never trigger fallback and Compatibility Jamo (U+3131..U+3163) remain untouched.
    cur_gset = base_tt.getGlyphSet()
    choseong_to_compat = [
        0x3131, 0x3132, 0x3134, 0x3137, 0x3138, 0x3139, 0x3141, 0x3142, 0x3143,
        0x3145, 0x3146, 0x3147, 0x3148, 0x3149, 0x314A, 0x314B, 0x314C, 0x314D, 0x314E,
    ]
    for idx, compat_u in enumerate(choseong_to_compat):
        cho_u = 0x1100 + idx
        if cho_u not in cmap and compat_u in cmap:
            g_obj = draw_transformed_glyph(cur_gset, cmap[compat_u])
            set_glyph(cho_u, f"jamo_{cho_u:04X}", g_obj, full_width)

    # Jungseong medial vowels (U+1161..U+1175 -> 0x314F..0x3163, wcwidth == 0)
    for idx in range(21):
        jung_u = 0x1161 + idx
        compat_u = 0x314F + idx
        if jung_u not in cmap and compat_u in cmap:
            g_obj = draw_transformed_glyph(cur_gset, cmap[compat_u], sx=0.65, sy=0.80, dx=-520.0, dy=60.0)
            set_glyph(jung_u, f"jamo_{jung_u:04X}", g_obj, 0)

    # Jongseong trailing consonants (U+11A8..U+11C2, wcwidth == 0)
    jong_compat = [u for u in range(0x3131, 0x314F) if u not in (0x3138, 0x3143, 0x3149)]
    for idx, compat_u in enumerate(jong_compat):
        jong_u = 0x11A8 + idx
        if jong_u not in cmap and compat_u in cmap:
            g_obj = draw_transformed_glyph(cur_gset, cmap[compat_u], sx=0.60, sy=0.55, dx=-960.0, dy=-120.0)
            set_glyph(jong_u, f"jamo_{jong_u:04X}", g_obj, 0)

    # Hangul Jamo Fillers (U+115F Choseong Filler = 1200, U+1160 Jungseong Filler = 0)
    if 0x115F not in cmap:
        set_glyph(0x115F, "jamo_115F", Glyph(), full_width)
    if 0x1160 not in cmap:
        set_glyph(0x1160, "jamo_1160", Glyph(), 0)

    # 6. Inject Layer 6: IBM Plex Sans JP (Hiragana, Katakana, 14,800+ Kanji, CJK Punctuation)
    jp_path = SOURCES_DIR / "plex-sans-jp" / f"IBMPlexSansJP-{base_weight}.ttf"
    jp_tt = TTFont(jp_path)
    jp_cmap = jp_tt.getBestCmap()
    jp_gset = jp_tt.getGlyphSet()
    jp_hmtx = jp_tt["hmtx"]

    jp_sx = float(sc["jp_scale_x"])
    jp_sy = float(sc["jp_scale_y"])
    jp_dy = float(sc["jp_shift_y"])

    for u, src_gname in sorted(jp_cmap.items()):
        if u in cmap:
            continue
        # Crucial: Discard JP's 105%-scaled Latin/Greek/Cyrillic (< U+2000)
        if u < 0x2000:
            continue
        if strip_emoji_overrides and u in (0x274C, 0x2705):
            continue

        target_w = get_target_cell_width(u, half_width, full_width)
        if target_w == 0:
            # Shift U+3099/U+309A fallback left into preceding 2-cell kana top-right corner
            dx = -340.0 if u in (0x3099, 0x309A) else 0.0
            g_obj = draw_transformed_glyph(jp_gset, src_gname, sx=1.0, shx=cjk_skew, sy=1.0, dx=dx, dy=0.0)
            set_glyph(u, f"jp_{u:04X}", g_obj, 0)
        elif target_w == full_width:
            orig_w = jp_hmtx[src_gname][0] or 1000
            g_cy = 350.0
            sx, sy = jp_sx, jp_sy
            extra_dx = 0.0
            if u in FULLWIDTH_OPEN_BRACKETS:
                extra_dx = -80.0
            elif u in FULLWIDTH_CLOSE_BRACKETS:
                extra_dx = 80.0
            elif u in FULLWIDTH_CORNER_PUNCT:
                sx *= 1.20
                sy *= 1.20
            dx = (full_width - orig_w * sx) / 2.0 + extra_dx - g_cy * cjk_skew
            g_obj = draw_transformed_glyph(
                jp_gset, src_gname, sx=sx, shx=cjk_skew, sy=sy, dx=dx, dy=jp_dy
            )
            set_glyph(u, f"jp_{u:04X}", g_obj, full_width)
        else:
            # 1-cell Halfwidth Katakana (U+FF61..U+FF9F) or EAW=A/N symbol
            bb = get_glyph_bbox(jp_tt, src_gname)
            if bb is not None:
                gw = bb[2] - bb[0]
                g_cx = (bb[0] + bb[2]) / 2.0
                g_cy = (bb[1] + bb[3]) / 2.0
                max_w = half_width - 84.0
                s = min(1.0, max_w / gw) if gw > 0 else 1.0
                dx = (half_width / 2.0) - (g_cx * s + g_cy * cjk_skew)
                g_obj = draw_transformed_glyph(
                    jp_gset, src_gname, sx=s, shx=cjk_skew, sy=min(1.0, s * 1.05), dx=dx, dy=jp_dy * 0.5
                )
            else:
                g_obj = Glyph()
            set_glyph(u, f"jp_{u:04X}", g_obj, half_width)

    # 7. Inject Layer 7: Korean KS X 1001 Hanja Supplement from IBM Plex Sans TC + NFKD Compatibility Ideographs
    ks_hanja = get_ks_x_1001_hanja()
    if include_tc_supplement:
        tc_path = SOURCES_DIR / "plex-sans-tc" / f"IBMPlexSansTC-{base_weight}.ttf"
        if tc_path.exists():
            tc_tt = TTFont(tc_path)
            tc_cmap = tc_tt.getBestCmap()
            tc_gset = tc_tt.getGlyphSet()
            tc_hmtx = tc_tt["hmtx"]
            tc_sx = float(sc["tc_scale_x"])
            tc_sy = float(sc["tc_scale_y"])
            tc_dy = float(sc["tc_shift_y"])

            for u in sorted(ks_hanja):
                if u in cmap or u not in tc_cmap:
                    continue
                src_gname = tc_cmap[u]
                orig_w = tc_hmtx[src_gname][0] or 1000
                dx = (full_width - orig_w * tc_sx) / 2.0 - 350.0 * cjk_skew
                g_obj = draw_transformed_glyph(
                    tc_gset, src_gname, sx=tc_sx, shx=cjk_skew, sy=tc_sy, dx=dx, dy=tc_dy
                )
                set_glyph(u, f"tc_{u:04X}", g_obj, full_width)

    # Map any remaining unmapped CJK Compatibility Ideographs (U+F900..U+FAFF) & KS Hanja via canonical NFKD
    for u in sorted(ks_hanja | set(range(0xF900, 0xFB00))):
        if u not in cmap:
            decomp = unicodedata.normalize("NFKD", chr(u))
            if len(decomp) == 1 and ord(decomp) in cmap:
                cmap[u] = cmap[ord(decomp)]

    # 8. Inject Layer 8: Nerd Fonts (SymbolsNerdFontMono-Regular.ttf, UPM = 2048 -> 600 cell)
    nf_path = SOURCES_DIR / "nerd-fonts" / "SymbolsNerdFontMono-Regular.ttf"
    nf_tt = TTFont(nf_path)
    nf_cmap = nf_tt.getBestCmap()
    nf_gset = nf_tt.getGlyphSet()
    nf_upm = float(nf_tt["head"].unitsPerEm)  # 2048.0
    nf_ascent = float(nf_tt["hhea"].ascent)   # 1638.0
    nf_descent = float(nf_tt["hhea"].descent) # -410.0

    for u, src_gname in sorted(nf_cmap.items()):
        is_pua = (0xE000 <= u <= 0xF8FF) or (0xF0000 <= u <= 0x10FFFF)
        if not include_nerd_fonts and u not in CORE_PROMPT_UNICODES:
            continue
        # --careful behavior: only overwrite PUA or missing standard symbols
        if u in cmap and not is_pua:
            continue
        # Only pull 1-cell compatible codepoints outside PUA
        if not is_pua and get_target_cell_width(u, half_width, full_width) != half_width:
            continue

        bb = get_glyph_bbox(nf_tt, src_gname)
        if bb is None:
            continue

        if 0xE0B0 <= u <= 0xE0D7:
            # Powerline dividers: preserve intentional horizontal edge bleed and map vertical span to [descender, ascender]
            sx = half_width / nf_upm
            sy = (ascender - descender) / (nf_ascent - nf_descent)
            dx = 0.0
            dy = descender - (nf_descent * sy)
            g_obj = draw_transformed_glyph(nf_gset, src_gname, sx=sx, sy=sy, dx=dx, dy=dy)
        elif 0x276C <= u <= 0x2771:
            # Prompt chevrons (❮ ❯ ❰ ❱): scale to match cap-height & prompt visual weight
            gw = bb[2] - bb[0]
            gh = bb[3] - bb[1]
            g_cx = (bb[0] + bb[2]) / 2.0
            g_cy = (bb[1] + bb[3]) / 2.0
            s = min(440.0 / gw, 620.0 / gh) if gw > 0 and gh > 0 else (532.0 / nf_upm)
            dx = (half_width / 2.0) - g_cx * s
            dy = 340.0 - g_cy * s
            g_obj = draw_transformed_glyph(nf_gset, src_gname, sx=s, sy=s, dx=dx, dy=dy)
        else:
            # Standard developer icon: preserve 1:1 aspect ratio and center optically at (300, 330)
            gw = bb[2] - bb[0]
            gh = bb[3] - bb[1]
            g_cx = (bb[0] + bb[2]) / 2.0
            g_cy = (bb[1] + bb[3]) / 2.0
            base_s = 532.0 / nf_upm
            max_w = half_width - 56.0  # 544
            max_h = (ascender - descender) - 140.0  # 1000
            s = base_s
            if gw * s > max_w and gw > 0:
                s = max_w / gw
            if gh * s > max_h and gh > 0:
                s = min(s, max_h / gh)
            dx = (half_width / 2.0) - g_cx * s
            dy = 330.0 - g_cy * s
            g_obj = draw_transformed_glyph(nf_gset, src_gname, sx=s, sy=s, dx=dx, dy=dy)

        set_glyph(u, f"nf_{u:04X}", g_obj, half_width)

    # Ensure standard 1-cell check & cross Dingbats (U+2714..U+2718) are always present and visually distinct
    base_gset = base_tt.getGlyphSet()
    if 0x2714 not in cmap and 0xF00C in nf_cmap:
        src_gname = nf_cmap[0xF00C]
        bb = get_glyph_bbox(nf_tt, src_gname)
        if bb is not None:
            g_cx = (bb[0] + bb[2]) / 2.0
            g_cy = (bb[1] + bb[3]) / 2.0
            sx = 540.0 / nf_upm
            sy = sx * 1.18
            dx = (half_width / 2.0) - g_cx * sx - 350.0 * cjk_skew
            dy = 350.0 - g_cy * sy
            g_obj = draw_transformed_glyph(nf_gset, src_gname, sx=sx, shx=cjk_skew, sy=sy, dx=dx, dy=dy)
            set_glyph(0x2714, "dingbat_2714", g_obj, half_width)

    # Light crosses (✕ U+2715, ✗ U+2717) derived from IBM Plex Mono's crisp × (U+00D7)
    for dst_u in (0x2715, 0x2717):
        if dst_u not in cmap and 0x00D7 in cmap:
            src_gname = cmap[0x00D7]
            bb = get_glyph_bbox(base_tt, src_gname)
            if bb is not None:
                g_cx = (bb[0] + bb[2]) / 2.0
                g_cy = (bb[1] + bb[3]) / 2.0
                s = 1.16 if dst_u == 0x2715 else 1.24
                dx = (half_width / 2.0) - g_cx * s
                dy = 340.0 - g_cy * s
                g_obj = draw_transformed_glyph(base_gset, src_gname, sx=s, sy=s, dx=dx, dy=dy)
                set_glyph(dst_u, f"dingbat_{dst_u:04X}", g_obj, half_width)

    # Heavy crosses (✖ U+2716, ✘ U+2718) from fa-xmark
    for dst_u in (0x2716, 0x2718):
        if dst_u not in cmap and 0xF00D in nf_cmap:
            src_gname = nf_cmap[0xF00D]
            bb = get_glyph_bbox(nf_tt, src_gname)
            if bb is not None:
                g_cx = (bb[0] + bb[2]) / 2.0
                g_cy = (bb[1] + bb[3]) / 2.0
                s = 500.0 / nf_upm
                dx = (half_width / 2.0) - g_cx * s - 340.0 * cjk_skew
                dy = 340.0 - g_cy * s
                g_obj = draw_transformed_glyph(nf_gset, src_gname, sx=s, shx=cjk_skew, sy=s, dx=dx, dy=dy)
                set_glyph(dst_u, f"dingbat_{dst_u:04X}", g_obj, half_width)

    # Ensure Greek NFD combining marks (U+0342 Perispomeni, U+0345 Ypogegrammeni) exist in cmap
    cur_gset_final = base_tt.getGlyphSet()
    if 0x0342 not in cmap and 0x0303 in cmap:
        g_obj = draw_transformed_glyph(cur_gset_final, cmap[0x0303])
        set_glyph(0x0342, "comb_0342", g_obj, 0)
    if 0x0345 not in cmap and 0x03B9 in cmap:
        iota_bb = get_glyph_bbox(base_tt, cmap[0x03B9])
        if iota_bb is not None:
            g_cx = (iota_bb[0] + iota_bb[2]) / 2.0
            g_obj = draw_transformed_glyph(
                cur_gset_final, cmap[0x03B9], sx=0.45, sy=0.42, dx=-half_width / 2.0 - g_cx * 0.45, dy=-210.0
            )
            set_glyph(0x0345, "comb_0345", g_obj, 0)

    # 9. Finalize glyph order, GSUB NFD->NFC compositions, cmap, metrics, and name tables
    base_tt.setGlyphOrder(glyph_order)
    add_nfd_composition_gsub(base_tt, cmap, glyph_order)
    configure_cmap_tables(base_tt, cmap)
    set_style_flags(base_tt, style, cfg)

    family_name = p["nf_name"] if include_nerd_fonts else p["name"]
    configure_name_table(
        base_tt,
        family_name=family_name,
        style=style,
        version=p["version"],
        copyright_str=p["copyright"],
        license_url=p["license_url"],
        vendor_url=p["repo_url"],
    )

    dt = time.time() - t0
    print(
        f"  [built] {family_name:14s} | {style:16s} | glyphs={len(glyph_order):5d} | cmap={len(cmap):5d} | {dt:.1f}s"
    )
    return base_tt


def save_ttc_bundle(fonts: list[TTFont], dest_path: Path) -> None:
    ttc = TTCollection()
    ttc.fonts = fonts
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    ttc.save(str(dest_path), shareTables=True)
    size_mb = dest_path.stat().st_size / (1024 * 1024)
    print(f"  [ttc]   {dest_path.relative_to(ROOT_DIR)} ({size_mb:.2f} MB, {len(fonts)} faces)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build TermVR Mono & TermVR Mono NF font family.")
    parser.add_argument(
        "--all-weights",
        action="store_true",
        help="Build all 16 styles (Thin..Bold x Roman/Italic) instead of core 4 styles.",
    )
    parser.add_argument(
        "--styles",
        nargs="+",
        help="Explicit list of styles to build (e.g. Regular Bold Italic BoldItalic).",
    )
    parser.add_argument(
        "--variant",
        choices=("both", "nf", "base"),
        default="both",
        help="Which font family variant(s) to build (default: both TermVR Mono NF and TermVR Mono).",
    )
    parser.add_argument(
        "--no-tc",
        action="store_true",
        help="Disable Korean KS X 1001 Hanja supplement from IBM Plex Sans TC.",
    )
    parser.add_argument(
        "--hidden-zenkaku-space",
        action="store_true",
        help="Keep U+3000 Ideographic Space invisible instead of corner-tick visualization.",
    )
    parser.add_argument(
        "--keep-emoji-glyphs",
        action="store_true",
        help="Keep monochrome U+274C/U+2705 glyphs instead of deferring to color emoji fallback.",
    )
    parser.add_argument(
        "--no-ttc",
        action="store_true",
        help="Skip building .ttc (TrueType Collection) bundle.",
    )
    args = parser.parse_args()

    with CONFIG_PATH.open("rb") as f:
        cfg = tomllib.load(f)

    if args.styles:
        styles = args.styles
    elif args.all_weights:
        styles = cfg["styles"]["all"]
    else:
        styles = cfg["styles"]["core"]

    include_tc = cfg["options"]["include_kr_hanja_supplement"] and not args.no_tc
    vis_zenkaku = cfg["options"]["visualize_zenkaku_space"] and not args.hidden_zenkaku_space
    strip_emoji = cfg["options"]["strip_color_emoji_overrides"] and not args.keep_emoji_glyphs

    # Ensure upstream sources exist
    fetch_all_sources(styles=styles, include_tc=include_tc, force=False)

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    variants: list[tuple[bool, str]] = []
    if args.variant in ("both", "nf"):
        variants.append((True, cfg["project"]["nf_family_slug"]))
    if args.variant in ("both", "base"):
        variants.append((False, cfg["project"]["family_slug"]))

    for is_nf, slug in variants:
        print(f"\n=== Building {slug} ({len(styles)} styles) ===")
        built_fonts: list[TTFont] = []
        out_subdir = DIST_DIR / "ttf"
        out_subdir.mkdir(parents=True, exist_ok=True)

        for style in styles:
            tt = build_single_font(
                style=style,
                cfg=cfg,
                include_nerd_fonts=is_nf,
                include_tc_supplement=include_tc,
                visualize_zenkaku_space=vis_zenkaku,
                strip_emoji_overrides=strip_emoji,
            )
            ttf_path = out_subdir / f"{slug}-{style}.ttf"
            tt.save(str(ttf_path))
            size_mb = ttf_path.stat().st_size / (1024 * 1024)
            print(f"          -> saved {ttf_path.relative_to(ROOT_DIR)} ({size_mb:.2f} MB)")
            built_fonts.append(TTFont(str(ttf_path)))

        if not args.no_ttc and len(built_fonts) > 1:
            ttc_path = DIST_DIR / "ttc" / f"{slug}.ttc"
            save_ttc_bundle(built_fonts, ttc_path)


if __name__ == "__main__":
    main()
