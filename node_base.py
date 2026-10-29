# SPDX-License-Identifier: GPL-3.0-or-later
"""Declarative BaseNode template and global node registry."""

from __future__ import annotations
import copy
from dataclasses import dataclass
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple, Type
import uuid

try:
    from .core_types import AccessMode, SocketType, Vec3, coerce_value
except (ImportError, ValueError):
    from core_types import AccessMode, SocketType, Vec3, coerce_value


@dataclass
class InputSpec:
    """Declarative specification for a node input pin and its inline UI widget."""
    id: str
    label: str
    type: SocketType = SocketType.FLOAT
    default: Any = 0.0
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    step: float = 0.1
    decimals: Optional[int] = None        # Decimal places for float sliders (default 2)
    choices: Optional[List[str]] = None   # If set on STRING type, renders a QComboBox
    access: AccessMode = AccessMode.ITEM  # ITEM = auto-broadcast lists; LIST = pass raw list
    hide_widget: bool = False             # True for geometry sockets that have no inline editor
    hide_socket: bool = False             # True for control params that have an inline widget but no socket dot


@dataclass
class OutputSpec:
    """Declarative specification for a node output pin."""
    id: str
    label: str
    type: SocketType = SocketType.FLOAT
    hide_preview: bool = False


# Global Registry mapping type_id -> BaseNode subclass (shared singleton across package/standalone imports)
_existing_registry = None
for _k, _mod in list(sys.modules.items()):
    if (_k == "node_base" or _k.endswith(".node_base")) and hasattr(_mod, "NODE_REGISTRY"):
        _existing_registry = _mod.NODE_REGISTRY
        break

NODE_REGISTRY: Dict[str, Type[BaseNode]] = _existing_registry if _existing_registry is not None else {}


def register_node(cls: Type[BaseNode]) -> Type[BaseNode]:
    """
    Class decorator that registers a BaseNode subclass into the Node Editor catalog.
    Validates required metadata so broken nodes never crash IngeTrazo.
    """
    if not getattr(cls, "type_id", ""):
        raise ValueError(f"Node class {cls.__name__} must define a unique 'type_id' string.")
    if cls.type_id in NODE_REGISTRY and NODE_REGISTRY[cls.type_id] is not cls:
        if cls.__name__ != NODE_REGISTRY[cls.type_id].__name__:
            import logging
            logging.getLogger("ingetrazo.plugins").warning(
                f"Duplicate type_id '{cls.type_id}' registered by {cls.__name__}, overwriting {NODE_REGISTRY[cls.type_id].__name__}"
            )
    NODE_REGISTRY[cls.type_id] = cls

    # Cross-module synchronization across sys.modules
    if "node_base" in sys.modules and hasattr(sys.modules["node_base"], "NODE_REGISTRY"):
        sys.modules["node_base"].NODE_REGISTRY[cls.type_id] = cls
    for k, v in list(sys.modules.items()):
        if (k.endswith(".node_base") or k == "node_base") and hasattr(v, "NODE_REGISTRY"):
            v.NODE_REGISTRY[cls.type_id] = cls

    return cls


class BaseNode:
    """
    Base class for all IngeTrazo Parametric Nodes.

    To create a new node, subclass `BaseNode`, decorate with `@register_node`,
    define `type_id`, `title`, `category`, `inputs`, `outputs`, and implement `compute()`.
    """
    type_id: str = "core.base"
    title: str = "Base Node"
    category: str = "General"
    subcategory: str = ""
    description: str = ""
    header_color: tuple[int, int, int] = (52, 73, 94)

    # Set to True if this node pushes geometry to IngeTrazo's viewport
    is_output_node: bool = False
    auto_broadcast: bool = True

    # Visual Icon & Badge Configuration
    icon: Optional[str] = None         # Filename in addon's icons/ folder or absolute path
    icon_tag: Optional[str] = None     # 1-4 character badge text or emoji (e.g. "SN", "WP", "🧱", "📐")

    # Addon metadata populated during discovery
    _addon_dir: Optional[str] = None
    _addon_icons_dir: Optional[str] = None

    inputs: List[InputSpec] = []
    outputs: List[OutputSpec] = []

    def __init__(self, node_id: Optional[str] = None) -> None:
        import copy
        self.id: str = node_id or uuid.uuid4().hex[:10]
        self.pos: tuple[float, float] = (0.0, 0.0)

        # Operational state (Power / Enable & Viewport Preview Eye)
        self.is_enabled: bool = True
        self.is_preview_visible: bool = True

        # Custom user-defined nickname
        self.custom_title: Optional[str] = None

        # Clone input specs per node instance so modifying min/max/decimals is localized
        self.inputs = [copy.copy(spec) for spec in self.__class__.inputs]

        # Inline widget fallback values when an input pin has no incoming wire
        self.param_values: Dict[str, Any] = {
            spec.id: spec.default for spec in self.inputs
        }

        # Runtime state managed by GraphEngine
        self.cached_outputs: Dict[str, Any] = {}
        self.is_dirty: bool = True
        self.error_message: Optional[str] = None

    def get_action_buttons(self) -> List[Dict[str, Any]]:
        """
        Returns list of action buttons to render on the node card.
        Each item: {'id': str, 'label': str, 'color': str, 'tooltip': str, 'action': str}
        """
        if getattr(self, "is_output_node", False):
            return [
                {
                    "id": "btn_bake",
                    "label": "🥐 Bake to IngeTrazo",
                    "tooltip": "Bake current solids to IngeTrazo scene",
                    "color": "#2e7d32",
                    "action": "bake",
                }
            ]
        return []

    def get_card_badge_text(self) -> Optional[str]:
        """Returns optional status/summary text to render on the node card."""
        return None

    def mark_dirty(self) -> None:
        """Marks the node dirty so the engine re-evaluates it on next pass."""
        self.is_dirty = True

    def set_param(self, input_id: str, value: Any) -> None:
        """Updates an inline parameter value and marks the node dirty."""
        spec = self.get_input_spec(input_id)
        if spec is not None:
            value = coerce_value(value, spec.type)
        if self.param_values.get(input_id) != value:
            self.param_values[input_id] = value
            self.is_dirty = True

    def get_input_spec(self, input_id: str) -> Optional[InputSpec]:
        for spec in self.inputs:
            if spec.id == input_id:
                return spec
        return None

    def get_output_spec(self, output_id: str) -> Optional[OutputSpec]:
        for spec in self.outputs:
            if spec.id == output_id:
                return spec
        return None

    def execute(self, raw_inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Coerces inputs, applies Grasshopper-style longest-list broadcasting
        for `AccessMode.ITEM` sockets, and invokes `self.compute(**kwargs)`.
        If the node is disabled/muted, returns empty outputs without computing.
        """
        if not self.is_enabled:
            return {out.id: None for out in self.outputs}

        coerced: Dict[str, Any] = {}
        item_lists: Dict[str, List[Any]] = {}
        max_len = 1
        has_broadcast = False

        if not getattr(self, "auto_broadcast", True):
            for spec in self.inputs:
                v = raw_inputs.get(spec.id, self.param_values.get(spec.id, spec.default))
                coerced[spec.id] = coerce_value(v, spec.type)
            return self.compute(**coerced)

        for spec in self.inputs:
            val = raw_inputs.get(spec.id, self.param_values.get(spec.id, spec.default))
            val = coerce_value(val, spec.type)

            # Preserve 3-4 element numeric lists (such as JSON-deserialized colors or points) as single values
            if isinstance(val, list):
                if spec.id.lower() in ("color", "rgb", "rgba") and len(val) in (3, 4) and all(isinstance(x, (int, float)) for x in val):
                    val = tuple(val)
                elif spec.type in (SocketType.VEC3, SocketType.POINT, SocketType.VECTOR) and len(val) == 3 and all(isinstance(x, (int, float)) for x in val):
                    val = Vec3(*val)

            coerced[spec.id] = val

            if spec.access == AccessMode.ITEM and isinstance(val, list):
                has_broadcast = True
                item_lists[spec.id] = val
                max_len = max(max_len, len(val))
            elif spec.access == AccessMode.LIST and not isinstance(val, list):
                coerced[spec.id] = [] if val is None else [val]

        if not has_broadcast:
            return self.compute(**coerced)

        if max_len == 0:
            return {out.id: [] for out in self.outputs}

        # Longest-list lacing: repeat last item of shorter lists to match max_len
        batched_results: Dict[str, List[Any]] = {out.id: [] for out in self.outputs}
        for i in range(max_len):
            slice_kwargs: Dict[str, Any] = {}
            for spec in self.inputs:
                if spec.id in item_lists:
                    lst = item_lists[spec.id]
                    slice_kwargs[spec.id] = lst[min(i, len(lst) - 1)]
                else:
                    slice_kwargs[spec.id] = coerced[spec.id]

            res = self.compute(**slice_kwargs)
            if isinstance(res, dict):
                for k, v in res.items():
                    if k not in batched_results:
                        batched_results[k] = []
                    batched_results[k].append(v)

        return batched_results

    def compute(self, **inputs: Any) -> Dict[str, Any]:
        """Override in subclasses: receives named inputs and returns dict of output_id -> value."""
        raise NotImplementedError(f"{self.__class__.__name__}.compute() is not implemented.")

    def to_dict(self) -> Dict[str, Any]:
        serialized_params: Dict[str, Any] = {}
        for k, v in self.param_values.items():
            if isinstance(v, Vec3):
                serialized_params[k] = {"__type__": "Vec3", "x": v.x, "y": v.y, "z": v.z}
            else:
                serialized_params[k] = v

        slider_configs: Dict[str, Any] = {}
        for spec in self.inputs:
            if spec.type in (SocketType.FLOAT, SocketType.INT):
                slider_configs[spec.id] = {
                    "min": spec.min_val,
                    "max": spec.max_val,
                    "step": spec.step,
                    "decimals": spec.decimals,
                }

        return {
            "id": self.id,
            "type_id": self.type_id,
            "pos": [round(self.pos[0], 2), round(self.pos[1], 2)],
            "params": serialized_params,
            "is_enabled": self.is_enabled,
            "is_preview_visible": self.is_preview_visible,
            "custom_title": self.custom_title,
            "slider_configs": slider_configs,
        }


# ============================================================================
# Dynamic Inputs Mixin
# ============================================================================
class DynamicInputsMixin:
    """
    Mixin for nodes with dynamically expandable and contractible input pins.
    Supports on-node interactive slider, properties panel scrub/spinbox,
    and context menu ➕ Add / ➖ Remove pin actions.
    """
    is_dynamic_inputs: bool = True
    min_inputs: int = 2
    max_inputs: int = 100
    default_input_count: int = 4
    input_prefix: str = "item_"
    input_label_prefix: str = "Item "
    input_socket_type: SocketType = SocketType.ANY

    def __init__(self, node_id: Optional[str] = None) -> None:
        super().__init__(node_id=node_id)
        self._sync_dynamic_inputs()

    def _is_dynamic_pin_id(self, spec_id: str) -> bool:
        return spec_id.startswith(self.input_prefix)

    def _get_dynamic_pin_id_and_label(self, idx: int) -> Tuple[str, str]:
        return f"{self.input_prefix}{idx}", f"{self.input_label_prefix}{idx}"

    def _sync_dynamic_inputs(self) -> bool:
        cur_count = int(self.param_values.get("count", self.default_input_count))
        cur_count = max(self.min_inputs, min(self.max_inputs, cur_count))
        self.param_values["count"] = cur_count

        sock_type = getattr(self, "input_socket_type", SocketType.ANY)
        dynamic_specs: List[InputSpec] = []
        for i in range(cur_count):
            pin_id, pin_label = self._get_dynamic_pin_id_and_label(i)
            dynamic_specs.append(
                InputSpec(pin_id, pin_label, sock_type, default=[], access=AccessMode.LIST, hide_widget=True)
            )
            if pin_id not in self.param_values:
                self.param_values[pin_id] = []

        new_inputs: List[InputSpec] = []
        dynamic_inserted = False
        for spec in self.__class__.inputs:
            if self._is_dynamic_pin_id(spec.id):
                if not dynamic_inserted:
                    new_inputs.extend(dynamic_specs)
                    dynamic_inserted = True
            else:
                new_inputs.append(copy.copy(spec))
                if spec.id not in self.param_values:
                    self.param_values[spec.id] = spec.default

        if not dynamic_inserted:
            new_inputs.extend(dynamic_specs)

        self.inputs = new_inputs
        self.is_dirty = True
        return True

    def set_param(self, input_id: str, value: Any) -> None:
        super().set_param(input_id, value)
        if input_id == "count":
            self._sync_dynamic_inputs()

    def add_input(self) -> bool:
        cur = int(self.param_values.get("count", self.default_input_count))
        if cur < self.max_inputs:
            self.set_param("count", cur + 1)
            return True
        return False

    def remove_input(self) -> bool:
        cur = int(self.param_values.get("count", self.default_input_count))
        if cur > self.min_inputs:
            self.set_param("count", cur - 1)
            return True
        return False
