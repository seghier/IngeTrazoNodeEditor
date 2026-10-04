# SPDX-License-Identifier: GPL-3.0-or-later
"""Geometric data models and primitive generators for IngeTrazo Node Editor."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Any, Union


@dataclass
class Point3D:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def to_tuple(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)

    def to_list(self) -> List[float]:
        return [self.x, self.y, self.z]

    def __add__(self, other: Union[Point3D, Vector3D]) -> Point3D:
        return Point3D(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Union[Point3D, Vector3D]) -> Vector3D:
        return Vector3D(self.x - other.x, self.y - other.y, self.z - other.z)

    def distance_to(self, other: Point3D) -> float:
        dx = self.x - other.x
        dy = self.y - other.y
        dz = self.z - other.z
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def translated(self, v: Vector3D) -> Point3D:
        return Point3D(self.x + v.x, self.y + v.y, self.z + v.z)

    def rotated_z(self, angle_deg: float, origin: Optional[Point3D] = None) -> Point3D:
        ox = origin.x if origin else 0.0
        oy = origin.y if origin else 0.0
        rad = math.radians(angle_deg)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        dx = self.x - ox
        dy = self.y - oy
        rx = dx * cos_a - dy * sin_a + ox
        ry = dx * sin_a + dy * cos_a + oy
        return Point3D(rx, ry, self.z)

    def scaled(self, factor: float, origin: Optional[Point3D] = None) -> Point3D:
        ox = origin.x if origin else 0.0
        oy = origin.y if origin else 0.0
        oz = origin.z if origin else 0.0
        return Point3D(
            ox + (self.x - ox) * factor,
            oy + (self.y - oy) * factor,
            oz + (self.z - oz) * factor
        )


@dataclass
class Vector3D:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def length(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def normalized(self) -> Vector3D:
        l = self.length()
        if l < 1e-12:
            return Vector3D(0.0, 0.0, 0.0)
        return Vector3D(self.x / l, self.y / l, self.z / l)

    def __add__(self, other: Vector3D) -> Vector3D:
        return Vector3D(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vector3D) -> Vector3D:
        return Vector3D(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> Vector3D:
        return Vector3D(self.x * scalar, self.y * scalar, self.z * scalar)

    def __rmul__(self, scalar: float) -> Vector3D:
        return self.__mul__(scalar)

    def dot(self, other: Vector3D) -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: Vector3D) -> Vector3D:
        return Vector3D(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x
        )


@dataclass
class PolylineData:
    points: List[Point3D] = field(default_factory=list)
    closed: bool = False

    def length(self) -> float:
        if len(self.points) < 2:
            return 0.0
        total = sum(self.points[i].distance_to(self.points[i + 1]) for i in range(len(self.points) - 1))
        if self.closed and len(self.points) > 2:
            total += self.points[-1].distance_to(self.points[0])
        return total


@dataclass
class FaceData:
    vertices: List[Point3D] = field(default_factory=list)
    holes: List[List[Point3D]] = field(default_factory=list)
    color: Optional[Tuple[float, float, float]] = None
    material: Optional[str] = None
    layer: Optional[str] = None
    opacity: Optional[float] = None

    def normal(self) -> Vector3D:
        if len(self.vertices) < 3:
            return Vector3D(0.0, 0.0, 1.0)
        nx = ny = nz = 0.0
        for i in range(len(self.vertices)):
            cur = self.vertices[i]
            nxt = self.vertices[(i + 1) % len(self.vertices)]
            nx += (cur.y - nxt.y) * (cur.z + nxt.z)
            ny += (cur.z - nxt.z) * (cur.x + nxt.x)
            nz += (cur.x - nxt.x) * (cur.y + nxt.y)
        v = Vector3D(nx, ny, nz)
        return v.normalized()

    def reversed(self) -> FaceData:
        return FaceData(
            vertices=list(reversed(self.vertices)),
            holes=[list(reversed(h)) for h in self.holes],
            color=self.color,
            material=self.material,
            layer=self.layer,
            opacity=self.opacity
        )


@dataclass
class EdgeData:
    a: Point3D
    b: Point3D
    soft: bool = False
    hidden: bool = False
    layer: Optional[str] = None


@dataclass
class MeshData:
    faces: List[FaceData] = field(default_factory=list)
    edges: List[EdgeData] = field(default_factory=list)
    name: str = "ParametricMesh"
    layer: Optional[str] = None
    material: Optional[str] = None
    terrain_obj: Optional[Any] = None
    is_terrain: bool = False

    def merge(self, other: MeshData) -> MeshData:
        return MeshData(
            faces=self.faces + other.faces,
            edges=self.edges + other.edges,
            name=self.name,
            layer=self.layer or other.layer,
            material=self.material or other.material,
            terrain_obj=self.terrain_obj or other.terrain_obj,
            is_terrain=self.is_terrain or other.is_terrain
        )

    def translated(self, v: Vector3D) -> MeshData:
        new_faces = [
            FaceData(
                vertices=[pt.translated(v) for pt in f.vertices],
                holes=[[pt.translated(v) for pt in h] for h in f.holes],
                color=f.color,
                material=f.material,
                layer=f.layer,
                opacity=f.opacity
            ) for f in self.faces
        ]
        new_edges = [
            EdgeData(a=e.a.translated(v), b=e.b.translated(v), soft=e.soft, hidden=e.hidden, layer=e.layer)
            for e in self.edges
        ]
        return MeshData(
            faces=new_faces,
            edges=new_edges,
            name=self.name,
            layer=self.layer,
            material=self.material,
            terrain_obj=self.terrain_obj,
            is_terrain=self.is_terrain
        )

    def rotated_z(self, angle_deg: float, origin: Optional[Point3D] = None) -> MeshData:
        new_faces = [
            FaceData(
                vertices=[pt.rotated_z(angle_deg, origin) for pt in f.vertices],
                holes=[[pt.rotated_z(angle_deg, origin) for pt in h] for h in f.holes],
                color=f.color,
                material=f.material,
                layer=f.layer,
                opacity=f.opacity
            ) for f in self.faces
        ]
        new_edges = [
            EdgeData(a=e.a.rotated_z(angle_deg, origin), b=e.b.rotated_z(angle_deg, origin), soft=e.soft, hidden=e.hidden, layer=e.layer)
            for e in self.edges
        ]
        return MeshData(
            faces=new_faces,
            edges=new_edges,
            name=self.name,
            layer=self.layer,
            material=self.material,
            terrain_obj=self.terrain_obj,
            is_terrain=self.is_terrain
        )

    def scaled(self, factor: float, origin: Optional[Point3D] = None) -> MeshData:
        new_faces = [
            FaceData(
                vertices=[pt.scaled(factor, origin) for pt in f.vertices],
                holes=[[pt.scaled(factor, origin) for pt in h] for h in f.holes],
                color=f.color,
                material=f.material,
                layer=f.layer,
                opacity=f.opacity
            ) for f in self.faces
        ]
        new_edges = [
            EdgeData(a=e.a.scaled(factor, origin), b=e.b.scaled(factor, origin), soft=e.soft, hidden=e.hidden, layer=e.layer)
            for e in self.edges
        ]
        return MeshData(
            faces=new_faces,
            edges=new_edges,
            name=self.name,
            layer=self.layer,
            material=self.material,
            terrain_obj=self.terrain_obj,
            is_terrain=self.is_terrain
        )


# -------------------------------------------------------------------------------------
# Primitive Builders
# -------------------------------------------------------------------------------------

def create_box(center: Point3D, dx: float, dy: float, dz: float, centered: bool = True) -> MeshData:
    """Create a 6-sided solid rectangular cuboid."""
    if centered:
        x0, x1 = center.x - dx / 2, center.x + dx / 2
        y0, y1 = center.y - dy / 2, center.y + dy / 2
        z0, z1 = center.z - dz / 2, center.z + dz / 2
    else:
        x0, x1 = center.x, center.x + dx
        y0, y1 = center.y, center.y + dy
        z0, z1 = center.z, center.z + dz

    # 8 corners
    p000 = Point3D(x0, y0, z0)
    p100 = Point3D(x1, y0, z0)
    p110 = Point3D(x1, y1, z0)
    p010 = Point3D(x0, y1, z0)

    p001 = Point3D(x0, y0, z1)
    p101 = Point3D(x1, y0, z1)
    p111 = Point3D(x1, y1, z1)
    p011 = Point3D(x0, y1, z1)

    faces = [
        FaceData([p000, p010, p110, p100]),  # Bottom (normals down)
        FaceData([p001, p101, p111, p011]),  # Top (normals up)
        FaceData([p000, p100, p101, p001]),  # Front (-Y)
        FaceData([p100, p110, p111, p101]),  # Right (+X)
        FaceData([p110, p010, p011, p111]),  # Back (+Y)
        FaceData([p010, p000, p001, p011]),  # Left (-X)
    ]
    return MeshData(faces=faces, name="Box")


def create_cylinder(base: Point3D, radius: float, height: float, segments: int = 24) -> MeshData:
    """Create a 3D cylinder with top and bottom caps."""
    segments = max(3, int(segments))
    bottom_pts: List[Point3D] = []
    top_pts: List[Point3D] = []

    for i in range(segments):
        angle = 2.0 * math.pi * i / segments
        x = base.x + radius * math.cos(angle)
        y = base.y + radius * math.sin(angle)
        bottom_pts.append(Point3D(x, y, base.z))
        top_pts.append(Point3D(x, y, base.z + height))

    faces: List[FaceData] = []
    # Bottom face (reversed for downward normal)
    faces.append(FaceData(list(reversed(bottom_pts))))
    # Top face (upward normal)
    faces.append(FaceData(top_pts))

    # Side quad faces
    for i in range(segments):
        nxt = (i + 1) % segments
        b0 = bottom_pts[i]
        b1 = bottom_pts[nxt]
        t1 = top_pts[nxt]
        t0 = top_pts[i]
        faces.append(FaceData([b0, b1, t1, t0]))

    return MeshData(faces=faces, name="Cylinder")


def create_sphere(center: Point3D, radius: float, rings: int = 12, segments: int = 24) -> MeshData:
    """Create a UV sphere mesh."""
    rings = max(3, int(rings))
    segments = max(4, int(segments))

    grid: List[List[Point3D]] = []
    for r in range(rings + 1):
        theta = math.pi * r / rings
        z = center.z + radius * math.cos(theta)
        ring_r = radius * math.sin(theta)
        ring: List[Point3D] = []
        for s in range(segments):
            phi = 2.0 * math.pi * s / segments
            x = center.x + ring_r * math.cos(phi)
            y = center.y + ring_r * math.sin(phi)
            ring.append(Point3D(x, y, z))
        grid.append(ring)

    faces: List[FaceData] = []
    for r in range(rings):
        for s in range(segments):
            nxt_s = (s + 1) % segments
            p00 = grid[r][s]
            p01 = grid[r][nxt_s]
            p10 = grid[r + 1][s]
            p11 = grid[r + 1][nxt_s]

            if r == 0:
                # Top triangle
                faces.append(FaceData([p00, p10, p11]))
            elif r == rings - 1:
                # Bottom triangle
                faces.append(FaceData([p00, p10, p01]))
            else:
                # Quad
                faces.append(FaceData([p00, p10, p11, p01]))

    return MeshData(faces=faces, name="Sphere")


def extrude_profile(profile_points: List[Point3D], direction: Vector3D) -> MeshData:
    """Extrude a 2D closed polygon or polyline along a vector into a 3D solid."""
    if len(profile_points) < 3:
        return MeshData()

    bottom = profile_points
    top = [p.translated(direction) for p in bottom]

    faces: List[FaceData] = []
    # Bottom cap (reversed for outward normal)
    faces.append(FaceData(list(reversed(bottom))))
    # Top cap
    faces.append(FaceData(top))

    # Side walls
    n = len(bottom)
    for i in range(n):
        nxt = (i + 1) % n
        faces.append(FaceData([bottom[i], bottom[nxt], top[nxt], top[i]]))

    return MeshData(faces=faces, name="Extrusion")
