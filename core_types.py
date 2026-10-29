# SPDX-License-Identifier: GPL-3.0-or-later
"""Core data types, socket specifications, and watertight geometry primitives."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, List, Optional, Tuple


class SocketType(str, Enum):
    FLOAT = "FLOAT"
    INT = "INT"
    BOOL = "BOOL"
    STRING = "STRING"
    VEC3 = "VEC3"
    POINT = "VEC3"
    VECTOR = "VEC3"
    CURVE = "CURVE"
    MESH = "MESH"
    ANY = "ANY"


class AccessMode(str, Enum):
    """Grasshopper-style access mode for node inputs."""
    ITEM = "ITEM"  # Engine auto-broadcasts lists and calls compute() per item
    LIST = "LIST"  # Engine passes the full list directly into compute()


# Color palette (R, G, B) for socket pins and wires
SOCKET_COLORS: dict[SocketType, Tuple[int, int, int]] = {
    SocketType.FLOAT:  (86, 182, 194),   # Cyan
    SocketType.INT:    (97, 175, 239),   # Blue
    SocketType.BOOL:   (224, 108, 117),  # Coral Red
    SocketType.STRING: (229, 192, 123),  # Warm Yellow
    SocketType.VEC3:   (152, 195, 121),  # Green
    SocketType.CURVE:  (209, 154, 102),  # Orange
    SocketType.MESH:   (198, 120, 221),  # Purple
    SocketType.ANY:    (171, 178, 191),  # Grey
}


@dataclass(frozen=True)
class Vec3:
    """Immutable 3D Vector/Point in Z-up meter coordinates."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __add__(self, o: Vec3) -> Vec3:
        return Vec3(self.x + o.x, self.y + o.y, self.z + o.z)

    def __sub__(self, o: Vec3) -> Vec3:
        return Vec3(self.x - o.x, self.y - o.y, self.z - o.z)

    def __mul__(self, s: float) -> Vec3:
        return Vec3(self.x * s, self.y * s, self.z * s)

    def __truediv__(self, s: float) -> Vec3:
        inv = 1.0 / float(s) if abs(s) > 1e-12 else 0.0
        return Vec3(self.x * inv, self.y * inv, self.z * inv)

    def dot(self, o: Vec3) -> float:
        return self.x * o.x + self.y * o.y + self.z * o.z

    def cross(self, o: Vec3) -> Vec3:
        return Vec3(
            self.y * o.z - self.z * o.y,
            self.z * o.x - self.x * o.z,
            self.x * o.y - self.y * o.x,
        )

    def length(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def distance_to(self, o: Vec3) -> float:
        return (self - o).length()

    def normalized(self) -> Vec3:
        ln = self.length()
        return self * (1.0 / ln) if ln > 1e-12 else Vec3(0.0, 0.0, 1.0)

    def to_tuple(self) -> Tuple[float, float, float]:
        return (float(self.x), float(self.y), float(self.z))

def extract_plane_frame(plane_or_origin: Any) -> Tuple[Vec3, Vec3, Vec3, Vec3]:
    """
    Extracts (origin, u_axis, v_axis, normal) from a plane dict, object, or Vec3.
    Defaults to World XY plane (origin, (1,0,0), (0,1,0), (0,0,1)).
    """
    if isinstance(plane_or_origin, dict):
        orig_val = plane_or_origin.get("origin")
        if isinstance(orig_val, Vec3):
            p0 = orig_val
        elif isinstance(orig_val, (tuple, list)) and len(orig_val) >= 3:
            p0 = Vec3(float(orig_val[0]), float(orig_val[1]), float(orig_val[2]))
        elif "x" in plane_or_origin:
            p0 = Vec3(float(plane_or_origin.get("x", 0.0)), float(plane_or_origin.get("y", 0.0)), float(plane_or_origin.get("z", 0.0)))
        else:
            p0 = Vec3(0.0, 0.0, 0.0)

        def _to_v3(k: str, default: Vec3) -> Vec3:
            v = plane_or_origin.get(k)
            if isinstance(v, Vec3):
                return v
            if isinstance(v, (tuple, list)) and len(v) >= 3:
                return Vec3(float(v[0]), float(v[1]), float(v[2]))
            return default

        u = _to_v3("u", _to_v3("u_axis", Vec3(1.0, 0.0, 0.0)))
        v = _to_v3("v", _to_v3("v_axis", Vec3(0.0, 1.0, 0.0)))
        n = _to_v3("normal", _to_v3("n", Vec3(0.0, 0.0, 1.0)))

        u_len = u.length()
        u = u * (1.0 / u_len) if u_len > 1e-6 else Vec3(1.0, 0.0, 0.0)
        v_len = v.length()
        v = v * (1.0 / v_len) if v_len > 1e-6 else Vec3(0.0, 1.0, 0.0)
        n_len = n.length()
        n = n * (1.0 / n_len) if n_len > 1e-6 else Vec3(0.0, 0.0, 1.0)
        return p0, u, v, n

    elif isinstance(plane_or_origin, Vec3):
        return plane_or_origin, Vec3(1.0, 0.0, 0.0), Vec3(0.0, 1.0, 0.0), Vec3(0.0, 0.0, 1.0)
    elif isinstance(plane_or_origin, (tuple, list)) and len(plane_or_origin) >= 3:
        p0 = Vec3(float(plane_or_origin[0]), float(plane_or_origin[1]), float(plane_or_origin[2]))
        return p0, Vec3(1.0, 0.0, 0.0), Vec3(0.0, 1.0, 0.0), Vec3(0.0, 0.0, 1.0)
    else:
        return Vec3(0.0, 0.0, 0.0), Vec3(1.0, 0.0, 0.0), Vec3(0.0, 1.0, 0.0), Vec3(0.0, 0.0, 1.0)



@dataclass
class CurveData:
    """3D polyline or closed profile loop."""
    points: List[Vec3] = field(default_factory=list)
    closed: bool = False

    def copy(self) -> CurveData:
        return CurveData(points=[Vec3(p.x, p.y, p.z) for p in self.points], closed=self.closed)

    def length(self) -> float:
        """Returns the total perimeter or arc length of the curve."""
        if len(self.points) < 2:
            return 0.0
        total = 0.0
        for i in range(len(self.points) - 1):
            total += self.points[i].distance_to(self.points[i + 1])
        if self.closed and len(self.points) >= 3:
            total += self.points[-1].distance_to(self.points[0])
        return total

    def transformed(
        self,
        offset: Vec3 = Vec3(),
        rot_z_deg: float = 0.0,
        scale: Vec3 = Vec3(1.0, 1.0, 1.0),
    ) -> CurveData:
        rad = math.radians(rot_z_deg)
        c, s = math.cos(rad), math.sin(rad)
        out_pts: List[Vec3] = []
        for p in self.points:
            sx, sy, sz = p.x * scale.x, p.y * scale.y, p.z * scale.z
            rx = sx * c - sy * s
            ry = sx * s + sy * c
            out_pts.append(Vec3(rx + offset.x, ry + offset.y, sz + offset.z))
        return CurveData(points=out_pts, closed=self.closed)

    def to_mesh_face(self, name: str = "PlanarCurveFace") -> MeshData:
        """Converts a closed planar curve into a single-face MeshData."""
        pts = [p.to_tuple() for p in self.points]
        if not pts or len(pts) < 3:
            return MeshData(name=name)
        # Ensure CCW orientation (positive 2D signed area)
        area2 = sum(
            pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
            for i in range(len(pts))
        )
        if area2 < 0:
            pts.reverse()
        face_idx = list(range(len(pts)))
        edges = [(i, (i + 1) % len(pts)) for i in range(len(pts))]
        return MeshData(vertices=pts, faces=[face_idx], edges=edges, name=name)

    def to_wire_mesh(self, name: str = "CurveWire") -> MeshData:
        """Converts curve into an edge-based wire MeshData for 3D viewport preview."""
        pts = [p.to_tuple() for p in self.points]
        if not pts:
            return MeshData(name=name)
        n = len(pts)
        if n < 2:
            return MeshData(vertices=pts, edges=[], name=name)
        edges = [(i, i + 1) for i in range(n - 1)]
        if self.closed and n >= 3:
            edges.append((n - 1, 0))
        return MeshData(vertices=pts, faces=[], edges=edges, name=name)


@dataclass
class MeshData:
    """
    Pure-Python B-Rep/Polygon Mesh container compatible with IngeTrazo's core.mesh.Mesh.
    All faces use Counter-Clockwise (CCW) outward winding so solids pass IngeTrazo's
    hermeticity guard (`is_closed` / `solid_report`) and report accurate IFC volumes.
    """
    vertices: List[Tuple[float, float, float]] = field(default_factory=list)
    faces: List[List[int]] = field(default_factory=list)
    edges: List[Tuple[int, int]] = field(default_factory=list)
    color: Optional[Tuple[float, float, float]] = None
    material_name: str = ""
    opacity: Optional[float] = None
    face_materials: List[str] = field(default_factory=list)
    face_colors: List[Optional[Tuple[float, float, float]]] = field(default_factory=list)
    face_opacities: List[Optional[float]] = field(default_factory=list)
    ifc_class: str = ""
    name: str = "ParametricSolid"
    outer: Optional[List[Any]] = None
    holes: Optional[List[List[Any]]] = None
    holed_faces: List[Tuple[List[int], List[List[int]]]] = field(default_factory=list)
    source_node_id: Optional[str] = None
    smooth: bool = True
    show_wires: bool = True

    def copy(self) -> MeshData:
        return MeshData(
            vertices=list(self.vertices),
            faces=[list(f) for f in self.faces],
            edges=list(self.edges),
            color=self.color,
            material_name=self.material_name,
            opacity=self.opacity,
            face_materials=list(self.face_materials),
            face_colors=list(self.face_colors),
            face_opacities=list(self.face_opacities),
            ifc_class=self.ifc_class,
            name=self.name,
            outer=list(self.outer) if self.outer else None,
            holes=[list(h) for h in self.holes] if self.holes else None,
            holed_faces=[(list(o), [list(h) for h in hl]) for (o, hl) in self.holed_faces],
            source_node_id=self.source_node_id,
            smooth=self.smooth,
            show_wires=self.show_wires,
        )

    def transformed(
        self,
        offset: Vec3 = Vec3(),
        rot_z_deg: float = 0.0,
        scale: Vec3 = Vec3(1.0, 1.0, 1.0),
    ) -> MeshData:
        rad = math.radians(rot_z_deg)
        c, s = math.cos(rad), math.sin(rad)
        new_verts: List[Tuple[float, float, float]] = []
        for vx, vy, vz in self.vertices:
            sx, sy, sz = vx * scale.x, vy * scale.y, vz * scale.z
            rx = sx * c - sy * s
            ry = sx * s + sy * c
            new_verts.append((rx + offset.x, ry + offset.y, sz + offset.z))
        out = self.copy()
        out.vertices = new_verts
        # If reflection occurred (negative determinant), flip face winding to stay outward CCW
        if (scale.x * scale.y * scale.z) < 0:
            out.faces = [list(reversed(f)) for f in out.faces]
        return out

    def perimeter_as_curve(self) -> CurveData:
        """Extracts the outermost perimeter boundary of this mesh as a CurveData."""
        verts = self.vertices
        if not verts:
            return CurveData()

        if self.faces:
            # 1. Single face fast-path (most common for 2D curve shapes)
            if len(self.faces) == 1:
                f = self.faces[0]
                pts = [Vec3(verts[i][0], verts[i][1], verts[i][2]) for i in f]
                return CurveData(points=pts, closed=True)

            # 2. Multi-face boundary edge loop tracing
            half_edges = set()
            edge_counts = {}
            for face in self.faces:
                k = len(face)
                for i in range(k):
                    u = face[i]
                    v = face[(i + 1) % k]
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
                            p += math.hypot(math.hypot(dx, dy), dz)
                        return p

                    largest_loop = max(loops, key=loop_perimeter)
                    pts = [Vec3(verts[i][0], verts[i][1], verts[i][2]) for i in largest_loop]
                    return CurveData(points=pts, closed=True)

        if self.edges:
            adj = {}
            for u, v in self.edges:
                adj.setdefault(u, []).append(v)
                adj.setdefault(v, []).append(u)
            start = next((k for k, neighbors in adj.items() if len(neighbors) == 1), None)
            if start is None and adj:
                start = next(iter(adj.keys()))
            if start is not None:
                ordered = [start]
                visited = {start}
                curr = start
                while True:
                    next_node = next((n for n in adj.get(curr, []) if n not in visited), None)
                    if next_node is None:
                        break
                    visited.add(next_node)
                    ordered.append(next_node)
                    curr = next_node
                pts = [Vec3(verts[i][0], verts[i][1], verts[i][2]) for i in ordered]
                is_closed = (len(ordered) >= 3 and ordered[0] in adj.get(ordered[-1], []))
                return CurveData(points=pts, closed=is_closed)

        pts = [Vec3(v[0], v[1], v[2]) for v in verts]
        return CurveData(points=pts, closed=False)

    @staticmethod
    def merge(meshes: List[MeshData], name: str = "MergedMesh") -> MeshData:
        result = MeshData(name=name)
        for m in meshes:
            if not isinstance(m, MeshData):
                continue
            v_offset = len(result.vertices)
            result.vertices.extend(m.vertices)
            for f_idx, f in enumerate(m.faces):
                result.faces.append([idx + v_offset for idx in f])
                mat = m.face_materials[f_idx] if f_idx < len(m.face_materials) else m.material_name
                col = m.face_colors[f_idx] if f_idx < len(m.face_colors) else m.color
                op = m.face_opacities[f_idx] if f_idx < len(m.face_opacities) else m.opacity
                result.face_materials.append(mat)
                result.face_colors.append(col)
                result.face_opacities.append(op)
            for e0, e1 in m.edges:
                result.edges.append((e0 + v_offset, e1 + v_offset))
            if m.color and not result.color:
                result.color = m.color
            if m.material_name and not result.material_name:
                result.material_name = m.material_name
            if m.opacity is not None and result.opacity is None:
                result.opacity = m.opacity
            if m.ifc_class and not result.ifc_class:
                result.ifc_class = m.ifc_class
        return result

    def extract_edges_as_curves(self) -> List[CurveData]:
        """Returns each edge of this mesh as a 2-point CurveData."""
        res: List[CurveData] = []
        for i0, i1 in self.edges:
            if 0 <= i0 < len(self.vertices) and 0 <= i1 < len(self.vertices):
                p0 = Vec3(float(self.vertices[i0][0]), float(self.vertices[i0][1]), float(self.vertices[i0][2]))
                p1 = Vec3(float(self.vertices[i1][0]), float(self.vertices[i1][1]), float(self.vertices[i1][2]))
                res.append(CurveData(points=[p0, p1], closed=False))
        return res

    def extract_wireframe_mesh(self, name: str = "Wireframe") -> MeshData:
        """Returns a lightweight wireframe MeshData containing only vertices and edges."""
        return MeshData(
            vertices=list(self.vertices),
            faces=[],
            edges=list(self.edges),
            name=name,
            color=self.color or (0.25, 0.65, 0.95),
            opacity=self.opacity,
        )

    def to_native_mesh(self) -> Any:
        """Converts this MeshData into an IngeTrazo core.mesh.Mesh instance."""
        try:
            from core.mesh import Mesh
            from PySide6.QtGui import QVector3D
        except ImportError:
            return None

        m = Mesh()
        qvecs = [QVector3D(float(x), float(y), float(z)) for (x, y, z) in self.vertices]

        if self.holed_faces:
            for face_indices in self.faces:
                valid_qvecs = [qvecs[idx] for idx in face_indices if 0 <= idx < len(qvecs)]
                if len(valid_qvecs) >= 3:
                    try:
                        m.add_face(valid_qvecs)
                    except Exception:
                        pass
            for outer_idx, hole_idx_list in self.holed_faces:
                outer_qvecs = [qvecs[i] for i in outer_idx if 0 <= i < len(qvecs)]
                holes_qvecs = [[qvecs[i] for i in h if 0 <= i < len(qvecs)] for h in hole_idx_list]
                if len(outer_qvecs) >= 3:
                    try:
                        m.add_face(outer_qvecs, hole_loops=holes_qvecs if holes_qvecs else None)
                    except Exception:
                        pass
        elif self.faces:
            for face_indices in self.faces:
                valid_qvecs = [qvecs[idx] for idx in face_indices if 0 <= idx < len(qvecs)]
                if len(valid_qvecs) >= 3:
                    try:
                        m.add_face(valid_qvecs)
                    except Exception:
                        pass
        elif self.outer:
            outer_qvecs = [QVector3D(float(p[0]), float(p[1]), float(p[2])) for p in self.outer]
            holes_qvecs = [[QVector3D(float(p[0]), float(p[1]), float(p[2])) for p in h] for h in (self.holes or [])]
            if len(outer_qvecs) >= 3:
                try:
                    m.add_face(outer_qvecs, hole_loops=holes_qvecs if holes_qvecs else None)
                except Exception:
                    pass

        if hasattr(m, "edges") and not m.edges and self.edges:
            for i0, i1 in self.edges:
                if 0 <= i0 < len(qvecs) and 0 <= i1 < len(qvecs):
                    try:
                        m.add_edge(qvecs[i0], qvecs[i1])
                    except Exception:
                        pass
        return m

    @classmethod
    def from_native_mesh(cls, native_mesh: Any, name: str = "Solid") -> MeshData:
        """Converts an IngeTrazo core.mesh.Mesh instance into a MeshData."""
        vert_map = {}
        vertices = []

        def get_v_idx(qv: Any) -> int:
            pos = getattr(qv, "position", qv)
            if hasattr(pos, "x"):
                x = float(pos.x() if callable(pos.x) else pos.x)
                y = float(pos.y() if callable(pos.y) else pos.y)
                z = float(pos.z() if callable(pos.z) else pos.z)
            elif isinstance(pos, (list, tuple)) and len(pos) >= 3:
                x, y, z = float(pos[0]), float(pos[1]), float(pos[2])
            else:
                x, y, z = 0.0, 0.0, 0.0
            key = (round(x, 6), round(y, 6), round(z, 6))
            if key not in vert_map:
                vert_map[key] = len(vertices)
                vertices.append((x, y, z))
            return vert_map[key]

        faces = []
        holed_faces = []
        for f in getattr(native_mesh, "faces", []):
            f_verts = getattr(f, "vertices", None)
            if f_verts is None:
                f_loop = getattr(f, "loop", None)
                f_verts = [getattr(v, "position", v) for v in f_loop] if f_loop else []
            outer_idx = [get_v_idx(v) for v in f_verts]
            holes_idx = []
            for h in getattr(f, "hole_loops", None) or getattr(f, "holes", None) or []:
                h_v = [get_v_idx(hv) for hv in h]
                if len(h_v) >= 3:
                    holes_idx.append(h_v)
            if holes_idx:
                holed_faces.append((outer_idx, holes_idx))
            if len(outer_idx) >= 3:
                faces.append(outer_idx)

        edges = []
        for e in getattr(native_mesh, "edges", []):
            p0 = getattr(e, "v0", None)
            p1 = getattr(e, "v1", None)
            if p0 is not None and p1 is not None:
                i0 = get_v_idx(p0)
                i1 = get_v_idx(p1)
                edges.append((i0, i1))

        if not edges and faces:
            seen_edges = set()
            for face in faces:
                k = len(face)
                for i in range(k):
                    a, b = face[i], face[(i + 1) % k]
                    undir = (min(a, b), max(a, b))
                    if undir not in seen_edges:
                        seen_edges.add(undir)
                        edges.append(undir)

        return cls(
            vertices=vertices,
            faces=faces,
            edges=edges,
            holed_faces=holed_faces,
            name=name,
        )

    @staticmethod
    def create_box(
        origin: Any = None,
        dx: float = 1.0,
        dy: float = 1.0,
        dz: float = 1.0,
        centered: bool = False,
        center_z: bool = False,
        plane: Any = None,
    ) -> MeshData:
        """
        Creates a watertight 6-face rectangular solid with outward CCW normals.
        Supports world axis alignment or arbitrary plane orientation, and
        centering in XY or XYZ.
        """
        frame_src = plane if plane is not None else origin
        p0, u, v, n = extract_plane_frame(frame_src)

        dx = float(dx)
        dy = float(dy)
        dz = float(dz)

        # Local coordinate bounds
        if centered:
            hx = abs(dx) * 0.5
            hy = abs(dy) * 0.5
            x0, x1 = -hx, hx
            y0, y1 = -hy, hy
        else:
            x0, x1 = 0.0, dx
            y0, y1 = 0.0, dy

        if center_z:
            hz = abs(dz) * 0.5
            z0, z1 = -hz, hz
        else:
            z0, z1 = 0.0, dz

        if x0 > x1: x0, x1 = x1, x0
        if y0 > y1: y0, y1 = y1, y0
        if z0 > z1: z0, z1 = z1, z0

        local_verts = [
            (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),  # 0..3 bottom
            (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),  # 4..7 top
        ]

        # Transform to world coordinates: P = p0 + x'*u + y'*v + z'*n
        verts: List[Tuple[float, float, float]] = []
        for lx, ly, lz in local_verts:
            wx = p0.x + lx * u.x + ly * v.x + lz * n.x
            wy = p0.y + lx * u.y + ly * v.y + lz * n.y
            wz = p0.z + lx * u.z + ly * v.z + lz * n.z
            verts.append((wx, wy, wz))

        faces = [
            [0, 3, 2, 1],  # Bottom (-Z)
            [4, 5, 6, 7],  # Top (+Z)
            [0, 1, 5, 4],  # Front (-Y)
            [1, 2, 6, 5],  # Right (+X)
            [2, 3, 7, 6],  # Back (+Y)
            [3, 0, 4, 7],  # Left (-X)
        ]
        edges = [
            (0, 1), (1, 2), (2, 3), (3, 0),
            (4, 5), (5, 6), (6, 7), (7, 4),
            (0, 4), (1, 5), (2, 6), (3, 7)
        ]
        return MeshData(vertices=verts, faces=faces, edges=edges, name="Box")

    @staticmethod
    def create_cylinder(center: Vec3, radius: float, height: float, segments: int = 24) -> MeshData:
        """Creates a watertight n-gon prism cylinder with outward CCW normals."""
        segments = max(3, int(segments))
        radius = max(1e-4, float(radius))
        z0 = center.z
        z1 = center.z + height
        if z0 > z1:
            z0, z1 = z1, z0

        verts: List[Tuple[float, float, float]] = []
        for z in (z0, z1):
            for i in range(segments):
                ang = 2.0 * math.pi * i / segments
                verts.append((
                    center.x + radius * math.cos(ang),
                    center.y + radius * math.sin(ang),
                    z,
                ))

        faces: List[List[int]] = []
        # Bottom cap (-Z): reversed for outward normal pointing down
        faces.append(list(reversed(range(0, segments))))
        # Top cap (+Z): CCW looking from above
        faces.append(list(range(segments, 2 * segments)))
        # Side quads
        for i in range(segments):
            nxt = (i + 1) % segments
            faces.append([i, nxt, segments + nxt, segments + i])

        edges: List[Tuple[int, int]] = []
        for i in range(segments):
            nxt = (i + 1) % segments
            edges.append((i, nxt))
            edges.append((segments + i, segments + nxt))
            edges.append((i, segments + i))

        return MeshData(vertices=verts, faces=faces, edges=edges, name="Cylinder")

    @staticmethod
    def create_sphere(
        center: Vec3 = Vec3(0, 0, 0),
        radius: float = 1.0,
        rings: int = 16,
        segments: int = 32,
    ) -> MeshData:
        """Creates a watertight UV sphere with shared vertices and outward CCW normals."""
        rings = max(3, int(rings))
        segments = max(4, int(segments))
        r = max(1e-4, float(radius))
        c = center or Vec3()

        verts: List[Tuple[float, float, float]] = []
        # North pole: index 0
        verts.append((c.x, c.y, c.z + r))

        # Intermediate rings
        for i in range(1, rings):
            phi = math.pi * i / rings
            sin_phi = math.sin(phi)
            cos_phi = math.cos(phi)
            z = c.z + r * cos_phi
            for j in range(segments):
                theta = 2.0 * math.pi * j / segments
                x = c.x + r * sin_phi * math.cos(theta)
                y = c.y + r * sin_phi * math.sin(theta)
                verts.append((x, y, z))

        # South pole: last index
        south_pole_idx = len(verts)
        verts.append((c.x, c.y, c.z - r))

        faces: List[List[int]] = []
        edges_set = set()

        def _add_edge(a: int, b: int) -> None:
            if a > b:
                a, b = b, a
            edges_set.add((a, b))

        # North pole fan
        for j in range(segments):
            nxt_j = (j + 1) % segments
            v1 = 1 + j
            v2 = 1 + nxt_j
            faces.append([0, v1, v2])
            _add_edge(0, v1)
            _add_edge(v1, v2)
            _add_edge(v2, 0)

        # Middle quads
        for i in range(rings - 2):
            ring1 = 1 + i * segments
            ring2 = 1 + (i + 1) * segments
            for j in range(segments):
                nxt_j = (j + 1) % segments
                v00 = ring1 + j
                v01 = ring1 + nxt_j
                v10 = ring2 + j
                v11 = ring2 + nxt_j
                faces.append([v00, v10, v11, v01])
                _add_edge(v00, v10)
                _add_edge(v10, v11)
                _add_edge(v11, v01)
                _add_edge(v01, v00)

        # South pole fan
        last_ring = 1 + (rings - 2) * segments
        for j in range(segments):
            nxt_j = (j + 1) % segments
            v1 = last_ring + j
            v2 = last_ring + nxt_j
            faces.append([south_pole_idx, v2, v1])
            _add_edge(south_pole_idx, v2)
            _add_edge(v2, v1)
            _add_edge(v1, south_pole_idx)

        return MeshData(vertices=verts, faces=faces, edges=list(edges_set), name="Sphere")

    @staticmethod
    def extrude_curve(curve: CurveData, height: float, cap: bool = True) -> MeshData:
        """Extrudes a 2D/3D CurveData along Z by `height`."""
        pts = curve.points
        if len(pts) < 2 or abs(height) < 1e-6:
            return MeshData()
        n = len(pts)
        dz = float(height)
        verts = [p.to_tuple() for p in pts] + [(p.x, p.y, p.z + dz) for p in pts]
        faces: List[List[int]] = []

        # Ensure 2D signed area is positive (CCW in XY) when extruding +Z
        area2 = 0.0
        for i in range(n):
            p1, p2 = pts[i], pts[(i + 1) % n]
            area2 += (p1.x * p2.y - p2.x * p1.y)
        flip = (area2 < 0) ^ (dz < 0)

        seg_count = n if curve.closed else n - 1
        for i in range(seg_count):
            nxt = (i + 1) % n
            quad = [i, nxt, n + nxt, n + i]
            faces.append(list(reversed(quad)) if flip else quad)

        if curve.closed and cap and n >= 3:
            bot = list(range(0, n))
            top = list(range(n, 2 * n))
            if not flip:
                bot.reverse()
            else:
                top.reverse()
            faces.insert(0, bot)
            faces.append(top)

        edges: List[Tuple[int, int]] = []
        for i in range(seg_count):
            nxt = (i + 1) % n
            edges.append((i, nxt))
            edges.append((n + i, n + nxt))
            edges.append((i, n + i))
        if not curve.closed:
            edges.append((n - 1, 2 * n - 1))

        return MeshData(vertices=verts, faces=faces, edges=edges, name="Extrusion")

    @staticmethod
    def extrude_face(
        face_data: Any,
        height: float = 3.0,
        cap: bool = True,
        direction: Optional[Vec3] = None,
        name: str = "ExtrudedSolid",
    ) -> MeshData:
        """
        Extrudes a planar face (simple, surface dict, or annular frame with holes) into a watertight 3D solid.
        Supports MeshData, dict ({'outer': ..., 'holes': ...}), CurveData, or list of faces.
        """
        if face_data is None:
            face_data = {
                "outer": [(0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (4.0, 4.0, 0.0), (0.0, 4.0, 0.0)],
                "holes": [],
            }

        # Multi-face / list handling
        if isinstance(face_data, list) and face_data and not isinstance(face_data[0], (Vec3, tuple, list, float, int)):
            solids = []
            for item in face_data:
                solids.append(MeshData.extrude_face(item, height=height, cap=cap, direction=direction, name=name))
            return MeshData.merge(solids, name=name)

        def _to_v3(p: Any) -> Vec3:
            if isinstance(p, Vec3):
                return p
            if hasattr(p, "x") and hasattr(p, "y") and hasattr(p, "z"):
                return Vec3(
                    float(p.x() if callable(p.x) else p.x),
                    float(p.y() if callable(p.y) else p.y),
                    float(p.z() if callable(p.z) else p.z),
                )
            if isinstance(p, (tuple, list)) and len(p) >= 3:
                return Vec3(float(p[0]), float(p[1]), float(p[2]))
            return Vec3(0, 0, 0)

        outer_pts: List[Vec3] = []
        hole_loops: List[List[Vec3]] = []

        if isinstance(face_data, dict):
            outer_pts = [_to_v3(p) for p in face_data.get("outer", [])]
            for h in face_data.get("holes", []):
                h_pts = [_to_v3(p) for p in h]
                if len(h_pts) >= 3:
                    hole_loops.append(h_pts)
        elif isinstance(face_data, MeshData):
            if getattr(face_data, "outer", None):
                outer_pts = [_to_v3(p) for p in face_data.outer]
                if getattr(face_data, "holes", None):
                    for h in face_data.holes:
                        h_pts = [_to_v3(p) for p in h]
                        if len(h_pts) >= 3:
                            hole_loops.append(h_pts)
            else:
                # Recover boundary loops from mesh edges or perimeter
                verts = [_to_v3(v) for v in face_data.vertices]
                if face_data.edges and verts:
                    adj: Dict[int, List[int]] = {}
                    for u, v in face_data.edges:
                        if 0 <= u < len(verts) and 0 <= v < len(verts):
                            adj.setdefault(u, []).append(v)
                            adj.setdefault(v, []).append(u)
                    visited_e = set()
                    cand_loops = []
                    for s_node in adj:
                        while True:
                            unused = [n for n in adj[s_node] if (min(s_node, n), max(s_node, n)) not in visited_e]
                            if not unused:
                                break
                            curr = s_node
                            lp = [curr]
                            while True:
                                nbrs = [n for n in adj[curr] if (min(curr, n), max(curr, n)) not in visited_e]
                                if not nbrs:
                                    break
                                nxt = nbrs[0]
                                visited_e.add((min(curr, nxt), max(curr, nxt)))
                                lp.append(nxt)
                                curr = nxt
                                if curr == s_node:
                                    break
                            if len(lp) >= 4 and lp[0] == lp[-1]:
                                cand_loops.append(lp[:-1])
                    if cand_loops:
                        def _area_of_indices(indices: List[int]) -> float:
                            pts_lp = [verts[idx] for idx in indices]
                            n_lp = len(pts_lp)
                            nx = ny = nz = 0.0
                            for i in range(n_lp):
                                a, b = pts_lp[i], pts_lp[(i + 1) % n_lp]
                                nx += (a.y - b.y) * (a.z + b.z)
                                ny += (a.z - b.z) * (a.x + b.x)
                                nz += (a.x - b.x) * (a.y + b.y)
                            return 0.5 * math.hypot(math.hypot(nx, ny), nz)
                        cand_loops.sort(key=_area_of_indices, reverse=True)
                        outer_pts = [verts[i] for i in cand_loops[0]]
                        for hl in cand_loops[1:]:
                            h_pts = [verts[i] for i in hl]
                            if len(h_pts) >= 3:
                                hole_loops.append(h_pts)
                if not outer_pts:
                    c = face_data.perimeter_as_curve()
                    outer_pts = [_to_v3(p) for p in c.points]
        elif isinstance(face_data, CurveData):
            outer_pts = [_to_v3(p) for p in face_data.points]
        elif isinstance(face_data, list) and face_data:
            outer_pts = [_to_v3(p) for p in face_data]

        if len(outer_pts) < 3:
            outer_pts = [Vec3(0, 0, 0), Vec3(4, 0, 0), Vec3(4, 4, 0), Vec3(0, 4, 0)]

        # Compute normal of outer boundary
        n_out = len(outer_pts)
        nx = ny = nz = 0.0
        for i in range(n_out):
            p0 = outer_pts[i]
            p1 = outer_pts[(i + 1) % n_out]
            nx += (p0.y - p1.y) * (p0.z + p1.z)
            ny += (p0.z - p1.z) * (p0.x + p1.x)
            nz += (p0.x - p1.x) * (p0.y + p1.y)
        norm_len = math.hypot(math.hypot(nx, ny), nz)
        normal = Vec3(0, 0, 1) if norm_len < 1e-9 else Vec3(nx / norm_len, ny / norm_len, nz / norm_len)

        # Ensure outer loop is CCW
        area_signed = sum((outer_pts[i].cross(outer_pts[(i + 1) % n_out])).dot(normal) for i in range(n_out))
        if area_signed < 0:
            outer_pts.reverse()

        valid_holes: List[List[Vec3]] = []
        for h in hole_loops:
            if len(h) >= 3:
                h_copy = list(h)
                h_area = sum((h_copy[i].cross(h_copy[(i + 1) % len(h_copy)])).dot(normal) for i in range(len(h_copy)))
                if h_area < 0:
                    h_copy.reverse()
                valid_holes.append(h_copy)

        h_dist = float(height)
        if direction is not None and isinstance(direction, Vec3) and direction.length() > 1e-6:
            ext_vec = direction.normalized() * h_dist
        else:
            if abs(normal.z) > 0.8:
                ext_vec = Vec3(0, 0, h_dist)
            else:
                ext_vec = normal * h_dist

        solid_verts: List[Tuple[float, float, float]] = []
        solid_faces: List[List[int]] = []
        solid_edges: List[Tuple[int, int]] = []

        base_outer_bot = 0
        for p in outer_pts:
            solid_verts.append((p.x, p.y, p.z))

        base_outer_top = len(solid_verts)
        for p in outer_pts:
            top_p = p + ext_vec
            solid_verts.append((top_p.x, top_p.y, top_p.z))

        # Outer walls (CCW outward)
        for i in range(n_out):
            nxt = (i + 1) % n_out
            v0 = base_outer_bot + i
            v1 = base_outer_bot + nxt
            v2 = base_outer_top + nxt
            v3 = base_outer_top + i
            solid_faces.append([v0, v1, v2, v3])
            solid_edges.append((v0, v1))
            solid_edges.append((v3, v2))
            solid_edges.append((v0, v3))

        # Hole walls (oriented inward to hole)
        hole_bases = []
        for h in valid_holes:
            nh = len(h)
            h_bot_base = len(solid_verts)
            for p in h:
                solid_verts.append((p.x, p.y, p.z))
            h_top_base = len(solid_verts)
            for p in h:
                top_p = p + ext_vec
                solid_verts.append((top_p.x, top_p.y, top_p.z))
            hole_bases.append((h_bot_base, h_top_base, nh))

            for j in range(nh):
                nxt = (j + 1) % nh
                v0 = h_bot_base + nxt
                v1 = h_bot_base + j
                v2 = h_top_base + j
                v3 = h_top_base + nxt
                solid_faces.append([v0, v1, v2, v3])
                solid_edges.append((h_bot_base + j, h_bot_base + nxt))
                solid_edges.append((h_top_base + j, h_top_base + nxt))
                solid_edges.append((h_bot_base + j, h_top_base + j))

        # Cap ends
        solid_holed_faces: List[Tuple[List[int], List[List[int]]]] = []
        if cap:
            if not valid_holes:
                solid_faces.append(list(reversed(range(base_outer_bot, base_outer_bot + n_out))))
                solid_faces.append(list(range(base_outer_top, base_outer_top + n_out)))
            else:
                # Clean SketchUp-style B-Rep caps with holes: NO internal diagonal wire edges!
                bot_outer = list(reversed(range(base_outer_bot, base_outer_bot + n_out)))
                bot_holes = [list(reversed(range(h_bot, h_bot + nh))) for (h_bot, h_top, nh) in hole_bases]
                top_outer = list(range(base_outer_top, base_outer_top + n_out))
                top_holes = [list(range(h_top, h_top + nh)) for (h_bot, h_top, nh) in hole_bases]
                solid_holed_faces.append((bot_outer, bot_holes))
                solid_holed_faces.append((top_outer, top_holes))

                # Continuous boundary loop face representation (1 bottom face + 1 top face)
                if len(hole_bases) == 1:
                    h_bot, h_top, nh = hole_bases[0]
                    # Bot slit loop
                    bot_slit = bot_outer + [bot_outer[0], bot_holes[0][0]] + list(reversed(bot_holes[0])) + [bot_holes[0][0], bot_outer[0]]
                    solid_faces.append(bot_slit)
                    # Top slit loop
                    top_slit = top_outer + [top_outer[0], top_holes[0][0]] + list(reversed(top_holes[0])) + [top_holes[0][0], top_outer[0]]
                    solid_faces.append(top_slit)
                else:
                    # Multi-hole fallback
                    for (h_bot, h_top, nh) in hole_bases:
                        pass
                    solid_faces.append(bot_outer)
                    solid_faces.append(top_outer)

        return MeshData(
            vertices=solid_verts,
            faces=solid_faces,
            edges=solid_edges,
            name=name,
            material_name="Extrusion",
            color=(0.75, 0.78, 0.82),
            holed_faces=solid_holed_faces,
        )


    @staticmethod
    def create_from_points(
        pts: List[Any],
        u_count: int = 10,
        v_count: int = 0,
        closed_u: bool = False,
        closed_v: bool = False,
        swap_uv: bool = False,
        triangulate: bool = False,
        flip_normals: bool = False,
        name: str = "MeshFromPoints",
    ) -> MeshData:
        """Constructs a 3D quad or triangulated mesh surface from a structured grid of points."""
        flat_pts: List[Tuple[float, float, float]] = []
        u_override: Optional[int] = None
        v_override: Optional[int] = None

        if pts and isinstance(pts, (list, tuple)) and len(pts) > 0 and isinstance(pts[0], (list, tuple)):
            if len(pts[0]) > 0 and (isinstance(pts[0][0], (Vec3, tuple, list)) or (hasattr(pts[0][0], "x") and hasattr(pts[0][0], "y"))):
                v_override = len(pts)     # Number of rows (V)
                u_override = len(pts[0])  # Number of columns (U)
                for row in pts:
                    for p in row:
                        if isinstance(p, Vec3):
                            flat_pts.append((p.x, p.y, p.z))
                        elif isinstance(p, (tuple, list)) and len(p) >= 3:
                            flat_pts.append((float(p[0]), float(p[1]), float(p[2])))
                        elif hasattr(p, "x") and hasattr(p, "y") and hasattr(p, "z"):
                            flat_pts.append((float(p.x), float(p.y), float(p.z)))

        if not flat_pts:
            for p in pts:
                if isinstance(p, Vec3):
                    flat_pts.append((p.x, p.y, p.z))
                elif isinstance(p, (tuple, list)) and len(p) >= 3:
                    flat_pts.append((float(p[0]), float(p[1]), float(p[2])))
                elif hasattr(p, "x") and hasattr(p, "y") and hasattr(p, "z"):
                    flat_pts.append((float(p.x), float(p.y), float(p.z)))

        total = len(flat_pts)
        if total < 4:
            return MeshData(name=name)

        final_u = u_override if u_override is not None else max(2, int(u_count))
        final_v = v_override if v_override is not None else int(v_count)
        if final_v <= 0:
            final_v = max(2, total // final_u)

        if total < final_u * final_v:
            return MeshData(name=name)

        # Standard row-major indexing: row is v (0 to final_v-1), col is u (0 to final_u-1).
        # point (u, v) is at v * final_u + u
        def get_idx(u_idx: int, v_idx: int) -> int:
            if swap_uv:
                return u_idx * final_v + v_idx
            return v_idx * final_u + u_idx

        u_cells = final_u if closed_u else final_u - 1
        v_cells = final_v if closed_v else final_v - 1
        faces: List[List[int]] = []
        edges_set = set()

        def _add_edge(a: int, b: int) -> None:
            edges_set.add((min(a, b), max(a, b)))

        for u in range(u_cells):
            u_next = (u + 1) % final_u
            for v in range(v_cells):
                v_next = (v + 1) % final_v
                i00 = get_idx(u, v)
                i10 = get_idx(u_next, v)
                i11 = get_idx(u_next, v_next)
                i01 = get_idx(u, v_next)

                if triangulate:
                    if flip_normals:
                        faces.append([i00, i11, i10])
                        faces.append([i00, i01, i11])
                    else:
                        faces.append([i00, i10, i11])
                        faces.append([i00, i11, i01])
                    _add_edge(i00, i10)
                    _add_edge(i10, i11)
                    _add_edge(i11, i00)
                    _add_edge(i11, i01)
                    _add_edge(i01, i00)
                else:
                    if flip_normals:
                        faces.append([i00, i01, i11, i10])
                    else:
                        faces.append([i00, i10, i11, i01])
                    _add_edge(i00, i10)
                    _add_edge(i10, i11)
                    _add_edge(i11, i01)
                    _add_edge(i01, i00)

        return MeshData(
            vertices=flat_pts[:final_u * final_v],
            faces=faces,
            edges=list(edges_set),
            name=name,
        )


def coerce_value(val: Any, target: SocketType) -> Any:
    """Safely casts incoming socket values to the expected SocketType."""
    if val is None or target == SocketType.ANY:
        return val
    if isinstance(val, list):
        return [coerce_value(v, target) for v in val]
    try:
        if target == SocketType.FLOAT:
            return float(val)
        if target == SocketType.INT:
            return int(round(float(val)))
        if target == SocketType.BOOL:
            if isinstance(val, str):
                return val.strip().lower() in ("1", "true", "yes", "on")
            return bool(val)
        if target == SocketType.STRING:
            return str(val)
        if target == SocketType.VEC3:
            if isinstance(val, Vec3):
                return val
            if isinstance(val, bool):
                return Vec3(0.0, 0.0, 0.0)
            if isinstance(val, dict):
                if "origin" in val:
                    orig = val["origin"]
                    if isinstance(orig, Vec3):
                        return orig
                    if isinstance(orig, (tuple, list)) and len(orig) >= 3:
                        return Vec3(float(orig[0]), float(orig[1]), float(orig[2]))
                return Vec3(float(val.get("x", 0.0)), float(val.get("y", 0.0)), float(val.get("z", 0.0)))
            if isinstance(val, (tuple, list)) and len(val) >= 3:
                return Vec3(float(val[0]), float(val[1]), float(val[2]))
            if not isinstance(val, bool) and isinstance(val, (int, float)):
                return Vec3(float(val), float(val), float(val))
        if target == SocketType.CURVE:
            if isinstance(val, CurveData):
                return val
        if target == SocketType.MESH:
            if isinstance(val, MeshData):
                return val
    except (ValueError, TypeError):
        pass
    return val
