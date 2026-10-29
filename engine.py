# SPDX-License-Identifier: GPL-3.0-or-later
"""Directed Acyclic Graph (DAG) execution engine with dirty-flag caching."""

from __future__ import annotations
from collections import deque
from dataclasses import dataclass
import json
import time
import traceback
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

try:
    from .core_types import CurveData, MeshData, Vec3
    from .node_base import BaseNode, NODE_REGISTRY
except (ImportError, ValueError):
    from core_types import CurveData, MeshData, Vec3
    from node_base import BaseNode, NODE_REGISTRY


@dataclass(frozen=True)
class Wire:
    """Directed connection from `src_node.src_socket` -> `dst_node.dst_socket`."""
    src_node: str
    src_socket: str
    dst_node: str
    dst_socket: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "src_node": self.src_node,
            "src_socket": self.src_socket,
            "dst_node": self.dst_node,
            "dst_socket": self.dst_socket,
        }


class GraphEngine:
    """
    Professional DAG evaluator for IngeTrazo.
    - Incremental dirty propagation: untouched upstream branches are O(1) cached.
    - Cycle detection: refuses wires that would create a feedback loop.
    - Fault isolation: captures node exceptions without breaking the UI or viewport.
    """

    def __init__(self) -> None:
        self.nodes: Dict[str, BaseNode] = {}
        self.wires: List[Wire] = []
        self.on_evaluated: Optional[Callable[[List[MeshData], List[Vec3], float], None]] = None
        self.last_eval_ms: float = 0.0

    # ------------------------------------------------------------------
    # Graph Mutation API
    # ------------------------------------------------------------------
    def add_node(self, type_id: str, pos: Tuple[float, float] = (0.0, 0.0), node_id: Optional[str] = None) -> BaseNode:
        cls = NODE_REGISTRY.get(type_id)
        if cls is None:
            raise KeyError(f"Unknown node type_id: '{type_id}'")
        node = cls(node_id=node_id)
        node.pos = pos
        self.nodes[node.id] = node
        return node

    def get_node(self, node_id: str) -> Optional[BaseNode]:
        return self.nodes.get(node_id)

    def remove_node(self, node_id: str) -> None:
        if node_id not in self.nodes:
            return
        node = self.nodes[node_id]
        if hasattr(node, "on_destroy") and callable(node.on_destroy):
            try:
                node.on_destroy()
            except Exception:
                pass
        for w in self.wires:
            if w.src_node == node_id:
                self.mark_dirty(w.dst_node)
        self.wires = [w for w in self.wires if w.src_node != node_id and w.dst_node != node_id]
        del self.nodes[node_id]

    def can_connect(self, src_node: str, src_socket: str, dst_node: str, dst_socket: str) -> bool:
        if src_node == dst_node:
            return False
        s_node = self.nodes.get(src_node)
        d_node = self.nodes.get(dst_node)
        if not s_node or not d_node:
            return False
        if not s_node.get_output_spec(src_socket) or not d_node.get_input_spec(dst_socket):
            return False
        if self._is_reachable(dst_node, src_node):
            return False
        return True

    def connect(
        self,
        src_node: str,
        src_socket: str,
        dst_node: str,
        dst_socket: str,
        replace_existing: bool = True,
    ) -> Optional[Wire]:
        if not self.can_connect(src_node, src_socket, dst_node, dst_socket):
            return None
        for w in self.wires:
            if (
                w.src_node == src_node
                and w.src_socket == src_socket
                and w.dst_node == dst_node
                and w.dst_socket == dst_socket
            ):
                return w
        if replace_existing:
            self.wires = [
                w for w in self.wires
                if not (w.dst_node == dst_node and w.dst_socket == dst_socket)
            ]
        wire = Wire(src_node, src_socket, dst_node, dst_socket)
        self.wires.append(wire)
        self.mark_dirty(dst_node)
        return wire

    def disconnect(self, wire: Wire) -> None:
        if wire in self.wires:
            self.wires.remove(wire)
            self.mark_dirty(wire.dst_node)

    def update_node_param(self, node_id: str, input_id: str, value: Any) -> None:
        node = self.nodes.get(node_id)
        if not node:
            return
        node.set_param(input_id, value)
        if node.is_dirty:
            self.mark_dirty(node_id)

    def mark_dirty(self, start_node_id: str) -> None:
        queue = deque([start_node_id])
        visited: Set[str] = set()
        while queue:
            curr = queue.popleft()
            if curr in visited or curr not in self.nodes:
                continue
            visited.add(curr)
            self.nodes[curr].is_dirty = True
            for w in self.wires:
                if w.src_node == curr:
                    queue.append(w.dst_node)

    # ------------------------------------------------------------------
    # Topological Sort & Evaluation
    # ------------------------------------------------------------------
    def _is_reachable(self, start_id: str, target_id: str) -> bool:
        queue = deque([start_id])
        visited: Set[str] = set()
        while queue:
            curr = queue.popleft()
            if curr == target_id:
                return True
            if curr in visited:
                continue
            visited.add(curr)
            for w in self.wires:
                if w.src_node == curr:
                    queue.append(w.dst_node)
        return False

    def topological_order(self) -> List[str]:
        in_degree: Dict[str, int] = {nid: 0 for nid in self.nodes}
        adj: Dict[str, List[str]] = {nid: [] for nid in self.nodes}
        for w in self.wires:
            if w.src_node in self.nodes and w.dst_node in self.nodes:
                adj[w.src_node].append(w.dst_node)
                in_degree[w.dst_node] += 1

        queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
        order: List[str] = []
        while queue:
            u = queue.popleft()
            order.append(u)
            for v in adj[u]:
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    queue.append(v)

        if len(order) != len(self.nodes):
            raise RuntimeError("Cycle detected in node graph.")
        return order

    def evaluate(self) -> Tuple[List[MeshData], List[Vec3]]:
        t0 = time.perf_counter()
        order = self.topological_order()

        incoming_map: Dict[Tuple[str, str], List[Wire]] = {}
        for w in self.wires:
            incoming_map.setdefault((w.dst_node, w.dst_socket), []).append(w)

        for nid in order:
            node = self.nodes[nid]
            if not node.is_enabled:
                node.cached_outputs = {out.id: None for out in node.outputs}
                node.error_message = None
                node.is_dirty = False
                continue

            if not node.is_dirty and node.error_message is None:
                continue

            raw_inputs: Dict[str, Any] = {}
            upstream_failed = False
            upstream_disabled = False
            for spec in node.inputs:
                wires = incoming_map.get((nid, spec.id))
                if not wires:
                    continue
                if len(wires) == 1:
                    wire = wires[0]
                    src = self.nodes.get(wire.src_node)
                    if src and src.error_message:
                        upstream_failed = True
                        break
                    if src and (not src.is_enabled or src.cached_outputs.get(wire.src_socket) is None):
                        upstream_disabled = True
                        break
                    if src:
                        raw_inputs[spec.id] = src.cached_outputs.get(wire.src_socket)
                else:
                    multi_vals: List[Any] = []
                    all_srcs_disabled = True
                    for wire in wires:
                        src = self.nodes.get(wire.src_node)
                        if src and src.error_message:
                            upstream_failed = True
                            break
                        if src and not src.is_enabled:
                            continue
                        if src:
                            val = src.cached_outputs.get(wire.src_socket)
                            if val is not None:
                                all_srcs_disabled = False
                                if isinstance(val, list):
                                    multi_vals.extend(val)
                                else:
                                    multi_vals.append(val)
                    if upstream_failed:
                        break
                    if all_srcs_disabled:
                        upstream_disabled = True
                        break
                    raw_inputs[spec.id] = multi_vals

            if upstream_failed or upstream_disabled:
                if upstream_failed:
                    node.error_message = "Upstream node error"
                else:
                    node.error_message = None
                node.cached_outputs = {out.id: None for out in node.outputs}
                node.is_dirty = False
                continue

            try:
                node.cached_outputs = node.execute(raw_inputs)
                node.error_message = None
                node.is_dirty = False
            except Exception as exc:
                node.error_message = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
                node.cached_outputs = {}
                node.is_dirty = False

        meshes, points = self.collect_preview_outputs()
        self.last_eval_ms = (time.perf_counter() - t0) * 1000.0
        if self.on_evaluated:
            self.on_evaluated(meshes, points, self.last_eval_ms)
        return meshes, points

    def collect_preview_outputs(self) -> Tuple[List[MeshData], List[Vec3]]:
        meshes: List[MeshData] = []
        points: List[Vec3] = []

        def _extract_preview(val: Any, default_name: str = "Shape", source_node_id: Optional[str] = None) -> None:
            if val is None:
                return
            if isinstance(val, MeshData):
                if val.vertices or val.edges:
                    m = val.copy()
                    if source_node_id:
                        m.source_node_id = source_node_id
                    meshes.append(m)
            elif isinstance(val, CurveData):
                if val.points:
                    m = val.to_wire_mesh(name=f"{default_name}_Curve")
                    if source_node_id:
                        m.source_node_id = source_node_id
                    meshes.append(m)
            elif hasattr(val, "parameter_range") or type(val).__name__ == "Curve":
                try:
                    from brep_engine import BRepEngine
                    if BRepEngine.is_available():
                        cd = BRepEngine.curve_to_curve_data(val)
                        if cd and cd.points:
                            m = cd.to_wire_mesh(name=f"{default_name}_Curve")
                            if source_node_id:
                                m.source_node_id = source_node_id
                            meshes.append(m)
                except Exception:
                    pass
            elif hasattr(val, "faces") or type(val).__name__ == "Brep":
                try:
                    from brep_engine import BRepEngine
                    if BRepEngine.is_available():
                        bm = BRepEngine.brep_to_mesh_data(val, name=default_name)
                        if bm and (bm.vertices or bm.edges):
                            m = bm.copy()
                            if source_node_id:
                                m.source_node_id = source_node_id
                            meshes.append(m)
                except Exception:
                    pass
            elif isinstance(val, Vec3):
                points.append(val)
            elif isinstance(val, dict):
                if "outer" in val and isinstance(val["outer"], list):
                    outer_pts = [p if isinstance(p, Vec3) else Vec3(*p) for p in val["outer"]]
                    m = CurveData(points=outer_pts, closed=True).to_wire_mesh(name="Face_Outer")
                    if source_node_id:
                        m.source_node_id = source_node_id
                    meshes.append(m)
                if "holes" in val and isinstance(val["holes"], list):
                    for idx, h in enumerate(val["holes"]):
                        h_pts = [p if isinstance(p, Vec3) else Vec3(*p) for p in h]
                        m = CurveData(points=h_pts, closed=True).to_wire_mesh(name=f"Face_Hole_{idx+1}")
                        if source_node_id:
                            m.source_node_id = source_node_id
                        meshes.append(m)
            elif isinstance(val, (list, tuple)):
                for item in val:
                    _extract_preview(item, default_name, source_node_id=source_node_id)

        active_output_sources = set()
        for node in self.nodes.values():
            if (
                (getattr(node, "is_output_node", False) or getattr(node, "type_id", "") == "scene.preview")
                and getattr(node, "is_enabled", True)
                and not node.error_message
            ):
                for w in self.wires:
                    if w.dst_node == node.id:
                        active_output_sources.add((w.src_node, w.src_socket))

        for node in self.nodes.values():
            if not getattr(node, "is_enabled", True) or not getattr(node, "is_preview_visible", True):
                continue
            if node.error_message:
                continue

            if getattr(node, "type_id", "") == "scene.preview":
                src_ids = [w.src_node for w in self.wires if w.dst_node == node.id]
                source_id = src_ids[0] if src_ids else node.id
                val = node.cached_outputs.get("preview")
                _extract_preview(val, default_name="Preview", source_node_id=source_id)
                continue

            if getattr(node, "is_output_node", False):
                if not node.param_values.get("enabled", True):
                    continue
                src_ids = [w.src_node for w in self.wires if w.dst_node == node.id]
                source_id = src_ids[0] if src_ids else node.id
                _extract_preview(node.cached_outputs.get("mesh_out"), default_name=node.title or "Output", source_node_id=source_id)
                continue

            for out_spec in node.outputs:
                if (node.id, out_spec.id) in active_output_sources:
                    continue
                if getattr(out_spec, "hide_preview", False):
                    continue
                if out_spec.id.lower() in ("tangents", "tangent", "normals", "normal"):
                    continue
                val = node.cached_outputs.get(out_spec.id)
                _extract_preview(val, default_name=node.title or out_spec.label, source_node_id=node.id)

        return meshes, points

    # Backward compatibility alias
    collect_scene_outputs = collect_preview_outputs

    def collect_bake_outputs(self, specific_node_id: Optional[str] = None) -> List[MeshData]:
        meshes: List[MeshData] = []

        def _extract_bake(val: Any) -> None:
            if val is None:
                return
            if isinstance(val, MeshData):
                if val.vertices or val.edges:
                    meshes.append(val)
            elif isinstance(val, CurveData):
                if len(val.points) >= 3 and val.closed:
                    meshes.append(val.to_mesh_face())
                elif val.points:
                    meshes.append(val.to_wire_mesh())
            elif isinstance(val, (list, tuple)):
                for item in val:
                    _extract_bake(item)

        if specific_node_id and specific_node_id in self.nodes:
            target_node = self.nodes[specific_node_id]
            if getattr(target_node, "is_output_node", False):
                _extract_bake(target_node.cached_outputs.get("mesh_out"))
            else:
                for val in target_node.cached_outputs.values():
                    _extract_bake(val)
            return meshes

        all_output_nodes = [n for n in self.nodes.values() if getattr(n, "is_output_node", False)]
        if all_output_nodes:
            for node in all_output_nodes:
                if not getattr(node, "is_enabled", True) or not getattr(node, "is_preview_visible", True) or node.error_message:
                    continue
                _extract_bake(node.cached_outputs.get("mesh_out"))
        else:
            for node in self.nodes.values():
                if not getattr(node, "is_enabled", True) or not getattr(node, "is_preview_visible", True) or node.error_message:
                    continue
                for val in node.cached_outputs.values():
                    _extract_bake(val)

        return meshes

    # ------------------------------------------------------------------
    # Serialization & High-Speed Cloner
    # ------------------------------------------------------------------
    def _paste_nodes_from_data(self, data: Dict[str, Any], offset: Tuple[float, float] = (40.0, 40.0)) -> List[BaseNode]:
        """Core high-speed cloner: instantiates nodes and re-links internal wires without redundant JSON string passes."""
        import uuid
        new_nodes: List[BaseNode] = []
        id_map: Dict[str, str] = {}

        for nd in data.get("nodes", []):
            type_id = nd.get("type_id", "")
            # Legacy migration: curve.rectangle with 'origin' was RectangleProfileNode
            if type_id == "curve.rectangle" and "origin" in nd.get("params", {}) and "fillet" not in nd.get("params", {}):
                type_id = "curve.rectangle_profile"
            if type_id not in NODE_REGISTRY:
                continue
            old_id = nd.get("id")
            fresh_id = uuid.uuid4().hex[:10]
            if old_id:
                id_map[old_id] = fresh_id

            pos_list = nd.get("pos", [0.0, 0.0])
            new_pos = (float(pos_list[0]) + offset[0], float(pos_list[1]) + offset[1])
            node = self.add_node(type_id, pos=new_pos, node_id=fresh_id)
            for k, v in nd.get("params", {}).items():
                node.set_param(k, v)
            node.is_enabled = nd.get("is_enabled", True)
            node.is_preview_visible = nd.get("is_preview_visible", True)
            node.custom_title = nd.get("custom_title")
            for sid, cfg in nd.get("slider_configs", {}).items():
                sp = node.get_input_spec(sid)
                if sp and isinstance(cfg, dict):
                    sp.min_val = cfg.get("min", sp.min_val)
                    sp.max_val = cfg.get("max", sp.max_val)
                    sp.step = cfg.get("step", sp.step)
                    sp.decimals = cfg.get("decimals", sp.decimals)
            node.is_dirty = True
            new_nodes.append(node)

        for wd in data.get("wires", []):
            src = id_map.get(wd["src_node"])
            dst = id_map.get(wd["dst_node"])
            if src and dst:
                self.connect(src, wd["src_socket"], dst, wd["dst_socket"], replace_existing=False)

        return new_nodes

    def copy_nodes(self, node_ids: List[str]) -> str:
        id_set = set(node_ids)
        nodes_data = [self.nodes[nid].to_dict() for nid in node_ids if nid in self.nodes]
        wires_data = [w.to_dict() for w in self.wires if w.src_node in id_set and w.dst_node in id_set]
        return json.dumps({"nodes": nodes_data, "wires": wires_data})

    def paste_nodes(self, json_str: str, offset: Tuple[float, float] = (40.0, 40.0)) -> List[BaseNode]:
        try:
            data = json.loads(json_str)
        except Exception:
            return []
        return self._paste_nodes_from_data(data, offset=offset)

    def duplicate_nodes(self, node_ids: List[str], offset: Tuple[float, float] = (40.0, 40.0)) -> List[BaseNode]:
        id_set = set(node_ids)
        nodes_data = [self.nodes[nid].to_dict() for nid in node_ids if nid in self.nodes]
        wires_data = [w.to_dict() for w in self.wires if w.src_node in id_set and w.dst_node in id_set]
        return self._paste_nodes_from_data({"nodes": nodes_data, "wires": wires_data}, offset=offset)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": "1.0",
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "wires": [w.to_dict() for w in self.wires],
        }

    def load_dict(self, data: Dict[str, Any]) -> None:
        for n in list(self.nodes.values()):
            if hasattr(n, "on_destroy") and callable(n.on_destroy):
                try:
                    n.on_destroy()
                except Exception:
                    pass
        self.nodes.clear()
        self.wires.clear()
        for nd in data.get("nodes", []):
            type_id = nd.get("type_id", "")
            # Legacy migration: curve.rectangle with 'origin' was RectangleProfileNode
            if type_id == "curve.rectangle" and "origin" in nd.get("params", {}) and "fillet" not in nd.get("params", {}):
                type_id = "curve.rectangle_profile"
            if type_id not in NODE_REGISTRY:
                continue
            pos_list = nd.get("pos", [0.0, 0.0])
            node = self.add_node(type_id, pos=(float(pos_list[0]), float(pos_list[1])), node_id=nd.get("id"))
            for k, v in nd.get("params", {}).items():
                node.set_param(k, v)
            node.is_enabled = nd.get("is_enabled", True)
            node.is_preview_visible = nd.get("is_preview_visible", True)
            node.custom_title = nd.get("custom_title")
            for sid, cfg in nd.get("slider_configs", {}).items():
                sp = node.get_input_spec(sid)
                if sp and isinstance(cfg, dict):
                    sp.min_val = cfg.get("min", sp.min_val)
                    sp.max_val = cfg.get("max", sp.max_val)
                    sp.step = cfg.get("step", sp.step)
                    sp.decimals = cfg.get("decimals", sp.decimals)
            node.is_dirty = True

        for wd in data.get("wires", []):
            self.connect(wd["src_node"], wd["src_socket"], wd["dst_node"], wd["dst_socket"], replace_existing=False)

    def save_file(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    def load_file(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as f:
            self.load_dict(json.load(f))