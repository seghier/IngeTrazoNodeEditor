# SPDX-License-Identifier: GPL-3.0-or-later
"""
Example Custom Node in a Separate File
=======================================
This file demonstrates how easy it is to create a new node in a separate file.
Any file placed inside the `nodes/` folder is automatically detected and registered
at startup (or when clicking 'Reload Nodes').

To create your own node:
1. Create a new `.py` file in `nodes/` (e.g. `nodes/my_tools.py`).
2. Subclass `NodeBase`.
3. That's it! It is detected automatically.
"""
from __future__ import annotations

import math
from typing import Optional, Dict, Any, List

# Core node and geometry imports
try:
    from ..engine import NodeBase, PortType
    from ..models import Point3D, FaceData, EdgeData, MeshData
except ImportError:
    from engine import NodeBase, PortType
    from models import Point3D, FaceData, EdgeData, MeshData


class StarPolygonNode(NodeBase):
    """
    Parametric 2D/3D star polygon with alternating outer and inner ray tips.
    Automatically detected by the node auto-discovery engine.
    """
    name = "Star Polygon"
    category = "Curve"
    description = (
        "Generate a 2D star polygon mesh with alternating inner and outer radii.\n"
        "Inputs:\n"
        "  - Center (Point): Center location (default 0,0,0)\n"
        "  - Points Count (Integer): Number of star points / rays (default 5)\n"
        "  - Outer Radius (Number): Distance to outer ray tips (default 10.0)\n"
        "  - Inner Radius (Number): Distance to inner valleys (default 4.0)\n"
        "Outputs:\n"
        "  - Mesh (Mesh): Ready-to-bake planar star mesh\n"
        "  - Points (Points): Ordered perimeter vertex points"
    )
    header_color = "#ebcb8b"  # Curve / Profile yellow

    def setup_ports(self) -> None:
        self.add_input("Center", PortType.POINT, Point3D(0.0, 0.0, 0.0), "Center location")
        self.add_input("Points Count", PortType.INTEGER, 5, "Number of star points")
        self.add_input("Outer Radius", PortType.NUMBER, 10.0, "Outer ray tip radius")
        self.add_input("Inner Radius", PortType.NUMBER, 4.0, "Inner valley radius")

        self.add_output("Mesh", PortType.MESH, "Generated planar star mesh")
        self.add_output("Points", PortType.ANY, "List of perimeter vertices")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        try:
            center_val = self.get_input("Center", Point3D(0.0, 0.0, 0.0))
            center = center_val if isinstance(center_val, Point3D) else Point3D(0.0, 0.0, 0.0)

            n_points = max(3, int(self.get_input("Points Count", 5)))
            r_outer = max(0.01, float(self.get_input("Outer Radius", 10.0)))
            r_inner = max(0.01, float(self.get_input("Inner Radius", 4.0)))

            total_vertices = n_points * 2
            verts: List[Point3D] = []

            for i in range(total_vertices):
                angle = (math.pi * i) / n_points
                r = r_outer if (i % 2 == 0) else r_inner
                x = center.x + r * math.cos(angle)
                y = center.y + r * math.sin(angle)
                z = center.z
                verts.append(Point3D(x, y, z))

            # Build edges for clean wireframe rendering
            edges: List[EdgeData] = []
            for i in range(total_vertices):
                nxt = (i + 1) % total_vertices
                edges.append(EdgeData(verts[i], verts[nxt], soft=False))

            face = FaceData(vertices=verts)
            mesh = MeshData(
                faces=[face],
                edges=edges,
                name=f"Star_{n_points}"
            )

            self.error = None
            self.set_output("Mesh", mesh)
            self.set_output("Points", verts)

        except Exception as ex:
            self.error = str(ex)
            self.set_output("Mesh", MeshData())
            self.set_output("Points", [])
