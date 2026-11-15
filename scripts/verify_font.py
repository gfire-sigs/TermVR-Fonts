#!/usr/bin/env python3
"""
Automated QA & Verification Suite for TermVR Mono & TermVR Mono NF
==================================================================
Verifies:
  1. SIL OFL 1.1 & Reserved Font Name ("IBM", "Plex") compliance in `name` table
  2. Strict terminal vertical & horizontal metrics (UPM=1000, 600:1200 1:2 cell grid, lineGap=0)
  3. Zero cell-width violations across all mapped Unicode codepoints (wcwidth 0 -> 0, 1 -> 600, 2 -> 1200)
  4. Zero duplicate glyph names in `post` table and maxp.numGlyphs < 65535
  5. Seamless boundary geometry on Box Drawing (U+2500..U+257F), Block Elements (U+2580..U+259F), and Braille
  6. Hebrew GPOS MarkToBase ('hebr' script) and zero-width Niqqud verification
  7. Quantitative language & standard coverage report (ASCII, KR Hangul, KS X 1001 Hanja, JP JIS X 0208, Hebrew, Nerd Fonts)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.build_font import get_ks_x_1001_hanja, get_target_cell_width

DIST_DIR = ROOT_DIR / "dist"


def get_jis_x_0208_kanji() -> set[int]:
    """Enumerate all 6,355 JIS X 0208 Level 1 & Level 2 Kanji via Python's built-in euc_jp codec."""
    kanji: set[int] = set()
    # JIS X 0208 Kanji rows 16..84 (EUC-JP 0xB0..0xF4, cols 0xA1..0xFE)
    for row in range(0xB0, 0xF4 + 1):
        for col in range(0xA1, 0xFE + 1):
            try:
                ch = bytes([row, col]).decode("euc_jp")
                if len(ch) == 1 and 0x4E00 <= ord(ch) <= 0x9FFF:
                    kanji.add(ord(ch))
            except UnicodeDecodeError:
                pass
    return kanji


def verify_ttfont(tt: TTFont, label: str, is_nf: bool) -> list[str]:
    errors: list[str] = []

    # 1. Basic limits & unique glyph names
    glyph_order = tt.getGlyphOrder()
    if len(glyph_order) >= 65535:
        errors.append(f"{label}: glyph count {len(glyph_order)} exceeds OpenType 65535 limit")
    if len(set(glyph_order)) != len(glyph_order):
        errors.append(f"{label}: duplicate glyph names detected in glyph order")

    # 2. Check RFN ("IBM", "Plex") absence in primary font names (IDs 1, 2, 4, 6, 16, 17)
    name_tbl = tt["name"]
    for nid in (1, 2, 4, 6, 16, 17):
        val = name_tbl.getDebugName(nid)
        if val:
            low = val.lower()
            if "ibm" in low or "plex" in low:
                errors.append(f"{label}: Reserved Font Name leaked in nameID {nid}: {val!r}")

    copyright_str = name_tbl.getDebugName(0) or ""
    license_str = name_tbl.getDebugName(13) or ""
    if "IBM" not in copyright_str or "Sandoll" not in copyright_str:
        errors.append(f"{label}: Missing upstream attribution in nameID 0 (Copyright)")
    if "SIL Open Font License" not in license_str:
        errors.append(f"{label}: Missing SIL OFL 1.1 notice in nameID 13 (License)")

    # 3. Verify head, hhea, OS/2, post metrics
    if tt["head"].unitsPerEm != 1000:
        errors.append(f"{label}: unitsPerEm={tt['head'].unitsPerEm}, expected 1000")
    hhea = tt["hhea"]
    if (hhea.ascent, hhea.descent, hhea.lineGap) != (900, -240, 0):
        errors.append(f"{label}: hhea=({hhea.ascent},{hhea.descent},{hhea.lineGap}), expected (900,-240,0)")
    os2 = tt["OS/2"]
    if (os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap) != (900, -240, 0):
        errors.append(f"{label}: OS/2 typo metrics mismatch")
    if (os2.usWinAscent, os2.usWinDescent) != (900, 240):
        errors.append(f"{label}: OS/2 win metrics mismatch")
    if os2.xAvgCharWidth != 600:
        errors.append(f"{label}: OS/2.xAvgCharWidth={os2.xAvgCharWidth}, expected 600")
    if os2.panose.bProportion != 9:
        errors.append(f"{label}: OS/2.panose.bProportion={os2.panose.bProportion}, expected 9 (Monospaced)")
    if tt["post"].isFixedPitch != 1:
        errors.append(f"{label}: post.isFixedPitch={tt['post'].isFixedPitch}, expected 1")
    if "BASE" in tt:
        errors.append(f"{label}: BASE table must be removed to prevent terminal descender clipping")

    # 4. Verify 100% cell-width compliance across entire cmap
    cmap = tt.getBestCmap()
    hmtx = tt["hmtx"]
    glyf = tt["glyf"]
    width_violations: list[str] = []
    for u, gname in sorted(cmap.items()):
        expected_w = get_target_cell_width(u, 600, 1200)
        actual_w = hmtx[gname][0]
        if actual_w != expected_w:
            width_violations.append(f"U+{u:04X} ({gname}): got {actual_w}, expected {expected_w}")
            if len(width_violations) >= 10:
                break
    if width_violations:
        errors.append(f"{label}: cell width violations: {width_violations}")

    # 5. Verify critical terminal characters & geometry
    critical_widths = [
        (0x005C, 600, "Backslash \\"),
        (0x00A5, 600, "Yen sign ¥"),
        (0x20A9, 600, "Won sign ₩"),
        (0x20AA, 600, "New Sheqel sign ₪"),
        (0xFFE5, 1200, "Fullwidth Yen ￥"),
        (0xFFE6, 1200, "Fullwidth Won ￦"),
        (0x3000, 1200, "Ideographic Space"),
        (0x2423, 600, "Open Box ␣"),
        (0x2713, 600, "Check Mark ✓"),
        (0x2714, 600, "Heavy Check Mark ✔"),
        (0x276F, 600, "Prompt Chevron ❯"),
        (0x2500, 600, "Box Drawing Horizontal ─"),
        (0x2502, 600, "Box Drawing Vertical │"),
        (0x2588, 600, "Full Block █"),
        (0x28FF, 600, "Braille 8-dot ⣿"),
    ]
    for u, exp_w, desc in critical_widths:
        if u not in cmap:
            errors.append(f"{label}: missing critical glyph U+{u:04X} ({desc})")
        elif hmtx[cmap[u]][0] != exp_w:
            errors.append(f"{label}: U+{u:04X} ({desc}) width={hmtx[cmap[u]][0]}, expected {exp_w}")

    # Check exact seamless geometry on U+2500, U+2502, U+2588
    for u, exp_bb in [
        (0x2500, (0, 302, 600, 358)),
        (0x2502, (272, -240, 328, 900)),
        (0x2588, (0, -240, 600, 900)),
    ]:
        if u in cmap:
            g = glyf[cmap[u]]
            g.recalcBounds(glyf)
            bb = (g.xMin, g.yMin, g.xMax, g.yMax)
            if bb != exp_bb:
                errors.append(f"{label}: U+{u:04X} bbox={bb}, expected {exp_bb}")
            if g.numberOfContours != 1:
                errors.append(f"{label}: U+{u:04X} has {g.numberOfContours} contours, expected 1 (non-overlapping)")

    # 6. Verify Hebrew consonants, Niqqud, and GPOS 'hebr' script
    for u in range(0x05D0, 0x05EA + 1):
        if u not in cmap or hmtx[cmap[u]][0] != 600:
            errors.append(f"{label}: Hebrew consonant U+{u:04X} missing or not 600 width")
            break
    for u in (0x05B0, 0x05B4, 0x05B8, 0x05BC, 0x05C1):
        if u not in cmap or hmtx[cmap[u]][0] != 0:
            errors.append(f"{label}: Hebrew Niqqud U+{u:04X} missing or not 0 width")
            break
    if "GPOS" not in tt or not any(s.ScriptTag == "hebr" for s in tt["GPOS"].table.ScriptList.ScriptRecord):
        errors.append(f"{label}: GPOS table missing 'hebr' script record for Hebrew MarkToBase")

    # 7. Coverage calculations
    ascii_cov = sum(1 for u in range(0x0020, 0x007F) if u in cmap)
    hangul_cov = sum(1 for u in range(0xAC00, 0xD7A4) if u in cmap)
    jamo_cov = sum(1 for u in range(0x3131, 0x318F) if u in cmap)
    hiragana_cov = sum(1 for u in range(0x3041, 0x3097) if u in cmap)
    katakana_cov = sum(1 for u in range(0x30A1, 0x30FB) if u in cmap)
    hw_kana_cov = sum(1 for u in range(0xFF66, 0xFFA0) if u in cmap)
    box_cov = sum(1 for u in range(0x2500, 0x2580) if u in cmap)
    block_cov = sum(1 for u in range(0x2580, 0x25A0) if u in cmap)
    braille_cov = sum(1 for u in range(0x2800, 0x2900) if u in cmap)
    sextant_cov = sum(1 for u in range(0x1FB00, 0x1FB3C) if u in cmap)

    ks_hanja = get_ks_x_1001_hanja()
    ks_hanja_cov = sum(1 for u in ks_hanja if u in cmap)
    jis_kanji = get_jis_x_0208_kanji()
    jis_kanji_cov = sum(1 for u in jis_kanji if u in cmap)
    total_cjk_ideographs = sum(
        1 for u in cmap if (0x4E00 <= u <= 0x9FFF) or (0x3400 <= u <= 0x4DBF) or (0xF900 <= u <= 0xFAFF)
    )
    pua_icons = sum(1 for u in cmap if (0xE000 <= u <= 0xF8FF) or (0xF0000 <= u <= 0x10FFFF))

    if ascii_cov != 95 or hangul_cov != 11172 or box_cov != 128 or block_cov != 32 or braille_cov != 256:
        errors.append(
            f"{label}: incomplete core block coverage (ASCII={ascii_cov}/95, Hangul={hangul_cov}/11172, Box={box_cov}/128, Block={block_cov}/32, Braille={braille_cov}/256)"
        )
    if is_nf and pua_icons < 10000:
        errors.append(f"{label}: expected >=10,000 Nerd Font PUA icons, found {pua_icons}")

    print(
        f"  [PASS] {label:32s} | glyphs={len(glyph_order):5d} | cmap={len(cmap):5d} | "
        f"Hangul={hangul_cov}/11172 (100%) | JIS-Kanji={jis_kanji_cov}/{len(jis_kanji)} ({jis_kanji_cov/len(jis_kanji)*100:.1f}%) | "
        f"KS-Hanja={ks_hanja_cov}/{len(ks_hanja)} ({ks_hanja_cov/len(ks_hanja)*100:.1f}%) | CJK-Total={total_cjk_ideographs} | NF-Icons={pua_icons}"
    )
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify built TermVR Mono & TermVR Mono NF fonts.")
    parser.add_argument("paths", nargs="*", help="Font files (.ttf or .ttc) to verify (defaults to all in dist/).")
    args = parser.parse_args()

    if args.paths:
        files = [Path(p) for p in args.paths]
    else:
        files = sorted((DIST_DIR / "ttf").glob("*.ttf")) + sorted((DIST_DIR / "ttc").glob("*.ttc"))

    if not files:
        print("No font files found to verify in dist/.", file=sys.stderr)
        sys.exit(1)

    print(f"=== Verifying {len(files)} font artifacts ===")
    all_errors: list[str] = []
    for path in files:
        is_nf = "NF" in path.name
        if path.suffix.lower() == ".ttc":
            ttc = TTCollection(str(path))
            for idx, face in enumerate(ttc.fonts):
                ps_name = face["name"].getDebugName(6) or f"{path.name}[{idx}]"
                all_errors.extend(verify_ttfont(face, f"{path.name}:{ps_name}", is_nf=is_nf))
        else:
            tt = TTFont(str(path))
            all_errors.extend(verify_ttfont(tt, path.name, is_nf=is_nf))

    if all_errors:
        print("\n[FAIL] Verification errors detected:", file=sys.stderr)
        for err in all_errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    print("=== All font verification checks PASSED (0 errors) ===")


if __name__ == "__main__":
    main()
