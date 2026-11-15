#!/usr/bin/env bash
# ==============================================================================
# TermVR Mono Nerd Font Patching & Synthesis Script
# ==============================================================================
# Supports two reproducible modes:
#   1. Default ("builtin"): Uses scripts/build_font.py to deterministically
#      extract, scale (2048 -> 1000 UPM), and center all 10,615+ icons from
#      pinned SymbolsNerdFontMono-Regular.ttf (v3.5.1) into exact 600-unit
#      1-cell glyphs while preserving 1200-unit CJK/Hangul fullwidth metrics.
#   2. Upstream FontForge ("font-patcher"): Runs official ryanoasis/nerd-fonts
#      FontPatcher (via local fontforge or Docker nerdfonts/patcher) with
#      `--mono --careful --complete`, followed by a CJK 1200-width restoration
#      pass so FontPatcher's `--mono` flag does not crush 2-cell CJK glyphs.
# ==============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${ROOT_DIR}/.venv/bin/python}"
if [[ ! -x "${PYTHON_BIN}" ]]; then
    PYTHON_BIN="python3"
fi

MODE="${1:-builtin}"

case "${MODE}" in
    builtin|--builtin)
        echo "[TermVR-Fonts] Building TermVR Mono NF via deterministic SymbolsNerdFontMono synthesizer..."
        "${PYTHON_BIN}" "${ROOT_DIR}/scripts/build_font.py" --variant nf "${@:2}"
        "${PYTHON_BIN}" "${ROOT_DIR}/scripts/verify_font.py"
        ;;
    font-patcher|--font-patcher)
        INPUT_TTF="${2:-${ROOT_DIR}/dist/ttf/TermVRMono-Regular.ttf}"
        OUT_DIR="${3:-${ROOT_DIR}/dist/ttf}"
        if [[ ! -f "${INPUT_TTF}" ]]; then
            echo "[TermVR-Fonts] Base font ${INPUT_TTF} not found; building base variant first..."
            "${PYTHON_BIN}" "${ROOT_DIR}/scripts/build_font.py" --variant base --no-ttc
        fi
        if command -v fontforge >/dev/null 2>&1 && [[ -f "${NERDFONTS_PATCHER:-font-patcher}" ]]; then
            echo "[TermVR-Fonts] Running local FontForge font-patcher (--mono --careful --complete)..."
            fontforge -script "${NERDFONTS_PATCHER:-font-patcher}" \
                --mono --careful --complete --outputdir "${OUT_DIR}" "${INPUT_TTF}"
        elif command -v docker >/dev/null 2>&1; then
            echo "[TermVR-Fonts] Running docker nerdfonts/patcher (--mono --careful --complete)..."
            docker run --rm \
                -v "$(dirname "${INPUT_TTF}"):/in:Z" \
                -v "${OUT_DIR}:/out:Z" \
                nerdfonts/patcher:latest \
                --mono --careful --complete "/in/$(basename "${INPUT_TTF}")"
        else
            echo "Error: Neither local 'fontforge' + 'font-patcher' nor 'docker' is available." >&2
            echo "Tip: Run '$0 builtin' to use the zero-Docker fontTools SymbolsNerdFontMono synthesizer." >&2
            exit 1
        fi
        ;;
    *)
        echo "Usage: $0 [builtin | font-patcher <input.ttf> <out_dir>]" >&2
        exit 1
        ;;
esac
