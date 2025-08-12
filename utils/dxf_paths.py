# utils/dxf_paths.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple, Iterable, Optional, Dict
import math

# You already have ezdxf in requirements; if not, add: ezdxf>=1.1
import ezdxf

Point = Tuple[float, float]  # (x_mm, y_mm)


@dataclass
class DXFMeta:
    units_name: str
    to_mm: float
    path_count: int
    vertex_count: int
    bbox: Tuple[float, float, float, float]  # (minx, miny, maxx, maxy)
    total_length_mm: float
    warnings: List[str]


def _insunits_to_mm_multiplier(code: int) -> Tuple[str, float]:
    # Most common codes:
    # 0 Unitless, 1 Inches, 2 Feet, 4 Millimeters, 5 Centimeters, 6 Meters, 13 Microns
    mapping: Dict[int, Tuple[str, float]] = {
        0: ("unitless", 1.0),      # assume mm unless overridden by unit_hint
        1: ("in", 25.4),
        2: ("ft", 304.8),
        3: ("mi", 1609344.0),
        4: ("mm", 1.0),
        5: ("cm", 10.0),
        6: ("m", 1000.0),
        7: ("km", 1_000_000.0),
        9: ("mil", 0.0254),
        11: ("Å", 1e-7),
        12: ("nm", 1e-6),
        13: ("µm", 1e-3),
        14: ("dm", 100.0),
    }
    return mapping.get(code, ("unitless", 1.0))


def _approx_arc(cx, cy, r, start_deg, end_deg, step_deg=5.0) -> List[Point]:
    pts: List[Point] = []
    # normalize direction
    a0 = math.radians(start_deg)
    a1 = math.radians(end_deg)
    da = a1 - a0
    # choose segment count ~ every step_deg
    n = max(2, int(abs(math.degrees(da)) / step_deg) + 1)
    for i in range(n + 1):
        t = i / n
        a = a0 + da * t
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _length(points: List[Point]) -> float:
    return sum(math.hypot(points[i+1][0]-points[i][0], points[i+1][1]-points[i][1]) for i in range(len(points)-1))


def _dedupe_close(points: List[Point], eps_mm: float) -> List[Point]:
    if not points:
        return points
    out = [points[0]]
    for p in points[1:]:
        if math.hypot(p[0]-out[-1][0], p[1]-out[-1][1]) >= eps_mm:
            out.append(p)
    return out


def read_dxf_to_paths_mm(
    path: str,
    unit_hint: Optional[str] = None,    # 'mm', 'um', 'in', etc
    origin: str = "lower_left",         # 'lower_left' | 'center' | 'none'
    close_threshold_um: float = 0.05,   # merge vertices closer than this
    arc_step_deg: float = 5.0           # arc discretization
) -> Tuple[List[List[Point]], DXFMeta]:
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    ins_code = doc.header.get("$INSUNITS", 0)
    ins_name, to_mm = _insunits_to_mm_multiplier(ins_code)

    if unit_hint:
        hint = unit_hint.lower()
        if hint in ("mm", "millimeter", "millimeters"):
            ins_name, to_mm = "mm", 1.0
        elif hint in ("um", "µm", "micron", "micrometer", "micrometers"):
            ins_name, to_mm = "µm", 1e-3
        elif hint in ("in", "inch", "inches"):
            ins_name, to_mm = "in", 25.4
        elif hint in ("cm",):
            ins_name, to_mm = "cm", 10.0
        elif hint in ("m",):
            ins_name, to_mm = "m", 1000.0

    paths: List[List[Point]] = []
    warnings: List[str] = []
    eps = close_threshold_um * 1e-3

    def add_path(seq: Iterable[Point]):
        pts = list(seq)
        pts = [(x * to_mm, y * to_mm) for x, y in pts]
        pts = _dedupe_close(pts, eps_mm=eps)
        if len(pts) >= 2:
            paths.append(pts)

    # Collect entities
    for e in msp:
        t = e.dxftype()
        try:
            if t == "LINE":
                add_path([(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)])
            elif t in ("LWPOLYLINE", "POLYLINE"):
                # Prefer virtual_entities to respect bulge arcs
                if hasattr(e, "virtual_entities"):
                    seg = []
                    last = None
                    for v in e.virtual_entities():
                        vt = v.dxftype()
                        if vt == "LINE":
                            p0 = (v.dxf.start.x, v.dxf.start.y)
                            p1 = (v.dxf.end.x, v.dxf.end.y)
                            if not seg:
                                seg.append(p0)
                            seg.append(p1)
                        elif vt == "ARC":
                            cx, cy = v.dxf.center.x, v.dxf.center.y
                            r = v.dxf.radius
                            pts = _approx_arc(cx, cy, r, v.dxf.start_angle, v.dxf.end_angle, arc_step_deg)
                            if not seg:
                                seg.append(pts[0])
                            seg.extend(pts[1:])
                        else:
                            warnings.append(f"Unsupported segment {vt} flattened.")
                    if seg:
                        add_path(seg)
                else:
                    pts = [(x, y) for x, y, *_ in e.get_points("xy")]
                    add_path(pts)
            elif t == "ARC":
                cx, cy = e.dxf.center.x, e.dxf.center.y
                r = e.dxf.radius
                pts = _approx_arc(cx, cy, r, e.dxf.start_angle, e.dxf.end_angle, arc_step_deg)
                add_path(pts)
            elif t == "CIRCLE":
                cx, cy = e.dxf.center.x, e.dxf.center.y
                r = e.dxf.radius
                pts = _approx_arc(cx, cy, r, 0.0, 360.0, arc_step_deg)
                add_path(pts)
            elif t == "SPLINE":
                # Approximate with built-in helper if present
                if hasattr(e, "approximate"):
                    pts = [(x, y) for x, y, _ in e.approximate(segments=64)]
                else:
                    pts = [(x, y) for x, y, _ in e.construction_tool().approximate(64)]
                add_path(pts)
            else:
                # ignore text, dims, etc.
                pass
        except Exception as ex:
            warnings.append(f"Failed to parse {t}: {ex!r}")

    if not paths:
        return [], DXFMeta(ins_name, to_mm, 0, 0, (0, 0, 0, 0), 0.0, warnings or ["No drawable entities found."])

    # Normalize origin
    minx = min(p[0] for path in paths for p in path)
    miny = min(p[1] for path in paths for p in path)
    maxx = max(p[0] for path in paths for p in path)
    maxy = max(p[1] for path in paths for p in path)

    if origin == "lower_left":
        dx, dy = -minx, -miny
    elif origin == "center":
        cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
        dx, dy = -cx, -cy
    else:
        dx, dy = 0.0, 0.0

    norm_paths: List[List[Point]] = [[(x + dx, y + dy) for (x, y) in path] for path in paths]
    total_len = sum(_length(p) for p in norm_paths)

    meta = DXFMeta(
        units_name=ins_name,
        to_mm=to_mm,
        path_count=len(norm_paths),
        vertex_count=sum(len(p) for p in norm_paths),
        bbox=(minx + dx, miny + dy, maxx + dx, maxy + dy),
        total_length_mm=total_len,
        warnings=warnings,
    )
    return norm_paths, meta
