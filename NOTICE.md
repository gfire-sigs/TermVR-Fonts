# Third-Party Notices & Attributions (`TermVR Mono`)

`TermVR Mono` and `TermVR Mono NF` are composite terminal typefaces engineered specifically for `gfire-sigs/TermVR`. They are built by normalizing, subsetting, and merging glyphs from the open-source typeface projects listed below, together with custom-generated geometric terminal glyphs (Box Drawing, Block Elements, Braille Patterns, Legacy Computing Sextants, and Ideographic Space indicators).

In compliance with Condition 3 of the **SIL Open Font License 1.1 (OFL-1.1)**, `TermVR Mono` does **not** use the Reserved Font Names `"IBM"` or `"Plex"` in its primary font family names or filenames.

---

## 1. IBM Plex® Typeface Family

* **Upstream Repository**: https://github.com/IBM/plex
* **License**: SIL Open Font License, Version 1.1 (`OFL-1.1`)
* **Reserved Font Names**: `"IBM"`, `"Plex"`
* **Copyright**: Copyright © 2017–2026 IBM Corp. All rights reserved.

### Included Sub-Families & Credits
1. **IBM Plex Mono (`@ibm/plex-mono`)**
   * **Role in TermVR Mono**: Primary 1-cell (`600` width) base typeface for ASCII, Latin Extended, Greek, Cyrillic, numerals, and core programming punctuation.
   * **Designers**: Mike Abbink, Paul van der Laan, Pieter van Rosmalen (Bold Monday).
2. **IBM Plex Math (`@ibm/plex-math`)**
   * **Role in TermVR Mono**: Native 1-cell (`600` width) mathematical operators (`U+2200`–`U+22FF`, `U+2A00`–`U+2AFF`), arrows (`U+2190`–`U+21FF`, `U+27F0`–`U+297F`), miscellaneous technical symbols (`U+2300`–`U+23FF`), geometric shapes (`U+25A0`–`U+25FF`), and dingbats (`U+2600`–`U+27BF`).
   * **Designers**: Bold Monday & IBM Corporate Design Team.
3. **IBM Plex Sans Hebrew (`@ibm/plex-sans-hebrew`)**
   * **Role in TermVR Mono**: Hebrew consonants (`U+05D0`–`U+05EA`, normalized to `600` width), Yiddish digraphs (`U+05F0`–`U+05F4`), Alphabetic Presentation Forms (`U+FB1D`–`U+FB4F`), New Sheqel sign (`₪`, `U+20AA`), and zero-width combining vowel points (*Niqqud*) & biblical cantillation marks (*Te'amim*, `U+0591`–`U+05C7` with preserved `GPOS` anchor positioning).
   * **Designers**: Mike Abbink, Paul van der Laan, Pieter van Rosmalen, Yanek Iontef.
4. **IBM Plex Sans KR (`@ibm/plex-sans-kr`)**
   * **Role in TermVR Mono**: Full modern Korean Hangul Syllables (`U+AC00`–`U+D7A3`, 11,172 glyphs), Hangul Jamo (`U+1100`–`U+11FF`, `U+3130`–`U+318F`), and Korean symbols normalized to 2-cell (`1200` width) grid alignment.
   * **Designers**: Mike Abbink, Paul van der Laan, Pieter van Rosmalen (Bold Monday), and Wujin Sim, Chorong Kim, Dohee Lee (Sandoll Inc.).
5. **IBM Plex Sans JP (`@ibm/plex-sans-jp`)**
   * **Role in TermVR Mono**: Japanese Hiragana (`U+3040`–`U+309F`), Katakana (`U+30A0`–`U+30FF`, `U+31F0`–`U+31FF`), Halfwidth Katakana (`U+FF65`–`U+FF9F`, 1-cell `600` width), and 7,160 CJK Unified Ideographs (Kanji / Hanja following Adobe-Japan1-3 / JIS X 0208, normalized to 2-cell `1200` width).
   * **Designers**: Bold Monday & Sandoll Inc. (Noh Eunyou, Ma Kichan, Zhang Jiashuo, Im Changseop, et al.).
6. **IBM Plex Sans TC (`@ibm/plex-sans-tc`, Optional Hanja Supplement)**
   * **Role in TermVR Mono**: Supplemental Traditional CJK Unified Ideographs to complete Korean KS X 1001 Hanja coverage where codepoints are absent from `IBM Plex Sans JP`.
   * **Designers**: Bold Monday & Sandoll Inc.

---

## 2. Nerd Fonts (`Symbols Nerd Font Mono`)

* **Upstream Repository**: https://github.com/ryanoasis/nerd-fonts
* **License**: MIT License (Project & Patcher Scripts), incorporating icon sets under SIL OFL 1.1, MIT, CC-BY 4.0, and Apache 2.0.
* **Copyright**: Copyright (c) 2014–2026, Ryan L McIntyre (https://ryanlmcintyre.com).
* **Included Icon Sets & Upstream Licenses**:
  * **Powerline Symbols / Powerline Extra Symbols** (`U+E0A0`–`U+E0D7`): MIT License — Copyright (c) 2015, Ryan L McIntyre / Kim Silkebækken.
  * **Font Awesome** (`U+ED00`–`U+F2FF`): SIL OFL 1.1 / CC-BY 4.0 — Fonticons, Inc. (https://fontawesome.com).
  * **Material Design Icons** (`U+F0001`–`U+F1AF0`): Apache License 2.0 / Pictogrammers Free License — Austin Andrews & Pictogrammers (https://pictogrammers.com).
  * **Devicons** (`U+E700`–`U+E8EF`): MIT License — Theodore Vorillas (http://vorillaz.github.io/devicons/).
  * **GitHub Octicons** (`U+F400`–`U+F533`, `U+2665`, `U+26A1`): MIT License — Copyright (c) GitHub, Inc.
  * **VS Code Codicons** (`U+EA60`–`U+EC1E`): CC-BY 4.0 / MIT — Microsoft Corporation (https://github.com/microsoft/vscode-codicons).
  * **Weather Icons** (`U+E300`–`U+E3E3`): SIL OFL 1.1 — Erik Flowers (https://erikflowers.github.io/weather-icons/).
  * **Font Logos** (`U+F300`–`U+F381`): GPLv2+ with Font Exception / MIT — Lukas W (https://github.com/Lukas-W/font-logos).
  * **Pomicons** (`U+E000`–`U+E00A`): MIT License — Gabyaten.
  * **IEC Power Symbols** (`U+23FB`–`U+23FE`, `U+2B58`): MIT License.

---

## 3. Custom Programmatic Terminal Glyphs (`gfire-sigs/TermVR-Fonts`)

* **License**: SIL Open Font License, Version 1.1 (`OFL-1.1`)
* **Copyright**: Copyright (c) 2026 gfire-sigs (https://github.com/gfire-sigs/TermVR-Fonts)
* **Generated Ranges**:
  * `U+2500`–`U+257F`: Box Drawing (mathematically aligned to `[0, 600]` × `[-240, 900]` cell boundaries for zero-seam VR terminal rendering).
  * `U+2580`–`U+259F`: Block Elements & Shades (`░▒▓█▄▀▌▐` with exact edge-to-edge geometry).
  * `U+2800`–`U+28FF`: Braille Patterns (all 256 8-dot combinations on a calibrated 2×4 grid).
  * `U+1FB00`–`U+1FB3B`: Symbols for Legacy Computing (2×3 Sextant mosaic graphics).
  * `U+3000`: Ideographic Space (optional subtle corner-bracket visualization glyph for CJK coding safety).
