#!/usr/bin/env python3
"""
Programmatic generator for precision terminal grid glyphs:
  - U+2500..U+257F: Box Drawing (128 glyphs, exact cell-boundary alignment, zero contour overlap)
  - U+2580..U+259F: Block Elements (32 glyphs, seamless edges + stipple shades)
  - U+2800..U+28FF: Braille Patterns (256 glyphs, 2x4 bitmask matrix)
  - U+1FB00..U+1FB3B: Symbols for Legacy Computing (60 2x3 sextant mosaic glyphs)
  - U+3000: Ideographic Space (2-cell 1200 width, with optional subtle corner ticks)
"""

from __future__ import annotations

from collections import defaultdict
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables._g_l_y_f import Glyph

# Segment styles for Box Drawing (left, right, up, down):
#   0 = none
#   1 = light
#   2 = heavy
#   3 = double
#   4 = light 2-dash
#   5 = heavy 2-dash
#   6 = light 3-dash
#   7 = heavy 3-dash
#   8 = light 4-dash
#   9 = heavy 4-dash
BOX_SPECS: dict[int, tuple[int, int, int, int]] = {
    0x2500: (1, 1, 0, 0),
    0x2501: (2, 2, 0, 0),
    0x2502: (0, 0, 1, 1),
    0x2503: (0, 0, 2, 2),
    0x2504: (6, 6, 0, 0),
    0x2505: (7, 7, 0, 0),
    0x2506: (0, 0, 6, 6),
    0x2507: (0, 0, 7, 7),
    0x2508: (8, 8, 0, 0),
    0x2509: (9, 9, 0, 0),
    0x250A: (0, 0, 8, 8),
    0x250B: (0, 0, 9, 9),
    0x250C: (0, 1, 0, 1),
    0x250D: (0, 2, 0, 1),
    0x250E: (0, 1, 0, 2),
    0x250F: (0, 2, 0, 2),
    0x2510: (1, 0, 0, 1),
    0x2511: (2, 0, 0, 1),
    0x2512: (1, 0, 0, 2),
    0x2513: (2, 0, 0, 2),
    0x2514: (0, 1, 1, 0),
    0x2515: (0, 2, 1, 0),
    0x2516: (0, 1, 2, 0),
    0x2517: (0, 2, 2, 0),
    0x2518: (1, 0, 1, 0),
    0x2519: (2, 0, 1, 0),
    0x251A: (1, 0, 2, 0),
    0x251B: (2, 0, 2, 0),
    0x251C: (0, 1, 1, 1),
    0x251D: (0, 2, 1, 1),
    0x251E: (0, 1, 2, 1),
    0x251F: (0, 1, 1, 2),
    0x2520: (0, 1, 2, 2),
    0x2521: (0, 2, 2, 1),
    0x2522: (0, 2, 1, 2),
    0x2523: (0, 2, 2, 2),
    0x2524: (1, 0, 1, 1),
    0x2525: (2, 0, 1, 1),
    0x2526: (1, 0, 2, 1),
    0x2527: (1, 0, 1, 2),
    0x2528: (1, 0, 2, 2),
    0x2529: (2, 0, 2, 1),
    0x252A: (2, 0, 1, 2),
    0x252B: (2, 0, 2, 2),
    0x252C: (1, 1, 0, 1),
    0x252D: (2, 1, 0, 1),
    0x252E: (1, 2, 0, 1),
    0x252F: (2, 2, 0, 1),
    0x2530: (1, 1, 0, 2),
    0x2531: (2, 1, 0, 2),
    0x2532: (1, 2, 0, 2),
    0x2533: (2, 2, 0, 2),
    0x2534: (1, 1, 1, 0),
    0x2535: (2, 1, 1, 0),
    0x2536: (1, 2, 1, 0),
    0x2537: (2, 2, 1, 0),
    0x2538: (1, 1, 2, 0),
    0x2539: (2, 1, 2, 0),
    0x253A: (1, 2, 2, 0),
    0x253B: (2, 2, 2, 0),
    0x253C: (1, 1, 1, 1),
    0x253D: (2, 1, 1, 1),
    0x253E: (1, 2, 1, 1),
    0x253F: (2, 2, 1, 1),
    0x2540: (1, 1, 2, 1),
    0x2541: (1, 1, 1, 2),
    0x2542: (1, 1, 2, 2),
    0x2543: (2, 1, 2, 1),
    0x2544: (1, 2, 2, 1),
    0x2545: (2, 1, 1, 2),
    0x2546: (1, 2, 1, 2),
    0x2547: (2, 2, 2, 1),
    0x2548: (2, 2, 1, 2),
    0x2549: (2, 1, 2, 2),
    0x254A: (1, 2, 2, 2),
    0x254B: (2, 2, 2, 2),
    0x254C: (4, 4, 0, 0),
    0x254D: (5, 5, 0, 0),
    0x254E: (0, 0, 4, 4),
    0x254F: (0, 0, 5, 5),
    0x2550: (3, 3, 0, 0),
    0x2551: (0, 0, 3, 3),
    0x2552: (0, 3, 0, 1),
    0x2553: (0, 1, 0, 3),
    0x2554: (0, 3, 0, 3),
    0x2555: (3, 0, 0, 1),
    0x2556: (1, 0, 0, 3),
    0x2557: (3, 0, 0, 3),
    0x2558: (0, 3, 1, 0),
    0x2559: (0, 1, 3, 0),
    0x255A: (0, 3, 3, 0),
    0x255B: (3, 0, 1, 0),
    0x255C: (1, 0, 3, 0),
    0x255D: (3, 0, 3, 0),
    0x255E: (0, 3, 1, 1),
    0x255F: (0, 1, 3, 3),
    0x2560: (0, 3, 3, 3),
    0x2561: (3, 0, 1, 1),
    0x2562: (1, 0, 3, 3),
    0x2563: (3, 0, 3, 3),
    0x2564: (3, 3, 0, 1),
    0x2565: (1, 1, 0, 3),
    0x2566: (3, 3, 0, 3),
    0x2567: (3, 3, 1, 0),
    0x2568: (1, 1, 3, 0),
    0x2569: (3, 3, 3, 0),
    0x256A: (3, 3, 1, 1),
    0x256B: (1, 1, 3, 3),
    0x256C: (3, 3, 3, 3),
    0x2574: (1, 0, 0, 0),
    0x2575: (0, 0, 1, 0),
    0x2576: (0, 1, 0, 0),
    0x2577: (0, 0, 0, 1),
    0x2578: (2, 0, 0, 0),
    0x2579: (0, 0, 2, 0),
    0x257A: (0, 2, 0, 0),
    0x257B: (0, 0, 0, 2),
    0x257C: (1, 2, 0, 0),
    0x257D: (0, 0, 1, 2),
    0x257E: (2, 1, 0, 0),
    0x257F: (0, 0, 2, 1),
}


def _union_rects_to_pen(pen: TTGlyphPen, rects: list[tuple[float, float, float, float]]) -> None:
    """
    Compute the exact boolean union of axis-aligned rectangles and emit
    minimal, non-overlapping clockwise TrueType contours to `pen`.
    """
    norm_rects: list[tuple[int, int, int, int]] = []
    for x0, y0, x1, y1 in rects:
        ix0, iy0, ix1, iy1 = round(x0), round(y0), round(x1), round(y1)
        if ix0 < ix1 and iy0 < iy1:
            norm_rects.append((ix0, iy0, ix1, iy1))
    if not norm_rects:
        return

    xs = sorted({x for r in norm_rects for x in (r[0], r[2])})
    ys = sorted({y for r in norm_rects for y in (r[1], r[3])})
    nx, ny = len(xs) - 1, len(ys) - 1

    def is_filled(i: int, j: int) -> bool:
        if not (0 <= i < nx and 0 <= j < ny):
            return False
        cx0, cx1 = xs[i], xs[i + 1]
        cy0, cy1 = ys[j], ys[j + 1]
        return any(rx0 <= cx0 and cx1 <= rx1 and ry0 <= cy0 and cy1 <= ry1 for rx0, ry0, rx1, ry1 in norm_rects)

    # Collect directed boundary segments in clockwise orientation around filled regions
    adj: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for i in range(nx):
        for j in range(ny):
            if not is_filled(i, j):
                continue
            x0, x1 = xs[i], xs[i + 1]
            y0, y1 = ys[j], ys[j + 1]
            # Left boundary: upward (x0, y0) -> (x0, y1)
            if not is_filled(i - 1, j):
                adj[(x0, y0)].append((x0, y1))
            # Top boundary: rightward (x0, y1) -> (x1, y1)
            if not is_filled(i, j + 1):
                adj[(x0, y1)].append((x1, y1))
            # Right boundary: downward (x1, y1) -> (x1, y0)
            if not is_filled(i + 1, j):
                adj[(x1, y1)].append((x1, y0))
            # Bottom boundary: leftward (x1, y0) -> (x0, y0)
            if not is_filled(i, j - 1):
                adj[(x1, y0)].append((x0, y0))

    # Trace closed loops
    while adj:
        start = next(iter(adj))
        loop = [start]
        curr = start
        while True:
            nxt_list = adj.get(curr)
            if not nxt_list:
                break
            nxt = nxt_list.pop()
            if not nxt_list:
                del adj[curr]
            if nxt == start:
                break
            loop.append(nxt)
            curr = nxt

        # Simplify colinear intermediate points
        if len(loop) >= 3:
            simplified: list[tuple[int, int]] = []
            m = len(loop)
            for k in range(m):
                p_prev = loop[(k - 1) % m]
                p_curr = loop[k]
                p_next = loop[(k + 1) % m]
                if (p_prev[0] == p_curr[0] == p_next[0]) or (p_prev[1] == p_curr[1] == p_next[1]):
                    continue
                simplified.append(p_curr)
            if len(simplified) >= 3:
                pen.moveTo(simplified[0])
                for pt in simplified[1:]:
                    pen.lineTo(pt)
                pen.closePath()


def _add_poly(pen: TTGlyphPen, pts: list[tuple[float, float]]) -> None:
    if len(pts) < 3:
        return
    pen.moveTo((round(pts[0][0]), round(pts[0][1])))
    for x, y in pts[1:]:
        pen.lineTo((round(x), round(y)))
    pen.closePath()


def _add_circle_quad(pen: TTGlyphPen, cx: float, cy: float, r: float) -> None:
    """Draw a smooth TrueType quadratic circle centered at (cx, cy)."""
    k = 0.41421356 * r
    s = 0.70710678 * r
    pen.moveTo((round(cx - r), round(cy)))
    pen.qCurveTo((round(cx - r), round(cy + k)), (round(cx - s), round(cy + s)))
    pen.qCurveTo((round(cx - k), round(cy + r)), (round(cx), round(cy + r)))
    pen.qCurveTo((round(cx + k), round(cy + r)), (round(cx + s), round(cy + s)))
    pen.qCurveTo((round(cx + r), round(cy + k)), (round(cx + r), round(cy)))
    pen.qCurveTo((round(cx + r), round(cy - k)), (round(cx + s), round(cy - s)))
    pen.qCurveTo((round(cx + k), round(cy - r)), (round(cx), round(cy - r)))
    pen.qCurveTo((round(cx - k), round(cy - r)), (round(cx - s), round(cy - s)))
    pen.qCurveTo((round(cx - r), round(cy - k)), (round(cx - r), round(cy)))
    pen.closePath()


def generate_box_drawing_glyph(
    u: int,
    width: int = 600,
    ymin: int = -240,
    ymax: int = 900,
) -> Glyph:
    pen = TTGlyphPen(None)
    cx = width / 2.0
    cy = (ymin + ymax) / 2.0  # 330.0
    light = 56.0
    heavy = 112.0
    dbl_stroke = 42.0
    dbl_gap = 56.0

    # Rounded corners U+256D..U+2570 (true quadratic Bezier arcs)
    if u in (0x256D, 0x256E, 0x256F, 0x2570):
        hs = light / 2.0
        r = 172.0
        r_out = r + hs
        r_in = r - hs
        k = 0.41421356  # tan(pi/8)
        s = 0.70710678  # sin(pi/4)

        def q_arc(
            ax: float, ay: float, rad: float, sx: float, sy: float, ex: float, ey: float
        ) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]]:
            # 2-segment quadratic Bezier for an exact 90-degree circular arc around (ax, ay)
            mx = ax + (sx + ex) * s * rad
            my = ay + (sy + ey) * s * rad
            c1x = ax + (sx + ex * k) * rad
            c1y = ay + (sy + ey * k) * rad
            c2x = ax + (ex + sx * k) * rad
            c2y = ay + (ey + sy * k) * rad
            p_end = (round(ax + ex * rad), round(ay + ey * rad))
            return (round(c1x), round(c1y)), (round(mx), round(my)), (round(c2x), round(c2y)), p_end

        if u == 0x256D:  # ╭ down + right (arc center at cx + r, cy - r)
            ax, ay = cx + r, cy - r
            pen.moveTo((round(cx - hs), ymin))
            pen.lineTo((round(cx - hs), round(ay)))
            c1, m, c2, p_end = q_arc(ax, ay, r_out, -1, 0, 0, 1)
            pen.qCurveTo(c1, m)
            pen.qCurveTo(c2, p_end)
            pen.lineTo((width, round(cy + hs)))
            pen.lineTo((width, round(cy - hs)))
            pen.lineTo((round(ax), round(cy - hs)))
            c1, m, c2, p_end = q_arc(ax, ay, r_in, 0, 1, -1, 0)
            pen.qCurveTo(c1, m)
            pen.qCurveTo(c2, p_end)
            pen.lineTo((round(cx + hs), ymin))
            pen.closePath()
        elif u == 0x256E:  # ╮ down + left (arc center at cx - r, cy - r)
            ax, ay = cx - r, cy - r
            pen.moveTo((0, round(cy + hs)))
            pen.lineTo((round(ax), round(cy + hs)))
            c1, m, c2, p_end = q_arc(ax, ay, r_out, 0, 1, 1, 0)
            pen.qCurveTo(c1, m)
            pen.qCurveTo(c2, p_end)
            pen.lineTo((round(cx + hs), ymin))
            pen.lineTo((round(cx - hs), ymin))
            pen.lineTo((round(cx - hs), round(ay)))
            c1, m, c2, p_end = q_arc(ax, ay, r_in, 1, 0, 0, 1)
            pen.qCurveTo(c1, m)
            pen.qCurveTo(c2, p_end)
            pen.lineTo((0, round(cy - hs)))
            pen.closePath()
        elif u == 0x256F:  # ╯ up + left (arc center at cx - r, cy + r)
            ax, ay = cx - r, cy + r
            pen.moveTo((round(cx + hs), ymax))
            pen.lineTo((round(cx + hs), round(ay)))
            c1, m, c2, p_end = q_arc(ax, ay, r_out, 1, 0, 0, -1)
            pen.qCurveTo(c1, m)
            pen.qCurveTo(c2, p_end)
            pen.lineTo((0, round(cy - hs)))
            pen.lineTo((0, round(cy + hs)))
            pen.lineTo((round(ax), round(cy + hs)))
            c1, m, c2, p_end = q_arc(ax, ay, r_in, 0, -1, 1, 0)
            pen.qCurveTo(c1, m)
            pen.qCurveTo(c2, p_end)
            pen.lineTo((round(cx - hs), ymax))
            pen.closePath()
        elif u == 0x2570:  # ╰ up + right (arc center at cx + r, cy + r)
            ax, ay = cx + r, cy + r
            pen.moveTo((width, round(cy - hs)))
            pen.lineTo((round(ax), round(cy - hs)))
            c1, m, c2, p_end = q_arc(ax, ay, r_out, 0, -1, -1, 0)
            pen.qCurveTo(c1, m)
            pen.qCurveTo(c2, p_end)
            pen.lineTo((round(cx - hs), ymax))
            pen.lineTo((round(cx + hs), ymax))
            pen.lineTo((round(cx + hs), round(ay)))
            c1, m, c2, p_end = q_arc(ax, ay, r_in, -1, 0, 0, -1)
            pen.qCurveTo(c1, m)
            pen.qCurveTo(c2, p_end)
            pen.lineTo((width, round(cy + hs)))
            pen.closePath()
        return pen.glyph()

    # Diagonals U+2571..U+2573
    if u in (0x2571, 0x2572, 0x2573):
        dx = 34.0
        dy = round(dx * 1.8)
        if u == 0x2571:  # ╱ bottom-left to top-right
            _add_poly(
                pen,
                [
                    (0, ymin),
                    (0, ymin + dy),
                    (width - dx, ymax),
                    (width, ymax),
                    (width, ymax - dy),
                    (dx, ymin),
                ],
            )
        elif u == 0x2572:  # ╲ top-left to bottom-right
            _add_poly(
                pen,
                [
                    (0, ymax - dy),
                    (0, ymax),
                    (dx, ymax),
                    (width, ymin + dy),
                    (width, ymin),
                    (width - dx, ymin),
                ],
            )
        else:  # ╳ diagonal cross (non-overlapping 12-gon)
            h = ymax - ymin
            slope = h / float(width)  # 1.9
            # Exact intersection of ╱ and ╲ around (cx, cy)
            ix_off = dx
            iy_off = round(dx * slope)
            _add_poly(
                pen,
                [
                    (0, ymin),
                    (0, ymin + dy),
                    (cx - ix_off, cy),
                    (0, ymax - dy),
                    (0, ymax),
                    (dx, ymax),
                    (cx, cy + iy_off),
                    (width - dx, ymax),
                    (width, ymax),
                    (width, ymax - dy),
                    (cx + ix_off, cy),
                    (width, ymin + dy),
                    (width, ymin),
                    (width - dx, ymin),
                    (cx, cy - iy_off),
                    (dx, ymin),
                ],
            )
        return pen.glyph()

    left, right, up, down = BOX_SPECS[u]
    rects = []

    # Dashed lines U+2504..U+250B, U+254C..U+254F
    if left in (4, 5, 6, 7, 8, 9) or up in (4, 5, 6, 7, 8, 9):
        style = left if left else up
        is_horiz = left != 0
        stroke = heavy if style in (5, 7, 9) else light
        hs = stroke / 2.0
        n_dashes = 2 if style in (4, 5) else (3 if style in (6, 7) else 4)
        span = width if is_horiz else (ymax - ymin)
        step = span / n_dashes
        dash_len = step * 0.65
        pad = (step - dash_len) / 2.0
        for i in range(n_dashes):
            start = (0 if is_horiz else ymin) + i * step + pad
            end = start + dash_len
            if is_horiz:
                rects.append((start, cy - hs, end, cy + hs))
            else:
                rects.append((cx - hs, start, cx + hs, end))
        _union_rects_to_pen(pen, rects)
        return pen.glyph()

    # Standard solid / double segments
    def half_span(s: int) -> float:
        if s == 1:
            return light / 2.0
        if s == 2:
            return heavy / 2.0
        if s == 3:
            return dbl_gap / 2.0 + dbl_stroke
        return 0.0

    ext_x = max(half_span(up), half_span(down), light / 2.0)
    ext_y = max(half_span(left), half_span(right), light / 2.0)

    if left in (1, 2):
        hs = half_span(left)
        rects.append((0, cy - hs, cx + ext_x, cy + hs))
    elif left == 3:
        in_y = dbl_gap / 2.0
        out_y = in_y + dbl_stroke
        x_end_top = cx - dbl_gap / 2.0 if up == 3 else cx + ext_x
        x_end_bot = cx - dbl_gap / 2.0 if down == 3 else cx + ext_x
        rects.append((0, cy + in_y, x_end_top, cy + out_y))
        rects.append((0, cy - out_y, x_end_bot, cy - in_y))

    if right in (1, 2):
        hs = half_span(right)
        rects.append((cx - ext_x, cy - hs, width, cy + hs))
    elif right == 3:
        in_y = dbl_gap / 2.0
        out_y = in_y + dbl_stroke
        x_start_top = cx + dbl_gap / 2.0 if up == 3 else cx - ext_x
        x_start_bot = cx + dbl_gap / 2.0 if down == 3 else cx - ext_x
        rects.append((x_start_top, cy + in_y, width, cy + out_y))
        rects.append((x_start_bot, cy - out_y, width, cy - in_y))

    if up in (1, 2):
        hs = half_span(up)
        rects.append((cx - hs, cy - ext_y, cx + hs, ymax))
    elif up == 3:
        in_x = dbl_gap / 2.0
        out_x = in_x + dbl_stroke
        y_start_left = cy + dbl_gap / 2.0 if left == 3 else cy - ext_y
        y_start_right = cy + dbl_gap / 2.0 if right == 3 else cy - ext_y
        rects.append((cx - out_x, y_start_left, cx - in_x, ymax))
        rects.append((cx + in_x, y_start_right, cx + out_x, ymax))

    if down in (1, 2):
        hs = half_span(down)
        rects.append((cx - hs, ymin, cx + hs, cy + ext_y))
    elif down == 3:
        in_x = dbl_gap / 2.0
        out_x = in_x + dbl_stroke
        y_end_left = cy - dbl_gap / 2.0 if left == 3 else cy + ext_y
        y_end_right = cy - dbl_gap / 2.0 if right == 3 else cy + ext_y
        rects.append((cx - out_x, ymin, cx - in_x, y_end_left))
        rects.append((cx + in_x, ymin, cx + out_x, y_end_right))

    _union_rects_to_pen(pen, rects)
    return pen.glyph()


def generate_block_element_glyph(
    u: int,
    width: int = 600,
    ymin: int = -240,
    ymax: int = 900,
) -> Glyph:
    pen = TTGlyphPen(None)
    h = ymax - ymin
    ymid = ymin + h / 2.0
    xmid = width / 2.0
    rects: list[tuple[float, float, float, float]] = []

    if u == 0x2580:
        rects.append((0, ymid, width, ymax))
    elif 0x2581 <= u <= 0x2588:
        k = u - 0x2580
        rects.append((0, ymin, width, ymin + h * k / 8.0))
    elif 0x2589 <= u <= 0x258F:
        k = 8 - (u - 0x2588)
        rects.append((0, ymin, width * k / 8.0, ymax))
    elif u == 0x2590:
        rects.append((xmid, ymin, width, ymax))
    elif u in (0x2591, 0x2592, 0x2593):
        cols, rows = 6, 12
        cw = width / cols
        rh = h / rows
        for r in range(rows):
            for c in range(cols):
                if u == 0x2591:
                    draw = (r % 2 == 0) and (c % 2 == (r // 2) % 2)
                elif u == 0x2592:
                    draw = (r + c) % 2 == 0
                else:
                    draw = not ((r % 2 == 0) and (c % 2 == (r // 2) % 2))
                if draw:
                    # Keep 4-unit separation on 50%/75% stipples so corners don't kiss
                    inset = 2.0 if u in (0x2592, 0x2593) else 0.0
                    rects.append(
                        (
                            c * cw + inset,
                            ymin + r * rh + inset,
                            (c + 1) * cw - inset,
                            ymin + (r + 1) * rh - inset,
                        )
                    )
    elif u == 0x2594:
        rects.append((0, ymax - h / 8.0, width, ymax))
    elif u == 0x2595:
        rects.append((width * 7.0 / 8.0, ymin, width, ymax))
    elif 0x2596 <= u <= 0x259F:
        quad_masks = {
            0x2596: 0b0001,
            0x2597: 0b0010,
            0x2598: 0b0100,
            0x2599: 0b0111,
            0x259A: 0b0110,
            0x259B: 0b1101,
            0x259C: 0b1110,
            0x259D: 0b1000,
            0x259E: 0b1001,
            0x259F: 0b1011,
        }
        mask = quad_masks[u]
        if u in (0x259A, 0x259E):
            # Diagonal quadrants: emit two separate rects directly so kiss-corner doesn't merge
            for bit, (x0, y0, x1, y1) in [
                (0b0001, (0, ymin, xmid, ymid)),
                (0b0010, (xmid, ymin, width, ymid)),
                (0b0100, (0, ymid, xmid, ymax)),
                (0b1000, (xmid, ymid, width, ymax)),
            ]:
                if mask & bit:
                    _union_rects_to_pen(pen, [(x0, y0, x1, y1)])
            return pen.glyph()
        if mask & 0b0001:
            rects.append((0, ymin, xmid, ymid))
        if mask & 0b0010:
            rects.append((xmid, ymin, width, ymid))
        if mask & 0b0100:
            rects.append((0, ymid, xmid, ymax))
        if mask & 0b1000:
            rects.append((xmid, ymid, width, ymax))

    _union_rects_to_pen(pen, rects)
    return pen.glyph()


def generate_braille_glyph(
    u: int,
    width: int = 600,
    ymin: int = -240,
    ymax: int = 900,
) -> Glyph:
    pen = TTGlyphPen(None)
    bits = u - 0x2800
    if bits == 0:
        return Glyph()

    xs = (180.0, 420.0)
    ys = (710.0, 455.0, 200.0, -55.0)
    dot_positions = [
        (xs[0], ys[0]),
        (xs[0], ys[1]),
        (xs[0], ys[2]),
        (xs[1], ys[0]),
        (xs[1], ys[1]),
        (xs[1], ys[2]),
        (xs[0], ys[3]),
        (xs[1], ys[3]),
    ]
    r = 56.0
    for idx, (cx, cy) in enumerate(dot_positions):
        if bits & (1 << idx):
            _add_circle_quad(pen, cx, cy, r)
    return pen.glyph()


def generate_sextant_glyph(
    u: int,
    width: int = 600,
    ymin: int = -240,
    ymax: int = 900,
) -> Glyph:
    sextant_masks = [m for m in range(1, 63) if m not in (21, 42)]
    idx = u - 0x1FB00
    if not (0 <= idx < len(sextant_masks)):
        return Glyph()
    mask = sextant_masks[idx]
    pen = TTGlyphPen(None)
    h = ymax - ymin
    xmid = width / 2.0
    y0 = ymin
    y1 = round(ymin + h / 3.0)
    y2 = round(ymin + 2.0 * h / 3.0)
    y3 = ymax
    cells = [
        (0, y2, xmid, y3),
        (xmid, y2, width, y3),
        (0, y1, xmid, y2),
        (xmid, y1, width, y2),
        (0, y0, xmid, y1),
        (xmid, y0, width, y1),
    ]
    for b, rect in enumerate(cells):
        if mask & (1 << b):
            _union_rects_to_pen(pen, [rect])
    return pen.glyph()


def generate_ideographic_space_glyph(
    full_width: int = 1200,
    visualize: bool = True,
) -> Glyph:
    if not visualize:
        return Glyph()
    pen = TTGlyphPen(None)
    pad_x = 160
    y_bot = -40
    y_top = 740
    arm = 110
    thick = 28
    rects = [
        # Bottom-left L
        (pad_x, y_bot, pad_x + arm, y_bot + thick),
        (pad_x, y_bot, pad_x + thick, y_bot + arm),
        # Bottom-right L
        (full_width - pad_x - arm, y_bot, full_width - pad_x, y_bot + thick),
        (full_width - pad_x - thick, y_bot, full_width - pad_x, y_bot + arm),
        # Top-left L
        (pad_x, y_top - thick, pad_x + arm, y_top),
        (pad_x, y_top - arm, pad_x + thick, y_top),
        # Top-right L
        (full_width - pad_x - arm, y_top - thick, full_width - pad_x, y_top),
        (full_width - pad_x - thick, y_top - arm, full_width - pad_x, y_top),
    ]
    _union_rects_to_pen(pen, rects)
    return pen.glyph()


def build_all_programmatic_glyphs(
    half_width: int = 600,
    full_width: int = 1200,
    ymin: int = -240,
    ymax: int = 900,
    visualize_zenkaku_space: bool = True,
) -> dict[int, tuple[str, Glyph, int]]:
    out: dict[int, tuple[str, Glyph, int]] = {}
    for u in range(0x2500, 0x2580):
        out[u] = (f"uni{u:04X}", generate_box_drawing_glyph(u, half_width, ymin, ymax), half_width)
    for u in range(0x2580, 0x25A0):
        out[u] = (f"uni{u:04X}", generate_block_element_glyph(u, half_width, ymin, ymax), half_width)
    for u in range(0x2800, 0x2900):
        out[u] = (f"uni{u:04X}", generate_braille_glyph(u, half_width, ymin, ymax), half_width)
    for u in range(0x1FB00, 0x1FB3C):
        out[u] = (f"u{u:05X}", generate_sextant_glyph(u, half_width, ymin, ymax), half_width)
    out[0x3000] = (
        "uni3000",
        generate_ideographic_space_glyph(full_width, visualize=visualize_zenkaku_space),
        full_width,
    )
    return out
