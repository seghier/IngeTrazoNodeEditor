# SPDX-License-Identifier: GPL-3.0-or-later
"""IngeTrazo Parametric Node Editor Extension Entry Point."""

from __future__ import annotations
import inspect
from pathlib import Path
import sys
from typing import Any, List, Optional

# Ensure package directory is on sys.path
_pkg_dir = str(Path(__file__).resolve().parent)
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)

# Import submodules flexibly
try:
    from . import core_types
    from . import node_base
    from . import engine
    from . import ui_canvas
    from . import nodes
    from . import i18n
except (ImportError, ValueError):
    import core_types
    import node_base
    import engine
    import ui_canvas
    import nodes
    import i18n

# Alias modules in sys.modules so all imports inside node files and UI match
sys.modules["core_types"] = core_types
sys.modules["node_base"] = node_base
sys.modules["engine"] = engine
sys.modules["ui_canvas"] = ui_canvas
sys.modules["nodes"] = nodes
sys.modules["i18n"] = i18n

_pkg_name = __name__
if _pkg_name:
    sys.modules[f"{_pkg_name}.core_types"] = core_types
    sys.modules[f"{_pkg_name}.node_base"] = node_base
    sys.modules[f"{_pkg_name}.engine"] = engine
    sys.modules[f"{_pkg_name}.ui_canvas"] = ui_canvas
    sys.modules[f"{_pkg_name}.nodes"] = nodes
    sys.modules[f"{_pkg_name}.i18n"] = i18n

from PySide6.QtCore import Qt
from PySide6.QtGui import QVector3D
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)

try:
    from .core_types import MeshData, Vec3
    from .engine import GraphEngine
    from .nodes import discover_nodes
    from .ui_canvas import NodeEditorWidget
except (ImportError, ValueError):
    from core_types import MeshData, Vec3
    from engine import GraphEngine
    from nodes import discover_nodes
    from ui_canvas import NodeEditorWidget

# Immediately discover all node types on module load
try:
    discover_nodes(reload_modules=False)
except Exception:
    pass

PLUGIN = {
    "name": "IngeTrazo Parametric Node Editor",
    "version": "1.7.7",
    "author": "seghier",
    "description": "Visual parametric node editor with Blender-style sliders, live viewport sync, and BIM tagging.",
}

_ACTIVE_APP: Optional[Any] = None
PREVIEW_TAG = "_ingetrazo_node_preview"


def is_preview_group(g: Any) -> bool:
    """Returns True if the group is tagged as an ephemeral Node Editor preview."""
    ext = getattr(g, "ext", None)
    return isinstance(ext, dict) and bool(ext.get(PREVIEW_TAG))


def _soften_and_apply_cad_edges(target_mesh: Any, mesh_data: MeshData) -> None:
    """
    Rhino-parity edge filter for 3D Viewport rendering:
    Softens internal triangulation facets between faces with small dihedral angle (< 32 deg) or coplanar facets,
    hiding triangle diagonal wires so curved surfaces (spheres, cylinders, fillets) read smooth like CAD B-Reps.
    Preserves true CAD boundary wires and crease edges as crisp hard lines.
    """
    if not hasattr(target_mesh, "edges") or not target_mesh.edges:
        return

    from PySide6.QtGui import QVector3D

    # 1. Soften internal facet edges if mesh_data is smooth (standard for B-Rep / CAD solids)
    if getattr(mesh_data, "smooth", False):
        try:
            if mesh_data.edges:
                # When explicit CAD boundary curves are provided, soften all face triangulation edges
                for e in target_mesh.edges:
                    e.soft = True
            else:
                # Dihedral normal threshold (< 32 deg) for facet softening
                fn_map = {id(f): f.normal().normalized() for f in target_mesh.faces}
                for e in target_mesh.edges:
                    fs = getattr(e, "faces", ())
                    if len(fs) == 2:
                        n0 = fn_map.get(id(fs[0]))
                        n1 = fn_map.get(id(fs[1]))
                        if n0 is not None and n1 is not None and QVector3D.dotProduct(n0, n1) > 0.85:
                            e.soft = True
                    elif len(fs) > 2:
                        e.soft = True
        except Exception:
            pass

    # 2. If show_wires is explicitly False, soften/hide ALL edges for seamless shaded view
    if not getattr(mesh_data, "show_wires", True):
        for e in target_mesh.edges:
            e.soft = True
    elif getattr(mesh_data, "edges", None):
        # 3. Ensure explicit CAD boundary wires remain crisp hard edges
        qvecs = [QVector3D(float(x), float(y), float(z)) for x, y, z in mesh_data.vertices]
        for i0, i1 in mesh_data.edges:
            if 0 <= i0 < len(qvecs) and 0 <= i1 < len(qvecs):
                try:
                    ed = target_mesh.add_edge(qvecs[i0], qvecs[i1])
                    if ed is not None:
                        ed.soft = False
                except Exception:
                    pass


def _populate_ingetrazo_mesh(target_mesh: Any, mesh_data: MeshData, scene: Optional[Any] = None) -> None:
    """
    Writes a watertight `MeshData` into an IngeTrazo `core.mesh.Mesh` instance.
    Supports clean SketchUp-style B-Rep faces with holes (zero diagonal triangulation wires),
    high-speed `add_faces_bulk`, and per-face materials/colors.
    """
    qvecs: List[QVector3D] = [
        QVector3D(float(x), float(y), float(z))
        for (x, y, z) in mesh_data.vertices
    ]

    def _apply_face_attrs(face: Any, f_idx: int) -> None:
        if face is None or not hasattr(face, "attrs") or not isinstance(face.attrs, dict):
            return
        mat_name = (
            mesh_data.face_materials[f_idx]
            if f_idx < len(mesh_data.face_materials) and mesh_data.face_materials[f_idx]
            else mesh_data.material_name
        )
        col = (
            mesh_data.face_colors[f_idx]
            if f_idx < len(mesh_data.face_colors) and mesh_data.face_colors[f_idx] is not None
            else mesh_data.color
        )
        op = (
            mesh_data.face_opacities[f_idx]
            if f_idx < len(mesh_data.face_opacities) and mesh_data.face_opacities[f_idx] is not None
            else mesh_data.opacity
        )
        if mat_name:
            face.attrs["mat"] = mat_name
        if col is not None:
            face.attrs["color"] = tuple(col)
        if op is not None:
            face.attrs["opacity"] = float(op)

        if scene is not None and hasattr(scene, "materials") and isinstance(scene.materials, dict):
            if mat_name and mat_name not in scene.materials:
                try:
                    from core.materials import Material
                    scene.materials[mat_name] = Material(
                        name=mat_name,
                        color=tuple(col) if col else None,
                        opacity=float(op) if op is not None else None,
                    )
                except Exception:
                    scene.materials[mat_name] = {
                        "name": mat_name,
                        "color": tuple(col) if col else None,
                        "opacity": float(op) if op is not None else None,
                    }

    # -------------------------------------------------------------------------
    # 0. Clean SketchUp-Style B-Rep Path (Native IngeTrazo Faces with Holes)
    # -------------------------------------------------------------------------
    if mesh_data.holed_faces:
        # First add side quads (regular polygon faces)
        for f_idx, face_indices in enumerate(mesh_data.faces):
            # Skip slit cap loops that are handled cleanly by holed_faces
            if any(len(face_indices) > 4 for _ in [0]):
                continue
            valid_qvecs = [qvecs[idx] for idx in face_indices if 0 <= idx < len(qvecs)]
            if len(valid_qvecs) >= 3:
                try:
                    face = target_mesh.add_face(valid_qvecs)
                    _apply_face_attrs(face, f_idx)
                except Exception:
                    pass

        # Add native cap faces with hole_loops (zero diagonal wire edges!)
        for h_f_idx, (outer_idx, hole_idx_list) in enumerate(mesh_data.holed_faces):
            outer_qvecs = [qvecs[i] for i in outer_idx if 0 <= i < len(qvecs)]
            holes_qvecs = [[qvecs[i] for i in h if 0 <= i < len(qvecs)] for h in hole_idx_list]
            if len(outer_qvecs) >= 3:
                try:
                    face = target_mesh.add_face(outer_qvecs, hole_loops=holes_qvecs if holes_qvecs else None)
                    _apply_face_attrs(face, len(mesh_data.faces) + h_f_idx)
                except Exception:
                    pass

        # Wire edges: only outer rim, inner rim, and wall edges (zero diagonal edges!)
        for i0, i1 in mesh_data.edges:
            if 0 <= i0 < len(qvecs) and 0 <= i1 < len(qvecs):
                try:
                    target_mesh.add_edge(qvecs[i0], qvecs[i1])
                except Exception:
                    pass
        return

    # Check 2D planar face with outer and holes (e.g. Offset Curve Frame)
    if mesh_data.outer and mesh_data.holes and len(mesh_data.faces) <= 1:
        outer_qvecs = [QVector3D(float(p[0]), float(p[1]), float(p[2])) for p in mesh_data.outer]
        holes_qvecs = [[QVector3D(float(p[0]), float(p[1]), float(p[2])) for p in h] for h in mesh_data.holes]
        if len(outer_qvecs) >= 3:
            try:
                face = target_mesh.add_face(outer_qvecs, hole_loops=holes_qvecs if holes_qvecs else None)
                _apply_face_attrs(face, 0)
            except Exception:
                pass
        for i0, i1 in mesh_data.edges:
            if 0 <= i0 < len(qvecs) and 0 <= i1 < len(qvecs):
                try:
                    target_mesh.add_edge(qvecs[i0], qvecs[i1])
                except Exception:
                    pass
        return
    # -------------------------------------------------------------------------
    # 1. High-Performance Bulk Bridge (Rust / ingetrazo_core / NumPy)
    # -------------------------------------------------------------------------
    if hasattr(target_mesh, "add_faces_bulk") and len(mesh_data.faces) > 8:
        try:
            import numpy as np
            v_arr = np.array(mesh_data.vertices, dtype=np.float32)
            corner_indices: List[int] = []
            ring_sizes: List[int] = []
            attrs_list: List[Optional[Dict[str, Any]]] = []
            valid_face_count = 0

            for f_idx, f in enumerate(mesh_data.faces):
                if len(f) >= 3 and all(0 <= idx < len(v_arr) for idx in f):
                    corner_indices.extend(f)
                    ring_sizes.append(len(f))
                    valid_face_count += 1

                    mat_name = (
                        mesh_data.face_materials[f_idx]
                        if f_idx < len(mesh_data.face_materials) and mesh_data.face_materials[f_idx]
                        else mesh_data.material_name
                    )
                    col = (
                        mesh_data.face_colors[f_idx]
                        if f_idx < len(mesh_data.face_colors) and mesh_data.face_colors[f_idx] is not None
                        else mesh_data.color
                    )
                    op = (
                        mesh_data.face_opacities[f_idx]
                        if f_idx < len(mesh_data.face_opacities) and mesh_data.face_opacities[f_idx] is not None
                        else mesh_data.opacity
                    )
                    f_attr: Dict[str, Any] = {}
                    if mat_name:
                        f_attr["mat"] = mat_name
                    if col is not None:
                        f_attr["color"] = tuple(col)
                    if op is not None:
                        f_attr["opacity"] = float(op)
                    attrs_list.append(f_attr if f_attr else None)

                    if scene is not None and hasattr(scene, "materials") and isinstance(scene.materials, dict):
                        if mat_name and mat_name not in scene.materials:
                            try:
                                from core.materials import Material
                                scene.materials[mat_name] = Material(
                                    name=mat_name,
                                    color=tuple(col) if col else None,
                                    opacity=float(op) if op is not None else None,
                                )
                            except Exception:
                                scene.materials[mat_name] = {
                                    "name": mat_name,
                                    "color": tuple(col) if col else None,
                                    "opacity": float(op) if op is not None else None,
                                }

            if valid_face_count > 0:
                pos = v_arr[corner_indices]
                r_sizes = np.array(ring_sizes, dtype=np.int64)
                f_counts = np.ones(valid_face_count, dtype=np.int64)
                target_mesh.add_faces_bulk(pos, r_sizes, f_counts, attrs=attrs_list)
                _soften_and_apply_cad_edges(target_mesh, mesh_data)
                return
        except Exception:
            pass  # Fall back to standard individual face loop

    # -------------------------------------------------------------------------
    # 2. Standard Shared-Vertex Fallback Loop
    # -------------------------------------------------------------------------
    qvecs: List[QVector3D] = [
        QVector3D(float(x), float(y), float(z))
        for (x, y, z) in mesh_data.vertices
    ]

    for f_idx, face_indices in enumerate(mesh_data.faces):
        valid_qvecs = [qvecs[idx] for idx in face_indices if 0 <= idx < len(qvecs)]
        if len(valid_qvecs) >= 3:
            try:
                face = target_mesh.add_face(valid_qvecs)
                if face is not None and hasattr(face, "attrs") and isinstance(face.attrs, dict):
                    mat_name = (
                        mesh_data.face_materials[f_idx]
                        if f_idx < len(mesh_data.face_materials) and mesh_data.face_materials[f_idx]
                        else mesh_data.material_name
                    )
                    col = (
                        mesh_data.face_colors[f_idx]
                        if f_idx < len(mesh_data.face_colors) and mesh_data.face_colors[f_idx] is not None
                        else mesh_data.color
                    )
                    op = (
                        mesh_data.face_opacities[f_idx]
                        if f_idx < len(mesh_data.face_opacities) and mesh_data.face_opacities[f_idx] is not None
                        else mesh_data.opacity
                    )
                    if mat_name:
                        face.attrs["mat"] = mat_name
                    if col is not None:
                        face.attrs["color"] = tuple(col)
                    if op is not None:
                        face.attrs["opacity"] = float(op)

                    if scene is not None and hasattr(scene, "materials") and isinstance(scene.materials, dict):
                        if mat_name and mat_name not in scene.materials:
                            try:
                                from core.materials import Material
                                mat_obj = Material(
                                    name=mat_name,
                                    color=tuple(col) if col else None,
                                    opacity=float(op) if op is not None else None,
                                )
                            except Exception:
                                mat_obj = {
                                    "name": mat_name,
                                    "color": tuple(col) if col else None,
                                    "opacity": float(op) if op is not None else None,
                                }
                            scene.materials[mat_name] = mat_obj
            except Exception:
                pass

    for i0, i1 in mesh_data.edges:
        if 0 <= i0 < len(qvecs) and 0 <= i1 < len(qvecs):
            try:
                target_mesh.add_edge(qvecs[i0], qvecs[i1])
            except Exception:
                pass

    _soften_and_apply_cad_edges(target_mesh, mesh_data)


def _make_ingetrazo_group(mesh_data: MeshData, graph_dict: dict, is_preview: bool = False, scene: Optional[Any] = None) -> Any:
    """Creates a native IngeTrazo `Group` from `MeshData`, preserving BIM tags and `group.ext`."""
    from core.mesh import Mesh
    try:
        from core.group import Group
    except ImportError:
        from core.scene import Group

    m = Mesh()
    _populate_ingetrazo_mesh(m, mesh_data, scene=scene)

    name_str = mesh_data.name or "Parametric_Solid"

    grp = None
    for kwargs in (
        {"mesh": m, "name": name_str},
        {"name": name_str, "mesh": m},
    ):
        try:
            grp = Group(**kwargs)
            break
        except TypeError:
            continue

    if grp is None:
        try:
            grp = Group(m, name_str)
        except TypeError:
            try:
                grp = Group(name_str)
                grp.mesh = m
            except TypeError:
                grp = Group()
                grp.name = name_str
                grp.mesh = m

    # Set container material (used by IngeTrazo viewport and effective_material)
    grp_mat = {}
    if mesh_data.material_name:
        grp_mat["mat"] = mesh_data.material_name
    if mesh_data.color is not None:
        grp_mat["color"] = [float(c) for c in mesh_data.color]
    if mesh_data.opacity is not None:
        grp_mat["opacity"] = float(mesh_data.opacity)
    if grp_mat:
        grp.material = grp_mat

    # Ensure mesh dirty flags are set for OpenGL chunk re-triangulation and shaders
    m._chunk_dirty = True
    m._attrs_dirty = True
    m._mut_serial = getattr(m, "_mut_serial", 0) + 1

    if mesh_data.ifc_class:
        grp.ifc = {"class": mesh_data.ifc_class, "name": name_str}
        if hasattr(grp, "ifc_class"):
            grp.ifc_class = mesh_data.ifc_class

    if not hasattr(grp, "ext") or not isinstance(grp.ext, dict):
        try:
            grp.ext = {}
        except Exception:
            pass

    if hasattr(grp, "ext") and isinstance(grp.ext, dict):
        if is_preview:
            grp.ext[PREVIEW_TAG] = True
            if getattr(mesh_data, "source_node_id", None):
                grp.ext["node_id"] = mesh_data.source_node_id
        else:
            grp.ext["node_graph"] = graph_dict

    for method_name in ("invalidate", "update_bounds", "rebuild_bounds"):
        fn = getattr(grp, method_name, None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass

    return grp


class IngeTrazoSceneBridge:
    """Bridges GraphEngine outputs into IngeTrazo's live Scene, Viewport, and History."""

    def __init__(self, app: Any, engine: GraphEngine) -> None:
        self.app = app
        self.engine = engine
        self.live_sync: bool = True
        self.last_error: Optional[str] = None
        self._is_internal_scene_bump: bool = False
        self._last_handled_version: Optional[int] = None
        self.on_scene_nodes_updated: Optional[Callable[[], None]] = None
        self.editor_widget: Optional[Any] = None
        self.is_panel_active_state: bool = True
        self._overlay_installed: bool = False
        self._preview_meshes: List[MeshData] = []
        self._preview_points: List[Vec3] = []
        self._selected_node_ids: set[str] = set()
        self.last_synced_doc_data: Optional[str] = None

        from PySide6.QtCore import QTimer
        self._doc_save_timer = QTimer()
        self._doc_save_timer.setSingleShot(True)
        self._doc_save_timer.setInterval(350)
        self._doc_save_timer.timeout.connect(self._commit_graph_to_doc_data)

        self.engine.on_evaluated = self._on_graph_evaluated
        self._setup_scene_listener()
        self.sanitize_scene_previews()

    def setup_overlay(self) -> None:
        """Registers the 3D preview overlay so previews draw over the viewport without touching scene.groups or files."""
        if self._overlay_installed:
            return
        if hasattr(self.app, "add_overlay"):
            try:
                self.app.add_overlay(self._draw_overlay)
                self._overlay_installed = True
            except Exception as ex:
                import logging
                logging.getLogger("ingetrazo.plugins").warning(f"Could not register viewport overlay: {ex}")

    def _draw_overlay(self, viewport: Any, painter: Any) -> None:
        """
        Draws live preview geometry (points, curves, wireframes, and shaded solids)
        directly onto the IngeTrazo viewport canvas without touching scene.groups.
        """
        if not self.live_sync or not self.is_editor_active():
            return
        if not self._preview_meshes and not self._preview_points:
            return

        try:
            from PySide6.QtCore import QLineF, QPointF, Qt
            from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF

            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            # 1. Collect all points to project in one batch
            pts_list = []
            mesh_offsets = []
            for m in self._preview_meshes:
                mesh_offsets.append(len(pts_list))
                pts_list.extend(m.vertices)

            pts_offset = len(pts_list)
            for p in self._preview_points:
                pts_list.append((p.x, p.y, p.z))

            if not pts_list:
                return

            if hasattr(self.app, "world_to_pixels"):
                px, py, ok = self.app.world_to_pixels(pts_list)
            elif hasattr(viewport, "world_to_pixels"):
                px, py, ok = viewport.world_to_pixels(pts_list)
            else:
                return

            # Camera position for depth-sorting
            cam = getattr(viewport, "camera", None)
            cam_eye = None
            if cam is not None and hasattr(cam, "eye"):
                try:
                    eye_pt = cam.eye()
                    cam_eye = (eye_pt.x(), eye_pt.y(), eye_pt.z())
                except Exception:
                    pass
            if cam_eye is None and cam is not None and hasattr(cam, "target"):
                cam_eye = (cam.target.x(), cam.target.y(), cam.target.z())
            if cam_eye is None:
                cam_eye = (0.0, 0.0, 0.0)

            # Sun/light vector for diffuse face shading
            lx, ly, lz = 0.38, -0.57, 0.72

            # 2. Draw Meshes
            for m_idx, m in enumerate(self._preview_meshes):
                offset = mesh_offsets[m_idx]
                is_selected = m.source_node_id in self._selected_node_ids if m.source_node_id else False

                if is_selected:
                    base_r, base_g, base_b = 1.0, 0.74, 0.18
                    alpha = 0.88
                    wire_color = QColor(255, 220, 60, 255)
                    wire_w = 2.0
                else:
                    if m.color is not None and len(m.color) >= 3:
                        base_r, base_g, base_b = float(m.color[0]), float(m.color[1]), float(m.color[2])
                    else:
                        base_r, base_g, base_b = 0.58, 0.65, 0.85
                    alpha = float(m.opacity) if m.opacity is not None else 0.85
                    wire_color = QColor.fromRgbF(
                        max(0.0, base_r - 0.28), max(0.0, base_g - 0.28), max(0.0, base_b - 0.28), 0.95
                    )
                    wire_w = 1.2

                # A. Faces (draw if present)
                if m.faces:
                    drawable_faces = []
                    for f in m.faces:
                        if len(f) < 3:
                            continue
                        global_indices = [offset + vi for vi in f]
                        if not all(ok[gi] for gi in global_indices):
                            continue

                        # Calculate face normal from first 3 vertices
                        v0 = pts_list[global_indices[0]]
                        v1 = pts_list[global_indices[1]]
                        v2 = pts_list[global_indices[2]]
                        e1x, e1y, e1z = v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2]
                        e2x, e2y, e2z = v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2]
                        nx = e1y * e2z - e1z * e2y
                        ny = e1z * e2x - e1x * e2z
                        nz = e1x * e2y - e1y * e2x
                        nlen = (nx * nx + ny * ny + nz * nz) ** 0.5
                        if nlen > 1e-8:
                            dot = (nx * lx + ny * ly + nz * lz) / nlen
                            shade = 0.42 + 0.58 * max(0.0, dot)
                        else:
                            shade = 0.72

                        face_col = QColor.fromRgbF(
                            min(1.0, base_r * shade),
                            min(1.0, base_g * shade),
                            min(1.0, base_b * shade),
                            alpha,
                        )
                        poly = QPolygonF([QPointF(float(px[gi]), float(py[gi])) for gi in global_indices])

                        # Distance from camera eye for back-to-front depth sorting
                        fc_x = sum(pts_list[gi][0] for gi in global_indices) / len(global_indices)
                        fc_y = sum(pts_list[gi][1] for gi in global_indices) / len(global_indices)
                        fc_z = sum(pts_list[gi][2] for gi in global_indices) / len(global_indices)
                        dist_sq = (fc_x - cam_eye[0]) ** 2 + (fc_y - cam_eye[1]) ** 2 + (fc_z - cam_eye[2]) ** 2
                        drawable_faces.append((dist_sq, poly, face_col))

                    # Sort back-to-front (painter's algorithm)
                    drawable_faces.sort(key=lambda item: item[0], reverse=True)
                    painter.setPen(Qt.PenStyle.NoPen)
                    for _, poly, col in drawable_faces:
                        painter.setBrush(col)
                        painter.drawPolygon(poly)

                # B. Edges / Wireframes
                if getattr(m, "show_wires", True) and m.edges:
                    painter.setPen(QPen(wire_color, wire_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                    lines = []
                    for i, j in m.edges:
                        gi, gj = offset + i, offset + j
                        if ok[gi] and ok[gj]:
                            lines.append(QLineF(float(px[gi]), float(py[gi]), float(px[gj]), float(py[gj])))
                    if lines:
                        painter.drawLines(lines)

            # 3. Draw Points
            if self._preview_points:
                pt_pen = QPen(QColor(86, 210, 255, 235), 2.0, Qt.PenStyle.SolidLine)
                painter.setPen(pt_pen)
                arm = 3.5
                pt_lines = []
                for k in range(len(self._preview_points)):
                    idx = pts_offset + k
                    if ok[idx]:
                        x, y = float(px[idx]), float(py[idx])
                        pt_lines.append(QLineF(x - arm, y, x + arm, y))
                        pt_lines.append(QLineF(x, y - arm, x, y + arm))
                if pt_lines:
                    painter.drawLines(pt_lines)

        except Exception as ex:
            import logging
            logging.getLogger("ingetrazo.plugins").debug(f"NodeEditor overlay draw error: {ex}")

    def _setup_scene_listener(self) -> None:
        """Connects viewport sceneVersionChanged signal and a fallback QTimer to detect external geometry moves."""
        vp = self.viewport
        if vp is not None and hasattr(vp, "sceneVersionChanged"):
            try:
                vp.sceneVersionChanged.connect(self._on_viewport_scene_changed)
            except Exception:
                pass

        try:
            from PySide6.QtCore import QTimer
            self._scene_poll_timer = QTimer()
            self._scene_poll_timer.setInterval(100)
            self._scene_poll_timer.timeout.connect(self._poll_scene_version)
            self._scene_poll_timer.start()
        except Exception:
            self._scene_poll_timer = None

    def _on_viewport_scene_changed(self, version: int = 0) -> None:
        if self._is_internal_scene_bump:
            return
        self._handle_external_scene_change()

    def _poll_scene_version(self) -> None:
        if self._is_internal_scene_bump:
            return
        sc = self.scene
        if sc is not None and hasattr(sc, "version"):
            curr_ver = sc.version
            if self._last_handled_version is None:
                self._last_handled_version = curr_ver
                return
            if curr_ver != self._last_handled_version:
                self._last_handled_version = curr_ver
                self._handle_external_scene_change()

    def _handle_external_scene_change(self) -> None:
        """When user moves/edits scene geometry, find any SelectCurveNode / ReferenceFaceNode and sync!"""
        if self._is_internal_scene_bump:
            return
        changed_any = False
        for node in list(self.engine.nodes.values()):
            if hasattr(node, "sync_from_scene"):
                try:
                    changed = node.sync_from_scene(self.app)
                    if changed:
                        self.engine.mark_dirty(node.id)
                        changed_any = True
                except Exception:
                    pass

        if changed_any:
            if callable(self.on_scene_nodes_updated):
                try:
                    self.on_scene_nodes_updated()
                except Exception:
                    pass
            self.engine.evaluate()

    def stop(self) -> None:
        if hasattr(self, "_scene_poll_timer") and self._scene_poll_timer is not None:
            try:
                self._scene_poll_timer.stop()
            except Exception:
                pass
        if hasattr(self, "_doc_save_timer") and self._doc_save_timer is not None:
            try:
                self._doc_save_timer.stop()
            except Exception:
                pass

    @property
    def scene(self) -> Any:
        sc = getattr(self.app, "scene", None)
        if sc is None and hasattr(self.app, "window"):
            sc = getattr(self.app.window, "scene", None)
        return sc

    @property
    def viewport(self) -> Any:
        vp = getattr(self.app, "viewport", None)
        if vp is None and hasattr(self.app, "window"):
            vp = getattr(self.app.window, "viewport", None)
        return vp

    def _bump_viewport(self) -> None:
        """Triggers a viewport redraw without touching private attributes."""
        vp = self.viewport
        if vp is not None:
            notify = getattr(vp, "notify_scene_changed", None)
            if callable(notify):
                try:
                    notify()
                except Exception:
                    pass
            update_fn = getattr(vp, "update", None)
            if callable(update_fn):
                try:
                    update_fn()
                except Exception:
                    pass

    def on_nodes_selected(self, selected_node_ids: List[str]) -> None:
        """Highlights the geometry of currently selected canvas node(s) in the overlay."""
        self._selected_node_ids = set(selected_node_ids)
        if self.viewport is not None and hasattr(self.viewport, "update"):
            self.viewport.update()

    def sanitize_scene_previews(self) -> None:
        """Removes any legacy preview groups loaded from older .igz files."""
        sc = self.scene
        if sc is not None and hasattr(sc, "groups"):
            sc.groups[:] = [g for g in sc.groups if not is_preview_group(g)]
        if self.viewport is not None and hasattr(self.viewport, "update"):
            self.viewport.update()

    def is_editor_active(self) -> bool:
        """Determines whether the Node Editor tab/window is currently active to the user."""
        ed = getattr(self, "editor_widget", None)
        if ed is not None and hasattr(ed, "is_panel_active"):
            try:
                return bool(ed.is_panel_active())
            except Exception:
                pass
        return getattr(self, "is_panel_active_state", True)

    def on_panel_visibility_changed(self, visible: bool) -> None:
        """Called whenever the Node Editor dock tab or floating window is shown or hidden."""
        self.is_panel_active_state = bool(visible)
        if not visible:
            self.clear_preview(refresh=True)
        else:
            if self.live_sync:
                self.engine.evaluate()

    def clear_preview(self, refresh: bool = True) -> None:
        """Removes transient live-preview overlays and any legacy preview groups."""
        self._preview_meshes.clear()
        self._preview_points.clear()
        sc = self.scene
        if sc is not None and hasattr(sc, "groups"):
            sc.groups[:] = [g for g in sc.groups if not is_preview_group(g)]
        if refresh and self.viewport is not None and hasattr(self.viewport, "update"):
            self.viewport.update()

    def set_live_sync(self, enabled: bool) -> None:
        self.live_sync = bool(enabled)
        if not self.live_sync:
            self.clear_preview(refresh=True)
        else:
            self.engine.evaluate()

    def _on_graph_evaluated(
        self,
        meshes: List[MeshData],
        points: List[Vec3],
        eval_ms: float,
    ) -> None:
        """Streams transient preview geometry into IngeTrazo's viewport overlay at 60 FPS."""
        self.last_error = None
        if not self.live_sync or not self.is_editor_active():
            self._preview_meshes.clear()
            self._preview_points.clear()
            if self.viewport is not None and hasattr(self.viewport, "update"):
                self.viewport.update()
            return

        self._preview_meshes = meshes
        self._preview_points = points
        if self.viewport is not None and hasattr(self.viewport, "update"):
            self.viewport.update()

    def notify_graph_changed(self) -> None:
        """Schedules debounced saving of the current graph to the document data."""
        if hasattr(self, "_doc_save_timer") and self._doc_save_timer is not None:
            self._doc_save_timer.start(350)

    def _commit_graph_to_doc_data(self) -> None:
        """Commits the current graph state into IngeTrazo's document data as one undo step."""
        if not hasattr(self.app, "set_document_data"):
            return
        graph_dict = self.engine.to_dict()
        try:
            import json
            graph_json = json.dumps(graph_dict, sort_keys=True)
            if graph_json != self.last_synced_doc_data:
                self.last_synced_doc_data = graph_json
                self.app.set_document_data(graph_dict)
        except Exception as ex:
            import logging
            logging.getLogger("ingetrazo.plugins").debug(f"Could not save graph to document data: {ex}")

    def restore_graph_from_document(self) -> bool:
        """Restores the node graph from document data if present."""
        saved = None
        if hasattr(self.app, "document_data"):
            try:
                saved = self.app.document_data(default=None)
            except TypeError:
                try:
                    saved = self.app.document_data()
                except Exception:
                    saved = None
            except Exception:
                saved = None
        if not saved:
            try:
                sc = self.scene
                pdata = getattr(sc, "plugin_data", {}) or {}
                saved = pdata.get("node_editor", None)
            except Exception:
                saved = None
        if saved and isinstance(saved, dict) and "nodes" in saved and saved["nodes"]:
            try:
                import json
                self.last_synced_doc_data = json.dumps(saved, sort_keys=True)
                self.engine.load_dict(saved)
                if self.editor_widget is not None and hasattr(self.editor_widget, "scene"):
                    self.editor_widget.scene.rebuild_from_engine()
                    if self.live_sync and self.editor_widget.isVisible():
                        self.editor_widget.schedule_eval()
                return True
            except Exception as ex:
                import logging
                logging.getLogger("ingetrazo.plugins").warning(f"Could not restore graph: {ex}")
        return False

    def on_document_changed(self) -> None:
        """
        Called when IngeTrazo's document changes (an edit, an undo, New, Open).
        Safely guards against overwriting unsaved graph changes on normal scene edits:
        only reloads when the document's stored graph data genuinely changed from the outside.
        """
        if not hasattr(self.app, "document_data"):
            return
        try:
            saved = self.app.document_data(default=None)
        except TypeError:
            try:
                saved = self.app.document_data()
            except Exception:
                saved = None
        except Exception:
            saved = None
        if not saved or not isinstance(saved, dict):
            return
        import json
        saved_json = json.dumps(saved, sort_keys=True)
        if saved_json == self.last_synced_doc_data:
            return  # Same graph: normal scene geometry edit, do NOT overwrite canvas
        self.last_synced_doc_data = saved_json
        try:
            self.engine.load_dict(saved)
            if self.editor_widget is not None and hasattr(self.editor_widget, "scene"):
                self.editor_widget.scene.rebuild_from_engine()
                if self.live_sync and self.editor_widget.isVisible():
                    self.editor_widget.schedule_eval()
        except Exception as ex:
            import logging
            logging.getLogger("ingetrazo.plugins").warning(f"Could not restore graph on document change: {ex}")

    def bake_to_scene(self, specific_node_id: Optional[str] = None) -> int:
        """
        Commits current node outputs as permanent, watertight IngeTrazo Groups.
        Supports both `SnapshotImport(callable)` and manual scene commit with Undo.
        """
        sc = self.scene
        if sc is None or not hasattr(sc, "groups"):
            return 0

        self.clear_preview(refresh=False)
        meshes = self.engine.collect_bake_outputs(specific_node_id=specific_node_id)
        valid_meshes = [m for m in meshes if m.vertices or m.edges]
        if not valid_meshes:
            self._bump_viewport()
            return 0

        graph_dict = self.engine.to_dict()
        baked_count = 0

        def _do_commit(target_scene: Any) -> None:
            nonlocal baked_count
            for mdata in valid_meshes:
                grp = _make_ingetrazo_group(mdata, graph_dict, is_preview=False, scene=target_scene)
                target_scene.groups.append(grp)
                baked_count += 1

        history = (
            getattr(self.viewport, "history", None)
            or getattr(self.app, "history", None)
            or getattr(sc, "history", None)
        )
        committed = False

        if history is not None:
            try:
                from core.history import SnapshotImport
                sig = inspect.signature(SnapshotImport.__init__)
                if len(sig.parameters) <= 2:
                    cmd = SnapshotImport(_do_commit)
                    if hasattr(history, "execute"):
                        history.execute(cmd)
                        committed = True
                    elif hasattr(history, "push"):
                        _do_commit(sc)
                        history.push(cmd)
                        committed = True
                else:
                    snap = SnapshotImport(sc, "Bake Parametric Node Graph")
                    _do_commit(sc)
                    if hasattr(snap, "finish"):
                        snap.finish()
                    if hasattr(history, "push"):
                        history.push(snap)
                    committed = True
            except Exception as exc:
                import logging
                logging.getLogger("ingetrazo.plugins").error(f"Bake history commit failed: {exc}", exc_info=True)
                committed = baked_count > 0

        if not committed:
            _do_commit(sc)

        self._bump_viewport()
        return baked_count

    def load_graph_from_selected_group(self) -> Optional[dict]:
        """Extracts embedded `group.ext["node_graph"]` from the selected Group in IngeTrazo."""
        sc = self.scene
        if sc is None:
            return None

        candidates: List[Any] = []
        for attr in ("selected_group", "active_group"):
            g = getattr(sc, attr, None)
            if g is not None:
                candidates.append(g)
        for attr in ("selected_groups", "selection"):
            sel = getattr(sc, attr, None)
            if isinstance(sel, (list, set, tuple)):
                candidates.extend(sel)

        if not candidates and hasattr(sc, "groups"):
            candidates = [g for g in sc.groups if getattr(g, "selected", False)]

        for grp in candidates:
            ext = getattr(grp, "ext", None)
            if isinstance(ext, dict) and "node_graph" in ext:
                return ext["node_graph"]
        return None


class NodeEditorDialog(QDialog):
    """Non-modal floating window hosting the Parametric Node Editor inside IngeTrazo."""

    def __init__(self, app: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent or getattr(app, "window", None))
        self.app = app
        self.setWindowTitle("IngeTrazo — Parametric Node Editor")
        self.resize(1060, 660)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        discover_nodes(reload_modules=False)

        self.engine = GraphEngine()
        self.bridge = IngeTrazoSceneBridge(app, self.engine)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.editor_widget = NodeEditorWidget(
            engine=self.engine,
            on_bake=self._handle_bake,
            on_live_toggled=self.bridge.set_live_sync,
            get_bridge_error=lambda: self.bridge.last_error,
            get_app=lambda: self.app,
            on_node_selection_changed=self.bridge.on_nodes_selected,
            parent=self,
        )
        self.editor_widget._bridge = self.bridge
        self.bridge.editor_widget = self.editor_widget
        self.bridge.is_panel_active_state = True
        self.bridge.on_scene_nodes_updated = self.editor_widget.scene.update_all_badges

        footer = QWidget()
        footer.setStyleSheet("background: #181a1f; color: #abb2bf; border-top: 1px solid #2c313a;")
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(8, 4, 8, 4)
        btn_load_sel = QPushButton("📥 Load Graph from Selected Scene Group")
        btn_load_sel.setStyleSheet("background: #2c313c; color: #e5c07b; padding: 3px 8px;")
        btn_load_sel.clicked.connect(self._handle_load_from_selection)
        f_layout.addWidget(btn_load_sel)
        f_layout.addStretch(1)

        layout.addWidget(self.editor_widget, stretch=1)
        layout.addWidget(footer)

    def _handle_bake(self, specific_node_id: Any = None) -> None:
        target_id = specific_node_id if isinstance(specific_node_id, str) else None
        count = self.bridge.bake_to_scene(specific_node_id=target_id)
        if count > 0:
            self.editor_widget.lbl_status.setText(f"🥐 Baked {count} watertight solid(s) to IngeTrazo Scene!")
        else:
            err = self.bridge.last_error or "No valid geometry to bake."
            self.editor_widget.lbl_status.setText(f"⚠️ {err}")

    def _handle_load_from_selection(self) -> None:
        graph_dict = self.bridge.load_graph_from_selected_group()
        if graph_dict:
            self.engine.load_dict(graph_dict)
            self.editor_widget.scene.rebuild_from_engine()
            self.editor_widget.lbl_status.setText("✅ Loaded node graph from selected Group!")
        else:
            QMessageBox.information(
                self,
                "No Embedded Graph Found",
                "Select a Group in IngeTrazo that was previously baked by the Node Editor.",
            )

    def closeEvent(self, event) -> None:
        self.bridge.stop()
        self.bridge.clear_preview(refresh=True)
        super().closeEvent(event)


_ACTIVE_DIALOG: Optional[NodeEditorDialog] = None


def open_node_editor(app: Any) -> None:
    """Opens or brings to front the Parametric Node Editor (tab or window)."""
    win = getattr(app, "_window", None) or getattr(app, "window", None)
    editor = getattr(win, "_node_editor_widget", None)
    if editor is not None and hasattr(editor, "is_floating") and editor.is_floating():
        editor.bring_to_front()
        editor.schedule_eval()
        return

    dock = getattr(win, "_node_editor_dock", None)
    if dock is not None:
        if hasattr(win, "set_tray_shown"):
            try:
                win.set_tray_shown(dock, True)
            except Exception:
                pass
        dock.show()
        dock.raise_()
        dock.activateWindow()
        if editor:
            editor.schedule_eval()
        return

    global _ACTIVE_DIALOG
    if _ACTIVE_DIALOG is None:
        _ACTIVE_DIALOG = NodeEditorDialog(app)
    _ACTIVE_DIALOG.show()
    _ACTIVE_DIALOG.raise_()
    _ACTIVE_DIALOG.activateWindow()
    _ACTIVE_DIALOG.editor_widget.schedule_eval()


# ============================================================================
# INGETRAZO EXTENSION CONTRACT (Tool SUBCLASS & setup(app) HOOK)
# ============================================================================
try:
    from tools.base import Tool
except ImportError:
    class Tool:
        pass


class NodeEditorTool(Tool):
    """Extensions menu entry to bring the Node Editor tab to the front."""
    name = "Node Editor"
    shortcut = "Ctrl+Shift+N"
    description = "Open the visual parametric node editor tab."
    uses_snap = False

    def on_activate(self, viewport) -> None:
        window = getattr(viewport, "window", None)
        if callable(window):
            window = window()
        editor = getattr(window, "_node_editor_widget", None)
        if editor is not None and hasattr(editor, "is_floating") and editor.is_floating():
            editor.bring_to_front()
            editor.schedule_eval()
            return

        dock = getattr(window, "_node_editor_dock", None)
        if dock is not None:
            if hasattr(window, "set_tray_shown"):
                try:
                    window.set_tray_shown(dock, True)
                except Exception:
                    pass
            dock.show()
            dock.raise_()
            dock.activateWindow()
            if editor:
                editor.schedule_eval()
        else:
            app = getattr(window, "_extension_app_handle", None)
            open_node_editor(app)

    def on_deactivate(self, viewport) -> None:
        pass


def setup(app: Any) -> None:
    """Extension initialization called by IngeTrazo's core.extensions loader."""
    global _ACTIVE_APP
    _ACTIVE_APP = app

    try:
        win = getattr(app, "_window", None) or getattr(app, "window", None)

        engine = GraphEngine()
        bridge = IngeTrazoSceneBridge(app, engine)

        def _handle_bake(specific_node_id: Any = None) -> None:
            target_id = specific_node_id if isinstance(specific_node_id, str) else None
            count = bridge.bake_to_scene(specific_node_id=target_id)
            if count > 0:
                editor_widget.lbl_status.setText(f"🥐 Baked {count} watertight solid(s) to IngeTrazo Scene!")
            else:
                err = bridge.last_error or "No valid geometry to bake."
                editor_widget.lbl_status.setText(f"⚠️ {err}")

        def _handle_load_from_selection() -> None:
            graph_dict = bridge.load_graph_from_selected_group()
            if graph_dict:
                engine.load_dict(graph_dict)
                editor_widget.scene.rebuild_from_engine()
                editor_widget.lbl_status.setText("✅ Loaded node graph from selected Group!")
            else:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(
                    editor_widget,
                    "No Embedded Graph Found",
                    "Select a Group in IngeTrazo that was previously baked by the Node Editor.",
                )

        editor_widget = NodeEditorWidget(
            engine=engine,
            on_bake=_handle_bake,
            on_live_toggled=bridge.set_live_sync,
            get_bridge_error=lambda: bridge.last_error,
            on_load_selection=_handle_load_from_selection,
            get_app=lambda: app,
            on_node_selection_changed=bridge.on_nodes_selected,
            on_panel_visibility_changed=bridge.on_panel_visibility_changed,
            on_graph_changed=bridge.notify_graph_changed,
        )
        editor_widget._bridge = bridge
        bridge.editor_widget = editor_widget
        bridge.on_scene_nodes_updated = editor_widget.scene.update_all_badges

        # Setup viewport overlay (previews draw cleanly without touching scene.groups or files)
        bridge.setup_overlay()

        # Restore graph on initial load if present in document_data
        bridge.restore_graph_from_document()

        # Register as a dock tab in the side tray (beside Properties, BIM, Solid Inspector)
        dock = None
        if hasattr(app, "add_panel"):
            dock = app.add_panel("Node Editor", editor_widget)
            if dock is not None:
                dock.setMinimumWidth(0)
                editor_widget.set_dock(dock)

        if win:
            win._node_editor_widget = editor_widget
            win._node_editor_dock = dock
            win._node_editor_bridge = bridge

            if hasattr(win, "setDockNestingEnabled"):
                try:
                    win.setDockNestingEnabled(True)
                except Exception:
                    pass

            if dock is not None:
                from PySide6.QtCore import QTimer
                def _join_tray():
                    tray = getattr(win, "tray", None)
                    if (tray is not None and not dock.isFloating() and not dock.isHidden()
                            and not win.tabifiedDockWidgets(dock)
                            and win.dockWidgetArea(dock) == win.dockWidgetArea(tray)):
                        win.tabifyDockWidget(tray, dock)
                    if hasattr(editor_widget, "_hook_dock_tab_bars"):
                        editor_widget._hook_dock_tab_bars()
                    if hasattr(editor_widget, "_check_panel_visibility"):
                        editor_widget._check_panel_visibility()
                QTimer.singleShot(0, _join_tray)
                if hasattr(editor_widget, "_hook_dock_tab_bars"):
                    QTimer.singleShot(150, editor_widget._hook_dock_tab_bars)
                QTimer.singleShot(200, bridge.sanitize_scene_previews)
                QTimer.singleShot(600, bridge.sanitize_scene_previews)

        # Listen for document changes, safely filtering out normal scene edits
        if hasattr(app, "on_document_changed"):
            try:
                app.on_document_changed(bridge.on_document_changed)
            except Exception:
                pass

    except Exception as ex:
        import logging
        logging.getLogger("ingetrazo.plugins").error(f"Error during Node Editor setup: {ex}", exc_info=True)


def register(app: Any) -> None:
    """IngeTrazo Extension entry point called when the plugin is enabled."""
    setup(app)


def unregister(app: Any) -> None:
    """IngeTrazo Extension cleanup hook called when the plugin is disabled or IngeTrazo exits."""
    global _ACTIVE_DIALOG
    if _ACTIVE_DIALOG is not None:
        _ACTIVE_DIALOG.bridge.clear_preview(refresh=True)
        _ACTIVE_DIALOG.close()
        _ACTIVE_DIALOG = None
    win = getattr(app, "_window", None) or getattr(app, "window", None)
    if win:
        bridge = getattr(win, "_node_editor_bridge", None)
        if bridge:
            bridge.clear_preview(refresh=True)
            bridge.stop()
        editor = getattr(win, "_node_editor_widget", None)
        if editor and hasattr(editor, "_floating_window") and editor._floating_window:
            try:
                editor._floating_window._is_host_closing = True
                editor._floating_window.close()
            except Exception:
                pass


if __name__ == "__main__":
    import sys

    class _DummyApp:
        scene = None
        viewport = None
        window = None

    qapp = QApplication.instance() or QApplication(sys.argv)
    dlg = NodeEditorDialog(_DummyApp())
    dlg.show()
    sys.exit(qapp.exec())
