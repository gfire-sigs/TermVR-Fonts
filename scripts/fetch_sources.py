#!/usr/bin/env python3
"""
Fetch pinned upstream source fonts for TermVR Mono:
  1. IBM Plex Mono (Roman & Italic)
  2. IBM Plex Math (Regular)
  3. IBM Plex Sans Hebrew (Upright weights)
  4. IBM Plex Sans KR (Unhinted TTF upright weights)
  5. IBM Plex Sans JP (Unhinted TTF upright weights)
  6. IBM Plex Sans TC (Unhinted TTF upright weights - for Korean Hanja supplement)
  7. Nerd Fonts Symbols Only (SymbolsNerdFontMono-Regular.ttf)
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import tarfile
import tomllib
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config" / "build_config.toml"
SOURCES_DIR = ROOT_DIR / "sources"


def get_base_weight(style: str) -> str:
    """Map an Italic/Roman style name to its upright base weight name."""
    if style == "Italic":
        return "Regular"
    if style.endswith("Italic"):
        return style[: -len("Italic")]
    return style


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def download_file(url: str, dest: Path, force: bool = False) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0 and not force:
        print(f"  [cached] {dest.relative_to(ROOT_DIR)} ({dest.stat().st_size / 1024:.1f} KB)")
        return dest

    print(f"  [fetch]  {url} -> {dest.relative_to(ROOT_DIR)}")
    tmp_path = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "TermVR-Fonts-Builder/1.0 (https://github.com/gfire-sigs/TermVR-Fonts)"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp, tmp_path.open("wb") as out:
        shutil.copyfileobj(resp, out)
    tmp_path.replace(dest)
    print(f"           saved ({dest.stat().st_size / 1024:.1f} KB, sha256={sha256_file(dest)[:12]}...)")
    return dest


def fetch_all_sources(styles: list[str], include_tc: bool = True, force: bool = False) -> dict[str, Path]:
    with CONFIG_PATH.open("rb") as f:
        cfg = tomllib.load(f)

    up = cfg["upstream"]
    plex_repo = up["ibm_plex_repo"]
    plex_commit = up["ibm_plex_commit"]
    plex_raw_base = f"https://raw.githubusercontent.com/{plex_repo}/{plex_commit}/packages"

    base_weights = sorted({get_base_weight(s) for s in styles})
    downloaded: dict[str, Path] = {}

    print(f"=== Fetching IBM Plex sources (commit {plex_commit[:10]}) ===")
    # 1. IBM Plex Mono (all requested styles including Italic)
    for style in styles:
        fname = f"IBMPlexMono-{style}.ttf"
        url = f"{plex_raw_base}/plex-mono/fonts/complete/ttf/{fname}"
        dest = SOURCES_DIR / "plex-mono" / fname
        downloaded[f"mono:{style}"] = download_file(url, dest, force=force)

    # 2. IBM Plex Math (Regular)
    math_fname = "IBMPlexMath-Regular.ttf"
    math_url = f"{plex_raw_base}/plex-math/fonts/complete/ttf/{math_fname}"
    downloaded["math:Regular"] = download_file(
        math_url, SOURCES_DIR / "plex-math" / math_fname, force=force
    )

    # 3. IBM Plex Sans Hebrew (upright weights)
    for w in base_weights:
        fname = f"IBMPlexSansHebrew-{w}.ttf"
        url = f"{plex_raw_base}/plex-sans-hebrew/fonts/complete/ttf/{fname}"
        dest = SOURCES_DIR / "plex-sans-hebrew" / fname
        downloaded[f"hebrew:{w}"] = download_file(url, dest, force=force)

    # 4. IBM Plex Sans KR (unhinted TTF upright weights)
    for w in base_weights:
        fname = f"IBMPlexSansKR-{w}.ttf"
        url = f"{plex_raw_base}/plex-sans-kr/fonts/complete/ttf/unhinted/{fname}"
        dest = SOURCES_DIR / "plex-sans-kr" / fname
        downloaded[f"kr:{w}"] = download_file(url, dest, force=force)

    # 5. IBM Plex Sans JP (unhinted TTF upright weights)
    for w in base_weights:
        fname = f"IBMPlexSansJP-{w}.ttf"
        url = f"{plex_raw_base}/plex-sans-jp/fonts/complete/ttf/unhinted/{fname}"
        dest = SOURCES_DIR / "plex-sans-jp" / fname
        downloaded[f"jp:{w}"] = download_file(url, dest, force=force)

    # 6. IBM Plex Sans TC (optional Hanja supplement for KS X 1001)
    if include_tc:
        for w in base_weights:
            fname = f"IBMPlexSansTC-{w}.ttf"
            url = f"{plex_raw_base}/plex-sans-tc/fonts/complete/ttf/unhinted/{fname}"
            dest = SOURCES_DIR / "plex-sans-tc" / fname
            downloaded[f"tc:{w}"] = download_file(url, dest, force=force)

    # 7. Nerd Fonts Symbols Only
    nf_repo = up["nerd_fonts_repo"]
    nf_tag = up["nerd_fonts_tag"]
    nf_asset = up["nerd_fonts_asset"]
    nf_dir = SOURCES_DIR / "nerd-fonts"
    nf_mono_ttf = nf_dir / "SymbolsNerdFontMono-Regular.ttf"
    nf_reg_ttf = nf_dir / "SymbolsNerdFont-Regular.ttf"

    print(f"=== Fetching Nerd Fonts Symbols ({nf_tag}) ===")
    if not (nf_mono_ttf.exists() and nf_reg_ttf.exists()) or force:
        archive_path = nf_dir / nf_asset
        nf_url = f"https://github.com/{nf_repo}/releases/download/{nf_tag}/{nf_asset}"
        download_file(nf_url, archive_path, force=force)
        print(f"  [extract] {archive_path.relative_to(ROOT_DIR)}")
        with tarfile.open(archive_path, "r:xz") as tar:
            for member in tar.getmembers():
                mname = Path(member.name).name
                if mname in ("SymbolsNerdFontMono-Regular.ttf", "SymbolsNerdFont-Regular.ttf", "LICENSE"):
                    member.name = mname
                    if hasattr(tarfile, "data_filter"):
                        tar.extract(member, path=nf_dir, filter="data")
                    else:
                        tar.extract(member, path=nf_dir)
    else:
        print(f"  [cached] {nf_mono_ttf.relative_to(ROOT_DIR)}")

    downloaded["nerdfont:Mono"] = nf_mono_ttf
    downloaded["nerdfont:Regular"] = nf_reg_ttf
    return downloaded


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch pinned source fonts for TermVR Mono.")
    parser.add_argument(
        "--all-weights",
        action="store_true",
        help="Fetch all 16 styles (8 weights x Roman/Italic) instead of core 4 styles.",
    )
    parser.add_argument(
        "--styles",
        nargs="+",
        help="Explicit list of styles to fetch (e.g. Regular Bold Italic BoldItalic).",
    )
    parser.add_argument(
        "--no-tc",
        action="store_true",
        help="Skip downloading IBM Plex Sans TC (Korean Hanja supplement).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download even if cached files exist.",
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

    fetch_all_sources(styles=styles, include_tc=not args.no_tc, force=args.force)
    print("=== Source fetch complete ===")


if __name__ == "__main__":
    main()
