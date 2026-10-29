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
    "version": "1.7.5",
    "author": "seghier",
    "description": "Visual parametric node editor with Blender-style sliders, live viewport sync, and BIM tagging.",
}

PREVIEW_TAG = "_ingetrazo_node_preview"


def is_preview_group(g: Any) -> bool:
    """Returns True if the group is a transient Node Editor live-preview or selection highlight."""
    if hasattr(g, "ext") and isinstance(g.ext, dict) and g.ext.get(PREVIEW_TAG):
        return True
    name = getattr(g, "name", None)
    if isinstance(name, str) and (
        name.startswith("[Preview] ")
        or name.startswith("[Selected] ")
        or name == "[Preview] Points"
    ):
        return True
    return False


def _install_igz_save_filter() -> None:
    """
    Wraps IngeTrazo's `formats.igz.save_scene` so that preview groups
    tagged with `PREVIEW_TAG` or named `[Preview] ...` are completely excluded
    from being serialized into `.igz` files (both manual saves and autosaves).
    """
    try:
        igz_mod = None
        try:
            import formats.igz as igz_mod
        except ImportError:
            pass
        if igz_mod is None and "formats.igz" in sys.modules:
            igz_mod = sys.modules["formats.igz"]
        if igz_mod is None or getattr(igz_mod, "_node_editor_save_filter_installed", False):
            return
        orig_save_scene = igz_mod.save_scene

        def _safe_save_scene(scene: Any, path: Any, *args: Any, **kwargs: Any) -> Any:
            groups = getattr(scene, "groups", None)
            if groups:
                preview_groups = [g for g in groups if is_preview_group(g)]
                if preview_groups:
                    clean_groups = [g for g in groups if not is_preview_group(g)]
                    try:
                        scene.groups = clean_groups
                        return orig_save_scene(scene, path, *args, **kwargs)
                    finally:
                        scene.groups = groups
            return orig_save_scene(scene, path, *args, **kwargs)

        igz_mod.save_scene = _safe_save_scene
        igz_mod._node_editor_save_filter_installed = True
    except Exception as ex:
        import logging
        logging.getLogger("ingetrazo.plugins").warning(f"Could not install igz save filter: {ex}")


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
        self.is_panel_active_state: bool = False
        self.engine.on_evaluated = self._on_graph_evaluated
        self._setup_scene_listener()
        self.sanitize_scene_previews()

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

    def _clear_internal_bump_flag(self) -> None:
        self._is_internal_scene_bump = False

    def _bump_viewport(self) -> None:
        """Notifies IngeTrazo's OpenGL renderer that scene geometry changed."""
        self._is_internal_scene_bump = True
        try:
            sc = self.scene
            if sc is not None:
                if hasattr(sc, "version"):
                    sc.version += 1
                bump = getattr(sc, "bump_view", None)
                if callable(bump):
                    try:
                        bump()
                    except Exception:
                        pass
                if hasattr(sc, "version"):
                    self._last_handled_version = sc.version
                for fn_name in ("invalidate", "mark_dirty"):
                    fn = getattr(sc, fn_name, None)
                    if callable(fn):
                        try:
                            fn()
                        except Exception:
                            pass

            vp = self.viewport
            if vp is not None:
                if hasattr(vp, "_epoch_same"):
                    vp._epoch_same = None
                if hasattr(vp, "_placements_memo"):
                    vp._placements_memo = None
                if hasattr(vp, "_inst_pool"):
                    vp._inst_pool = None
                notify = getattr(vp, "notify_scene_changed", None)
                if callable(notify):
                    try:
                        notify()
                    except Exception:
                        pass
                for fn_name in ("invalidate_buffers", "mark_dirty", "update"):
                    fn = getattr(vp, fn_name, None)
                    if callable(fn):
                        try:
                            fn()
                        except Exception:
                            pass
                try:
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(0, lambda: vp.update() if (vp is not None and hasattr(vp, 'update')) else None)
                    QTimer.singleShot(30, lambda: vp.update() if (vp is not None and hasattr(vp, 'update')) else None)
                except Exception:
                    pass
        finally:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, self._clear_internal_bump_flag)

    def on_nodes_selected(self, selected_node_ids: List[str]) -> None:
        """Highlights the geometry of currently selected canvas node(s) in the 3D viewport."""
        sc = self.scene
        if sc is None or not hasattr(sc, "selection"):
            return

        # Discard previous preview group selections and ephemeral [Selected] groups
        to_discard = [g for g in sc.selection if is_preview_group(g)]
        for g in to_discard:
            try:
                sc.selection.discard(g)
            except Exception:
                pass
        sc.groups[:] = [g for g in sc.groups if not (getattr(g, "name", "").startswith("[Selected] "))]


        if not selected_node_ids:
            self._bump_viewport()
            return

        sel_set = set(selected_node_ids)
        matching = []
        for g in getattr(sc, "groups", []):
            if is_preview_group(g):
                if hasattr(g, "ext") and isinstance(g.ext, dict) and g.ext.get("node_id") in sel_set:
                    matching.append(g)

        for g in matching:
            sc.selection.add(g)

        # If a selected node is NOT in active preview (e.g. its output was wired downstream),
        # extract its cached geometry directly and create an ephemeral selected preview group!
        existing_nids = {g.ext.get("node_id") for g in matching}
        missing_nids = sel_set - existing_nids
        for nid in missing_nids:
            node = self.engine.nodes.get(nid)
            if node and getattr(node, "is_enabled", True) and not node.error_message:
                for out_spec in node.outputs:
                    val = node.cached_outputs.get(out_spec.id)
                    if val is None:
                        continue
                    m_list = []
                    if isinstance(val, MeshData):
                        m_list.append(val)
                    elif isinstance(val, CurveData):
                        m_list.append(val.to_wire_mesh(name=f"{node.title}_Curve"))
                    elif isinstance(val, list):
                        for item in val:
                            if isinstance(item, MeshData):
                                m_list.append(item)
                            elif isinstance(item, CurveData):
                                m_list.append(item.to_wire_mesh(name=f"{node.title}_Curve"))
                    for mdata in m_list:
                        sel_mdata = mdata.copy()
                        sel_mdata.source_node_id = nid
                        sel_mdata.name = f"[Selected] {node.title}"
                        sel_grp = _make_ingetrazo_group(sel_mdata, {}, is_preview=True, scene=sc)
                        sc.groups.append(sel_grp)
                        sc.selection.add(sel_grp)

        self._bump_viewport()

    def sanitize_scene_previews(self) -> None:
        """Removes any pre-existing or stale [Preview] groups loaded from previous .igz files."""
        self.clear_preview(refresh=False)

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
        """Removes transient live-preview groups from `scene.groups` and `scene.selection`."""
        sc = self.scene
        if sc is None or not hasattr(sc, "groups"):
            return
        before = len(sc.groups)
        sc.groups[:] = [g for g in sc.groups if not is_preview_group(g)]
        if hasattr(sc, "selection") and sc.selection:
            to_discard = [g for g in sc.selection if is_preview_group(g)]
            for g in to_discard:
                try:
                    sc.selection.discard(g)
                except Exception:
                    pass
        if refresh:
            self._bump_viewport()

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
        """Streams transient preview geometry into IngeTrazo's viewport at 60 FPS."""
        self.last_error = None
        if not self.live_sync or self.scene is None:
            return

        if not self.is_editor_active():
            self.clear_preview(refresh=False)
            return

        self.clear_preview(refresh=False)
        graph_dict = self.engine.to_dict()

        try:
            for mdata in meshes:
                if not mdata.vertices and not mdata.edges:
                    continue
                preview_data = mdata.copy()
                preview_data.name = f"[Preview] {mdata.name}"
                grp = _make_ingetrazo_group(preview_data, graph_dict, is_preview=True, scene=self.scene)
                self.scene.groups.append(grp)


            # Render preview points as 3D crosshairs inside a single preview group
            if points:
                pt_mesh = MeshData(name="[Preview] Points")
                arm = 0.08
                for p in points:
                    base = len(pt_mesh.vertices)
                    pt_mesh.vertices.extend([
                        (p.x - arm, p.y, p.z), (p.x + arm, p.y, p.z),
                        (p.x, p.y - arm, p.z), (p.x, p.y + arm, p.z),
                        (p.x, p.y, p.z - arm), (p.x, p.y, p.z + arm),
                    ])
                    pt_mesh.edges.extend([(base, base + 1), (base + 2, base + 3), (base + 4, base + 5)])
                grp_pts = _make_ingetrazo_group(pt_mesh, graph_dict, is_preview=True, scene=self.scene)
                self.scene.groups.append(grp_pts)

            self._bump_viewport()
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"

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
                # IngeTrazo's SnapshotImport(fn) takes a single callable `lambda s: ...`
                if len(sig.parameters) <= 2:
                    cmd = SnapshotImport(_do_commit)
                    if hasattr(history, "execute"):
                        # IngeTrazo's History.execute(cmd) takes only the command
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
                committed = baked_count > 0  # never re-bake after a partial commit

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
    try:
        discover_nodes(reload_modules=False)
        _install_igz_save_filter()

        win = getattr(app, "_window", None) or getattr(app, "window", None)
        if win:
            win._extension_app_handle = app

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
        )
        editor_widget._bridge = bridge
        bridge.editor_widget = editor_widget
        bridge.on_scene_nodes_updated = editor_widget.scene.update_all_badges

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

            if hasattr(win, "_do_save") and not getattr(win, "_node_editor_save_hooked", False):
                orig_win_do_save = win._do_save
                def _safe_win_do_save(save_path: Any) -> Any:
                    bridge.clear_preview(refresh=False)
                    try:
                        return orig_win_do_save(save_path)
                    finally:
                        if bridge.live_sync and editor_widget.isVisible():
                            editor_widget.schedule_eval()
                win._do_save = _safe_win_do_save
                win._node_editor_save_hooked = True
            if hasattr(win, "setDockNestingEnabled"):
                try:
                    win.setDockNestingEnabled(True)
                except Exception:
                    pass

            # Ensure the tab is tabified with the side tray
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
