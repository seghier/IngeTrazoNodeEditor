# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene integration nodes for referencing IngeTrazo geometry, curves, faces, and viewports."""

from __future__ import annotations
import math
from typing import Any, Dict, List, Optional, Tuple

try:
    from ..core_types import CurveData, MeshData, SocketType, Vec3
    from ..node_base import BaseNode, InputSpec, OutputSpec, register_node, NODE_REGISTRY
except (ImportError, ValueError):
    from core_types import CurveData, MeshData, SocketType, Vec3
    from node_base import BaseNode, InputSpec, OutputSpec, register_node, NODE_REGISTRY


@register_node
class ReferenceFaceNode(BaseNode):
    type_id = "scene.reference_face"
    title = "Reference Face"
    category = "Scene"
    description = (
        "Reference one or multiple faces/surfaces from the IngeTrazo 3D viewport into the node graph.\n"
        "Click '📌 Set Selected Face(s)' on the node card to store the currently selected face(s).\n"
        "Automatically extracts the outer perimeter and all courtyard/interior holes for each face.\n"
        "Live tracking automatically keeps faces in sync when moved or edited in the scene.\n"
        "The referenced faces are saved directly in the file (.itgraph) so they are remembered when reopening."
    )
    header_color = (94, 129, 172)

    inputs = [
        InputSpec("name", "Name", SocketType.STRING, default="Referenced_Face"),
        InputSpec("live_sync", "Live Tracking", SocketType.BOOL, default=True),
    ]
    outputs = [
        OutputSpec("surfaces", "Surfaces", SocketType.ANY),
        OutputSpec("surface", "Surface", SocketType.ANY),
        OutputSpec("meshes", "Face Meshes", SocketType.ANY),
        OutputSpec("mesh", "Combined Mesh", SocketType.MESH),
        OutputSpec("outers", "Outer Curves", SocketType.ANY),
        OutputSpec("outer", "Outer Boundary", SocketType.CURVE),
        OutputSpec("holes", "Courtyard Holes", SocketType.ANY),
        OutputSpec("points", "Points", SocketType.VEC3),
        OutputSpec("count", "Face Count", SocketType.INT),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._live_targets: Optional[List[Any]] = None
        self._app_ref: Any = None

    def get_action_buttons(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "btn_set_face",
                "label": "📌 Set Selected Face(s)",
                "tooltip": "Store currently selected face(s) from IngeTrazo 3D viewport",
                "color": "#2b5278",
                "action": "set_face",
            },
            {
                "id": "btn_sync_face",
                "label": "🔄 Update from Scene",
                "tooltip": "Re-read live positions of referenced face(s) from scene",
                "color": "#3b6e50",
                "action": "sync_face",
            },
            {
                "id": "btn_clear_face",
                "label": "❌ Clear Face(s)",
                "tooltip": "Clear stored face(s) back to default",
                "color": "#4c566a",
                "action": "clear_face",
            },
        ]

    def get_card_badge_text(self) -> Optional[str]:
        stored_faces = self.param_values.get("stored_faces")
        if not stored_faces:
            stored_single = self.param_values.get("stored_face")
            if stored_single and isinstance(stored_single, dict) and "outer" in stored_single:
                stored_faces = [stored_single]

        is_live = bool(getattr(self, "_live_targets", None))
        prefix = "🔗 Live" if is_live else "📌 Stored"

        if stored_faces:
            n_faces = len(stored_faces)
            if n_faces > 1:
                total_pts = sum(len(f.get("outer", [])) for f in stored_faces)
                return f"{prefix}: {n_faces} faces ({total_pts} pts)"
            n_outer = len(stored_faces[0].get("outer", []))
            n_holes = len(stored_faces[0].get("holes", []))
            if n_holes > 0:
                return f"{prefix}: {n_outer} pts ({n_holes} hole{'s' if n_holes > 1 else ''})"
            return f"{prefix}: {n_outer} pts"
        return "⚪ No face referenced"

    @staticmethod
    def _to_vec3(p: Any, xform: Optional[Any] = None) -> Optional[Vec3]:
        """Convert any IngeTrazo Vertex, QVector3D, or coordinate tuple to Vec3, applying optional xform."""
        if p is None:
            return None
        if hasattr(p, "position"):
            p = p.position
        if xform is not None and hasattr(xform, "map"):
            try:
                p = xform.map(p)
            except Exception:
                pass
        if isinstance(p, Vec3):
            return p
        if hasattr(p, "x"):
            x = float(p.x() if callable(p.x) else p.x)
            y = float(p.y() if callable(p.y) else p.y)
            z = float(p.z() if callable(p.z) else p.z)
            return Vec3(x, y, z)
        if isinstance(p, (list, tuple)) and len(p) >= 3:
            return Vec3(float(p[0]), float(p[1]), float(p[2]))
        return None

    @classmethod
    def _extract_face_loops(cls, f: Any, xform: Optional[Any] = None) -> Tuple[List[Vec3], List[List[Vec3]]]:
        """Extract outer vertices and holes from an IngeTrazo Face object, with optional transform mapping."""
        outer: List[Vec3] = []
        holes: List[List[Vec3]] = []

        raw_verts = getattr(f, "vertices", None)
        if raw_verts is None:
            raw_loop = getattr(f, "loop", None)
            raw_verts = [getattr(v, "position", v) for v in raw_loop] if raw_loop else []

        if raw_verts:
            for v in raw_verts:
                pt = cls._to_vec3(v, xform)
                if pt:
                    outer.append(pt)

        raw_holes = getattr(f, "holes", None) or getattr(f, "hole_loops", None) or []
        for h_ring in raw_holes:
            h_pts: List[Vec3] = []
            for hv in h_ring:
                pt = cls._to_vec3(hv, xform)
                if pt:
                    h_pts.append(pt)
            if len(h_pts) >= 3:
                holes.append(h_pts)

        return outer, holes

    def _extract_faces_from_targets(self, targets: List[Any], scene: Any = None) -> List[Tuple[List[Vec3], List[List[Vec3]]]]:
        collected_faces: List[Tuple[List[Vec3], List[List[Vec3]]]] = []
        for target in targets:
            item = target
            xform = None
            if isinstance(target, tuple) and len(target) == 2:
                item, grp = target
                xform = getattr(grp, "xform", None)
            else:
                xform = getattr(item, "xform", None)

            if hasattr(item, "vertices") or hasattr(item, "loop"):
                o, h = self._extract_face_loops(item, xform)
                if len(o) >= 3:
                    collected_faces.append((o, h))
            elif hasattr(item, "mesh") and hasattr(item.mesh, "faces"):
                for gf in item.mesh.faces:
                    o, h = self._extract_face_loops(gf, xform)
                    if len(o) >= 3:
                        collected_faces.append((o, h))
        return collected_faces

    def _update_from_targets(self, targets: List[Any], scene: Any = None) -> bool:
        collected_faces = self._extract_faces_from_targets(targets, scene)
        if not collected_faces:
            return False

        faces_data: List[Dict[str, Any]] = []
        for outer, holes in collected_faces:
            faces_data.append({
                "outer": [(p.x, p.y, p.z) for p in outer],
                "holes": [[(p.x, p.y, p.z) for p in h] for h in holes],
                "base_z": outer[0].z if outer else 0.0,
            })

        old_data = self.param_values.get("stored_faces")
        if old_data == faces_data:
            return False

        self.param_values["stored_faces"] = faces_data
        self.param_values["stored_face"] = faces_data[0]
        self.is_dirty = True
        return True

    def sync_from_scene(self, app: Any = None) -> bool:
        """Re-reads live coordinates from the referenced scene face(s). Returns True if changed."""
        targets = getattr(self, "_live_targets", None)
        if not targets:
            return False
        app = app or getattr(self, "_app_ref", None)
        if app is None:
            try:
                from PySide6.QtWidgets import QApplication
                qapp = QApplication.instance()
                app = getattr(qapp, "_extension_app_handle", None)
            except Exception:
                app = None
        viewport = getattr(app, "viewport", None) if app else None
        scene = getattr(viewport, "scene", None) or getattr(app, "scene", None) if app else None
        return self._update_from_targets(targets, scene)

    def reference_from_selection(self, app: Any = None) -> Tuple[str, bool]:
        """Extract all selected faces from the active IngeTrazo viewport and save into param_values."""
        if app is None:
            try:
                from PySide6.QtWidgets import QApplication
                qapp = QApplication.instance()
                app = getattr(qapp, "_extension_app_handle", None)
            except Exception:
                app = None

        if not app:
            return ("No IngeTrazo app handle available", False)

        viewport = getattr(app, "viewport", None)
        scene = getattr(viewport, "scene", None) or getattr(app, "scene", None)
        if not scene:
            return ("No active scene found", False)

        sel = getattr(scene, "selection", None) or getattr(viewport, "selection", None) or []
        selected_faces = getattr(scene, "selected_faces", None) or getattr(viewport, "selected_faces", None)
        if selected_faces:
            sel = list(sel) + list(selected_faces)

        if not sel:
            return ("Please select face(s) in IngeTrazo first!", False)

        collected_targets: List[Any] = []
        for item in sel:
            if hasattr(item, "vertices") or hasattr(item, "loop"):
                collected_targets.append(item)
            elif hasattr(item, "mesh") and hasattr(item.mesh, "faces"):
                for gf in item.mesh.faces:
                    collected_targets.append((gf, item))

        if not collected_targets:
            return ("Selected item has no planar faces", False)

        self._live_targets = collected_targets
        self._app_ref = app
        self._update_from_targets(collected_targets, scene)

        faces_data = self.param_values.get("stored_faces", [])
        if len(faces_data) > 1:
            total_pts = sum(len(f["outer"]) for f in faces_data)
            summary_txt = f"{len(faces_data)} faces ({total_pts} pts) [Live Linked]"
        else:
            outer = faces_data[0]["outer"]
            holes = faces_data[0]["holes"]
            summary_txt = f"{len(outer)} pts" + (f", {len(holes)} hole(s)" if holes else "") + " [Live Linked]"

        return (f"Saved: {summary_txt}", True)

    def clear_reference(self) -> None:
        """Clear stored referenced faces and live link."""
        self._live_targets = None
        if "stored_faces" in self.param_values:
            del self.param_values["stored_faces"]
        if "stored_face" in self.param_values:
            del self.param_values["stored_face"]
        self.is_dirty = True

    def compute(
        self,
        name: str = "Referenced_Face",
        live_sync: bool = True,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if live_sync and getattr(self, "_live_targets", None):
            self.sync_from_scene()

        stored_faces = self.param_values.get("stored_faces")
        if not stored_faces:
            s = self.param_values.get("stored_face")
            if s and isinstance(s, dict) and "outer" in s:
                stored_faces = [s]

        parsed_faces: List[Tuple[List[Vec3], List[List[Vec3]]]] = []
        if stored_faces:
            for f_dict in stored_faces:
                outer_pts = [Vec3(float(p[0]), float(p[1]), float(p[2])) for p in f_dict.get("outer", [])]
                holes_pts = []
                for h_ring in f_dict.get("holes", []):
                    holes_pts.append([Vec3(float(p[0]), float(p[1]), float(p[2])) for p in h_ring])
                if len(outer_pts) >= 3:
                    parsed_faces.append((outer_pts, holes_pts))

        # Sensible default if nothing referenced yet: 24x16m building with 8x6m courtyard hole
        if not parsed_faces:
            parsed_faces = [([
                Vec3(0.0, 0.0, 3.0),
                Vec3(24.0, 0.0, 3.0),
                Vec3(24.0, 16.0, 3.0),
                Vec3(0.0, 16.0, 3.0),
            ], [[
                Vec3(8.0, 5.0, 3.0),
                Vec3(16.0, 5.0, 3.0),
                Vec3(16.0, 11.0, 3.0),
                Vec3(8.0, 11.0, 3.0),
            ]])]

        surfaces: List[Dict[str, Any]] = []
        meshes: List[MeshData] = []
        outers: List[CurveData] = []
        all_holes: List[CurveData] = []
        all_points: List[Vec3] = []

        for idx, (outer_pts, holes_pts) in enumerate(parsed_faces):
            c_outer = CurveData(points=outer_pts, closed=True)
            outers.append(c_outer)
            all_points.extend(outer_pts)

            c_holes = [CurveData(points=h, closed=True) for h in holes_pts]
            all_holes.extend(c_holes)

            face_name = f"{name}_{idx + 1}" if len(parsed_faces) > 1 else (name or "ReferencedFace")
            f_mesh = c_outer.to_mesh_face(name=face_name)
            meshes.append(f_mesh)

            surfaces.append({
                "outer": [(p.x, p.y, p.z) for p in outer_pts],
                "holes": [[(p.x, p.y, p.z) for p in h] for h in holes_pts],
                "base_z": outer_pts[0].z if outer_pts else 0.0,
            })

        combined_mesh = MeshData.merge(meshes, name=name or "ReferencedFaces")
        primary_surface = surfaces[0] if surfaces else {}
        primary_outer = outers[0] if outers else CurveData()

        return {
            "surfaces": surfaces,
            "surface": primary_surface,
            "meshes": meshes,
            "mesh": combined_mesh,
            "outers": outers,
            "outer": primary_outer,
            "holes": all_holes,
            "points": all_points,
            "count": len(parsed_faces),
        }


# ============================================================================
# Select Curve Node (Scene Tab - Multi-Curve Selection)
# ============================================================================
@register_node
class SelectCurveNode(BaseNode):
    type_id = "scene.select_curve"
    title = "Select Curve"
    category = "Scene"
    description = (
        "Select or reference existing curve(s) or polylines from the IngeTrazo 3D viewport into the node graph.\n"
        "Supports selecting multiple curves at once.\n"
        "Click '📌 Set Selected Curve(s)' to store the active viewport selection.\n"
        "Live tracking automatically keeps curves in sync when moved or edited in the scene.\n"
        "Outputs referenced curves, ordered points, total curve length, and closed state."
    )
    header_color = (94, 129, 172)

    inputs = [
        InputSpec("name", "Name", SocketType.STRING, default="Referenced_Curves"),
        InputSpec("live_sync", "Live Tracking", SocketType.BOOL, default=True),
    ]
    outputs = [
        OutputSpec("curves", "Curves", SocketType.ANY),
        OutputSpec("curve", "Curve", SocketType.CURVE),
        OutputSpec("points", "Points", SocketType.VEC3),
        OutputSpec("length", "Length (m)", SocketType.FLOAT),
        OutputSpec("closed", "Is Closed", SocketType.BOOL),
        OutputSpec("count", "Curve Count", SocketType.INT),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._live_targets: Optional[List[Any]] = None
        self._app_ref: Any = None

    def get_action_buttons(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "btn_set_curve",
                "label": "📌 Set Selected Curve(s)",
                "tooltip": "Store currently selected curve(s) or edges from IngeTrazo 3D viewport",
                "color": "#2b5278",
                "action": "set_curve",
            },
            {
                "id": "btn_sync_curve",
                "label": "🔄 Update from Scene",
                "tooltip": "Re-read live positions of referenced curve(s) from scene",
                "color": "#3b6e50",
                "action": "sync_curve",
            },
            {
                "id": "btn_clear_curve",
                "label": "❌ Clear Curve(s)",
                "tooltip": "Clear stored curve(s) back to default",
                "color": "#4c566a",
                "action": "clear_curve",
            },
        ]

    def get_card_badge_text(self) -> Optional[str]:
        stored_list = self.param_values.get("stored_curves")
        if not stored_list:
            stored_single = self.param_values.get("stored_curve")
            if stored_single and isinstance(stored_single, dict) and "points" in stored_single:
                stored_list = [stored_single]

        is_live = bool(getattr(self, "_live_targets", None))
        prefix = "🔗 Live" if is_live else "📌 Stored"

        if stored_list:
            n_curves = len(stored_list)
            total_pts = sum(len(c.get("points", [])) for c in stored_list)
            if n_curves > 1:
                return f"{prefix}: {n_curves} curves ({total_pts} pts)"
            cls_txt = "Closed" if stored_list[0].get("closed", False) else "Open"
            return f"{prefix}: {total_pts} pts ({cls_txt})"
        return "⚪ No curve referenced"

    @staticmethod
    def _to_vec3(p: Any, xform: Optional[Any] = None) -> Optional[Vec3]:
        if p is None:
            return None
        if hasattr(p, "position"):
            p = p.position
        if xform is not None and hasattr(xform, "map"):
            try:
                p = xform.map(p)
            except Exception:
                pass
        if isinstance(p, Vec3):
            return p
        if hasattr(p, "x"):
            x = float(p.x() if callable(p.x) else p.x)
            y = float(p.y() if callable(p.y) else p.y)
            z = float(p.z() if callable(p.z) else p.z)
            return Vec3(x, y, z)
        if isinstance(p, (list, tuple)) and len(p) >= 3:
            return Vec3(float(p[0]), float(p[1]), float(p[2]))
        return None

    @classmethod
    def _chain_segments_into_curves(cls, segments: List[Tuple[Vec3, Vec3]]) -> List[CurveData]:
        """Chains unordered segments into connected continuous polylines/loops."""
        if not segments:
            return []

        def qkey(p: Vec3) -> Tuple[int, int, int]:
            return (round(p.x * 10000), round(p.y * 10000), round(p.z * 10000))

        key_to_pt: Dict[Tuple[int, int, int], Vec3] = {}
        adj: Dict[Tuple[int, int, int], List[Tuple[int, int, int]]] = {}
        edges_set = set()

        for p0, p1 in segments:
            if p0.distance_to(p1) < 1e-5:
                continue
            k0, k1 = qkey(p0), qkey(p1)
            if k0 == k1:
                continue
            edge_key = (min(k0, k1), max(k0, k1))
            if edge_key in edges_set:
                continue
            edges_set.add(edge_key)

            key_to_pt[k0] = p0
            key_to_pt[k1] = p1
            adj.setdefault(k0, []).append(k1)
            adj.setdefault(k1, []).append(k0)

        if not adj:
            return []

        visited_edges = set()
        curves: List[CurveData] = []

        # Find connected components
        visited_nodes = set()
        components: List[List[Tuple[int, int, int]]] = []
        for node in adj:
            if node not in visited_nodes:
                comp = []
                queue = [node]
                visited_nodes.add(node)
                while queue:
                    curr = queue.pop(0)
                    comp.append(curr)
                    for nbr in adj.get(curr, []):
                        if nbr not in visited_nodes:
                            visited_nodes.add(nbr)
                            queue.append(nbr)
                components.append(comp)

        for comp in components:
            endpoints = [k for k in comp if len(adj[k]) == 1]
            start_k = endpoints[0] if endpoints else comp[0]

            curr = start_k
            path = [curr]

            while True:
                nbrs = [n for n in adj[curr] if (min(curr, n), max(curr, n)) not in visited_edges]
                if not nbrs:
                    break
                next_k = nbrs[0]
                visited_edges.add((min(curr, next_k), max(curr, next_k)))
                path.append(next_k)
                curr = next_k
                if curr == start_k:
                    break

            pts = [key_to_pt[k] for k in path]
            if len(pts) >= 2:
                is_closed = (path[0] == path[-1]) or (pts[0].distance_to(pts[-1]) < 1e-4)
                if is_closed and len(pts) > 2 and (pts[0].distance_to(pts[-1]) < 1e-4):
                    pts = pts[:-1]
                curves.append(CurveData(points=pts, closed=is_closed))

        return curves

    def _extract_curves_from_items(self, targets: List[Any], scene: Any = None) -> List[CurveData]:
        raw_segments: List[Tuple[Vec3, Vec3]] = []
        collected_curves: List[CurveData] = []
        seen_curves = set()

        mesh = getattr(scene, "mesh", None) if scene else None

        for target in targets:
            group = None
            item = target
            if isinstance(target, tuple) and len(target) == 2:
                item, group = target

            xform = getattr(group, "xform", None) if group else getattr(item, "xform", None)

            # 1. Group object itself with edges
            if hasattr(item, "mesh") and hasattr(item.mesh, "edges") and not hasattr(item, "v0"):
                g_mesh = item.mesh
                g_xform = getattr(item, "xform", None)
                for ge in getattr(g_mesh, "edges", []):
                    p0 = self._to_vec3(ge.v0, g_xform)
                    p1 = self._to_vec3(ge.v1, g_xform)
                    if p0 and p1:
                        raw_segments.append((p0, p1))
                continue

            # 2. Whole Curve objects with points
            if hasattr(item, "points") and len(item.points) >= 2:
                pts = [self._to_vec3(p, xform) for p in item.points]
                pts = [p for p in pts if p is not None]
                if len(pts) >= 2:
                    cls_flag = bool(getattr(item, "closed", getattr(item, "is_closed", False)))
                    collected_curves.append(CurveData(points=pts, closed=cls_flag))
                    continue

            # 3. Edges with incident curve
            if hasattr(item, "v0") and hasattr(item, "v1"):
                c_parent = getattr(item, "curve", None)
                cur_mesh = getattr(group, "mesh", None) if group else mesh
                if c_parent is not None and cur_mesh and hasattr(cur_mesh, "curve_edges") and c_parent not in seen_curves:
                    seen_curves.add(c_parent)
                    try:
                        c_edges = cur_mesh.curve_edges(c_parent)
                        for ce in c_edges:
                            p0 = self._to_vec3(ce.v0, xform)
                            p1 = self._to_vec3(ce.v1, xform)
                            if p0 and p1:
                                raw_segments.append((p0, p1))
                        continue
                    except Exception:
                        pass

                p0 = self._to_vec3(item.v0, xform)
                p1 = self._to_vec3(item.v1, xform)
                if p0 and p1:
                    raw_segments.append((p0, p1))

            # 4. Face object (boundary)
            elif hasattr(item, "vertices") or hasattr(item, "loop"):
                raw_loop = getattr(item, "loop", None)
                if not raw_loop and hasattr(item, "vertices"):
                    raw_loop = item.vertices
                if raw_loop:
                    pts = [self._to_vec3(v, xform) for v in raw_loop]
                    pts = [p for p in pts if p is not None]
                    if len(pts) >= 3:
                        collected_curves.append(CurveData(points=pts, closed=True))

        if raw_segments:
            chained = self._chain_segments_into_curves(raw_segments)
            collected_curves.extend(chained)

        return collected_curves

    def _update_from_targets(self, targets: List[Any], scene: Any = None) -> bool:
        new_curves = self._extract_curves_from_items(targets, scene=scene)
        if not new_curves:
            return False

        stored_curves_data: List[Dict[str, Any]] = []
        for c in new_curves:
            stored_curves_data.append({
                "points": [(p.x, p.y, p.z) for p in c.points],
                "closed": bool(c.closed),
                "length": float(c.length()),
            })

        old_data = self.param_values.get("stored_curves")
        if old_data == stored_curves_data:
            return False

        self.param_values["stored_curves"] = stored_curves_data
        self.param_values["stored_curve"] = stored_curves_data[0]
        self.is_dirty = True
        return True

    def sync_from_scene(self, app: Any = None) -> bool:
        """Re-reads live coordinates from the referenced scene curve/edges. Returns True if changed."""
        targets = getattr(self, "_live_targets", None)
        if not targets:
            return False
        app = app or getattr(self, "_app_ref", None)
        if app is None:
            try:
                from PySide6.QtWidgets import QApplication
                qapp = QApplication.instance()
                app = getattr(qapp, "_extension_app_handle", None)
            except Exception:
                app = None
        viewport = getattr(app, "viewport", None) if app else None
        scene = getattr(viewport, "scene", None) or getattr(app, "scene", None) if app else None
        return self._update_from_targets(targets, scene)

    def reference_from_selection(self, app: Any = None) -> Tuple[str, bool]:
        """Extract all selected curves or edges from IngeTrazo viewport and store live references."""
        if app is None:
            try:
                from PySide6.QtWidgets import QApplication
                qapp = QApplication.instance()
                app = getattr(qapp, "_extension_app_handle", None)
            except Exception:
                app = None

        if not app:
            return ("No IngeTrazo app handle available", False)

        viewport = getattr(app, "viewport", None)
        scene = getattr(viewport, "scene", None) or getattr(app, "scene", None)
        if not scene:
            return ("No active scene found", False)

        sel = getattr(scene, "selection", None) or getattr(viewport, "selection", None) or []
        selected_edges = getattr(scene, "selected_edges", None) or getattr(viewport, "selected_edges", None)
        selected_curves = getattr(scene, "selected_curves", None) or getattr(viewport, "selected_curves", None)

        combined_sel = list(sel)
        for extra in (selected_edges, selected_curves):
            if extra:
                for x in extra:
                    if x not in combined_sel:
                        combined_sel.append(x)

        if not combined_sel:
            return ("Please select curve(s) or edges in IngeTrazo first!", False)

        collected_targets: List[Any] = []
        for item in combined_sel:
            if hasattr(item, "mesh") and hasattr(item.mesh, "edges") and not hasattr(item, "v0"):
                for ge in getattr(item.mesh, "edges", []):
                    collected_targets.append((ge, item))
            elif hasattr(item, "v0") and hasattr(item, "v1"):
                collected_targets.append(item)
            elif hasattr(item, "points"):
                collected_targets.append(item)
            elif hasattr(item, "loop") or hasattr(item, "vertices"):
                collected_targets.append(item)

        if not collected_targets:
            return ("No valid curve or edge geometry found in selection", False)

        self._live_targets = collected_targets
        self._app_ref = app

        ok = self._update_from_targets(collected_targets, scene)
        if not ok:
            return ("Could not extract valid curve geometry from selection", False)

        stored_curves_data = self.param_values.get("stored_curves", [])
        n_c = len(stored_curves_data)
        total_pts = sum(len(c["points"]) for c in stored_curves_data)
        if n_c > 1:
            summary_txt = f"{n_c} curves ({total_pts} pts) [Live Linked]"
        else:
            cls_txt = "Closed" if stored_curves_data[0]["closed"] else "Open"
            summary_txt = f"{total_pts} pts ({cls_txt}) [Live Linked]"

        return (f"Saved: {summary_txt}", True)

    def clear_reference(self) -> None:
        """Clear stored referenced curves and live references."""
        self._live_targets = None
        if "stored_curves" in self.param_values:
            del self.param_values["stored_curves"]
        if "stored_curve" in self.param_values:
            del self.param_values["stored_curve"]
        self.is_dirty = True

    def compute(
        self,
        name: str = "Referenced_Curves",
        live_sync: bool = True,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if live_sync and getattr(self, "_live_targets", None):
            self.sync_from_scene()

        stored_list = self.param_values.get("stored_curves")
        if not stored_list:
            stored_single = self.param_values.get("stored_curve")
            if stored_single and isinstance(stored_single, dict) and "points" in stored_single:
                stored_list = [stored_single]

        curves: List[CurveData] = []
        if stored_list:
            for item in stored_list:
                pts = [Vec3(float(p[0]), float(p[1]), float(p[2])) for p in item.get("points", [])]
                if len(pts) >= 2:
                    curves.append(CurveData(points=pts, closed=bool(item.get("closed", False))))

        if not curves:
            # Default fallback: 1 open S-curve
            curves = [
                CurveData(
                    points=[
                        Vec3(0.0, 0.0, 0.0),
                        Vec3(4.0, 2.0, 0.0),
                        Vec3(8.0, -1.0, 0.0),
                        Vec3(12.0, 1.0, 0.0),
                    ],
                    closed=False,
                )
            ]

        first_curve = curves[0]
        all_points: List[Vec3] = []
        total_length = 0.0
        for c in curves:
            all_points.extend(c.points)
            total_length += c.length()

        return {
            "curves": curves,
            "curve": first_curve,
            "points": all_points,
            "length": total_length,
            "closed": first_curve.closed,
            "count": len(curves),
        }


# Register backward compatibility alias for curve.select
NODE_REGISTRY["curve.select"] = SelectCurveNode


# ============================================================================
# Select Solid Node (Scene Tab - Multi-Solid / Group Selection)
# ============================================================================
@register_node
class SelectSolidNode(BaseNode):
    type_id = "scene.select_solid"
    title = "Select Solid"
    category = "Scene"
    description = (
        "Select or reference existing solid(s), groups, or meshes from the IngeTrazo 3D viewport into the node graph.\n"
        "Supports selecting multiple solids or groups at once.\n"
        "Click '📌 Set Selected Solid(s)' to store the active viewport selection.\n"
        "Live tracking automatically keeps geometry in sync when moved or edited in the scene.\n"
        "Outputs referenced solid MeshData, individual edges as curves, wireframe preview, and edge indices."
    )
    header_color = (94, 129, 172)

    inputs = [
        InputSpec("name", "Name", SocketType.STRING, default="Referenced_Solid"),
        InputSpec("live_sync", "Live Tracking", SocketType.BOOL, default=True),
    ]
    outputs = [
        OutputSpec("solid", "Solid", SocketType.MESH),
        OutputSpec("solids", "Solids", SocketType.ANY),
        OutputSpec("edges", "Edges", SocketType.ANY),
        OutputSpec("wireframe", "Wireframe", SocketType.MESH),
        OutputSpec("indices", "Edge Indices", SocketType.ANY),
        OutputSpec("edge_count", "Edge Count", SocketType.INT),
        OutputSpec("count", "Solid Count", SocketType.INT),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._live_targets: Optional[List[Any]] = None
        self._app_ref: Any = None

    def get_action_buttons(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "btn_set_solid",
                "label": "📌 Set Selected Solid(s)",
                "tooltip": "Store currently selected solid(s), group(s), or mesh(es) from IngeTrazo 3D viewport",
                "color": "#2b5278",
                "action": "set_solid",
            },
            {
                "id": "btn_sync_solid",
                "label": "🔄 Update from Scene",
                "tooltip": "Re-read live positions of referenced solid(s) from scene",
                "color": "#3b6e50",
                "action": "sync_solid",
            },
            {
                "id": "btn_clear_solid",
                "label": "❌ Clear Solid(s)",
                "tooltip": "Clear stored solid(s) back to default",
                "color": "#4c566a",
                "action": "clear_solid",
            },
        ]

    def get_card_badge_text(self) -> Optional[str]:
        stored_list = self.param_values.get("stored_solids")
        if not stored_list:
            stored_single = self.param_values.get("stored_solid")
            if stored_single and isinstance(stored_single, dict) and "vertices" in stored_single:
                stored_list = [stored_single]

        is_live = bool(getattr(self, "_live_targets", None))
        prefix = "🔗 Live" if is_live else "📌 Stored"

        if stored_list:
            n_solids = len(stored_list)
            total_edges = sum(len(s.get("edges", [])) for s in stored_list)
            total_verts = sum(len(s.get("vertices", [])) for s in stored_list)
            if n_solids > 1:
                return f"{prefix}: {n_solids} solids ({total_edges} edges)"
            return f"{prefix}: 1 solid ({total_edges} edges, {total_verts} verts)"
        return "⚪ No solid referenced"

    def _extract_meshdata_from_target(self, target: Any) -> Optional[MeshData]:
        item = target
        group = None
        if isinstance(target, tuple) and len(target) == 2:
            item, group = target

        # 1. Try world_mesh from core.solids for Group / ComponentInstance
        try:
            from core.solids import world_mesh
            if group is not None:
                native_m = world_mesh(group)
                if native_m:
                    return MeshData.from_native_mesh(native_m, name=getattr(group, "name", "Solid"))
            elif hasattr(item, "children") or hasattr(item, "prototype") or hasattr(item, "xform"):
                native_m = world_mesh(item)
                if native_m:
                    return MeshData.from_native_mesh(native_m, name=getattr(item, "name", "Solid"))
        except Exception:
            pass

        # 2. Extract from item.mesh with optional transform
        if hasattr(item, "mesh") and hasattr(item.mesh, "faces"):
            native_m = item.mesh
            xform = getattr(item, "xform", None) or (getattr(group, "xform", None) if group else None)
            md = MeshData.from_native_mesh(native_m, name=getattr(item, "name", "Solid"))
            if xform is not None and hasattr(xform, "map"):
                mapped_verts = []
                for vx, vy, vz in md.vertices:
                    try:
                        from PySide6.QtGui import QVector3D
                        pv = xform.map(QVector3D(vx, vy, vz))
                        mapped_verts.append((float(pv.x()), float(pv.y()), float(pv.z())))
                    except Exception:
                        mapped_verts.append((vx, vy, vz))
                md.vertices = mapped_verts
            return md

        # 3. Direct IngeTrazo Mesh object
        if hasattr(item, "faces") and hasattr(item, "edges"):
            return MeshData.from_native_mesh(item, name="Solid")

        # 4. Pure MeshData
        if isinstance(item, MeshData):
            return item.copy()

        return None

    def _update_from_targets(self, targets: List[Any], scene: Any = None) -> bool:
        collected: List[Dict[str, Any]] = []
        for t in targets:
            md = self._extract_meshdata_from_target(t)
            if md and md.vertices:
                collected.append({
                    "vertices": md.vertices,
                    "faces": md.faces,
                    "edges": md.edges,
                    "holed_faces": md.holed_faces,
                    "name": md.name,
                    "color": md.color,
                    "material_name": md.material_name,
                    "opacity": md.opacity,
                })

        if not collected:
            return False

        old_data = self.param_values.get("stored_solids")
        if old_data == collected:
            return False

        self.param_values["stored_solids"] = collected
        self.param_values["stored_solid"] = collected[0]
        self.is_dirty = True
        return True

    def sync_from_scene(self, app: Any = None) -> bool:
        """Re-reads live geometry from the referenced scene solid(s). Returns True if changed."""
        targets = getattr(self, "_live_targets", None)
        if not targets:
            return False
        app = app or getattr(self, "_app_ref", None)
        if app is None:
            try:
                from PySide6.QtWidgets import QApplication
                qapp = QApplication.instance()
                app = getattr(qapp, "_extension_app_handle", None)
            except Exception:
                app = None
        viewport = getattr(app, "viewport", None) if app else None
        scene = getattr(viewport, "scene", None) or getattr(app, "scene", None) if app else None
        return self._update_from_targets(targets, scene)

    def reference_from_selection(self, app: Any = None) -> Tuple[str, bool]:
        """Extract all selected solids/groups from the active IngeTrazo viewport and save into param_values."""
        if app is None:
            try:
                from PySide6.QtWidgets import QApplication
                qapp = QApplication.instance()
                app = getattr(qapp, "_extension_app_handle", None)
            except Exception:
                app = None

        if not app:
            return ("No IngeTrazo app handle available", False)

        viewport = getattr(app, "viewport", None)
        scene = getattr(viewport, "scene", None) or getattr(app, "scene", None)
        if not scene:
            return ("No active scene found", False)

        sel = getattr(scene, "selection", None) or getattr(viewport, "selection", None) or []
        if not sel:
            return ("Please select solid(s) or group(s) in IngeTrazo first!", False)

        collected_targets: List[Any] = []
        for item in sel:
            if hasattr(item, "mesh") or hasattr(item, "faces") or hasattr(item, "children"):
                collected_targets.append(item)
            elif isinstance(item, tuple) and len(item) == 2:
                collected_targets.append(item)

        if not collected_targets:
            return ("Selected item contains no 3D solids or meshes", False)

        self._live_targets = collected_targets
        self._app_ref = app
        ok = self._update_from_targets(collected_targets, scene)
        if not ok and "stored_solids" not in self.param_values:
            return ("Could not extract 3D mesh from selection", False)

        solids_data = self.param_values.get("stored_solids", [])
        n_s = len(solids_data)
        total_edges = sum(len(s.get("edges", [])) for s in solids_data)
        total_verts = sum(len(s.get("vertices", [])) for s in solids_data)
        if n_s > 1:
            summary_txt = f"{n_s} solids ({total_edges} edges) [Live Linked]"
        else:
            summary_txt = f"1 solid ({total_edges} edges, {total_verts} verts) [Live Linked]"

        return (f"Saved: {summary_txt}", True)

    def clear_reference(self) -> None:
        """Clear stored referenced solids and live link."""
        self._live_targets = None
        if "stored_solids" in self.param_values:
            del self.param_values["stored_solids"]
        if "stored_solid" in self.param_values:
            del self.param_values["stored_solid"]
        self.is_dirty = True

    def compute(
        self,
        name: str = "Referenced_Solid",
        live_sync: bool = True,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if live_sync and getattr(self, "_live_targets", None):
            self.sync_from_scene()

        stored_list = self.param_values.get("stored_solids")
        if not stored_list:
            stored_single = self.param_values.get("stored_solid")
            if stored_single and isinstance(stored_single, dict) and "vertices" in stored_single:
                stored_list = [stored_single]

        solids: List[MeshData] = []
        if stored_list:
            for s_dict in stored_list:
                md = MeshData(
                    vertices=[(float(v[0]), float(v[1]), float(v[2])) for v in s_dict.get("vertices", [])],
                    faces=[list(f) for f in s_dict.get("faces", [])],
                    edges=[(int(e[0]), int(e[1])) for e in s_dict.get("edges", [])],
                    holed_faces=s_dict.get("holed_faces", []),
                    name=s_dict.get("name", name or "ReferencedSolid"),
                    color=s_dict.get("color"),
                    material_name=s_dict.get("material_name", ""),
                    opacity=s_dict.get("opacity"),
                )
                if md.vertices:
                    solids.append(md)

        if not solids:
            box = MeshData.create_box(origin=Vec3(0, 0, 0), dx=2.0, dy=2.0, dz=1.5)
            box.name = name or "DefaultSolid"
            solids = [box]

        primary_solid = solids[0]
        edges_curves = primary_solid.extract_edges_as_curves()
        wireframe = primary_solid.extract_wireframe_mesh(name=f"{primary_solid.name}_Wireframe")
        indices = list(range(len(primary_solid.edges)))

        return {
            "solid": primary_solid,
            "solids": solids,
            "edges": edges_curves,
            "wireframe": wireframe,
            "indices": indices,
            "edge_count": len(primary_solid.edges),
            "count": len(solids),
        }


# Register backward compatibility aliases for select solid
NODE_REGISTRY["scene.select_solid"] = SelectSolidNode
NODE_REGISTRY["solid.select"] = SelectSolidNode
NODE_REGISTRY["solid.select_solid"] = SelectSolidNode


@register_node
class PreviewNode(BaseNode):
    type_id = "scene.preview"
    title = "Preview"
    category = "Scene Output"
    description = (
        "Clean, lightweight viewport visualizer.\n"
        "Connect any geometry (Mesh, Curve, Surface, Solids) to preview it immediately in the IngeTrazo 3D viewport.\n"
        "No BIM properties, no group names, no bake buttons: purely a visual geometry preview."
    )
    header_color = (22, 160, 133)  # Crisp Emerald / Teal

    inputs = [
        InputSpec("geometry", "Geometry", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("color", "Color", SocketType.ANY, default=(0.55, 0.78, 0.92)),
        InputSpec("opacity", "Opacity", SocketType.FLOAT, default=1.0, min_val=0.0, max_val=1.0, step=0.05),
        InputSpec("visible", "Visible", SocketType.BOOL, default=True),
    ]
    outputs = [
        OutputSpec("preview", "Preview", SocketType.MESH),
    ]

    def compute(
        self,
        geometry: Any = None,
        color: Any = (0.55, 0.78, 0.92),
        opacity: float = 1.0,
        visible: bool = True,
    ) -> Dict[str, Any]:
        if not visible or geometry is None:
            return {"preview": None}

        col_tuple = None
        if isinstance(color, (tuple, list)) and len(color) >= 3:
            col_tuple = (float(color[0]), float(color[1]), float(color[2]))

        op_float = float(opacity)

        if hasattr(geometry, "faces") or type(geometry).__name__ == "Brep":
            try:
                from brep_engine import BRepEngine
                if BRepEngine.is_available():
                    geometry = BRepEngine.brep_to_mesh_data(geometry, name="BRep_Preview")
            except Exception:
                pass
        elif hasattr(geometry, "parameter_range") or type(geometry).__name__ == "Curve":
            try:
                from brep_engine import BRepEngine
                if BRepEngine.is_available():
                    cd = BRepEngine.curve_to_curve_data(geometry)
                    if cd and cd.points:
                        geometry = cd.to_wire_mesh(name="BRep_Preview_Curve")
            except Exception:
                pass

        if isinstance(geometry, MeshData):
            m = geometry.copy()
            if col_tuple is not None:
                m.color = col_tuple
            m.opacity = op_float
            m.source_node_id = self.id
            return {"preview": m}
        elif isinstance(geometry, CurveData):
            m = geometry.to_wire_mesh(name="Preview_Curve")
            if col_tuple is not None:
                m.color = col_tuple
            m.opacity = op_float
            m.source_node_id = self.id
            return {"preview": m}
        elif isinstance(geometry, list):
            meshes = []
            for item in geometry:
                if isinstance(item, MeshData):
                    cm = item.copy()
                    if col_tuple is not None:
                        cm.color = col_tuple
                    cm.opacity = op_float
                    cm.source_node_id = self.id
                    meshes.append(cm)
                elif isinstance(item, CurveData):
                    cm = item.to_wire_mesh(name="Preview_Curve")
                    if col_tuple is not None:
                        cm.color = col_tuple
                    cm.opacity = op_float
                    cm.source_node_id = self.id
                    meshes.append(cm)
            if meshes:
                merged = MeshData.merge(meshes, name="Preview_Batch")
                merged.source_node_id = self.id
                return {"preview": merged}
        elif isinstance(geometry, dict) and ("outer" in geometry or "faces" in geometry):
            outer = geometry.get("outer", [])
            holes = geometry.get("holes", [])
            m = MeshData(
                outer=outer,
                holes=holes,
                name="Preview_Face",
                color=col_tuple or (0.55, 0.78, 0.92),
                opacity=op_float,
                source_node_id=self.id,
            )
            return {"preview": m}

        return {"preview": geometry}
