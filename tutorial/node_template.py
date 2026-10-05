# SPDX-License-Identifier: GPL-3.0-or-later
"""
IngeTrazo Node Editor - Node Authoring Templates
=================================================
This file provides ready-to-use boilerplate templates for creating new custom
nodes in IngeTrazo Node Editor.

To add a new node:
1. Copy one of the templates below.
2. Adjust the class name, `name`, `category`, `description`, and `header_color`.
3. Define your inputs and outputs in `setup_ports()`.
4. Implement your calculation logic in `compute()`.
5. Decorate the class with `@register_node` to automatically register it in the
   double-click search palette and top category menus.
"""
from __future__ import annotations

import math
from typing import Optional, Dict, Any, List, Union

# Import base node and port definitions (supports both relative package import and standalone file in nodes/)
try:
    from ..engine import NodeBase, PortType, Port
    from ..models import (
        Point3D, Vector3D, PolylineData, FaceData, EdgeData, MeshData,
        Domain, Domain2D,
        create_box, create_cylinder, create_sphere, extrude_profile
    )
    from ..nodes import register_node
except ImportError:
    try:
        from engine import NodeBase, PortType, Port
        from models import (
            Point3D, Vector3D, PolylineData, FaceData, EdgeData, MeshData,
            Domain, Domain2D,
            create_box, create_cylinder, create_sphere, extrude_profile
        )
        from nodes_library import register_node
    except ImportError:
        def register_node(cls): return cls


# =====================================================================================
# TEMPLATE 1: MINIMAL MATH / VALUE PROCESSOR NODE
# Use this pattern for calculations, number transformations, or string operations.
# =====================================================================================

@register_node
class SimpleMathTemplateNode(NodeBase):
    """
    Template for a simple mathematical or numeric transformation node.
    """
    name = "Custom Math (Template)"     # Name displayed in header and search
    category = "Math"                   # Category grouping in menus
    description = (
        "Calculates a custom formula: (A * B) + Offset.\n"
        "Inputs:\n"
        "  - A (Number): Primary operand\n"
        "  - B (Number): Secondary multiplier\n"
        "  - Offset (Number): Constant added to product\n"
        "Outputs:\n"
        "  - Result (Number): The evaluated result"
    )
    header_color = "#d08770"            # Nord theme accent color for Math

    def setup_ports(self) -> None:
        """Define input and output sockets."""
        # add_input(name, port_type, default_value, description)
        self.add_input("A", PortType.NUMBER, 1.0, "First number")
        self.add_input("B", PortType.NUMBER, 2.0, "Multiplier")
        self.add_input("Offset", PortType.NUMBER, 0.0, "Offset added to product")

        # add_output(name, port_type, description)
        self.add_output("Result", PortType.NUMBER, "Calculated output")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        """
        Execution logic. Called whenever an upstream node changes or an input updates.
        """
        # Retrieve input values with safe fallbacks
        try:
            a = float(self.get_input("A", 1.0))
            b = float(self.get_input("B", 2.0))
            offset = float(self.get_input("Offset", 0.0))

            # Perform computation
            result = (a * b) + offset

            # Clear any previous error and push to output port
            self.error = None
            self.set_output("Result", result)

        except Exception as ex:
            # Setting self.error marks the node with a red error badge on canvas
            self.error = str(ex)
            self.set_output("Result", 0.0)


# =====================================================================================
# TEMPLATE 2: GEOMETRY GENERATOR / MESH CREATOR NODE
# Use this pattern to create 3D points, curves, polylines, or 3D meshes.
# =====================================================================================

@register_node
class CustomGeometryTemplateNode(NodeBase):
    """
    Template for generating 3D geometric entities (e.g., regular polygon mesh).
    """
    name = "Regular Polygon Mesh (Template)"
    category = "Mesh"
    description = (
        "Creates a planar regular polygon mesh centered at a point.\n"
        "Inputs:\n"
        "  - Center (Point): Center location\n"
        "  - Radius (Number): Outer radius\n"
        "  - Sides (Integer): Number of vertices (min 3)\n"
        "Outputs:\n"
        "  - Mesh (Mesh): Resulting 2D polygon mesh\n"
        "  - Points (List[Point]): Ordered polygon vertices"
    )
    header_color = "#f28b25"            # Mesh orange accent color

    def setup_ports(self) -> None:
        self.add_input("Center", PortType.POINT, Point3D(0.0, 0.0, 0.0), "Center point")
        self.add_input("Radius", PortType.NUMBER, 5.0, "Outer radius")
        self.add_input("Sides", PortType.INTEGER, 6, "Number of polygon sides")

        self.add_output("Mesh", PortType.MESH, "Generated polygon mesh")
        self.add_output("Points", PortType.POINT, "List of perimeter vertices")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        try:
            center_val = self.get_input("Center", Point3D(0.0, 0.0, 0.0))
            if not isinstance(center_val, Point3D):
                center = Point3D(0.0, 0.0, 0.0)
            else:
                center = center_val

            radius = max(1e-4, float(self.get_input("Radius", 5.0)))
            sides = max(3, int(self.get_input("Sides", 6)))

            # Generate vertices along circle
            points: List[Point3D] = []
            for i in range(sides):
                angle = (2.0 * math.pi * i) / sides
                x = center.x + radius * math.cos(angle)
                y = center.y + radius * math.sin(angle)
                z = center.z
                points.append(Point3D(x, y, z))

            # Build edges for crisp wireframe visualization
            edges: List[EdgeData] = []
            for i in range(sides):
                nxt = (i + 1) % sides
                edges.append(EdgeData(points[i], points[nxt], soft=False))

            # Build single planar face from polygon points
            face = FaceData(vertices=points)

            # Assemble MeshData container
            mesh = MeshData(
                faces=[face],
                edges=edges,
                name=f"Polygon_{sides}gon"
            )

            self.error = None
            self.set_output("Mesh", mesh)
            self.set_output("Points", points)

        except Exception as ex:
            self.error = str(ex)
            self.set_output("Mesh", MeshData())
            self.set_output("Points", [])


# =====================================================================================
# TEMPLATE 3: LIST-AWARE POLYGLOT PROCESSOR NODE
# Handles both single items and lists seamlessly (Grasshopper-style list wrapping).
# =====================================================================================

@register_node
class ListAwareTemplateNode(NodeBase):
    """
    Template for nodes that process single values OR lists of values (polyglot input).
    """
    name = "Offset Points (Template)"
    category = "Transform"
    description = (
        "Translates a Point3D (or list of points) along the Z axis by an offset.\n"
        "Supports single points or lists of points."
    )
    header_color = "#88c0d0"            # Transform cyan accent color

    def setup_ports(self) -> None:
        self.add_input("Point", PortType.ANY, Point3D(0.0, 0.0, 0.0), "Point or list of points")
        self.add_input("Distance", PortType.ANY, 1.0, "Offset distance or list of offsets")
        self.add_output("Result", PortType.ANY, "Offset point or list of points")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        try:
            pt_in = self.get_input("Point", Point3D(0.0, 0.0, 0.0))
            dist_in = self.get_input("Distance", 1.0)

            # Check if any input is a list/tuple
            is_list = isinstance(pt_in, (list, tuple)) or isinstance(dist_in, (list, tuple))

            if not is_list:
                # SINGLE ITEM EXECUTION
                pt = pt_in if isinstance(pt_in, Point3D) else Point3D(0, 0, 0)
                dist = float(dist_in)
                new_pt = Point3D(pt.x, pt.y, pt.z + dist)

                self.error = None
                self.set_output("Result", new_pt)
            else:
                # LIST ZIP EXECUTION (repeating the shorter list, standard CAD behavior)
                pts = pt_in if isinstance(pt_in, (list, tuple)) else [pt_in]
                dists = dist_in if isinstance(dist_in, (list, tuple)) else [dist_in]

                count = max(len(pts), len(dists))
                results: List[Point3D] = []

                for i in range(count):
                    raw_p = pts[min(i, len(pts) - 1)]
                    raw_d = dists[min(i, len(dists) - 1)]

                    p = raw_p if isinstance(raw_p, Point3D) else Point3D(0, 0, 0)
                    d = float(raw_d)
                    results.append(Point3D(p.x, p.y, p.z + d))

                self.error = None
                self.set_output("Result", results)

        except Exception as ex:
            self.error = str(ex)
            self.set_output("Result", None)
