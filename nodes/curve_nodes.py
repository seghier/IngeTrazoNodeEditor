# SPDX-License-Identifier: GPL-3.0-or-later
"""Parametric 2D/3D Curve Shape Nodes."""

from __future__ import annotations
import math
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from ..core_types import AccessMode, CurveData, MeshData, SocketType, Vec3, extract_plane_frame
    from ..node_base import BaseNode, DynamicInputsMixin, InputSpec, OutputSpec, register_node, NODE_REGISTRY
except (ImportError, ValueError):
    from core_types import AccessMode, CurveData, MeshData, SocketType, Vec3, extract_plane_frame
    from node_base import BaseNode, DynamicInputsMixin, InputSpec, OutputSpec, register_node, NODE_REGISTRY


# ============================================================================
# 1. Circle Curve Node
# ============================================================================
@register_node
class CircleCurveNode(BaseNode):
    type_id = "curve.circle"
    title = "Circle Curve"
    category = "Curves"
    description = "Generates a closed circular polyline curve and optional planar face."
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("radius", "Radius (m)", SocketType.FLOAT, default=2.0, min_val=0.01, step=0.1),
        InputSpec("angle", "Angle (°)", SocketType.FLOAT, default=360.0, min_val=1.0, max_val=360.0, step=5.0),
        InputSpec("segments", "Segments", SocketType.INT, default=32, min_val=3, max_val=256, step=1),
        InputSpec("center", "Center", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
    ]
    outputs = [
        OutputSpec("curve", "Curve", SocketType.CURVE),
        OutputSpec("face", "Face", SocketType.MESH),
    ]

    def compute(self, radius: float, angle: float = 360.0, segments: int = 32, center: Vec3 = None) -> Dict[str, Any]:
        r = max(1e-4, float(radius))
        ang_deg = float(angle) if angle is not None else 360.0
        n = max(3, int(segments))
        c = center or Vec3()

        is_full_circle = abs(ang_deg) >= 360.0 or abs(ang_deg) < 1e-4

        pts: List[Vec3] = []
        if is_full_circle:
            for i in range(n):
                ang = 2.0 * math.pi * i / n
                pts.append(Vec3(c.x + r * math.cos(ang), c.y + r * math.sin(ang), c.z))
            curve = CurveData(points=pts, closed=True)
            face = curve.to_mesh_face("CircleFace")
        else:
            total_rad = math.radians(ang_deg)
            for i in range(n + 1):
                ang = total_rad * i / n
                pts.append(Vec3(c.x + r * math.cos(ang), c.y + r * math.sin(ang), c.z))
            curve = CurveData(points=pts, closed=False)
            sector_curve = CurveData(points=[c] + pts, closed=True)
            face = sector_curve.to_mesh_face("ArcFace")

        return {
            "curve": curve,
            "face": face,
        }


# ============================================================================
# 2. Rectangle Curve Node (with optional Corner Fillet)
# ============================================================================
@register_node
class RectangleCurveNode(BaseNode):
    type_id = "curve.rectangle"
    title = "Rectangle Curve"
    category = "Curves"
    description = (
        "Generates a rectangular polyline with optional rounded fillet corners.\n"
        "Supports drawing from corner or centered on origin/plane, with 3D plane orientation."
    )
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("width", "Width (X)", SocketType.FLOAT, default=6.0, min_val=0.01, step=0.5),
        InputSpec("length", "Length (Y)", SocketType.FLOAT, default=4.0, min_val=0.01, step=0.5),
        InputSpec("fillet", "Fillet Radius", SocketType.FLOAT, default=0.0, min_val=0.0, step=0.1),
        InputSpec("origin", "Origin / Plane", SocketType.ANY, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("plane", "Plane", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("centered", "Center", SocketType.BOOL, default=True),
    ]
    outputs = [
        OutputSpec("curve", "Curve", SocketType.CURVE),
        OutputSpec("face", "Face", SocketType.MESH),
    ]

    def compute(
        self,
        width: float = 6.0,
        length: float = 4.0,
        fillet: float = 0.0,
        origin: Any = None,
        centered: Any = True,
        plane: Any = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        # Handle backwards-compatibility and flexible wiring
        if "center" in kwargs:
            c_val = kwargs["center"]
            if isinstance(c_val, bool):
                centered = c_val
            elif c_val is not None:
                origin = c_val

        # If boolean toggle was wired into origin socket
        if isinstance(origin, bool):
            centered = origin
            origin = None

        frame_src = plane if plane is not None else origin
        p0, u, v, n = extract_plane_frame(frame_src)

        w = max(1e-4, float(width))
        l = max(1e-4, float(length))
        is_centered = bool(centered)

        if is_centered:
            hw, hl = w * 0.5, l * 0.5
            x_min, x_max = -hw, hw
            y_min, y_max = -hl, hl
        else:
            x_min, x_max = 0.0, w
            y_min, y_max = 0.0, l

        r = max(0.0, min(float(fillet), (x_max - x_min) * 0.5 - 1e-4, (y_max - y_min) * 0.5 - 1e-4))

        local_pts: List[Tuple[float, float]] = []
        if r < 1e-4:
            local_pts = [
                (x_min, y_min),
                (x_max, y_min),
                (x_max, y_max),
                (x_min, y_max),
            ]
        else:
            # 4 filleted corners CCW: SE, NE, NW, SW
            corners = [
                (x_max - r, y_min + r, 270.0, 360.0),  # SE
                (x_max - r, y_max - r, 0.0, 90.0),     # NE
                (x_min + r, y_max - r, 90.0, 180.0),   # NW
                (x_min + r, y_min + r, 180.0, 270.0),  # SW
            ]
            segs_per_corner = 6
            for cx, cy, start_deg, end_deg in corners:
                for s in range(segs_per_corner):
                    ang = math.radians(start_deg + (end_deg - start_deg) * s / segs_per_corner)
                    local_pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))

        # Transform local (lx, ly) to 3D world: P = p0 + lx*u + ly*v
        world_pts: List[Vec3] = []
        for lx, ly in local_pts:
            wx = p0.x + lx * u.x + ly * v.x
            wy = p0.y + lx * u.y + ly * v.y
            wz = p0.z + lx * u.z + ly * v.z
            world_pts.append(Vec3(wx, wy, wz))

        curve = CurveData(points=world_pts, closed=True)
        return {
            "curve": curve,
            "face": curve.to_mesh_face("RectangleFace"),
        }


# ============================================================================
# 3. Ellipse Curve Node
# ============================================================================
@register_node
class EllipseCurveNode(BaseNode):
    type_id = "curve.ellipse"
    title = "Ellipse Curve"
    category = "Curves"
    description = "Generates an elliptical polyline with independent X and Y radii."
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("radius_x", "Radius X (m)", SocketType.FLOAT, default=3.0, min_val=0.01, step=0.2),
        InputSpec("radius_y", "Radius Y (m)", SocketType.FLOAT, default=1.8, min_val=0.01, step=0.2),
        InputSpec("segments", "Segments", SocketType.INT, default=36, min_val=6, max_val=256, step=1),
        InputSpec("center", "Center", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
    ]
    outputs = [
        OutputSpec("curve", "Curve", SocketType.CURVE),
        OutputSpec("face", "Face", SocketType.MESH),
    ]

    def compute(self, radius_x: float, radius_y: float, segments: int, center: Vec3) -> Dict[str, Any]:
        rx = max(1e-4, float(radius_x))
        ry = max(1e-4, float(radius_y))
        n = max(6, int(segments))
        c = center or Vec3()
        pts: List[Vec3] = []
        for i in range(n):
            ang = 2.0 * math.pi * i / n
            pts.append(Vec3(c.x + rx * math.cos(ang), c.y + ry * math.sin(ang), c.z))
        curve = CurveData(points=pts, closed=True)
        return {
            "curve": curve,
            "face": curve.to_mesh_face("EllipseFace"),
        }


# ============================================================================
# 4. Regular Polygon Curve Node
# ============================================================================
@register_node
class RegularPolygonCurveNode(BaseNode):
    type_id = "curve.polygon"
    title = "Polygon Curve"
    category = "Curves"
    description = "Generates a regular polygon (triangle, pentagon, hexagon, octagon, etc.)."
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("radius", "Radius (m)", SocketType.FLOAT, default=2.5, min_val=0.01, step=0.2),
        InputSpec("sides", "Sides", SocketType.INT, default=6, min_val=3, max_val=64, step=1),
        InputSpec("center", "Center", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
    ]
    outputs = [
        OutputSpec("curve", "Curve", SocketType.CURVE),
        OutputSpec("face", "Face", SocketType.MESH),
    ]

    def compute(self, radius: float, sides: int, center: Vec3) -> Dict[str, Any]:
        r = max(1e-4, float(radius))
        s = max(3, int(sides))
        c = center or Vec3()
        pts: List[Vec3] = []
        for i in range(s):
            ang = 2.0 * math.pi * i / s
            pts.append(Vec3(c.x + r * math.cos(ang), c.y + r * math.sin(ang), c.z))
        curve = CurveData(points=pts, closed=True)
        return {
            "curve": curve,
            "face": curve.to_mesh_face("PolygonFace"),
        }


# ============================================================================
# 5. Star Curve Node
# ============================================================================
@register_node
class StarCurveNode(BaseNode):
    type_id = "curve.star"
    title = "Star Curve"
    category = "Curves"
    description = "Generates an n-pointed parametric star polyline."
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("inner_radius", "Inner Radius", SocketType.FLOAT, default=1.2, min_val=0.01, step=0.1),
        InputSpec("outer_radius", "Outer Radius", SocketType.FLOAT, default=2.8, min_val=0.01, step=0.1),
        InputSpec("points_count", "Points Count", SocketType.INT, default=5, min_val=3, max_val=32, step=1),
        InputSpec("center", "Center", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
    ]
    outputs = [
        OutputSpec("curve", "Curve", SocketType.CURVE),
        OutputSpec("face", "Face", SocketType.MESH),
    ]

    def compute(self, inner_radius: float, outer_radius: float, points_count: int, center: Vec3) -> Dict[str, Any]:
        r_in = max(1e-4, float(inner_radius))
        r_out = max(r_in + 1e-4, float(outer_radius))
        n = max(3, int(points_count))
        c = center or Vec3()
        pts: List[Vec3] = []
        for i in range(2 * n):
            ang = math.pi * i / n
            r = r_out if (i % 2 == 0) else r_in
            pts.append(Vec3(c.x + r * math.cos(ang), c.y + r * math.sin(ang), c.z))
        curve = CurveData(points=pts, closed=True)
        return {
            "curve": curve,
            "face": curve.to_mesh_face("StarFace"),
        }


# ============================================================================
# 6. Slot / Capsule Curve Node
# ============================================================================
@register_node
class SlotCapsuleCurveNode(BaseNode):
    type_id = "curve.slot"
    title = "Slot / Capsule"
    category = "Curves"
    description = "Generates a pill / stadium / elongated slot polyline."
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("length", "Length (m)", SocketType.FLOAT, default=5.0, min_val=0.1, step=0.5),
        InputSpec("width", "Width (m)", SocketType.FLOAT, default=2.0, min_val=0.1, step=0.2),
        InputSpec("center", "Center", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
    ]
    outputs = [
        OutputSpec("curve", "Curve", SocketType.CURVE),
        OutputSpec("face", "Face", SocketType.MESH),
    ]

    def compute(self, length: float, width: float, center: Vec3) -> Dict[str, Any]:
        l = max(0.1, float(length))
        w = max(0.05, float(width))
        c = center or Vec3()
        r = w * 0.5
        d = max(0.0, l * 0.5 - r)

        pts: List[Vec3] = []
        segs = 12
        # Right semicircular cap
        for i in range(segs + 1):
            ang = -math.pi * 0.5 + math.pi * i / segs
            pts.append(Vec3(c.x + d + r * math.cos(ang), c.y + r * math.sin(ang), c.z))
        # Left semicircular cap
        for i in range(segs + 1):
            ang = math.pi * 0.5 + math.pi * i / segs
            pts.append(Vec3(c.x - d + r * math.cos(ang), c.y + r * math.sin(ang), c.z))

        curve = CurveData(points=pts, closed=True)
        return {
            "curve": curve,
            "face": curve.to_mesh_face("SlotFace"),
        }


# ============================================================================
# 7. Architectural L-Shape Profile Curve Node
# ============================================================================
@register_node
class LShapeCurveNode(BaseNode):
    type_id = "curve.l_shape"
    title = "L-Shape Profile"
    category = "Curves"
    description = "Generates an architectural or structural L-shape polyline."
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("width", "Width (m)", SocketType.FLOAT, default=8.0, min_val=0.5, step=0.5),
        InputSpec("length", "Length (m)", SocketType.FLOAT, default=10.0, min_val=0.5, step=0.5),
        InputSpec("leg_x", "Leg X (m)", SocketType.FLOAT, default=3.5, min_val=0.2, step=0.5),
        InputSpec("leg_y", "Leg Y (m)", SocketType.FLOAT, default=4.0, min_val=0.2, step=0.5),
        InputSpec("center", "Center", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
    ]
    outputs = [
        OutputSpec("curve", "Curve", SocketType.CURVE),
        OutputSpec("face", "Face", SocketType.MESH),
    ]

    def compute(self, width: float, length: float, leg_x: float, leg_y: float, center: Vec3) -> Dict[str, Any]:
        w = max(0.5, float(width))
        l = max(0.5, float(length))
        lx = min(w - 0.1, max(0.1, float(leg_x)))
        ly = min(l - 0.1, max(0.1, float(leg_y)))
        c = center or Vec3()

        pts = [
            Vec3(c.x, c.y, c.z),
            Vec3(c.x + w, c.y, c.z),
            Vec3(c.x + w, c.y + ly, c.z),
            Vec3(c.x + lx, c.y + ly, c.z),
            Vec3(c.x + lx, c.y + l, c.z),
            Vec3(c.x, c.y + l, c.z),
        ]
        curve = CurveData(points=pts, closed=True)
        return {
            "curve": curve,
            "face": curve.to_mesh_face("LShapeFace"),
        }


# ============================================================================
# 8. Structural I-Beam / H-Profile Curve Node
# ============================================================================
@register_node
class IShapeCurveNode(BaseNode):
    type_id = "curve.i_shape"
    title = "I-Beam Profile"
    category = "Curves"
    description = "Generates a structural steel I-beam or H-profile cross section."
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("width", "Flange Width (m)", SocketType.FLOAT, default=0.30, min_val=0.05, step=0.05),
        InputSpec("height", "Total Height (m)", SocketType.FLOAT, default=0.50, min_val=0.05, step=0.05),
        InputSpec("flange_thick", "Flange Thick (m)", SocketType.FLOAT, default=0.04, min_val=0.01, step=0.01),
        InputSpec("web_thick", "Web Thick (m)", SocketType.FLOAT, default=0.025, min_val=0.01, step=0.01),
        InputSpec("center", "Center", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
    ]
    outputs = [
        OutputSpec("curve", "Curve", SocketType.CURVE),
        OutputSpec("face", "Face", SocketType.MESH),
    ]

    def compute(self, width: float, height: float, flange_thick: float, web_thick: float, center: Vec3) -> Dict[str, Any]:
        bf = max(0.05, float(width))
        d = max(0.05, float(height))
        tf = min(d * 0.4, max(0.005, float(flange_thick)))
        tw = min(bf * 0.8, max(0.005, float(web_thick)))
        c = center or Vec3()

        hw, hh = bf * 0.5, d * 0.5
        htw = tw * 0.5

        # 12 CCW vertices of an I-beam
        pts = [
            Vec3(c.x - hw, c.y - hh, c.z),
            Vec3(c.x + hw, c.y - hh, c.z),
            Vec3(c.x + hw, c.y - hh + tf, c.z),
            Vec3(c.x + htw, c.y - hh + tf, c.z),
            Vec3(c.x + htw, c.y + hh - tf, c.z),
            Vec3(c.x + hw, c.y + hh - tf, c.z),
            Vec3(c.x + hw, c.y + hh, c.z),
            Vec3(c.x - hw, c.y + hh, c.z),
            Vec3(c.x - hw, c.y + hh - tf, c.z),
            Vec3(c.x - htw, c.y + hh - tf, c.z),
            Vec3(c.x - htw, c.y - hh + tf, c.z),
            Vec3(c.x - hw, c.y - hh + tf, c.z),
        ]
        curve = CurveData(points=pts, closed=True)
        return {
            "curve": curve,
            "face": curve.to_mesh_face("IBeamFace"),
        }


# ============================================================================
# 9. Spiral / Helix Curve Node
# ============================================================================
@register_node
class SpiralCurveNode(BaseNode):
    type_id = "curve.spiral"
    title = "Spiral / Helix"
    category = "Curves"
    description = "Generates a 2D or 3D Archimedean spiral or helical stair path."
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("start_radius", "Start Radius", SocketType.FLOAT, default=1.0, min_val=0.0, step=0.2),
        InputSpec("end_radius", "End Radius", SocketType.FLOAT, default=3.0, min_val=0.0, step=0.2),
        InputSpec("turns", "Turns", SocketType.FLOAT, default=3.0, min_val=0.5, max_val=20.0, step=0.5),
        InputSpec("height", "Total Height", SocketType.FLOAT, default=2.5, min_val=0.0, step=0.5),
        InputSpec("segments", "Segments", SocketType.INT, default=96, min_val=12, max_val=512, step=12),
        InputSpec("center", "Center", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
    ]
    outputs = [
        OutputSpec("curve", "Curve", SocketType.CURVE),
    ]

    def compute(
        self,
        start_radius: float,
        end_radius: float,
        turns: float,
        height: float,
        segments: int,
        center: Vec3,
    ) -> Dict[str, Any]:
        r0 = max(0.0, float(start_radius))
        r1 = max(0.0, float(end_radius))
        t = max(0.1, float(turns))
        h = float(height)
        n = max(12, int(segments))
        c = center or Vec3()

        total_angle = 2.0 * math.pi * t
        pts: List[Vec3] = []
        for i in range(n + 1):
            frac = i / n
            ang = total_angle * frac
            cur_r = r0 + (r1 - r0) * frac
            cur_z = c.z + h * frac
            pts.append(Vec3(c.x + cur_r * math.cos(ang), c.y + cur_r * math.sin(ang), cur_z))

        curve = CurveData(points=pts, closed=False)
        return {"curve": curve}


@register_node
class LineNode(BaseNode):
    type_id = "curve.line"
    title = "Line Segment"
    category = "Curves"
    description = "Generates a straight 3D line curve connecting start point A and end point B."
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("start", "Start Pt A", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("end", "End Pt B", SocketType.VEC3, default=Vec3(5, 0, 0), hide_widget=True),
    ]
    outputs = [
        OutputSpec("curve", "Curve", SocketType.CURVE),
        OutputSpec("length", "Length (m)", SocketType.FLOAT),
    ]

    def compute(self, start: Vec3, end: Vec3) -> Dict[str, Any]:
        p0 = start or Vec3()
        p1 = end or Vec3(1, 0, 0)
        curve = CurveData(points=[p0, p1], closed=False)
        length = (p1 - p0).length()
        return {"curve": curve, "length": length}


@register_node
class FaceFromPointsNode(BaseNode):
    type_id = "curve.face_from_points"
    title = "Face from Points"
    category = "Curves"
    description = "Generates a planar 2D/3D polygon face mesh from boundary vertices and optional hole loops."
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("points", "Boundary Points", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("holes", "Holes", SocketType.ANY, default=None, hide_widget=True),
    ]
    outputs = [
        OutputSpec("face", "Face Mesh", SocketType.MESH),
    ]

    def compute(self, points: Any, holes: Any = None) -> Dict[str, Any]:
        outer: List[Vec3] = []
        if isinstance(points, CurveData):
            outer = list(points.points)
        elif isinstance(points, list):
            for p in points:
                if isinstance(p, Vec3):
                    outer.append(p)
                elif isinstance(p, (tuple, list)) and len(p) >= 3:
                    outer.append(Vec3(float(p[0]), float(p[1]), float(p[2])))

        if len(outer) < 3:
            outer = [Vec3(0, 0, 0), Vec3(4, 0, 0), Vec3(4, 4, 0), Vec3(0, 4, 0)]

        outer_curve = CurveData(points=outer, closed=True)
        face_mesh = outer_curve.to_mesh_face("PlanarPolygonFace")
        return {"face": face_mesh}


# ============================================================================
# 11b. Face Outline Node (Extract Outline / Boundary Curves from Face)
# ============================================================================
@register_node
class FaceOutlineNode(BaseNode):
    type_id = "curve.face_outline"
    title = "Face Outline"
    category = "Curves"
    description = (
        "Extracts closed boundary outline curve(s) from any input face, surface, or planar mesh.\n"
        "Outputs the outer perimeter curve, interior hole loops, and ordered boundary vertices."
    )
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("face", "Face / Surface", SocketType.ANY, default=None, hide_widget=True),
    ]
    outputs = [
        OutputSpec("curve", "Outline Curve", SocketType.CURVE),
        OutputSpec("holes", "Holes", SocketType.CURVE),
        OutputSpec("points", "Points", SocketType.VEC3),
        OutputSpec("count", "Count", SocketType.INT),
    ]

    def compute(self, face: Any = None) -> Dict[str, Any]:
        if face is None:
            d_pts = [Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(1, 1, 0), Vec3(0, 1, 0)]
            d_c = CurveData(points=d_pts, closed=True)
            return {"curve": d_c, "holes": [], "points": d_pts, "count": 4}

        if isinstance(face, CurveData):
            return {
                "curve": face,
                "holes": [],
                "points": list(face.points),
                "count": len(face.points),
            }

        if isinstance(face, dict):
            if "outer" in face:
                raw_outer = face["outer"]
                if isinstance(raw_outer, CurveData):
                    outer_c = raw_outer
                else:
                    outer_pts = [p if isinstance(p, Vec3) else Vec3(float(p[0]), float(p[1]), float(p[2])) for p in raw_outer]
                    outer_c = CurveData(points=outer_pts, closed=True)
                raw_holes = face.get("holes", [])
                hole_curves = []
                for h in raw_holes:
                    if isinstance(h, CurveData):
                        hole_curves.append(h)
                    elif isinstance(h, list) and h:
                        h_pts = [p if isinstance(p, Vec3) else Vec3(float(p[0]), float(p[1]), float(p[2])) for p in h]
                        hole_curves.append(CurveData(points=h_pts, closed=True))
                return {
                    "curve": outer_c,
                    "holes": hole_curves,
                    "points": list(outer_c.points),
                    "count": len(outer_c.points),
                }
            if "curve" in face and isinstance(face["curve"], CurveData):
                return {
                    "curve": face["curve"],
                    "holes": face.get("holes", []),
                    "points": list(face["curve"].points),
                    "count": len(face["curve"].points),
                }
            if "face" in face:
                return self.compute(face["face"])
            if "mesh" in face:
                return self.compute(face["mesh"])

        # Handle IngeTrazo native Face or Group objects
        if hasattr(face, "outer_loop"):
            loop_pts = []
            try:
                for v in getattr(face.outer_loop, "vertices", []):
                    pos = getattr(v, "position", None) or getattr(v, "pos", None)
                    if pos is not None:
                        loop_pts.append(Vec3(float(pos.x()), float(pos.y()), float(pos.z())))
            except Exception:
                pass
            if loop_pts:
                c = CurveData(points=loop_pts, closed=True)
                return {"curve": c, "holes": [], "points": loop_pts, "count": len(loop_pts)}

        if hasattr(face, "mesh"):
            face = getattr(face, "mesh")

        # Handle MeshData
        if isinstance(face, MeshData):
            verts = face.vertices
            faces = face.faces
            if not faces and verts:
                pts = [Vec3(v[0], v[1], v[2]) for v in verts]
                c = CurveData(points=pts, closed=True)
                return {"curve": c, "holes": [], "points": pts, "count": len(pts)}
            if len(faces) == 1:
                pts = [Vec3(verts[i][0], verts[i][1], verts[i][2]) for i in faces[0]]
                c = CurveData(points=pts, closed=True)
                return {"curve": c, "holes": [], "points": pts, "count": len(pts)}

            # Multi-face mesh: topological boundary half-edges
            half_edges = set()
            edge_counts = {}
            for f in faces:
                fn = len(f)
                for i in range(fn):
                    u, v = f[i], f[(i + 1) % fn]
                    half_edges.add((u, v))
                    undir = (min(u, v), max(u, v))
                    edge_counts[undir] = edge_counts.get(undir, 0) + 1

            boundary_next = {}
            for (u, v) in half_edges:
                if (v, u) not in half_edges or edge_counts.get((min(u, v), max(u, v)), 0) == 1:
                    boundary_next[u] = v

            loops = []
            if boundary_next:
                visited = set()
                for start in list(boundary_next.keys()):
                    if start in visited:
                        continue
                    curr = start
                    loop = []
                    while curr is not None and curr not in visited:
                        visited.add(curr)
                        loop.append(curr)
                        curr = boundary_next.get(curr)
                        if curr == start:
                            break
                    if len(loop) >= 3:
                        loops.append(loop)

            if not loops:
                pts = [Vec3(v[0], v[1], v[2]) for v in verts]
                c = CurveData(points=pts, closed=True)
                return {"curve": c, "holes": [], "points": pts, "count": len(pts)}

            def loop_perimeter(lp):
                p = 0.0
                for i in range(len(lp)):
                    p0 = verts[lp[i]]
                    p1 = verts[lp[(i + 1) % len(lp)]]
                    p += ((p1[0] - p0[0]) ** 2 + (p1[1] - p0[1]) ** 2 + (p1[2] - p0[2]) ** 2) ** 0.5
                return p

            sorted_loops = sorted(loops, key=loop_perimeter, reverse=True)
            outer_loop = sorted_loops[0]
            hole_loops = sorted_loops[1:]

            outer_pts = [Vec3(verts[i][0], verts[i][1], verts[i][2]) for i in outer_loop]
            outer_curve = CurveData(points=outer_pts, closed=True)
            hole_curves = [
                CurveData(points=[Vec3(verts[i][0], verts[i][1], verts[i][2]) for i in hl], closed=True)
                for hl in hole_loops
            ]

            return {
                "curve": outer_curve,
                "holes": hole_curves,
                "points": outer_pts,
                "count": len(outer_pts),
            }

        # Fallback if list of points
        if isinstance(face, (list, tuple)) and face:
            pts = [p if isinstance(p, Vec3) else Vec3(float(p[0]), float(p[1]), float(p[2])) for p in face]
            c = CurveData(points=pts, closed=True)
            return {"curve": c, "holes": [], "points": pts, "count": len(pts)}

        # Default fallback
        d_pts = [Vec3(0, 0, 0), Vec3(1, 0, 0), Vec3(1, 1, 0), Vec3(0, 1, 0)]
        d_c = CurveData(points=d_pts, closed=True)
        return {"curve": d_c, "holes": [], "points": d_pts, "count": 4}


# ============================================================================
# 11. Curve / Surface Points Extraction Node
# ============================================================================
@register_node
class CurvePointsNode(BaseNode):
    type_id = "curve.points"
    title = "Curve Points"
    category = "Curves"
    description = "Extracts vertices or boundary points from any input curve or surface / planar mesh."
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("geometry", "Curve / Surface", SocketType.ANY, default=None, hide_widget=True),
    ]
    outputs = [
        OutputSpec("points", "Points", SocketType.VEC3),
        OutputSpec("curve", "Boundary Curve", SocketType.CURVE),
        OutputSpec("count", "Count", SocketType.INT),
    ]

    def compute(self, geometry: Any = None) -> Dict[str, Any]:
        pts: List[Vec3] = []
        is_closed = True

        if isinstance(geometry, CurveData):
            pts = [Vec3(p.x, p.y, p.z) for p in geometry.points]
            is_closed = geometry.closed
        elif isinstance(geometry, MeshData):
            verts = geometry.vertices
            faces = geometry.faces
            if faces:
                if len(faces) == 1:
                    pts = [Vec3(verts[i][0], verts[i][1], verts[i][2]) for i in faces[0]]
                else:
                    half_edges = set()
                    edge_counts = {}
                    for face in faces:
                        fn = len(face)
                        for i in range(fn):
                            u, v = face[i], face[(i + 1) % fn]
                            half_edges.add((u, v))
                            undir = (min(u, v), max(u, v))
                            edge_counts[undir] = edge_counts.get(undir, 0) + 1

                    boundary_next = {}
                    for (u, v) in half_edges:
                        if (v, u) not in half_edges or edge_counts.get((min(u, v), max(u, v)), 0) == 1:
                            boundary_next[u] = v

                    if boundary_next:
                        visited = set()
                        loops = []
                        for start_node in list(boundary_next.keys()):
                            if start_node in visited:
                                continue
                            loop = []
                            curr = start_node
                            while curr is not None and curr not in visited:
                                visited.add(curr)
                                loop.append(curr)
                                curr = boundary_next.get(curr)
                                if curr == start_node:
                                    break
                            if len(loop) >= 2:
                                loops.append(loop)

                        if loops:
                            def loop_perimeter(lp):
                                p = 0.0
                                for i in range(len(lp)):
                                    p0 = verts[lp[i]]
                                    p1 = verts[lp[(i + 1) % len(lp)]]
                                    dx, dy, dz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
                                    p += (dx*dx + dy*dy + dz*dz)**0.5
                                return p

                            largest_loop = max(loops, key=loop_perimeter)
                            pts = [Vec3(verts[i][0], verts[i][1], verts[i][2]) for i in largest_loop]
                        else:
                            pts = [Vec3(v[0], v[1], v[2]) for v in verts]
                    else:
                        pts = [Vec3(v[0], v[1], v[2]) for v in verts]
            elif geometry.edges:
                pts = [Vec3(v[0], v[1], v[2]) for v in verts]
                is_closed = False
            elif verts:
                pts = [Vec3(v[0], v[1], v[2]) for v in verts]
                is_closed = False
        elif isinstance(geometry, list):
            for item in geometry:
                if isinstance(item, Vec3):
                    pts.append(item)
                elif isinstance(item, (tuple, list)) and len(item) >= 3:
                    pts.append(Vec3(float(item[0]), float(item[1]), float(item[2])))
            is_closed = False
        elif isinstance(geometry, Vec3):
            pts = [geometry]
            is_closed = False

        curve = CurveData(points=pts, closed=is_closed)
        return {
            "points": pts,
            "curve": curve,
            "count": len(pts),
        }


# ============================================================================
# 13. Divide Curve Node
# ============================================================================
@register_node
class DivideCurveNode(BaseNode):
    type_id = "curve.divide"
    title = "Divide Curve"
    category = "Curves"
    description = (
        "Divide a curve or face boundary into equal-length segments, outputting division points, tangent-aligned planes,\n"
        "tangent vectors, normal vectors, and segment curves along the perimeter."
    )
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("curve", "Curve / Face", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("count", "Count", SocketType.INT, default=10, min_val=1, max_val=500, step=1),
        InputSpec("include_ends", "Include Ends", SocketType.BOOL, default=True),
    ]
    outputs = [
        OutputSpec("points", "Points", SocketType.VEC3),
        OutputSpec("planes", "Planes", SocketType.ANY),
        OutputSpec("tangents", "Tangents", SocketType.VEC3, hide_preview=True),
        OutputSpec("normals", "Normals", SocketType.VEC3),
        OutputSpec("segments", "Segments", SocketType.ANY),
        OutputSpec("params", "Parameters (0-1)", SocketType.FLOAT),
        OutputSpec("curve", "Curve", SocketType.CURVE),
    ]

    def compute(self, curve: Any = None, count: int = 10, include_ends: bool = True) -> Dict[str, Any]:
        n_div = max(1, int(count))

        pts: List[Vec3] = []
        is_closed = False
        if isinstance(curve, CurveData) and curve.points:
            pts = [Vec3(p.x, p.y, p.z) for p in curve.points]
            is_closed = curve.closed
        elif isinstance(curve, MeshData):
            c = curve.perimeter_as_curve()
            pts = [Vec3(p.x, p.y, p.z) for p in c.points]
            is_closed = c.closed
        elif isinstance(curve, dict) and "outer" in curve:
            pts = [Vec3(float(p[0]), float(p[1]), float(p[2])) for p in curve.get("outer", [])]
            is_closed = True
        elif isinstance(curve, list) and curve:
            for p in curve:
                if isinstance(p, Vec3):
                    pts.append(p)
                elif isinstance(p, (list, tuple)) and len(p) >= 3:
                    pts.append(Vec3(float(p[0]), float(p[1]), float(p[2])))
            is_closed = False

        if len(pts) < 2:
            pts = [Vec3(0.0, 0.0, 0.0), Vec3(10.0, 0.0, 0.0)]
            is_closed = False

        poly_pts = list(pts)
        if is_closed and (poly_pts[0].distance_to(poly_pts[-1]) > 1e-4):
            poly_pts.append(poly_pts[0])

        cum_lens: List[float] = [0.0]
        for i in range(len(poly_pts) - 1):
            seg_len = poly_pts[i].distance_to(poly_pts[i + 1])
            cum_lens.append(cum_lens[-1] + seg_len)

        total_len = cum_lens[-1]
        out_curve = CurveData(points=pts, closed=is_closed)
        if total_len < 1e-9:
            deg_p = poly_pts[0]
            deg_plane = {
                "origin": (deg_p.x, deg_p.y, deg_p.z),
                "u": (1.0, 0.0, 0.0),
                "v": (0.0, 1.0, 0.0),
                "normal": (0.0, 0.0, 1.0),
            }
            return {
                "points": [deg_p],
                "planes": [deg_plane],
                "tangents": [Vec3(1.0, 0.0, 0.0)],
                "normals": [Vec3(0.0, 1.0, 0.0)],
                "segments": [],
                "params": [0.0],
                "curve": out_curve,
            }

        div_points: List[Vec3] = []
        div_planes: List[Dict[str, Any]] = []
        div_tangents: List[Vec3] = []
        div_normals: List[Vec3] = []
        div_params: List[float] = []

        if is_closed:
            targets = [i * (total_len / n_div) for i in range(n_div)]
        else:
            if include_ends:
                targets = [i * (total_len / n_div) for i in range(n_div + 1)]
            else:
                targets = [(i + 1) * (total_len / (n_div + 1)) for i in range(n_div)]

        def sample_at(dist: float) -> Tuple[Vec3, Vec3]:
            idx = 0
            while idx < len(cum_lens) - 2 and cum_lens[idx + 1] < dist:
                idx += 1
            l0, l1 = cum_lens[idx], cum_lens[idx + 1]
            p0, p1 = poly_pts[idx], poly_pts[idx + 1]
            seg_l = max(1e-9, l1 - l0)
            t = max(0.0, min(1.0, (dist - l0) / seg_l))
            pt = Vec3(p0.x + t * (p1.x - p0.x), p0.y + t * (p1.y - p0.y), p0.z + t * (p1.z - p0.z))
            tang = (p1 - p0).normalized()
            return pt, tang

        for d in targets:
            p, t = sample_at(d)
            u = t.normalized()
            if u.length() < 1e-6:
                u = Vec3(1.0, 0.0, 0.0)

            # Upright guide vector
            if abs(u.z) < 0.95:
                guide = Vec3(0.0, 0.0, 1.0)
            else:
                guide = Vec3(1.0, 0.0, 0.0)

            # Normal vector in horizontal / transverse plane (guide x u)
            v_raw = guide.cross(u)
            v = v_raw.normalized()
            if v.length() < 1e-6:
                v = Vec3(0.0, 1.0, 0.0)

            # Upright vector normal to plane (u x v)
            n = u.cross(v).normalized()

            plane_dict = {
                "origin": (p.x, p.y, p.z),
                "u": (u.x, u.y, u.z),
                "v": (v.x, v.y, v.z),
                "normal": (n.x, n.y, n.z),
            }

            div_points.append(p)
            div_planes.append(plane_dict)
            div_tangents.append(u)
            div_normals.append(v)
            div_params.append(round(d / total_len, 6))

        segments: List[CurveData] = []
        if is_closed:
            for i in range(len(div_points)):
                p_curr = div_points[i]
                p_next = div_points[(i + 1) % len(div_points)]
                segments.append(CurveData(points=[p_curr, p_next], closed=False))
        else:
            for i in range(len(div_points) - 1):
                segments.append(CurveData(points=[div_points[i], div_points[i + 1]], closed=False))

        return {
            "points": div_points,
            "planes": div_planes,
            "tangents": div_tangents,
            "normals": div_normals,
            "segments": segments,
            "params": div_params,
            "curve": out_curve,
        }


# ============================================================================
# 14. Offset Curve Node
# ============================================================================
@register_node
class OffsetCurveNode(BaseNode):
    type_id = "curve.offset"
    title = "Offset Curve"
    category = "Curves"
    description = (
        "Offset a curve or surface in its plane (like walls or window frames in IngeTrazo).\n"
        "Outputs the offset curve, a frame mesh, and the offset curve face (clean planar face, no triangulation)."
    )
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("curve", "Curve / Surface", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("distance", "Distance (m)", SocketType.FLOAT, default=0.2, min_val=-10.0, max_val=10.0, step=0.05),
        InputSpec("inset", "Inset (Inward)", SocketType.BOOL, default=True),
    ]
    outputs = [
        OutputSpec("curve", "Offset Curve", SocketType.CURVE),
        OutputSpec("frame", "Frame", SocketType.MESH),
        OutputSpec("face", "Curve Face", SocketType.MESH),
    ]

    @staticmethod
    def _line_intersect_2d(p0: Vec3, u: Vec3, p1: Vec3, v: Vec3, n: Vec3) -> Optional[Vec3]:
        cross_uv = u.cross(v)
        denom = cross_uv.dot(n)
        if abs(denom) < 1e-7:
            return Vec3((p0.x + p1.x) * 0.5, (p0.y + p1.y) * 0.5, (p0.z + p1.z) * 0.5)
        diff = p1 - p0
        diff_cross_v = diff.cross(v)
        s = diff_cross_v.dot(n) / denom
        return Vec3(p0.x + s * u.x, p0.y + s * u.y, p0.z + s * u.z)

    def compute(self, curve: Any = None, distance: float = 0.2, inset: bool = True) -> Dict[str, Any]:
        d = float(distance)
        if inset:
            d = abs(d)
        else:
            d = -abs(d)

        pts: List[Vec3] = []
        is_closed = True

        if isinstance(curve, CurveData) and curve.points:
            pts = [Vec3(p.x, p.y, p.z) for p in curve.points]
            is_closed = curve.closed
        elif isinstance(curve, MeshData):
            c = curve.perimeter_as_curve()
            pts = [Vec3(p.x, p.y, p.z) for p in c.points]
            is_closed = True
        elif isinstance(curve, dict) and "outer" in curve:
            pts = [Vec3(float(p[0]), float(p[1]), float(p[2])) for p in curve.get("outer", [])]
            is_closed = True
        elif isinstance(curve, list) and curve:
            for p in curve:
                if isinstance(p, Vec3):
                    pts.append(p)
                elif isinstance(p, (list, tuple)) and len(p) >= 3:
                    pts.append(Vec3(float(p[0]), float(p[1]), float(p[2])))
            is_closed = True

        # Default fallback: 2.0m x 1.5m window profile at Z=1.0m
        if len(pts) < 3:
            pts = [
                Vec3(0.0, 0.0, 1.0),
                Vec3(2.0, 0.0, 1.0),
                Vec3(2.0, 0.0, 2.5),
                Vec3(0.0, 0.0, 2.5),
            ]
            is_closed = True

        n_pts = len(pts)

        nx = ny = nz = 0.0
        for i in range(n_pts):
            p0 = pts[i]
            p1 = pts[(i + 1) % n_pts]
            nx += (p0.y - p1.y) * (p0.z + p1.z)
            ny += (p0.z - p1.z) * (p0.x + p1.x)
            nz += (p0.x - p1.x) * (p0.y + p1.y)
        norm_len = math.sqrt(nx * nx + ny * ny + nz * nz)
        if norm_len < 1e-9:
            normal = Vec3(0.0, 0.0, 1.0)
        else:
            normal = Vec3(nx / norm_len, ny / norm_len, nz / norm_len)

        offset_pts: List[Vec3] = []

        if is_closed and n_pts >= 3:
            offset_lines: List[Tuple[Vec3, Vec3]] = []
            for i in range(n_pts):
                a = pts[i]
                b = pts[(i + 1) % n_pts]
                edge = b - a
                e_dir = edge.normalized()
                inward = normal.cross(e_dir).normalized()
                line_pt = Vec3(a.x + inward.x * d, a.y + inward.y * d, a.z + inward.z * d)
                offset_lines.append((line_pt, e_dir))

            for i in range(n_pts):
                p0, u = offset_lines[(i - 1) % n_pts]
                p1, v = offset_lines[i]
                pt = self._line_intersect_2d(p0, u, p1, v, normal)
                if pt is None:
                    pt = pts[i]
                offset_pts.append(pt)

            for i in range(n_pts):
                orig_len = pts[i].distance_to(pts[(i + 1) % n_pts])
                new_len = offset_pts[i].distance_to(offset_pts[(i + 1) % n_pts])
                if new_len < 1e-4 or pts[i].distance_to(offset_pts[i]) > 10.0 * max(0.1, abs(d)):
                    centroid = Vec3(sum(p.x for p in pts) / n_pts, sum(p.y for p in pts) / n_pts, sum(p.z for p in pts) / n_pts)
                    scale_f = max(0.05, 1.0 - (d / max(1.0, orig_len)))
                    offset_pts = [Vec3(centroid.x + (p.x - centroid.x) * scale_f,
                                       centroid.y + (p.y - centroid.y) * scale_f,
                                       centroid.z + (p.z - centroid.z) * scale_f) for p in pts]
                    break
        else:
            for i in range(n_pts):
                if i == 0:
                    tang = (pts[1] - pts[0]).normalized()
                elif i == n_pts - 1:
                    tang = (pts[-1] - pts[-2]).normalized()
                else:
                    tang = (pts[i + 1] - pts[i - 1]).normalized()
                inward = normal.cross(tang).normalized()
                offset_pts.append(Vec3(pts[i].x + inward.x * d, pts[i].y + inward.y * d, pts[i].z + inward.z * d))

        offset_curve = CurveData(points=[Vec3(p.x, p.y, p.z) for p in offset_pts], closed=is_closed)

        frame_verts: List[Tuple[float, float, float]] = []
        frame_faces: List[List[int]] = []
        frame_edges: List[Tuple[int, int]] = []

        if is_closed and n_pts >= 3:
            def polygon_area(poly: List[Vec3], norm: Vec3) -> float:
                nx = ny = nz = 0.0
                k_len = len(poly)
                for k in range(k_len):
                    p0 = poly[k]
                    p1 = poly[(k + 1) % k_len]
                    nx += (p0.y - p1.y) * (p0.z + p1.z)
                    ny += (p0.z - p1.z) * (p0.x + p1.x)
                    nz += (p0.x - p1.x) * (p0.y + p1.y)
                return (nx * norm.x + ny * norm.y + nz * norm.z) * 0.5

            def ensure_ccw(poly: List[Vec3], norm: Vec3) -> List[Vec3]:
                if polygon_area(poly, norm) < 0:
                    return list(reversed(poly))
                return poly

            pts_ccw = ensure_ccw(pts, normal)
            off_ccw = ensure_ccw(offset_pts, normal)

            area_pts = polygon_area(pts_ccw, normal)
            area_off = polygon_area(off_ccw, normal)

            if area_off > area_pts:
                # Outward offset: offset_pts is larger outer ring, original pts is inner hole
                outer_loop = off_ccw
                hole_loop = pts_ccw
            else:
                # Inward offset: original pts is larger outer ring, offset_pts is inner hole
                outer_loop = pts_ccw
                hole_loop = off_ccw

            n_out = len(outer_loop)
            n_hole = len(hole_loop)

            for p in outer_loop:
                frame_verts.append((p.x, p.y, p.z))
            for p in hole_loop:
                frame_verts.append((p.x, p.y, p.z))

            # Single continuous annular face loop (outer loop CCW + bridge slit + inner hole CW + bridge back)
            single_face = list(range(n_out)) + [0, n_out] + [n_out + ((n_hole - 1 - j) % n_hole) for j in range(n_hole)] + [n_out, 0]
            frame_faces.append(single_face)

            # Only outer and inner boundary edges (NO radial dividing curves/edges!)
            for i in range(n_out):
                frame_edges.append((i, (i + 1) % n_out))
            for i in range(n_hole):
                frame_edges.append((n_out + i, n_out + (i + 1) % n_hole))

            frame_mesh = MeshData(
                vertices=frame_verts,
                faces=frame_faces,
                edges=frame_edges,
                name="Frame",
                material_name="Frame",
                color=(0.22, 0.24, 0.28),
                face_materials=["Frame"] * len(frame_faces),
                face_colors=[(0.22, 0.24, 0.28)] * len(frame_faces),
                outer=[(p.x, p.y, p.z) for p in outer_loop],
                holes=[[(p.x, p.y, p.z) for p in hole_loop]],
                holed_faces=[(list(range(n_out)), [list(range(n_out, n_out + n_hole))])],
            )
        else:
            for p in pts:
                frame_verts.append((p.x, p.y, p.z))
            for p in offset_pts:
                frame_verts.append((p.x, p.y, p.z))

            # Open curve ribbon (e.g. arc, polyline, line):
            # Form ONE single continuous planar face loop without interior radial dividing edges
            # Loop travels: 0 -> 1 -> ... -> n_pts - 1, across to 2*n_pts - 1 -> ... -> n_pts, back to 0
            ribbon_face = list(range(n_pts)) + list(range(2 * n_pts - 1, n_pts - 1, -1))

            # Orient ribbon_face so its normal matches the curve plane's normal
            poly_nx = poly_ny = poly_nz = 0.0
            m_poly = len(ribbon_face)
            for k in range(m_poly):
                pa = frame_verts[ribbon_face[k]]
                pb = frame_verts[ribbon_face[(k + 1) % m_poly]]
                poly_nx += (pa[1] - pb[1]) * (pa[2] + pb[2])
                poly_ny += (pa[2] - pb[2]) * (pa[0] + pb[0])
                poly_nz += (pa[0] - pb[0]) * (pa[1] + pb[1])

            if (poly_nx * normal.x + poly_ny * normal.y + poly_nz * normal.z) < 0:
                ribbon_face.reverse()

            frame_faces.append(ribbon_face)

            # Perimeter boundary edges only (outer curve + end cap + inner curve + start cap; ZERO radial dividing edges!)
            for i in range(n_pts - 1):
                frame_edges.append((i, i + 1))
                frame_edges.append((n_pts + i, n_pts + i + 1))
            frame_edges.append((0, n_pts))
            frame_edges.append((n_pts - 1, 2 * n_pts - 1))

            frame_mesh = MeshData(
                vertices=frame_verts,
                faces=frame_faces,
                edges=frame_edges,
                name="Frame",
                material_name="Frame",
                color=(0.22, 0.24, 0.28),
                face_materials=["Frame"] * len(frame_faces),
                face_colors=[(0.22, 0.24, 0.28)] * len(frame_faces),
                outer=[frame_verts[idx] for idx in ribbon_face],
                holes=[],
                holed_faces=[],
            )

        face_verts: List[Tuple[float, float, float]] = [(p.x, p.y, p.z) for p in offset_pts]
        face_faces: List[List[int]] = []
        face_edges: List[Tuple[int, int]] = []

        if is_closed and len(offset_pts) >= 3:
            m_off = len(offset_pts)
            # Clean single planar face (NO fan triangulation spokes!)
            face_faces.append(list(range(m_off)))
            for i in range(m_off):
                face_edges.append((i, (i + 1) % m_off))
        elif len(offset_pts) >= 2:
            for i in range(len(offset_pts) - 1):
                face_edges.append((i, i + 1))

        curve_face = MeshData(
            vertices=face_verts,
            faces=face_faces,
            edges=face_edges,
            name="OffsetCurveFace",
            material_name="Face",
            color=(0.55, 0.78, 0.92),
            face_materials=["Face"] * len(face_faces),
            face_colors=[(0.55, 0.78, 0.92)] * len(face_faces),
        )

        return {
            "curve": offset_curve,
            "frame": frame_mesh,
            "face": curve_face,
        }


# ============================================================================
# 15. Join Curves Node
# ============================================================================
@register_node
class JoinCurvesNode(BaseNode):
    type_id = "curve.join"
    title = "Join Curves"
    category = "Curves"
    description = (
        "Joins a list of contiguous open or closed curves/edges into unified polylines or closed loops.\n"
        "Connect directly to Curve Select (Curves output), List nodes (Create List, Merge), or multiple curve wires.\n"
        "Automatically bridges touching endpoints within tolerance and detects closed loops."
    )
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("curves", "Curves List", SocketType.CURVE, default=[], access=AccessMode.LIST, hide_widget=True),
        InputSpec("tolerance", "Tolerance (m)", SocketType.FLOAT, default=0.001, min_val=0.0001, max_val=1.0, step=0.001),
        InputSpec("close", "Close Loop", SocketType.BOOL, default=False),
    ]
    outputs = [
        OutputSpec("curve", "Joined Curve", SocketType.CURVE),
        OutputSpec("curves", "Joined Curves", SocketType.ANY),
        OutputSpec("closed", "Is Closed", SocketType.BOOL),
        OutputSpec("length", "Length (m)", SocketType.FLOAT),
        OutputSpec("count", "Curve Count", SocketType.INT),
    ]

    @staticmethod
    def _gather_curves(val: Any, out_list: List[CurveData]) -> None:
        if val is None:
            return
        if isinstance(val, CurveData):
            out_list.append(val)
        elif isinstance(val, (list, tuple)):
            for item in val:
                JoinCurvesNode._gather_curves(item, out_list)
        elif isinstance(val, dict) and "points" in val:
            pts_raw = val.get("points", [])
            pts = [
                Vec3(float(p[0]), float(p[1]), float(p[2])) if isinstance(p, (list, tuple)) else p
                for p in pts_raw
                if p is not None
            ]
            if len(pts) >= 2:
                out_list.append(CurveData(points=pts, closed=bool(val.get("closed", False))))

    @staticmethod
    def _chain_curves(curves: List[CurveData], tolerance: float = 0.001, close_loop: bool = False) -> List[CurveData]:
        segments: List[Tuple[Vec3, Vec3]] = []
        for c in curves:
            pts = c.points
            if len(pts) < 2:
                continue
            n_segs = len(pts) if c.closed else len(pts) - 1
            for i in range(n_segs):
                p0 = pts[i]
                p1 = pts[(i + 1) % len(pts)]
                if p0.distance_to(p1) > 1e-6:
                    segments.append((p0, p1))

        if not segments:
            return []

        scale = 1.0 / max(1e-6, tolerance)

        def qkey(p: Vec3) -> Tuple[int, int, int]:
            return (round(p.x * scale), round(p.y * scale), round(p.z * scale))

        key_to_pt: Dict[Tuple[int, int, int], Vec3] = {}
        adj: Dict[Tuple[int, int, int], List[Tuple[int, int, int]]] = {}
        edges_set = set()

        for p0, p1 in segments:
            k0, k1 = qkey(p0), qkey(p1)
            if k0 == k1:
                continue
            edge_key = (min(k0, k1), max(k0, k1))
            if edge_key in edges_set:
                continue
            edges_set.add(edge_key)

            key_to_pt.setdefault(k0, p0)
            key_to_pt.setdefault(k1, p1)
            adj.setdefault(k0, []).append(k1)
            adj.setdefault(k1, []).append(k0)

        visited_edges = set()
        result_curves: List[CurveData] = []
        nodes = list(adj.keys())
        visited_nodes = set()

        for start_node in nodes:
            if start_node in visited_nodes:
                continue
            comp = []
            q = [start_node]
            visited_nodes.add(start_node)
            while q:
                curr = q.pop(0)
                comp.append(curr)
                for nbr in adj.get(curr, []):
                    if nbr not in visited_nodes:
                        visited_nodes.add(nbr)
                        q.append(nbr)

            deg1 = [k for k in comp if len(adj[k]) == 1]
            start_k = deg1[0] if deg1 else comp[0]

            curr = start_k
            path = [curr]
            while True:
                nbrs = [n for n in adj[curr] if (min(curr, n), max(curr, n)) not in visited_edges]
                if not nbrs:
                    break
                nxt = nbrs[0]
                visited_edges.add((min(curr, nxt), max(curr, nxt)))
                path.append(nxt)
                curr = nxt
                if curr == start_k:
                    break

            pts = [key_to_pt[k] for k in path]
            if len(pts) >= 2:
                is_closed = (path[0] == path[-1]) or (pts[0].distance_to(pts[-1]) <= tolerance) or close_loop
                if is_closed and len(pts) > 2 and (pts[0].distance_to(pts[-1]) <= tolerance):
                    pts = pts[:-1]
                result_curves.append(CurveData(points=pts, closed=is_closed))

        return result_curves

    def compute(
        self,
        curves: Any = None,
        tolerance: float = 0.001,
        close: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        tol = float(tolerance)
        close_loop = bool(close)

        collected: List[CurveData] = []
        if curves is not None:
            self._gather_curves(curves, collected)
        for k, v in kwargs.items():
            if k not in ("tolerance", "close"):
                self._gather_curves(v, collected)

        if not collected:
            fallback = CurveData(points=[Vec3(0, 0, 0), Vec3(1, 0, 0)], closed=False)
            return {
                "curve": fallback,
                "curves": [fallback],
                "closed": False,
                "length": 1.0,
                "count": 0,
            }

        joined_curves = self._chain_curves(collected, tolerance=tol, close_loop=close_loop)
        if not joined_curves:
            joined_curves = collected

        def _curve_length(c: CurveData) -> float:
            total = 0.0
            n_segs = len(c.points) if c.closed else len(c.points) - 1
            for i in range(n_segs):
                total += c.points[i].distance_to(c.points[(i + 1) % len(c.points)])
            return total

        primary = max(joined_curves, key=_curve_length)
        total_len = sum(_curve_length(c) for c in joined_curves)

        return {
            "curve": primary,
            "curves": joined_curves,
            "closed": primary.closed,
            "length": round(total_len, 4),
            "count": len(joined_curves),
        }


# ============================================================================
# Midpoint Node
# ============================================================================
@register_node
class MidpointNode(BaseNode):
    type_id = "curve.midpoint"
    title = "Midpoint"
    category = "Curves"
    description = (
        "Calculates the exact 50% length midpoint along a curve, or the midpoint between two points.\n"
        "Outputs the midpoint position, local tangent vector, and perpendicular alignment plane."
    )
    header_color = (68, 108, 179)
    icon = "point.midpoint.png"

    inputs = [
        InputSpec("curve", "Curve / Point A", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("point_b", "Point B", SocketType.VEC3, default=None, hide_widget=True),
    ]
    outputs = [
        OutputSpec("point", "Midpoint", SocketType.VEC3),
        OutputSpec("points", "Points", SocketType.ANY),
        OutputSpec("tangent", "Tangent", SocketType.VEC3),
        OutputSpec("plane", "Plane", SocketType.ANY),
    ]

    def compute(self, curve: Any = None, point_b: Any = None) -> Dict[str, Any]:
        if isinstance(point_b, Vec3) or (isinstance(curve, Vec3) and point_b is not None):
            pA = curve if isinstance(curve, Vec3) else Vec3(0, 0, 0)
            pB = point_b if isinstance(point_b, Vec3) else Vec3(0, 0, 0)
            mid = (pA + pB) * 0.5
            diff = pB - pA
            length = diff.length()
            tangent = diff * (1.0 / length) if length > 1e-7 else Vec3(1, 0, 0)

            guide = Vec3(0, 0, 1) if abs(tangent.z) < 0.9 else Vec3(0, 1, 0)
            n_raw = Vec3(
                tangent.y * guide.z - tangent.z * guide.y,
                tangent.z * guide.x - tangent.x * guide.z,
                tangent.x * guide.y - tangent.y * guide.x,
            )
            n_len = n_raw.length()
            norm = n_raw * (1.0 / n_len) if n_len > 1e-7 else Vec3(0, 0, 1)
            u = tangent
            v = Vec3(
                norm.y * u.z - norm.z * u.y,
                norm.z * u.x - norm.x * u.z,
                norm.x * u.y - norm.y * u.x,
            )

            plane_dict = {
                "origin": (mid.x, mid.y, mid.z),
                "normal": (tangent.x, tangent.y, tangent.z),
                "u_axis": (norm.x, norm.y, norm.z),
                "v_axis": (v.x, v.y, v.z),
            }
            return {
                "point": mid,
                "points": [mid],
                "tangent": tangent,
                "plane": plane_dict,
            }

        def _mid_curve(c: CurveData) -> Tuple[Vec3, Vec3, Dict[str, Any]]:
            pts = list(c.points)
            if not pts:
                p0 = Vec3(0, 0, 0)
                return p0, Vec3(1, 0, 0), {"origin": (0, 0, 0), "normal": (0, 0, 1), "u_axis": (1, 0, 0), "v_axis": (0, 1, 0)}

            if len(pts) == 1:
                p0 = pts[0]
                return p0, Vec3(1, 0, 0), {"origin": (p0.x, p0.y, p0.z), "normal": (0, 0, 1), "u_axis": (1, 0, 0), "v_axis": (0, 1, 0)}

            if c.closed and (pts[-1] - pts[0]).length() > 1e-6:
                pts.append(pts[0])

            seg_lens = []
            total_len = 0.0
            for i in range(len(pts) - 1):
                sl = (pts[i + 1] - pts[i]).length()
                seg_lens.append(sl)
                total_len += sl

            if total_len < 1e-8:
                p0 = pts[0]
                return p0, Vec3(1, 0, 0), {"origin": (p0.x, p0.y, p0.z), "normal": (0, 0, 1), "u_axis": (1, 0, 0), "v_axis": (0, 1, 0)}

            target_len = total_len * 0.5
            accum = 0.0
            mid_pt = pts[-1]
            tan_vec = Vec3(1, 0, 0)

            for i, sl in enumerate(seg_lens):
                if accum + sl >= target_len - 1e-8:
                    sub_t = (target_len - accum) / sl if sl > 1e-8 else 0.0
                    sub_t = max(0.0, min(1.0, sub_t))
                    mid_pt = pts[i] + (pts[i + 1] - pts[i]) * sub_t
                    diff = pts[i + 1] - pts[i]
                    tan_vec = diff * (1.0 / sl) if sl > 1e-8 else Vec3(1, 0, 0)
                    break
                accum += sl

            guide = Vec3(0, 0, 1) if abs(tan_vec.z) < 0.9 else Vec3(0, 1, 0)
            n_raw = Vec3(
                tan_vec.y * guide.z - tan_vec.z * guide.y,
                tan_vec.z * guide.x - tan_vec.x * guide.z,
                tan_vec.x * guide.y - tan_vec.y * guide.x,
            )
            n_len = n_raw.length()
            norm = n_raw * (1.0 / n_len) if n_len > 1e-7 else Vec3(0, 0, 1)
            u = tan_vec
            v = Vec3(
                norm.y * u.z - norm.z * u.y,
                norm.z * u.x - norm.x * u.z,
                norm.x * u.y - norm.y * u.x,
            )

            plane_dict = {
                "origin": (mid_pt.x, mid_pt.y, mid_pt.z),
                "normal": (tan_vec.x, tan_vec.y, tan_vec.z),
                "u_axis": (norm.x, norm.y, norm.z),
                "v_axis": (v.x, v.y, v.z),
            }
            return mid_pt, tan_vec, plane_dict

        if isinstance(curve, list) and curve and isinstance(curve[0], CurveData):
            mids = [_mid_curve(c) for c in curve]
            return {
                "point": mids[0][0],
                "points": [m[0] for m in mids],
                "tangent": mids[0][1],
                "plane": mids[0][2],
            }

        if not isinstance(curve, CurveData):
            curve = CurveData(points=[Vec3(0, 0, 0), Vec3(2, 0, 0)], closed=False)

        mid_pt, tan_vec, pl = _mid_curve(curve)
        return {
            "point": mid_pt,
            "points": [mid_pt],
            "tangent": tan_vec,
            "plane": pl,
        }

NODE_REGISTRY["point.midpoint"] = MidpointNode


# ============================================================================
# Safe Imports for Interactive Viewport Tool & Handles
# ============================================================================
try:
    from tools.base import Tool, ToolContext
except ImportError:
    class Tool:  # type: ignore
        name = "Tool"
        description = ""
        uses_snap = True
        vcb_label = None
        def on_activate(self, viewport: Any) -> None: pass
        def on_deactivate(self, viewport: Any) -> None: pass
        def on_click(self, ctx: Any) -> None: pass
        def on_hover(self, ctx: Any) -> None: pass
        def on_cancel(self, viewport: Any) -> None: pass
        def on_double_click(self, ctx: Any) -> None: pass
        def on_undo(self, viewport: Any) -> bool: return False
        def on_value(self, viewport: Any, value: Any) -> bool: return False
        def rubber_band_lines(self) -> List[Any]: return []

    class ToolContext:  # type: ignore
        pass

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QMatrix4x4, QVector3D
except ImportError:
    Qt = None  # type: ignore
    QMatrix4x4 = None  # type: ignore
    QVector3D = None  # type: ignore


# ============================================================================
# Pure Mathematical Spline / NURBS Evaluators
# ============================================================================
def evaluate_nurbs_curve(
    control_points: List[Vec3],
    degree: int = 3,
    closed: bool = False,
    samples: int = 100,
) -> Tuple[List[Vec3], float]:
    """
    Evaluates a smooth B-Spline / NURBS curve from control points using De Boor's algorithm.
    Returns (evaluated_points, curve_length).
    """
    n = len(control_points)
    if n == 0:
        return [], 0.0
    if n == 1:
        return [control_points[0]], 0.0
    if n == 2:
        p0, p1 = control_points[0], control_points[1]
        num_s = max(2, samples)
        pts = [
            Vec3(
                p0.x + (p1.x - p0.x) * (i / float(num_s - 1)),
                p0.y + (p1.y - p0.y) * (i / float(num_s - 1)),
                p0.z + (p1.z - p0.z) * (i / float(num_s - 1)),
            )
            for i in range(num_s)
        ]
        return pts, p0.distance_to(p1)

    p = max(1, min(degree, n - 1))
    pts_in = list(control_points)

    if closed:
        pts_in = pts_in + pts_in[:p]
        m = len(pts_in)
        knots = [float(i) for i in range(m + p + 1)]
        u_min = knots[p]
        u_max = knots[m]
    else:
        m = n
        num_middle = m - p
        knots = [0.0] * (p + 1)
        for i in range(1, num_middle):
            knots.append(i / float(num_middle))
        knots.extend([1.0] * (p + 1))
        u_min = 0.0
        u_max = 1.0

    eval_pts: List[Vec3] = []
    total_len = 0.0
    prev_pt: Optional[Vec3] = None
    num_eval = max(2, samples)

    for s_idx in range(num_eval):
        t = s_idx / float(num_eval - 1)
        u = u_min + t * (u_max - u_min)
        if s_idx == num_eval - 1:
            u = u_max - 1e-9

        k = p
        for j in range(p, len(knots) - p - 1):
            if knots[j] <= u < knots[j + 1]:
                k = j
                break
        else:
            k = len(knots) - p - 2

        d = [Vec3(pts_in[j].x, pts_in[j].y, pts_in[j].z) for j in range(k - p, k + 1)]

        for r in range(1, p + 1):
            for j in range(p, r - 1, -1):
                i_knot = j + k - p
                denom = knots[i_knot + p + 1 - r] - knots[i_knot]
                alpha = (u - knots[i_knot]) / denom if abs(denom) > 1e-12 else 0.0
                d[j] = Vec3(
                    (1.0 - alpha) * d[j - 1].x + alpha * d[j].x,
                    (1.0 - alpha) * d[j - 1].y + alpha * d[j].y,
                    (1.0 - alpha) * d[j - 1].z + alpha * d[j].z,
                )

        pt = d[p]
        eval_pts.append(pt)
        if prev_pt is not None:
            total_len += prev_pt.distance_to(pt)
        prev_pt = pt

    if closed and eval_pts:
        total_len += eval_pts[-1].distance_to(eval_pts[0])

    return eval_pts, total_len


def evaluate_interpolated_curve(
    points: List[Vec3],
    closed: bool = False,
    samples: int = 100,
    alpha: float = 0.5,
) -> Tuple[List[Vec3], float, List[Vec3]]:
    """
    Evaluates a smooth spline passing directly through all given points.
    alpha=0.5 -> Centripetal (avoids loops and cusps).
    Returns (evaluated_points, total_length, tangent_vectors).
    """
    n = len(points)
    if n == 0:
        return [], 0.0, []
    if n == 1:
        return [points[0]], 0.0, [Vec3(0, 0, 1)]
    if n == 2:
        p0, p1 = points[0], points[1]
        tangent = (p1 - p0).normalized() if p0.distance_to(p1) > 1e-9 else Vec3(0, 0, 1)
        num_s = max(2, samples)
        pts = [
            Vec3(
                p0.x + (p1.x - p0.x) * (i / float(num_s - 1)),
                p0.y + (p1.y - p0.y) * (i / float(num_s - 1)),
                p0.z + (p1.z - p0.z) * (i / float(num_s - 1)),
            )
            for i in range(num_s)
        ]
        return pts, p0.distance_to(p1), [tangent] * num_s

    pts = list(points)
    num_segments = n if closed else n - 1
    eval_pts: List[Vec3] = []
    tangents: List[Vec3] = []
    total_len = 0.0
    prev_pt: Optional[Vec3] = None
    samples_per_seg = max(2, samples // num_segments)

    for seg_idx in range(num_segments):
        if closed:
            p0 = pts[(seg_idx - 1) % n]
            p1 = pts[seg_idx % n]
            p2 = pts[(seg_idx + 1) % n]
            p3 = pts[(seg_idx + 2) % n]
        else:
            p1 = pts[seg_idx]
            p2 = pts[seg_idx + 1]
            p0 = (p1 * 2.0 - p2) if seg_idx == 0 else pts[seg_idx - 1]
            p3 = (p2 * 2.0 - p1) if seg_idx == num_segments - 1 else pts[seg_idx + 2]

        def get_t(t_curr: float, pa: Vec3, pb: Vec3) -> float:
            d = pa.distance_to(pb)
            return t_curr + (d ** alpha if d > 1e-9 else 1e-4)

        t0 = 0.0
        t1 = get_t(t0, p0, p1)
        t2 = get_t(t1, p1, p2)
        t3 = get_t(t2, p2, p3)

        seg_samples = samples_per_seg if seg_idx < num_segments - 1 else (samples - len(eval_pts))
        seg_samples = max(2, seg_samples)
        num_steps = seg_samples if (seg_idx == num_segments - 1 and not closed) else seg_samples - 1

        for step in range(num_steps):
            s = step / float(seg_samples - 1)
            t = t1 + s * (t2 - t1)

            a1 = p0 * ((t1 - t) / (t1 - t0)) + p1 * ((t - t0) / (t1 - t0))
            a2 = p1 * ((t2 - t) / (t2 - t1)) + p2 * ((t - t1) / (t2 - t1))
            a3 = p2 * ((t3 - t) / (t3 - t2)) + p3 * ((t - t2) / (t3 - t2))

            b1 = a1 * ((t2 - t) / (t2 - t0)) + a2 * ((t - t0) / (t2 - t0))
            b2 = a2 * ((t3 - t) / (t3 - t1)) + a3 * ((t - t1) / (t3 - t1))

            c = b1 * ((t2 - t) / (t2 - t1)) + b2 * ((t - t1) / (t2 - t1))

            eval_pts.append(c)
            if prev_pt is not None:
                d = prev_pt.distance_to(c)
                total_len += d
                tan = (c - prev_pt).normalized() if d > 1e-9 else Vec3(0, 0, 1)
                tangents.append(tan)
            prev_pt = c

    if eval_pts and len(tangents) < len(eval_pts):
        tangents.append(tangents[-1] if tangents else Vec3(0, 0, 1))

    if closed and eval_pts:
        total_len += eval_pts[-1].distance_to(eval_pts[0])

    return eval_pts, total_len, tangents


# ============================================================================
# Interactive Viewport Point Insertion Tool
# ============================================================================
class PointInsertTool(Tool):
    """Interactive 3D viewport tool for clicking and placing curve points with live snapping."""
    name = "Insert Curve Points"
    description = "Click in 3D viewport to insert curve control points (Enter/Esc/double-click when done, Backspace to undo)."
    uses_snap = True
    vcb_label = "Point (X;Y;Z)"
    qt_cursor = Qt.CursorShape.CrossCursor if Qt is not None else None

    def __init__(self, node: Any, on_change: Optional[Callable[[], None]] = None) -> None:
        super().__init__()
        self.node = node
        self.on_change = on_change
        self.hover_point: Any = None
        self.viewport: Any = None
        self.start_point: Optional[QVector3D] = None
        self.dragging: bool = True  # Marks tool as having an operation in progress for Viewport._tool_busy

    def claims_key(self, key: int, modifiers: Any = None) -> bool:
        """Claims Enter, Return, Escape, Backspace, and Delete keys so Viewport forwards key events to this tool."""
        # Qt.Key_Return = 16777220, Qt.Key_Enter = 16777221, Qt.Key_Escape = 16777216, Qt.Key_Backspace = 16777219, Qt.Key_Delete = 16777223
        return key in (16777220, 16777221, 16777216, 16777219, 16777223)

    def on_key(self, viewport: Any, key: int, modifiers: Any = None) -> bool:
        """Handles keyboard shortcuts during point placement."""
        if key in (16777220, 16777221, 16777216):  # Enter, Return, Escape -> Commit and finish
            self.finish(viewport)
            return True
        elif key in (16777219, 16777223):  # Backspace, Delete -> Undo last point
            return self.on_undo(viewport)
        return False

    def on_activate(self, viewport: Any) -> None:
        self.viewport = viewport
        self.dragging = True
        pts = self.node.param_values.get("stored_points", [])
        if pts and QVector3D is not None:
            last = pts[-1]
            try:
                if isinstance(last, QVector3D):
                    self.start_point = last
                elif hasattr(last, "x") and callable(last.x):
                    self.start_point = QVector3D(float(last.x()), float(last.y()), float(last.z()))
                elif hasattr(last, "x"):
                    self.start_point = QVector3D(float(last.x), float(last.y), float(last.z))
                elif isinstance(last, (list, tuple)) and len(last) >= 3:
                    self.start_point = QVector3D(float(last[0]), float(last[1]), float(last[2]))
            except Exception:
                self.start_point = None
        else:
            self.start_point = None

        if Qt is not None and hasattr(viewport, "setCursor"):
            viewport.setCursor(Qt.CursorShape.CrossCursor)
        flash = getattr(viewport, "flash_status", None)
        if callable(flash):
            flash(f"📍 Point Insertion Active: {len(pts)} existing points. Click in viewport to add points. Press Enter/Esc when finished.")

    def on_deactivate(self, viewport: Any) -> None:
        self.dragging = False
        self.start_point = None
        if hasattr(viewport, "unsetCursor"):
            viewport.unsetCursor()
        self.hover_point = None

    def on_click(self, ctx: Any) -> None:
        world_pt = getattr(ctx, "world", None)
        if world_pt is None:
            return
        px = float(world_pt.x() if callable(world_pt.x) else world_pt.x)
        py = float(world_pt.y() if callable(world_pt.y) else world_pt.y)
        pz = float(world_pt.z() if callable(world_pt.z) else world_pt.z)

        pts = list(self.node.param_values.get("stored_points", []))
        pts.append((round(px, 4), round(py, 4), round(pz, 4)))
        self.node.param_values["stored_points"] = pts
        self.node.is_dirty = True
        if QVector3D is not None:
            self.start_point = QVector3D(px, py, pz)
        self.dragging = True

        app = getattr(self.node, "_app_ref", None) or getattr(getattr(ctx.viewport, "window", None), "_extension_app_handle", None)
        if self.node.param_values.get("handles_active", False):
            self.node.spawn_handles(app)

        if callable(self.on_change):
            self.on_change()

        if hasattr(self.node, "_item_ref") and self.node._item_ref:
            try:
                self.node._item_ref._update_badge()
                self.node._item_ref._update_action_buttons()
                self.node._item_ref.update()
            except Exception:
                pass

        flash = getattr(ctx.viewport, "flash_status", None)
        if callable(flash):
            flash(f"Point #{len(pts)} placed at ({px:.2f}, {py:.2f}, {pz:.2f}) — click more points, or Enter/Esc to finish")
        ctx.viewport.update()

    def on_hover(self, ctx: Any) -> None:
        self.hover_point = getattr(ctx, "world", None)
        if hasattr(ctx.viewport, "update"):
            ctx.viewport.update()

    def rubber_band_lines(self) -> List[Any]:
        pts = self.node.param_values.get("stored_points", [])
        if not pts or QVector3D is None:
            return []
        qvecs = []
        for p in pts:
            try:
                if isinstance(p, QVector3D):
                    qvecs.append(p)
                elif hasattr(p, "x") and callable(p.x):
                    qvecs.append(QVector3D(float(p.x()), float(p.y()), float(p.z())))
                elif hasattr(p, "x"):
                    qvecs.append(QVector3D(float(p.x), float(p.y), float(p.z)))
                elif isinstance(p, (list, tuple)) and len(p) >= 3:
                    qvecs.append(QVector3D(float(p[0]), float(p[1]), float(p[2])))
            except Exception:
                pass
        lines = []
        for i in range(len(qvecs) - 1):
            lines.append((qvecs[i], qvecs[i + 1]))
        if qvecs and self.hover_point is not None:
            hp = None
            try:
                if isinstance(self.hover_point, QVector3D):
                    hp = self.hover_point
                elif hasattr(self.hover_point, "x") and callable(self.hover_point.x):
                    hp = QVector3D(float(self.hover_point.x()), float(self.hover_point.y()), float(self.hover_point.z()))
                elif hasattr(self.hover_point, "x"):
                    hp = QVector3D(float(self.hover_point.x), float(self.hover_point.y), float(self.hover_point.z))
                elif isinstance(self.hover_point, (list, tuple)) and len(self.hover_point) >= 3:
                    hp = QVector3D(float(self.hover_point[0]), float(self.hover_point[1]), float(self.hover_point[2]))
            except Exception:
                pass
            if hp is not None:
                lines.append((qvecs[-1], hp))
                if self.node.param_values.get("closed"):
                    lines.append((hp, qvecs[0]))
        return lines

    def on_double_click(self, ctx: Any) -> None:
        self.finish(ctx.viewport)

    def on_cancel(self, viewport: Any) -> None:
        self.finish(viewport)

    def finish(self, viewport: Any) -> None:
        self.dragging = False
        self.start_point = None
        win = viewport.window() if callable(getattr(viewport, "window", None)) else getattr(viewport, "window", None)
        if win and hasattr(win, "activate_select_tool"):
            try:
                win.activate_select_tool()
            except Exception:
                pass
        elif hasattr(viewport, "set_active_tool"):
            try:
                viewport.set_active_tool(None)
            except Exception:
                pass
        if hasattr(viewport, "unsetCursor"):
            try:
                viewport.unsetCursor()
            except Exception:
                pass
        if hasattr(viewport, "update"):
            try:
                viewport.update()
            except Exception:
                pass
        if callable(self.on_change):
            try:
                self.on_change()
            except Exception:
                pass
        if hasattr(self.node, "_item_ref") and self.node._item_ref:
            try:
                self.node._item_ref._update_badge()
                self.node._item_ref._update_action_buttons()
                self.node._item_ref.update()
            except Exception:
                pass
        flash = getattr(viewport, "flash_status", None)
        if callable(flash):
            n = len(self.node.param_values.get("stored_points", []))
            flash(f"Finished inserting points: {n} points committed.")

    def on_undo(self, viewport: Any) -> bool:
        pts = list(self.node.param_values.get("stored_points", []))
        if pts:
            popped = pts.pop()
            self.node.param_values["stored_points"] = pts
            self.node.is_dirty = True
            if pts and QVector3D is not None:
                last = pts[-1]
                try:
                    if isinstance(last, QVector3D):
                        self.start_point = last
                    elif hasattr(last, "x") and callable(last.x):
                        self.start_point = QVector3D(float(last.x()), float(last.y()), float(last.z()))
                    elif hasattr(last, "x"):
                        self.start_point = QVector3D(float(last.x), float(last.y), float(last.z))
                    elif isinstance(last, (list, tuple)) and len(last) >= 3:
                        self.start_point = QVector3D(float(last[0]), float(last[1]), float(last[2]))
                except Exception:
                    self.start_point = None
            else:
                self.start_point = None

            app = getattr(self.node, "_app_ref", None) or getattr(getattr(viewport, "window", None), "_extension_app_handle", None)
            if self.node.param_values.get("handles_active", False):
                self.node.spawn_handles(app)
            if callable(self.on_change):
                self.on_change()
            if hasattr(self.node, "_item_ref") and self.node._item_ref:
                try:
                    self.node._item_ref._update_badge()
                    self.node._item_ref._update_action_buttons()
                    self.node._item_ref.update()
                except Exception:
                    pass
            viewport.update()
            flash = getattr(viewport, "flash_status", None)
            if callable(flash):
                flash(f"Undid point {popped} ({len(pts)} points remaining)")
            return True
        return False


class ViewportCurveNodeBase(BaseNode):
    """Shared base class for curves supporting interactive viewport point insertion and draggable handles."""

    DEFAULT_POINTS = [
        (0.0, 0.0, 0.0),
        (2.0, 3.0, 0.0),
        (5.0, 3.0, 0.0),
        (7.0, 0.0, 0.0),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.param_values.setdefault("stored_points", [list(p) for p in self.DEFAULT_POINTS])
        self.param_values.setdefault("handles_active", False)
        self._app_ref: Any = None
        self._item_ref: Any = None
        self._last_evaluated_points: List[Vec3] = []

    def get_action_buttons(self) -> List[Dict[str, Any]]:
        is_handles = self.param_values.get("handles_active", False)
        btn_handles_label = "🎯 Hide Handles" if is_handles else "🎯 Viewport Handles"
        btn_handles_color = "#3b6e50" if is_handles else "#434c5e"
        return [
            {
                "id": "btn_insert_points",
                "label": "📍 Click in Viewport",
                "tooltip": "Click anywhere in the 3D viewport to insert curve control points (Enter/Esc to finish)",
                "color": "#2b5278",
                "action": "insert_points",
            },
            {
                "id": "btn_toggle_handles",
                "label": btn_handles_label,
                "tooltip": "Spawn draggable 3D handle markers in the scene so you can drag points anytime with the Move tool (M)",
                "color": btn_handles_color,
                "action": "toggle_handles",
            },
            {
                "id": "btn_clear_points",
                "label": "❌ Clear Points",
                "tooltip": "Clear all stored/clicked points back to empty",
                "color": "#4c566a",
                "action": "clear_points",
            },
        ]

    def get_card_badge_text(self) -> Optional[str]:
        pts = self.get_active_points()
        n = len(pts)
        is_handles = self.param_values.get("handles_active", False)
        handle_str = " (Handles 🟢)" if is_handles else ""
        if n == 0:
            return "⚪ No points (click button to add)"
        return f"📍 {n} pts{handle_str}"

    def get_active_points(self, inputs_points: Any = None) -> List[Vec3]:
        """
        Returns active control points.
        When handles are active, user is interactively manipulating stored points in viewport.
        When handles are inactive and a wire is connected, wire takes precedence.
        """
        is_handles = self.param_values.get("handles_active", False)
        if inputs_points is not None and not is_handles:
            if isinstance(inputs_points, (list, tuple)):
                res = []
                for p in inputs_points:
                    if isinstance(p, Vec3):
                        res.append(p)
                    elif hasattr(p, "x") and hasattr(p, "y") and hasattr(p, "z"):
                        res.append(Vec3(float(p.x), float(p.y), float(p.z)))
                    elif isinstance(p, (list, tuple)) and len(p) >= 3:
                        res.append(Vec3(float(p[0]), float(p[1]), float(p[2])))
                if res:
                    return res
            elif isinstance(inputs_points, Vec3):
                return [inputs_points]

        stored = self.param_values.get("stored_points", [])
        res = []
        for p in stored:
            if isinstance(p, Vec3):
                res.append(p)
            elif isinstance(p, (list, tuple)) and len(p) >= 3:
                res.append(Vec3(float(p[0]), float(p[1]), float(p[2])))
            elif isinstance(p, dict) and "x" in p:
                res.append(Vec3(float(p["x"]), float(p["y"]), float(p.get("z", 0.0))))
        if not res and inputs_points is None and not self.param_values.get("cleared_explicitly", False):
            # Fall back to default control points
            return [Vec3(float(p[0]), float(p[1]), float(p[2])) for p in self.DEFAULT_POINTS]
        return res

    def _resolve_app(self, app: Any = None) -> Any:
        app = app or getattr(self, "_app_ref", None)
        if app is not None:
            return app
        try:
            import sys
            for mod_name in ("IngeTrazoNodeEditor", "__main__"):
                mod = sys.modules.get(mod_name)
                if mod and getattr(mod, "_ACTIVE_APP", None):
                    return getattr(mod, "_ACTIVE_APP")
        except Exception:
            pass
        try:
            from PySide6.QtWidgets import QApplication
            qapp = QApplication.instance()
            if qapp is not None:
                app = getattr(qapp, "_extension_app_handle", None)
                if app:
                    return app
                for w in qapp.topLevelWidgets():
                    if hasattr(w, "viewport") or hasattr(w, "scene"):
                        return w
                    if hasattr(w, "_extension_app_handle"):
                        return getattr(w, "_extension_app_handle")
        except Exception:
            pass
        return app

    def _resolve_context(self, app: Any = None) -> Tuple[Optional[Any], Optional[Any], Optional[Any]]:
        app = self._resolve_app(app)
        win = None
        vp = None
        sc = None
        if app is not None:
            win = getattr(app, "_window", None) or getattr(app, "window", None) or app
            vp = getattr(app, "viewport", None) or getattr(win, "viewport", None)
            sc = getattr(app, "scene", None) or getattr(win, "scene", None) or (getattr(vp, "scene", None) if vp else None)

        if vp is None or not hasattr(vp, "set_active_tool"):
            # Deep fallback: scan QApplication.allWidgets() for IngeTrazo Viewport
            try:
                from PySide6.QtWidgets import QApplication
                qapp = QApplication.instance()
                if qapp is not None:
                    for w in qapp.allWidgets():
                        if type(w).__name__ == "Viewport" and hasattr(w, "set_active_tool"):
                            vp = w
                            win = w.window()
                            app = getattr(win, "_extension_app_handle", None) or win
                            sc = getattr(w, "scene", None) or getattr(win, "scene", None)
                            break
            except Exception:
                pass

        return (app, sc, vp)

    def insert_points(self, app: Any = None) -> Tuple[str, bool]:
        app, sc, vp = self._resolve_context(app)
        self._app_ref = app
        if not vp or not hasattr(vp, "set_active_tool"):
            return ("No IngeTrazo viewport available", False)

        def _on_points_changed() -> None:
            self.is_dirty = True
            win = getattr(app, "_window", None) or getattr(app, "window", None) or app
            editor = getattr(win, "_node_editor_widget", None)
            if editor and hasattr(editor, "schedule_eval"):
                editor.schedule_eval()

        tool = PointInsertTool(self, on_change=_on_points_changed)
        vp.set_active_tool(tool)
        if hasattr(vp, "setFocus"):
            try:
                vp.setFocus()
            except Exception:
                pass
        return ("Point insertion active in viewport", True)

    def toggle_handles(self, app: Any = None) -> Tuple[str, bool]:
        is_active = self.param_values.get("handles_active", False)
        new_state = not is_active
        self.param_values["handles_active"] = new_state
        if new_state:
            msg = self.spawn_handles(app)
            return (msg, True)
        else:
            msg = self.clear_handles(app)
            return (msg, True)

    def spawn_handles(self, app: Any = None) -> str:
        app, scene, vp = self._resolve_context(app)
        if scene is None or not hasattr(scene, "groups"):
            return "No scene available"

        self.clear_handles(app)

        # If stored_points is empty but we had wired points, initialize stored_points from them!
        if not self.param_values.get("stored_points") and self._last_evaluated_points:
            self.param_values["stored_points"] = [
                (round(float(p.x), 4), round(float(p.y), 4), round(float(p.z), 4))
                for p in self._last_evaluated_points
            ]

        pts = self.get_active_points()
        if not pts:
            self.param_values["stored_points"] = [list(p) for p in self.DEFAULT_POINTS]
            pts = self.get_active_points()

        try:
            from core.mesh import Mesh
        except ImportError:
            return "core.mesh not available"

        try:
            from core.group import Group
        except ImportError:
            try:
                from core.scene import Group
            except ImportError:
                return "Group not available"

        try:
            from PySide6.QtGui import QMatrix4x4, QVector3D
        except ImportError:
            return "PySide6.QtGui not available"

        def _make_handle_marker(rad: float = 0.08) -> Any:
            m_obj = Mesh()
            try:
                v_pts = [
                    QVector3D(rad, 0, 0), QVector3D(-rad, 0, 0),
                    QVector3D(0, rad, 0), QVector3D(0, -rad, 0),
                    QVector3D(0, 0, rad), QVector3D(0, 0, -rad),
                ]
                faces = [
                    [v_pts[4], v_pts[0], v_pts[2]], [v_pts[4], v_pts[2], v_pts[1]],
                    [v_pts[4], v_pts[1], v_pts[3]], [v_pts[4], v_pts[3], v_pts[0]],
                    [v_pts[5], v_pts[2], v_pts[0]], [v_pts[5], v_pts[1], v_pts[2]],
                    [v_pts[5], v_pts[3], v_pts[1]], [v_pts[5], v_pts[0], v_pts[3]],
                ]
                for f_pts in faces:
                    m_obj.add_face(f_pts)
            except Exception:
                pass
            return m_obj

        for i, p in enumerate(pts):
            m = _make_handle_marker()
            m._chunk_dirty = True
            m._attrs_dirty = True

            handle_name = f"CP {i + 1} ({self.title})"
            try:
                grp = Group(m, handle_name)
            except TypeError:
                try:
                    grp = Group(name=handle_name, mesh=m)
                except TypeError:
                    grp = Group()
                    grp.name = handle_name
                    grp.mesh = m

            grp.xform = QMatrix4x4()
            grp.xform.translate(QVector3D(float(p.x), float(p.y), float(p.z)))
            grp.material = {"color": [0.95, 0.6, 0.1, 1.0]}
            grp.ext = {
                "_is_curve_handle": True,
                "node_id": self.id,
                "point_index": i,
            }
            scene.groups.append(grp)

        try:
            from core.history import _dirty_group_chunks
            _dirty_group_chunks(scene)
        except Exception:
            pass

        if hasattr(scene, "version"):
            scene.version += 1

        if vp is not None:
            flash = getattr(vp, "flash_status", None)
            if callable(flash):
                flash(f"🎯 Viewport handles active: {len(pts)} points. Drag with Move tool (M).")
            if hasattr(vp, "update"):
                vp.update()

        return f"Spawned {len(pts)} handles in viewport"

    def clear_handles(self, app: Any = None) -> str:
        app, scene, vp = self._resolve_context(app)
        if scene is None or not hasattr(scene, "groups"):
            return "No scene available"

        before = len(scene.groups)
        scene.groups[:] = [
            g for g in scene.groups
            if not (hasattr(g, "ext") and isinstance(g.ext, dict)
                    and g.ext.get("_is_curve_handle") and g.ext.get("node_id") == self.id)
        ]
        if len(scene.groups) != before:
            try:
                from core.history import _dirty_group_chunks
                _dirty_group_chunks(scene)
            except Exception:
                pass
            if hasattr(scene, "version"):
                scene.version += 1
            if vp is not None and hasattr(vp, "update"):
                vp.update()
        return "Cleared handles"

    def clear_points(self, app: Any = None) -> Tuple[str, bool]:
        self.clear_handles(app)
        self.param_values["stored_points"] = []
        self.param_values["handles_active"] = False
        self.param_values["cleared_explicitly"] = True
        self.is_dirty = True
        app, scene, vp = self._resolve_context(app)
        if vp is not None:
            flash = getattr(vp, "flash_status", None)
            if callable(flash):
                flash("❌ Points cleared")
        return ("Points cleared", True)

    def sync_from_scene(self, app: Any = None) -> bool:
        if not self.param_values.get("handles_active", False):
            return False
        app, scene, vp = self._resolve_context(app)
        if scene is None or not hasattr(scene, "groups"):
            return False

        stored = list(self.param_values.get("stored_points", []))
        if not stored:
            return False

        try:
            from PySide6.QtGui import QVector3D
        except ImportError:
            return False

        changed = False
        for grp in scene.groups:
            ext = getattr(grp, "ext", None)
            if isinstance(ext, dict) and ext.get("_is_curve_handle") and ext.get("node_id") == self.id:
                idx = ext.get("point_index")
                if idx is not None and 0 <= idx < len(stored):
                    pos = None
                    if getattr(grp, "xform", None) is not None:
                        pos = grp.xform.map(QVector3D(0.0, 0.0, 0.0))
                    elif hasattr(grp, "mesh") and grp.mesh and hasattr(grp.mesh, "vertices") and grp.mesh.vertices:
                        vs = list(grp.mesh.vertices)
                        pos = QVector3D(
                            sum(v.position.x() for v in vs) / len(vs),
                            sum(v.position.y() for v in vs) / len(vs),
                            sum(v.position.z() for v in vs) / len(vs),
                        )

                    if pos is not None:
                        nx, ny, nz = round(float(pos.x()), 4), round(float(pos.y()), 4), round(float(pos.z()), 4)
                        ox, oy, oz = round(float(stored[idx][0]), 4), round(float(stored[idx][1]), 4), round(float(stored[idx][2]), 4)
                        if (nx, ny, nz) != (ox, oy, oz):
                            stored[idx] = (nx, ny, nz)
                            changed = True

        if changed:
            self.param_values["stored_points"] = stored
            self.is_dirty = True
        return changed

    def on_destroy(self) -> None:
        self.clear_handles()


# ============================================================================
# NURBS Curve Node
# ============================================================================
@register_node
class NurbsCurveNode(ViewportCurveNodeBase):
    type_id = "curve.nurbs"
    title = "NURBS Curve"
    category = "Curves"
    description = (
        "Generates a smooth Non-Uniform Rational B-Spline (NURBS) curve from control points using De Boor's algorithm.\n"
        "Click '📍 Click in Viewport' to place points directly in the 3D scene, or connect points to the input.\n"
        "Click '🎯 Viewport Handles' to drag points anytime with the Move tool (M).\n"
        "Outputs smooth curve, dense points, curve length, and control points."
    )
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("points", "Points", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("degree", "Degree", SocketType.INT, default=3, min_val=1, max_val=5, step=1),
        InputSpec("closed", "Closed", SocketType.BOOL, default=False),
        InputSpec("samples", "Samples", SocketType.INT, default=100, min_val=10, max_val=1000, step=10),
    ]
    outputs = [
        OutputSpec("curve", "Curve", SocketType.CURVE),
        OutputSpec("points", "Points", SocketType.VEC3, hide_preview=True),
        OutputSpec("length", "Length (m)", SocketType.FLOAT),
        OutputSpec("control_points", "Control Points", SocketType.VEC3, hide_preview=True),
    ]

    def compute(
        self,
        points: Any = None,
        degree: int = 3,
        closed: bool = False,
        samples: int = 100,
    ) -> Dict[str, Any]:
        active_pts = self.get_active_points(points)
        self._last_evaluated_points = active_pts
        if not active_pts:
            return {
                "curve": CurveData(points=[], closed=bool(closed)),
                "points": [],
                "length": 0.0,
                "control_points": [],
            }

        degree_val = max(1, min(5, int(degree)))
        samples_val = max(10, min(1000, int(samples)))
        closed_val = bool(closed)

        eval_pts, total_len = evaluate_nurbs_curve(
            active_pts,
            degree=degree_val,
            closed=closed_val,
            samples=samples_val,
        )

        cdata = CurveData(points=eval_pts, closed=closed_val)
        return {
            "curve": cdata,
            "points": eval_pts,
            "length": round(total_len, 4),
            "control_points": active_pts,
        }


# ============================================================================
# Interpolate Curve Node
# ============================================================================
@register_node
class InterpolateCurveNode(ViewportCurveNodeBase):
    type_id = "curve.interpolate"
    title = "Interpolate Curve"
    category = "Curves"
    description = (
        "Creates a smooth interpolated spline curve passing directly through every input point using Centripetal Catmull-Rom interpolation.\n"
        "Click '📍 Click in Viewport' to insert points directly in the 3D scene, or connect points to the input.\n"
        "Click '🎯 Viewport Handles' to drag points anytime in the viewport with the Move tool (M).\n"
        "Outputs smooth curve, dense points, curve length, and tangent vectors."
    )
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("points", "Points", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("closed", "Closed", SocketType.BOOL, default=False),
        InputSpec("samples", "Samples", SocketType.INT, default=100, min_val=10, max_val=1000, step=10),
        InputSpec("alpha", "Tension", SocketType.FLOAT, default=0.5, min_val=0.0, max_val=1.0, step=0.05),
    ]
    outputs = [
        OutputSpec("curve", "Curve", SocketType.CURVE),
        OutputSpec("points", "Points", SocketType.VEC3, hide_preview=True),
        OutputSpec("length", "Length (m)", SocketType.FLOAT),
        OutputSpec("tangents", "Tangents", SocketType.VEC3, hide_preview=True),
    ]

    def compute(
        self,
        points: Any = None,
        closed: bool = False,
        samples: int = 100,
        alpha: float = 0.5,
    ) -> Dict[str, Any]:
        active_pts = self.get_active_points(points)
        self._last_evaluated_points = active_pts
        if not active_pts:
            return {
                "curve": CurveData(points=[], closed=bool(closed)),
                "points": [],
                "length": 0.0,
                "tangents": [],
            }

        samples_val = max(10, min(1000, int(samples)))
        closed_val = bool(closed)
        alpha_val = max(0.0, min(1.0, float(alpha)))

        eval_pts, total_len, tangents = evaluate_interpolated_curve(
            active_pts,
            closed=closed_val,
            samples=samples_val,
            alpha=alpha_val,
        )

        cdata = CurveData(points=eval_pts, closed=closed_val)
        return {
            "curve": cdata,
            "points": eval_pts,
            "length": round(total_len, 4),
            "tangents": tangents,
        }


NODE_REGISTRY["curve.nurbs_curve"] = NurbsCurveNode
NODE_REGISTRY["curve.spline"] = InterpolateCurveNode


# ============================================================================
# Fillet & Chamfer Mathematical Helpers for 3D Polylines & Face Loops
# ============================================================================
def _parse_index_set(indices_val: Any) -> Optional[set[int]]:
    """Parses int, list/tuple/set of ints, or comma-separated string into a set of integers."""
    if indices_val is None or indices_val == "":
        return None
    if isinstance(indices_val, (int, float)):
        return {int(indices_val)}
    if isinstance(indices_val, (list, tuple, set)):
        res = set()
        for x in indices_val:
            if isinstance(x, (int, float)):
                res.add(int(x))
            elif isinstance(x, str) and (x.strip().isdigit() or (x.strip().startswith("-") and x.strip()[1:].isdigit())):
                res.add(int(x.strip()))
        return res if res else None
    if isinstance(indices_val, str):
        s = indices_val.strip()
        if not s or s.lower() in ("all", "none", "*"):
            return None
        parts = s.replace(";", ",").split(",")
        res = set()
        for p in parts:
            p = p.strip()
            if p and (p.isdigit() or (p.startswith("-") and p[1:].isdigit())):
                res.add(int(p))
        return res if res else None
    return None


def _fillet_polyline(
    pts: List[Vec3],
    closed: bool,
    radius: float,
    segments: int = 4,
    indices: Optional[set[int]] = None,
) -> List[Vec3]:
    """
    Fillets the sharp corners of a 3D polyline (open or closed) with circular arcs.
    Uses Rodrigues rotation in 3D so arbitrary 3D orientations are preserved.
    """
    n = len(pts)
    if n < (3 if closed else 3):
        return [Vec3(p.x, p.y, p.z) for p in pts]

    r = max(1e-5, float(radius))
    seg = max(1, min(32, int(segments)))

    out: List[Vec3] = []
    start_i = 0 if closed else 1
    end_i = n if closed else n - 1

    if not closed:
        out.append(pts[0])

    for i in range(start_i, end_i):
        p_curr = pts[i]
        p_prev = pts[(i - 1 + n) % n]
        p_next = pts[(i + 1) % n]

        # Check vertex index filter
        if indices is not None and i not in indices:
            out.append(p_curr)
            continue

        v1 = p_curr - p_prev
        v2 = p_next - p_curr
        l1 = v1.length()
        l2 = v2.length()
        if l1 < 1e-6 or l2 < 1e-6:
            out.append(p_curr)
            continue

        u1 = v1 * (1.0 / l1)
        u2 = v2 * (1.0 / l2)
        dot = max(-1.0, min(1.0, u1.dot(u2)))

        # Collinear (straight line) or folded 180° back
        if dot > 0.9999 or dot < -0.9999:
            out.append(p_curr)
            continue

        tan_half = math.sqrt(max(1e-9, (1.0 + dot) / (1.0 - dot)))
        t = r / tan_half
        # Clamp tangent length to 48% of adjacent segment lengths to prevent overlap
        t_clamped = min(t, 0.48 * l1, 0.48 * l2)
        r_eff = t_clamped * tan_half

        pa = p_curr - u1 * t_clamped
        pb = p_curr + u2 * t_clamped

        bisect = (u2 - u1).normalized()
        d_c = math.sqrt(t_clamped * t_clamped + r_eff * r_eff)
        center = p_curr + bisect * d_c

        norm = u1.cross(u2).normalized()
        ra = pa - center
        rb = pb - center

        cos_beta = max(-1.0, min(1.0, (ra.normalized()).dot(rb.normalized())))
        beta = math.acos(cos_beta)

        if ra.cross(rb).dot(norm) < 0:
            norm = norm * -1.0

        for s in range(seg + 1):
            theta = beta * (s / seg)
            cos_t = math.cos(theta)
            sin_t = math.sin(theta)
            rotated = ra * cos_t + norm.cross(ra) * sin_t + norm * (norm.dot(ra)) * (1.0 - cos_t)
            out.append(center + rotated)

    if not closed:
        out.append(pts[-1])

    return out


def _chamfer_polyline(
    pts: List[Vec3],
    closed: bool,
    distance: float,
    indices: Optional[set[int]] = None,
) -> List[Vec3]:
    """
    Chamfers / bevels sharp corners of a 3D polyline (open or closed) with flat bevels.
    """
    n = len(pts)
    if n < (3 if closed else 3):
        return [Vec3(p.x, p.y, p.z) for p in pts]

    d = max(1e-5, float(distance))
    out: List[Vec3] = []
    start_i = 0 if closed else 1
    end_i = n if closed else n - 1

    if not closed:
        out.append(pts[0])

    for i in range(start_i, end_i):
        p_curr = pts[i]
        p_prev = pts[(i - 1 + n) % n]
        p_next = pts[(i + 1) % n]

        if indices is not None and i not in indices:
            out.append(p_curr)
            continue

        v1 = p_curr - p_prev
        v2 = p_next - p_curr
        l1 = v1.length()
        l2 = v2.length()
        if l1 < 1e-6 or l2 < 1e-6:
            out.append(p_curr)
            continue

        u1 = v1 * (1.0 / l1)
        u2 = v2 * (1.0 / l2)
        dot = max(-1.0, min(1.0, u1.dot(u2)))

        if dot > 0.9999 or dot < -0.9999:
            out.append(p_curr)
            continue

        t_clamped = min(d, 0.48 * l1, 0.48 * l2)
        pa = p_curr - u1 * t_clamped
        pb = p_curr + u2 * t_clamped

        out.append(pa)
        out.append(pb)

    if not closed:
        out.append(pts[-1])

    return out


# ============================================================================
# Fillet Curve / Face Node
# ============================================================================
@register_node
class FilletCurveNode(BaseNode):
    type_id = "curve.fillet"
    title = "Fillet Curve / Face"
    category = "Curves"
    description = (
        "Rounds sharp corners of an open curve, closed curve, or selected face by radius.\n"
        "Generates smooth circular arc fillets in 3D using Rodrigues rotation.\n"
        "Preserves end-points on open polylines while filleting interior sharp corners.\n"
        "For closed curves or faces (e.g. from Reference Face), fillets all outer corners and interior courtyard holes.\n"
        "Input 'indices' optionally specifies vertex index or list/string of indices to fillet (e.g. [1, 2] or '1, 2'). Default fillets all corners."
    )
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("curve", "Curve / Face", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("radius", "Radius (m)", SocketType.FLOAT, default=0.2, min_val=0.001, max_val=50.0, step=0.05),
        InputSpec("segments", "Segments", SocketType.INT, default=4, min_val=1, max_val=32),
        InputSpec("indices", "Corner Indices", SocketType.ANY, default="", access=AccessMode.LIST),
    ]
    outputs = [
        OutputSpec("curve", "Curve", SocketType.CURVE),
        OutputSpec("mesh", "Mesh / Face", SocketType.MESH),
        OutputSpec("points", "Points", SocketType.VEC3),
        OutputSpec("length", "Length (m)", SocketType.FLOAT),
    ]

    def compute(
        self,
        curve: Any = None,
        radius: float = 0.2,
        segments: int = 4,
        indices: Any = "",
    ) -> Dict[str, Any]:
        idx_set = _parse_index_set(indices)
        r = max(1e-4, float(radius))
        seg = max(1, min(32, int(segments)))

        # 1. MeshData input (from Reference Face or 2D polygon)
        if isinstance(curve, MeshData) or (isinstance(curve, dict) and ("outer" in curve or "faces" in curve)):
            outer_raw = curve.outer if isinstance(curve, MeshData) else curve.get("outer", [])
            holes_raw = curve.holes if isinstance(curve, MeshData) else curve.get("holes", [])

            if outer_raw:
                outer_pts = [Vec3(float(p[0]), float(p[1]), float(p[2])) for p in outer_raw]
                filleted_outer = _fillet_polyline(outer_pts, closed=True, radius=r, segments=seg, indices=idx_set)
                filleted_outer_tuples = [(p.x, p.y, p.z) for p in filleted_outer]

                filleted_holes_tuples: List[List[Tuple[float, float, float]]] = []
                for h_loop in (holes_raw or []):
                    h_pts = [Vec3(float(p[0]), float(p[1]), float(p[2])) for p in h_loop]
                    f_h = _fillet_polyline(h_pts, closed=True, radius=r, segments=seg, indices=idx_set)
                    if len(f_h) >= 3:
                        filleted_holes_tuples.append([(p.x, p.y, p.z) for p in f_h])

                f_mesh = MeshData(
                    outer=filleted_outer_tuples,
                    holes=filleted_holes_tuples,
                    name=getattr(curve, "name", "FilletedFace"),
                    color=getattr(curve, "color", (0.55, 0.78, 0.92)),
                    opacity=getattr(curve, "opacity", 1.0),
                )
                f_curve = CurveData(points=filleted_outer, closed=True)
                return {
                    "curve": f_curve,
                    "mesh": f_mesh,
                    "points": filleted_outer,
                    "length": f_curve.length(),
                }
            elif isinstance(curve, MeshData) and curve.faces:
                # Multi-face or single-face planar mesh: extract perimeter curve
                perim = curve.perimeter_as_curve()
                f_pts = _fillet_polyline(perim.points, closed=perim.closed, radius=r, segments=seg, indices=idx_set)
                f_curve = CurveData(points=f_pts, closed=perim.closed)
                f_mesh = f_curve.to_mesh_face(f"{curve.name}_Fillet") if f_curve.closed else f_curve.to_wire_mesh()
                return {
                    "curve": f_curve,
                    "mesh": f_mesh,
                    "points": f_pts,
                    "length": f_curve.length(),
                }

        # 2. CurveData input
        if isinstance(curve, CurveData) and curve.points:
            f_pts = _fillet_polyline(curve.points, closed=curve.closed, radius=r, segments=seg, indices=idx_set)
            f_curve = CurveData(points=f_pts, closed=curve.closed)
            f_mesh = f_curve.to_mesh_face("FilletedFace") if f_curve.closed else f_curve.to_wire_mesh("FilletedWire")
            return {
                "curve": f_curve,
                "mesh": f_mesh,
                "points": f_pts,
                "length": f_curve.length(),
            }

        # 3. Default fallback: Open L-shape curve with sharp 90-degree corner
        default_pts = [Vec3(0.0, 4.0, 0.0), Vec3(0.0, 0.0, 0.0), Vec3(4.0, 0.0, 0.0)]
        f_pts = _fillet_polyline(default_pts, closed=False, radius=r, segments=seg, indices=idx_set)
        f_curve = CurveData(points=f_pts, closed=False)
        return {
            "curve": f_curve,
            "mesh": f_curve.to_wire_mesh("FilletedCurve"),
            "points": f_pts,
            "length": f_curve.length(),
        }


# ============================================================================
# Chamfer Curve / Face Node
# ============================================================================
@register_node
class ChamferCurveNode(BaseNode):
    type_id = "curve.chamfer"
    title = "Chamfer Curve / Face"
    category = "Curves"
    description = (
        "Bevels sharp corners of an open curve, closed curve, or selected face by cutting back a specified distance.\n"
        "Generates clean straight chamfer edges in 3D.\n"
        "Preserves end-points on open polylines while chamfering interior sharp corners.\n"
        "For closed curves or faces (e.g. from Reference Face), chamfers all outer corners and interior courtyard holes.\n"
        "Input 'indices' optionally specifies vertex index or list/string of indices to chamfer (e.g. [1, 2] or '1, 2'). Default chamfers all corners."
    )
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("curve", "Curve / Face", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("distance", "Distance (m)", SocketType.FLOAT, default=0.2, min_val=0.001, max_val=50.0, step=0.05),
        InputSpec("indices", "Corner Indices", SocketType.ANY, default="", access=AccessMode.LIST),
    ]
    outputs = [
        OutputSpec("curve", "Curve", SocketType.CURVE),
        OutputSpec("mesh", "Mesh / Face", SocketType.MESH),
        OutputSpec("points", "Points", SocketType.VEC3),
        OutputSpec("length", "Length (m)", SocketType.FLOAT),
    ]

    def compute(
        self,
        curve: Any = None,
        distance: float = 0.2,
        indices: Any = "",
    ) -> Dict[str, Any]:
        idx_set = _parse_index_set(indices)
        d = max(1e-4, float(distance))

        # 1. MeshData input
        if isinstance(curve, MeshData) or (isinstance(curve, dict) and ("outer" in curve or "faces" in curve)):
            outer_raw = curve.outer if isinstance(curve, MeshData) else curve.get("outer", [])
            holes_raw = curve.holes if isinstance(curve, MeshData) else curve.get("holes", [])

            if outer_raw:
                outer_pts = [Vec3(float(p[0]), float(p[1]), float(p[2])) for p in outer_raw]
                chamfered_outer = _chamfer_polyline(outer_pts, closed=True, distance=d, indices=idx_set)
                chamfered_outer_tuples = [(p.x, p.y, p.z) for p in chamfered_outer]

                chamfered_holes_tuples: List[List[Tuple[float, float, float]]] = []
                for h_loop in (holes_raw or []):
                    h_pts = [Vec3(float(p[0]), float(p[1]), float(p[2])) for p in h_loop]
                    c_h = _chamfer_polyline(h_pts, closed=True, distance=d, indices=idx_set)
                    if len(c_h) >= 3:
                        chamfered_holes_tuples.append([(p.x, p.y, p.z) for p in c_h])

                c_mesh = MeshData(
                    outer=chamfered_outer_tuples,
                    holes=chamfered_holes_tuples,
                    name=getattr(curve, "name", "ChamferedFace"),
                    color=getattr(curve, "color", (0.55, 0.78, 0.92)),
                    opacity=getattr(curve, "opacity", 1.0),
                )
                c_curve = CurveData(points=chamfered_outer, closed=True)
                return {
                    "curve": c_curve,
                    "mesh": c_mesh,
                    "points": chamfered_outer,
                    "length": c_curve.length(),
                }
            elif isinstance(curve, MeshData) and curve.faces:
                perim = curve.perimeter_as_curve()
                c_pts = _chamfer_polyline(perim.points, closed=perim.closed, distance=d, indices=idx_set)
                c_curve = CurveData(points=c_pts, closed=perim.closed)
                c_mesh = c_curve.to_mesh_face(f"{curve.name}_Chamfer") if c_curve.closed else c_curve.to_wire_mesh()
                return {
                    "curve": c_curve,
                    "mesh": c_mesh,
                    "points": c_pts,
                    "length": c_curve.length(),
                }

        # 2. CurveData input
        if isinstance(curve, CurveData) and curve.points:
            c_pts = _chamfer_polyline(curve.points, closed=curve.closed, distance=d, indices=idx_set)
            c_curve = CurveData(points=c_pts, closed=curve.closed)
            c_mesh = c_curve.to_mesh_face("ChamferedFace") if c_curve.closed else c_curve.to_wire_mesh("ChamferedWire")
            return {
                "curve": c_curve,
                "mesh": c_mesh,
                "points": c_pts,
                "length": c_curve.length(),
            }

        # 3. Default fallback: Open L-shape curve
        default_pts = [Vec3(0.0, 4.0, 0.0), Vec3(0.0, 0.0, 0.0), Vec3(4.0, 0.0, 0.0)]
        c_pts = _chamfer_polyline(default_pts, closed=False, distance=d, indices=idx_set)
        c_curve = CurveData(points=c_pts, closed=False)
        return {
            "curve": c_curve,
            "mesh": c_curve.to_wire_mesh("ChamferedCurve"),
            "points": c_pts,
            "length": c_curve.length(),
        }


# Register backward compatibility aliases
NODE_REGISTRY["curve.fillet"] = FilletCurveNode
NODE_REGISTRY["curve.chamfer"] = ChamferCurveNode
