# SPDX-License-Identifier: GPL-3.0-or-later
"""Built-in parametric nodes for IngeTrazo."""

from __future__ import annotations
import ast
import copy
import math
import operator
from typing import Any, Dict, List, Optional, Tuple

try:
    from ..core_types import AccessMode, CurveData, MeshData, SocketType, Vec3, extract_plane_frame
    from ..node_base import BaseNode, DynamicInputsMixin, InputSpec, OutputSpec, register_node, NODE_REGISTRY
except (ImportError, ValueError):
    from core_types import AccessMode, CurveData, MeshData, SocketType, Vec3, extract_plane_frame
    from node_base import BaseNode, DynamicInputsMixin, InputSpec, OutputSpec, register_node, NODE_REGISTRY


# ============================================================================
# 1. INPUTS & GENERATORS
# ============================================================================
@register_node
class NumberSliderNode(BaseNode):
    type_id = "input.number"
    description = "Floating-point number slider with decimal precision and customizable limits."
    title = "Number Slider"
    category = "Inputs"
    header_color = (44, 110, 130)
    inputs = [
        InputSpec("val", "Value", SocketType.FLOAT, default=2.0, min_val=-100.0, max_val=100.0, step=0.1),
    ]
    outputs = [
        OutputSpec("out", "Number", SocketType.FLOAT),
    ]

    def compute(self, val: float) -> Dict[str, Any]:
        return {"out": float(val)}


@register_node
class IntegerSliderNode(BaseNode):
    type_id = "input.integer"
    description = "Integer number slider with customizable limits and step value."
    title = "Integer Slider"
    category = "Inputs"
    header_color = (44, 110, 130)
    inputs = [
        InputSpec("val", "Value", SocketType.INT, default=5, min_val=-1000, max_val=1000, step=1),
    ]
    outputs = [
        OutputSpec("out", "Integer", SocketType.INT),
    ]

    def compute(self, val: int) -> Dict[str, Any]:
        return {"out": int(round(val))}


@register_node
class BooleanToggleNode(BaseNode):
    type_id = "input.toggle"
    title = "Boolean Toggle"
    category = "Inputs"
    description = "Sleek Grasshopper-style boolean switch. Click the button to toggle between True and False."
    header_color = (44, 110, 130)
    inputs = []
    outputs = [
        OutputSpec("out", "Value", SocketType.BOOL),
    ]

    def get_action_buttons(self) -> List[Dict[str, Any]]:
        val = bool(self.param_values.get("val", True))
        return [
            {
                "id": "btn_toggle",
                "label": "🟢 TRUE" if val else "🔴 FALSE",
                "tooltip": "Click to toggle True / False",
                "color": "#2e7d32" if val else "#c62828",
                "action": "toggle_value",
            }
        ]

    def get_card_badge_text(self) -> Optional[str]:
        return None

    def toggle_value(self) -> None:
        val = bool(self.param_values.get("val", True))
        self.set_param("val", not val)
        self.is_dirty = True

    def compute(self, val: Optional[bool] = None) -> Dict[str, Any]:
        if val is not None:
            return {"out": bool(val)}
        current = bool(self.param_values.get("val", True))
        return {"out": current}


@register_node
class StringInputNode(BaseNode):
    type_id = "input.string"
    description = "Text string input or constant."
    title = "String / Text"
    category = "Inputs"
    header_color = (44, 110, 130)
    inputs = [
        InputSpec("text", "Text", SocketType.STRING, default="Hello IngeTrazo"),
    ]
    outputs = [
        OutputSpec("out", "String", SocketType.STRING),
    ]

    def compute(self, text: str) -> Dict[str, Any]:
        return {"out": str(text)}


@register_node
class PanelNode(BaseNode):
    type_id = "input.panel"
    title = "Panel"
    category = "Inputs"
    description = (
        "Grasshopper-style multi-line data inspector and input panel.\n"
        "• When wired: acts as a data viewer, formatting items with indices [0], [1]...\n"
        "• When unwired: type multi-line numbers, text, or coordinates (x, y, z) to output as lists."
    )
    header_color = (44, 110, 130)
    inputs = [
        InputSpec("data", "Data", SocketType.ANY, default=None, access=AccessMode.LIST, hide_widget=True),
    ]
    outputs = [
        OutputSpec("out", "Output", SocketType.ANY),
    ]

    def compute(self, data: Any = None, text: Optional[str] = None) -> Dict[str, Any]:
        if data is not None and (not isinstance(data, list) or len(data) > 0):
            display_str = self._format_data(data)
            return {"out": data, "text": display_str}
        else:
            raw_text = text if text is not None else str(self.param_values.get("text", ""))
            parsed = self._parse_text(raw_text)
            return {"out": parsed, "text": raw_text}

    def _format_data(self, val: Any, max_items: int = 100) -> str:
        if isinstance(val, (list, tuple)):
            if not val:
                return "[Empty List]"
            lines = []
            for i, item in enumerate(val[:max_items]):
                lines.append(f"[{i}] {self._format_item(item)}")
            if len(val) > max_items:
                lines.append(f"... ({len(val) - max_items} more items, total {len(val)})")
            return "\n".join(lines)
        return self._format_item(val)

    def _format_item(self, item: Any) -> str:
        if item is None:
            return "None"
        if isinstance(item, Vec3):
            return f"Point({item.x:.2f}, {item.y:.2f}, {item.z:.2f})"
        if isinstance(item, MeshData):
            closed_str = "closed" if getattr(item, "is_closed", False) else "open"
            return f"MeshData ({len(item.vertices)} verts, {len(item.faces)} faces, {closed_str})"
        if isinstance(item, CurveData):
            return f"CurveData ({len(item.points)} pts, closed={item.closed})"
        if isinstance(item, float):
            return f"{item:.4f}".rstrip("0").rstrip(".") or "0"
        return str(item)

    def _parse_text(self, text: str) -> Any:
        if not text or not text.strip():
            return ""
        raw_lines = text.splitlines()
        lines = [ln.strip() for ln in raw_lines if ln.strip()]
        if not lines:
            return ""
        parsed = []
        for line in lines:
            if line.lower() == "true":
                parsed.append(True)
                continue
            if line.lower() == "false":
                parsed.append(False)
                continue
            # Try parsing Vec3 / Point coordinate: e.g. "1, 2, 3" or "(1, 2, 3)"
            clean_coord = line.strip("()[]{}")
            if "," in clean_coord:
                parts = [p.strip() for p in clean_coord.split(",")]
                if len(parts) in (2, 3):
                    try:
                        x = float(parts[0])
                        y = float(parts[1])
                        z = float(parts[2]) if len(parts) == 3 else 0.0
                        parsed.append(Vec3(x, y, z))
                        continue
                    except ValueError:
                        pass
            try:
                parsed.append(int(line))
                continue
            except ValueError:
                pass
            try:
                parsed.append(float(line))
                continue
            except ValueError:
                pass
            parsed.append(line)

        if len(lines) == 1 and "\n" not in text:
            return parsed[0]
        return parsed


@register_node
class SeriesNode(BaseNode):
    type_id = "math.series"
    description = "Generates an arithmetic series of numbers."
    title = "Series (Range)"
    category = "Math"
    header_color = (60, 100, 140)
    inputs = [
        InputSpec("start", "Start", SocketType.FLOAT, default=0.0, step=0.5),
        InputSpec("step", "Step", SocketType.FLOAT, default=3.0, step=0.5),
        InputSpec("count", "Count", SocketType.INT, default=4, min_val=1, max_val=500, step=1),
    ]
    outputs = [
        OutputSpec("seq", "List", SocketType.FLOAT),
    ]

    def compute(self, start: float, step: float, count: int) -> Dict[str, Any]:
        n = max(0, min(2000, int(count)))
        return {"seq": [start + i * step for i in range(n)]}


# Safe AST math environment for ExpressionNode
_SAFE_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow, ast.USub: operator.neg,
}
_SAFE_FUNCS = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "sqrt": math.sqrt, "abs": abs, "min": min, "max": max,
    "pi": math.pi, "rad": math.radians, "deg": math.degrees,
}


def _eval_ast(node: ast.AST, env: Dict[str, Any]) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name) and node.id in env:
        return float(env[node.id])
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
        return float(_SAFE_OPS[type(node.op)](_eval_ast(node.left, env), _eval_ast(node.right, env)))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
        return float(_SAFE_OPS[type(node.op)](_eval_ast(node.operand, env)))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _SAFE_FUNCS:
        fn = _SAFE_FUNCS[node.func.id]
        args = [_eval_ast(a, env) for a in node.args]
        return float(fn(*args))
    raise ValueError(f"Unsupported expression syntax: {ast.dump(node)}")


@register_node
class MathExpressionNode(BaseNode):
    type_id = "math.expression"
    description = "Evaluates a mathematical formula expression f(x, y)."
    title = "Math Expression"
    category = "Math"
    header_color = (60, 100, 140)
    inputs = [
        InputSpec("expr", "f(x,y)", SocketType.STRING, default="sin(x) * cos(y) + 2.0"),
        InputSpec("x", "x", SocketType.FLOAT, default=1.0, step=0.25),
        InputSpec("y", "y", SocketType.FLOAT, default=1.0, step=0.25),
    ]
    outputs = [
        OutputSpec("result", "Result", SocketType.FLOAT),
    ]

    def compute(self, expr: str, x: float, y: float) -> Dict[str, Any]:
        tree = ast.parse(expr.strip(), mode="eval")
        env = {**_SAFE_FUNCS, "x": x, "y": y}
        return {"result": _eval_ast(tree.body, env)}


@register_node
class DivideDomainNode(BaseNode):
    type_id = "math.divide_domain"
    description = "Divides a numeric range or interval into N equal steps."
    title = "Divide Domain"
    category = "Math"
    header_color = (60, 100, 140)
    inputs = [
        InputSpec("start", "Start", SocketType.FLOAT, default=0.0, step=0.5),
        InputSpec("end", "End", SocketType.FLOAT, default=10.0, step=0.5),
        InputSpec("count", "Segments", SocketType.INT, default=10, min_val=1, max_val=1000, step=1),
    ]
    outputs = [
        OutputSpec("seq", "List", SocketType.FLOAT),
        OutputSpec("step", "Step Size", SocketType.FLOAT),
    ]

    def compute(self, start: float, end: float, count: int) -> Dict[str, Any]:
        n = max(1, min(2000, int(count)))
        step = (end - start) / float(n)
        return {
            "seq": [start + i * step for i in range(n + 1)],
            "step": step,
        }


@register_node
class CrossReferenceNode(BaseNode):
    type_id = "math.cross_reference"
    description = "Performs Cartesian cross-referencing between two lists."
    title = "Cross Reference"
    category = "Lists"
    header_color = (60, 100, 140)
    inputs = [
        InputSpec("list_a", "List A", SocketType.ANY, default=[], access=AccessMode.LIST, hide_widget=True),
        InputSpec("list_b", "List B", SocketType.ANY, default=[], access=AccessMode.LIST, hide_widget=True),
    ]
    outputs = [
        OutputSpec("a_out", "A x B", SocketType.ANY),
        OutputSpec("b_out", "B x A", SocketType.ANY),
    ]

    def compute(self, list_a: List[Any], list_b: List[Any]) -> Dict[str, Any]:
        la = list(list_a) if isinstance(list_a, (list, tuple)) else ([list_a] if list_a is not None else [])
        lb = list(list_b) if isinstance(list_b, (list, tuple)) else ([list_b] if list_b is not None else [])
        if not la or not lb:
            return {"a_out": [], "b_out": []}
        out_a: List[Any] = []
        out_b: List[Any] = []
        for a in la:
            for b in lb:
                out_a.append(a)
                out_b.append(b)
        return {"a_out": out_a, "b_out": out_b}


# ============================================================================
# 3B. LIST PROCESSING & AGGREGATION NODES
# ============================================================================
@register_node
class CreateListNode(DynamicInputsMixin, BaseNode):
    type_id = "list.create"
    description = "Creates a combined list from multiple individual items or sub-lists (Grasshopper Merge parity)."
    title = "Create List"
    category = "Lists"
    header_color = (60, 100, 140)
    icon_tag = "📋"
    min_inputs = 2
    max_inputs = 100
    default_input_count = 4
    input_prefix = "item_"
    input_label_prefix = "Item "
    inputs = [
        InputSpec("count", "Inputs", SocketType.INT, default=4, min_val=2, max_val=100, step=1, hide_socket=True),
        InputSpec("item_0", "Item 0", SocketType.ANY, default=[], access=AccessMode.LIST, hide_widget=True),
        InputSpec("item_1", "Item 1", SocketType.ANY, default=[], access=AccessMode.LIST, hide_widget=True),
        InputSpec("item_2", "Item 2", SocketType.ANY, default=[], access=AccessMode.LIST, hide_widget=True),
        InputSpec("item_3", "Item 3", SocketType.ANY, default=[], access=AccessMode.LIST, hide_widget=True),
        InputSpec("flatten", "Flatten", SocketType.BOOL, default=True),
    ]
    outputs = [
        OutputSpec("list", "List", SocketType.ANY),
        OutputSpec("length", "Length", SocketType.INT),
    ]

    def compute(
        self,
        item_0: Any = None,
        item_1: Any = None,
        item_2: Any = None,
        item_3: Any = None,
        flatten: bool = True,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        count = int(kwargs.get("count", self.param_values.get("count", self.default_input_count)))
        flatten = bool(flatten if "flatten" not in kwargs else kwargs.get("flatten"))
        res: List[Any] = []

        def _collect(val: Any) -> None:
            if flatten and isinstance(val, (list, tuple)):
                for sub in val:
                    _collect(sub)
            else:
                res.append(val)

        kwargs["item_0"] = item_0 if item_0 is not None else kwargs.get("item_0")
        kwargs["item_1"] = item_1 if item_1 is not None else kwargs.get("item_1")
        kwargs["item_2"] = item_2 if item_2 is not None else kwargs.get("item_2")
        kwargs["item_3"] = item_3 if item_3 is not None else kwargs.get("item_3")

        for i in range(count):
            val = kwargs.get(f"item_{i}")
            if val is None:
                continue
            if isinstance(val, (list, tuple)):
                for it in val:
                    if it is not None:
                        _collect(it)
            else:
                _collect(val)

        return {"list": res, "length": len(res)}


@register_node
class MergeListNode(DynamicInputsMixin, BaseNode):
    type_id = "list.merge"
    description = "Merges multiple data streams into a single list (Grasshopper Merge node parity)."
    title = "Merge (List)"
    category = "Lists"
    header_color = (60, 100, 140)
    icon_tag = "🔀"
    min_inputs = 2
    max_inputs = 100
    default_input_count = 4
    input_prefix = "d"
    input_label_prefix = "D"
    inputs = [
        InputSpec("count", "Inputs", SocketType.INT, default=4, min_val=2, max_val=100, step=1, hide_socket=True),
        InputSpec("d0", "D0", SocketType.ANY, default=[], access=AccessMode.LIST, hide_widget=True),
        InputSpec("d1", "D1", SocketType.ANY, default=[], access=AccessMode.LIST, hide_widget=True),
        InputSpec("d2", "D2", SocketType.ANY, default=[], access=AccessMode.LIST, hide_widget=True),
        InputSpec("d3", "D3", SocketType.ANY, default=[], access=AccessMode.LIST, hide_widget=True),
        InputSpec("flatten", "Flatten", SocketType.BOOL, default=True),
    ]
    outputs = [
        OutputSpec("result", "Result", SocketType.ANY),
        OutputSpec("length", "Length", SocketType.INT),
    ]

    def compute(
        self,
        d0: Any = None,
        d1: Any = None,
        d2: Any = None,
        d3: Any = None,
        flatten: bool = True,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        count = int(kwargs.get("count", self.param_values.get("count", self.default_input_count)))
        flatten = bool(flatten if "flatten" not in kwargs else kwargs.get("flatten"))
        res: List[Any] = []

        def _collect(val: Any) -> None:
            if flatten and isinstance(val, (list, tuple)):
                for sub in val:
                    _collect(sub)
            else:
                res.append(val)

        kwargs["d0"] = d0 if d0 is not None else kwargs.get("d0")
        kwargs["d1"] = d1 if d1 is not None else kwargs.get("d1")
        kwargs["d2"] = d2 if d2 is not None else kwargs.get("d2")
        kwargs["d3"] = d3 if d3 is not None else kwargs.get("d3")

        for i in range(count):
            val = kwargs.get(f"d{i}")
            if val is None:
                continue
            if isinstance(val, (list, tuple)):
                for it in val:
                    if it is not None:
                        _collect(it)
            else:
                _collect(val)

        return {"result": res, "length": len(res)}


@register_node
class ListJoinNode(DynamicInputsMixin, BaseNode):
    type_id = "list.join"
    description = "Combines multiple lists into a single concatenated list."
    title = "List Join"
    category = "Lists"
    header_color = (60, 100, 140)
    icon_tag = "➕"
    min_inputs = 2
    max_inputs = 100
    default_input_count = 2
    input_prefix = "list_"
    inputs = [
        InputSpec("count", "Inputs", SocketType.INT, default=2, min_val=2, max_val=100, step=1, hide_socket=True),
        InputSpec("list_a", "List A", SocketType.ANY, default=[], access=AccessMode.LIST, hide_widget=True),
        InputSpec("list_b", "List B", SocketType.ANY, default=[], access=AccessMode.LIST, hide_widget=True),
        InputSpec("flatten", "Flatten", SocketType.BOOL, default=False),
    ]
    outputs = [
        OutputSpec("list", "Combined List", SocketType.ANY),
        OutputSpec("length", "Length", SocketType.INT),
    ]

    def _is_dynamic_pin_id(self, spec_id: str) -> bool:
        return spec_id.startswith("list_") and spec_id != "list_in"

    def _get_dynamic_pin_id_and_label(self, idx: int) -> Tuple[str, str]:
        letter = chr(ord('a') + idx) if idx < 26 else str(idx)
        return f"list_{letter}", f"List {letter.upper()}"

    def compute(
        self,
        list_a: Any = None,
        list_b: Any = None,
        flatten: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        count = int(kwargs.get("count", self.param_values.get("count", self.default_input_count)))
        flatten = bool(flatten if "flatten" not in kwargs else kwargs.get("flatten"))
        res: List[Any] = []

        def _add(items: List[Any]) -> None:
            for it in items:
                if it is None:
                    continue
                if flatten and isinstance(it, (list, tuple)):
                    for sub in it:
                        _add([sub])
                else:
                    res.append(it)

        kwargs["list_a"] = list_a if list_a is not None else kwargs.get("list_a")
        kwargs["list_b"] = list_b if list_b is not None else kwargs.get("list_b")

        for i in range(count):
            letter = chr(ord('a') + i) if i < 26 else str(i)
            val = kwargs.get(f"list_{letter}", kwargs.get(f"list_{i}"))
            if val is None:
                continue
            la = list(val) if isinstance(val, (list, tuple)) else ([val] if val is not None else [])
            _add(la)

        return {"list": res, "length": len(res)}


@register_node
class ListItemNode(BaseNode):
    type_id = "list.item"
    description = "Retrieves an item from a list at the specified index (Grasshopper List Item parity)."
    title = "List Item"
    category = "Lists"
    header_color = (60, 100, 140)
    icon_tag = "🔍"
    inputs = [
        InputSpec("list_in", "List", SocketType.ANY, default=[], access=AccessMode.LIST, hide_widget=True),
        InputSpec("index", "Index", SocketType.INT, default=0, step=1, access=AccessMode.ITEM),
        InputSpec("wrap", "Wrap Index", SocketType.BOOL, default=True, access=AccessMode.ITEM),
    ]
    outputs = [
        OutputSpec("item", "Item", SocketType.ANY),
    ]

    def compute(self, list_in: List[Any], index: int = 0, wrap: bool = True) -> Dict[str, Any]:
        if not list_in:
            return {"item": None}
        n = len(list_in)
        if wrap:
            idx = int(index) % n
        else:
            idx = max(0, min(int(index), n - 1))
        return {"item": list_in[idx]}


@register_node
class ListLengthNode(BaseNode):
    type_id = "list.length"
    description = "Measures the number of items in a list (Grasshopper List Length parity)."
    title = "List Length"
    category = "Lists"
    header_color = (60, 100, 140)
    icon_tag = "#"
    inputs = [
        InputSpec("list_in", "List", SocketType.ANY, default=[], access=AccessMode.LIST, hide_widget=True),
    ]
    outputs = [
        OutputSpec("length", "Length", SocketType.INT),
    ]

    def compute(self, list_in: List[Any]) -> Dict[str, Any]:
        return {"length": len(list_in)}


@register_node
class ReverseListNode(BaseNode):
    type_id = "list.reverse"
    description = "Reverses the order of items in a list."
    title = "Reverse List"
    category = "Lists"
    header_color = (60, 100, 140)
    icon_tag = "🔁"
    inputs = [
        InputSpec("list_in", "List", SocketType.ANY, default=[], access=AccessMode.LIST, hide_widget=True),
    ]
    outputs = [
        OutputSpec("list", "Reversed List", SocketType.ANY),
        OutputSpec("length", "Length", SocketType.INT),
    ]

    def compute(self, list_in: List[Any]) -> Dict[str, Any]:
        rev = list(reversed(list_in))
        return {"list": rev, "length": len(rev)}


@register_node
class FlattenListNode(BaseNode):
    type_id = "list.flatten"
    description = "Flattens nested lists or tuples into a flat 1-dimensional list."
    title = "Flatten List"
    category = "Lists"
    header_color = (60, 100, 140)
    icon_tag = "⬇️"
    inputs = [
        InputSpec("list_in", "List", SocketType.ANY, default=[], access=AccessMode.LIST, hide_widget=True),
    ]
    outputs = [
        OutputSpec("list", "Flattened List", SocketType.ANY),
        OutputSpec("length", "Length", SocketType.INT),
    ]

    def compute(self, list_in: List[Any]) -> Dict[str, Any]:
        flat: List[Any] = []

        def _flat(it: Any) -> None:
            if isinstance(it, (list, tuple)):
                for sub in it:
                    _flat(sub)
            else:
                flat.append(it)

        for elem in list_in:
            _flat(elem)
        return {"list": flat, "length": len(flat)}


@register_node
class MathAddNode(BaseNode):
    type_id = "math.add"
    description = "Adds numbers, vectors, or lists."
    title = "Add"
    category = "Math"
    header_color = (60, 100, 140)
    inputs = [
        InputSpec("a", "A", SocketType.ANY, default=0.0),
        InputSpec("b", "B", SocketType.ANY, default=0.0),
    ]
    outputs = [
        OutputSpec("res", "Result", SocketType.ANY),
    ]

    def compute(self, a: Any, b: Any) -> Dict[str, Any]:
        if isinstance(a, Vec3) and isinstance(b, Vec3):
            return {"res": a + b}
        if isinstance(a, Vec3):
            return {"res": Vec3(a.x + float(b), a.y + float(b), a.z + float(b))}
        if isinstance(b, Vec3):
            return {"res": Vec3(float(a) + b.x, float(a) + b.y, float(a) + b.z)}
        try:
            return {"res": float(a) + float(b)}
        except Exception:
            return {"res": 0.0}


@register_node
class MathSubtractNode(BaseNode):
    type_id = "math.subtract"
    description = "Subtracts input B from input A."
    title = "Subtract"
    category = "Math"
    header_color = (60, 100, 140)
    inputs = [
        InputSpec("a", "A", SocketType.ANY, default=0.0),
        InputSpec("b", "B", SocketType.ANY, default=0.0),
    ]
    outputs = [
        OutputSpec("res", "Result", SocketType.ANY),
    ]

    def compute(self, a: Any, b: Any) -> Dict[str, Any]:
        if isinstance(a, Vec3) and isinstance(b, Vec3):
            return {"res": a - b}
        if isinstance(a, Vec3):
            return {"res": Vec3(a.x - float(b), a.y - float(b), a.z - float(b))}
        if isinstance(b, Vec3):
            return {"res": Vec3(float(a) - b.x, float(a) - b.y, float(a) - b.z)}
        try:
            return {"res": float(a) - float(b)}
        except Exception:
            return {"res": 0.0}


@register_node
class MathMultiplyNode(BaseNode):
    type_id = "math.multiply"
    description = "Multiplies numbers, vectors, or lists."
    title = "Multiply"
    category = "Math"
    header_color = (60, 100, 140)
    inputs = [
        InputSpec("a", "A", SocketType.ANY, default=1.0),
        InputSpec("b", "B", SocketType.ANY, default=1.0),
    ]
    outputs = [
        OutputSpec("res", "Result", SocketType.ANY),
    ]

    def compute(self, a: Any, b: Any) -> Dict[str, Any]:
        if isinstance(a, Vec3):
            return {"res": a * float(b)}
        if isinstance(b, Vec3):
            return {"res": b * float(a)}
        try:
            return {"res": float(a) * float(b)}
        except Exception:
            return {"res": 0.0}


@register_node
class MathDivideNode(BaseNode):
    type_id = "math.divide"
    description = "Divides input A by input B."
    title = "Divide"
    category = "Math"
    header_color = (60, 100, 140)
    inputs = [
        InputSpec("a", "A", SocketType.ANY, default=1.0),
        InputSpec("b", "B", SocketType.ANY, default=1.0),
    ]
    outputs = [
        OutputSpec("res", "Result", SocketType.ANY),
    ]

    def compute(self, a: Any, b: Any) -> Dict[str, Any]:
        try:
            fb = float(b)
            if abs(fb) < 1e-12:
                return {"res": 0.0}
            if isinstance(a, Vec3):
                return {"res": Vec3(a.x / fb, a.y / fb, a.z / fb)}
            return {"res": float(a) / fb}
        except Exception:
            return {"res": 0.0}


# ============================================================================
# 2. POINTS, VECTORS & GRIDS
# ============================================================================
@register_node
class ConstructPointNode(BaseNode):
    type_id = "vec.point_xyz"
    description = "Constructs a 3D point from X, Y, Z coordinates."
    title = "Point XYZ"
    category = "Points & Vectors"
    header_color = (58, 125, 68)
    inputs = [
        InputSpec("x", "X (m)", SocketType.FLOAT, default=0.0, step=0.5),
        InputSpec("y", "Y (m)", SocketType.FLOAT, default=0.0, step=0.5),
        InputSpec("z", "Z (m)", SocketType.FLOAT, default=0.0, step=0.5),
    ]
    outputs = [
        OutputSpec("pt", "Point", SocketType.VEC3),
    ]

    def compute(self, x: float, y: float, z: float) -> Dict[str, Any]:
        return {"pt": Vec3(x, y, z)}


@register_node
class PointGrid2DNode(BaseNode):
    type_id = "vec.grid_2d"
    description = "Generates a 2D regular grid of points with spacing and counts."
    title = "Point Grid (2D)"
    category = "Points & Vectors"
    header_color = (58, 125, 68)
    inputs = [
        InputSpec("origin", "Origin", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("nx", "Count X", SocketType.INT, default=3, min_val=1, max_val=100, step=1),
        InputSpec("ny", "Count Y", SocketType.INT, default=3, min_val=1, max_val=100, step=1),
        InputSpec("sx", "Spacing X", SocketType.FLOAT, default=4.0, min_val=0.05, step=0.5),
        InputSpec("sy", "Spacing Y", SocketType.FLOAT, default=4.0, min_val=0.05, step=0.5),
    ]
    outputs = [
        OutputSpec("points", "Points", SocketType.VEC3),
    ]

    def compute(self, origin: Vec3, nx: int, ny: int, sx: float, sy: float) -> Dict[str, Any]:
        pts: List[Vec3] = []
        for ix in range(max(1, nx)):
            for iy in range(max(1, ny)):
                pts.append(Vec3(origin.x + ix * sx, origin.y + iy * sy, origin.z))
        return {"points": pts}


@register_node
class DeconstructPointNode(BaseNode):
    type_id = "vec.deconstruct"
    description = "Deconstructs a point or vector into its X, Y, Z coordinate components."
    title = "Deconstruct Point"
    category = "Points & Vectors"
    header_color = (58, 125, 68)
    inputs = [
        InputSpec("pt", "Point", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
    ]
    outputs = [
        OutputSpec("x", "X", SocketType.FLOAT),
        OutputSpec("y", "Y", SocketType.FLOAT),
        OutputSpec("z", "Z", SocketType.FLOAT),
    ]

    def compute(self, pt: Vec3) -> Dict[str, Any]:
        p = pt if isinstance(pt, Vec3) else Vec3()
        return {"x": float(p.x), "y": float(p.y), "z": float(p.z)}


@register_node
class DistanceNode(BaseNode):
    type_id = "vec.distance"
    description = "Calculates Euclidean distance between two points."
    title = "Distance"
    category = "Points & Vectors"
    header_color = (58, 125, 68)
    inputs = [
        InputSpec("a", "Point A", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("b", "Point B", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
    ]
    outputs = [
        OutputSpec("dist", "Distance", SocketType.FLOAT),
    ]

    def compute(self, a: Vec3, b: Vec3) -> Dict[str, Any]:
        pa = a if isinstance(a, Vec3) else Vec3()
        pb = b if isinstance(b, Vec3) else Vec3()
        return {"dist": pa.distance_to(pb)}


@register_node
class VectorMathNode(BaseNode):
    type_id = "vec.math"
    description = "Performs vector arithmetic (Addition, Subtraction, Dot Product, Cross Product, Normalization)."
    title = "Vector Math"
    category = "Points & Vectors"
    header_color = (58, 125, 68)
    inputs = [
        InputSpec("a", "Vector A", SocketType.VEC3, default=Vec3(0, 0, 1), hide_widget=True),
        InputSpec("b", "Vector B", SocketType.VEC3, default=Vec3(0, 1, 0), hide_widget=True),
        InputSpec("op", "Operation", SocketType.STRING, default="Add", choices=["Add", "Subtract", "Cross Product", "Dot Product", "Normalize A"]),
    ]
    outputs = [
        OutputSpec("vec", "Vector", SocketType.VEC3),
        OutputSpec("val", "Scalar", SocketType.FLOAT),
    ]

    def compute(self, a: Vec3, b: Vec3, op: str) -> Dict[str, Any]:
        va = a if isinstance(a, Vec3) else Vec3()
        vb = b if isinstance(b, Vec3) else Vec3()
        if op == "Add":
            return {"vec": va + vb, "val": (va + vb).length()}
        elif op == "Subtract":
            return {"vec": va - vb, "val": (va - vb).length()}
        elif op == "Cross Product":
            cp = va.cross(vb)
            return {"vec": cp, "val": cp.length()}
        elif op == "Dot Product":
            dp = va.dot(vb)
            return {"vec": Vec3(), "val": dp}
        elif op == "Normalize A":
            norm = va.normalized()
            return {"vec": norm, "val": 1.0}
        return {"vec": va, "val": 0.0}


@register_node
class PlaneFromNormalNode(BaseNode):
    type_id = "vec.plane_normal"
    title = "Plane from Normal"
    category = "Points & Vectors"
    description = (
        "Constructs an orthonormal 3D plane coordinate system from an origin point and normal vector.\n"
        "Emits origin, unit normal, unit U (X-axis in plane), unit V (Y-axis in plane), a visual preview rectangle, and a plane dictionary."
    )
    header_color = (58, 125, 68)

    inputs = [
        InputSpec("origin", "Origin", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("normal", "Normal", SocketType.VEC3, default=Vec3(0, 0, 1), hide_widget=True),
        InputSpec("size", "Preview Size (m)", SocketType.FLOAT, default=2.0, min_val=0.1, step=0.5),
    ]
    outputs = [
        OutputSpec("origin", "Origin", SocketType.VEC3),
        OutputSpec("normal", "Normal", SocketType.VEC3),
        OutputSpec("u_axis", "U Axis (X)", SocketType.VEC3),
        OutputSpec("v_axis", "V Axis (Y)", SocketType.VEC3),
        OutputSpec("preview", "Plane Preview", SocketType.CURVE),
        OutputSpec("plane", "Plane", SocketType.ANY),
    ]

    def compute(self, origin: Any = None, normal: Any = None, size: float = 2.0) -> Dict[str, Any]:
        p0 = origin if isinstance(origin, Vec3) else Vec3(0, 0, 0)
        n = normal if isinstance(normal, Vec3) else Vec3(0, 0, 1)

        length = math.sqrt(n.x * n.x + n.y * n.y + n.z * n.z)
        if length < 1e-6:
            n = Vec3(0, 0, 1)
        else:
            n = Vec3(n.x / length, n.y / length, n.z / length)

        if abs(n.z) < 0.9:
            guide = Vec3(0, 0, 1)
        else:
            guide = Vec3(1, 0, 0)

        # U = normalize(guide x n)
        u_raw = Vec3(
            guide.y * n.z - guide.z * n.y,
            guide.z * n.x - guide.x * n.z,
            guide.x * n.y - guide.y * n.x,
        )
        u_len = math.sqrt(u_raw.x * u_raw.x + u_raw.y * u_raw.y + u_raw.z * u_raw.z)
        u = Vec3(u_raw.x / u_len, u_raw.y / u_len, u_raw.z / u_len)

        # V = normalize(n x u)
        v = Vec3(
            n.y * u.z - n.z * u.y,
            n.z * u.x - n.x * u.z,
            n.x * u.y - n.y * u.x,
        )

        s = float(size) * 0.5
        c0 = p0 - u * s - v * s
        c1 = p0 + u * s - v * s
        c2 = p0 + u * s + v * s
        c3 = p0 - u * s + v * s
        preview_curve = CurveData(points=[c0, c1, c2, c3], closed=True)

        plane_dict = {
            "origin": (p0.x, p0.y, p0.z),
            "normal": (n.x, n.y, n.z),
            "u": (u.x, u.y, u.z),
            "v": (v.x, v.y, v.z),
        }

        return {
            "origin": p0,
            "normal": n,
            "u_axis": u,
            "v_axis": v,
            "preview": preview_curve,
            "plane": plane_dict,
        }


# ============================================================================
# 3. 2D PROFILES & 3D WATERTIGHT SOLIDS
# ============================================================================
@register_node
class RectangleProfileNode(BaseNode):
    type_id = "curve.rectangle_profile"
    icon = "curve.rectangle_profile.png"
    description = (
        "Generates a 2D rectangular profile polyline from origin and dimensions.\n"
        "Supports drawing from corner or centered, with optional plane orientation."
    )
    title = "Rectangle Profile"
    category = "Curves"
    header_color = (165, 105, 45)
    inputs = [
        InputSpec("origin", "Origin / Plane", SocketType.ANY, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("plane", "Plane", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("width", "Width (X)", SocketType.FLOAT, default=4.0, min_val=0.01, step=0.25),
        InputSpec("length", "Length (Y)", SocketType.FLOAT, default=3.0, min_val=0.01, step=0.25),
        InputSpec("centered", "Center", SocketType.BOOL, default=False),
    ]
    outputs = [
        OutputSpec("curve", "Profile", SocketType.CURVE),
    ]

    def compute(
        self,
        origin: Any = None,
        width: float = 4.0,
        length: float = 3.0,
        centered: bool = False,
        plane: Any = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        frame_src = plane if plane is not None else origin
        p0, u, v, n = extract_plane_frame(frame_src)
        w = max(1e-4, float(width))
        l = max(1e-4, float(length))
        if centered:
            hw, hl = w * 0.5, l * 0.5
            x0, x1 = -hw, hw
            y0, y1 = -hl, hl
        else:
            x0, x1 = 0.0, w
            y0, y1 = 0.0, l

        local_pts = [
            (x0, y0),
            (x1, y0),
            (x1, y1),
            (x0, y1),
        ]
        pts = [
            Vec3(p0.x + lx * u.x + ly * v.x, p0.y + lx * u.y + ly * v.y, p0.z + lx * u.z + ly * v.z)
            for lx, ly in local_pts
        ]
        return {"curve": CurveData(points=pts, closed=True)}


@register_node
class BoxSolidNode(BaseNode):
    type_id = "solid.box"
    description = (
        "Generates a 3D watertight cuboid / box solid.\n"
        "Supports drawing from corner or centered on origin/plane, with optional plane orientation."
    )
    title = "Box (Cuboid)"
    category = "3D Solids"
    header_color = (125, 70, 150)
    inputs = [
        InputSpec("origin", "Origin / Plane", SocketType.ANY, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("plane", "Plane", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("dx", "Size X (m)", SocketType.FLOAT, default=2.0, min_val=0.01, step=0.2),
        InputSpec("dy", "Size Y (m)", SocketType.FLOAT, default=2.0, min_val=0.01, step=0.2),
        InputSpec("dz", "Height Z (m)", SocketType.FLOAT, default=3.0, min_val=0.01, step=0.2),
        InputSpec("centered", "Center", SocketType.BOOL, default=False),
        InputSpec("center_z", "Center Z", SocketType.BOOL, default=False),
    ]
    outputs = [
        OutputSpec("mesh", "Solid", SocketType.MESH),
    ]

    def compute(
        self,
        origin: Any = None,
        dx: float = 2.0,
        dy: float = 2.0,
        dz: float = 3.0,
        centered: bool = False,
        center_z: bool = False,
        plane: Any = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        return {
            "mesh": MeshData.create_box(
                origin=origin,
                dx=dx,
                dy=dy,
                dz=dz,
                centered=bool(centered),
                center_z=bool(center_z),
                plane=plane,
            )
        }


@register_node
class CylinderSolidNode(BaseNode):
    type_id = "solid.cylinder"
    description = "Generates a 3D watertight cylinder or architectural column solid."
    title = "Cylinder / Column"
    category = "3D Solids"
    header_color = (125, 70, 150)
    inputs = [
        InputSpec("center", "Base Pt", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("radius", "Radius (m)", SocketType.FLOAT, default=0.3, min_val=0.01, step=0.05),
        InputSpec("height", "Height (m)", SocketType.FLOAT, default=3.2, min_val=0.01, step=0.2),
        InputSpec("segments", "Segments", SocketType.INT, default=24, min_val=3, max_val=128, step=1),
    ]
    outputs = [
        OutputSpec("mesh", "Solid", SocketType.MESH),
    ]

    def compute(self, center: Vec3, radius: float, height: float, segments: int) -> Dict[str, Any]:
        return {"mesh": MeshData.create_cylinder(center, radius, height, segments)}


@register_node
class SphereSolidNode(BaseNode):
    type_id = "solid.sphere"
    description = "Generates a 3D watertight UV sphere solid."
    title = "Sphere"
    category = "3D Solids"
    header_color = (125, 70, 150)
    inputs = [
        InputSpec("center", "Center Pt", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("radius", "Radius (m)", SocketType.FLOAT, default=1.0, min_val=0.01, step=0.1),
        InputSpec("rings", "Rings (Lat)", SocketType.INT, default=16, min_val=3, max_val=64, step=1),
        InputSpec("segments", "Segments (Lon)", SocketType.INT, default=24, min_val=3, max_val=128, step=1),
    ]
    outputs = [
        OutputSpec("mesh", "Solid", SocketType.MESH),
    ]

    def compute(self, center: Vec3, radius: float, rings: int, segments: int) -> Dict[str, Any]:
        return {"mesh": MeshData.create_sphere(center, radius, rings, segments)}


@register_node
class MeshFromPointsNode(BaseNode):
    type_id = "solid.mesh_from_points"
    description = "Generates a 3D mesh surface from a grid or array of points."
    title = "Mesh From Points"
    category = "3D Solids"
    header_color = (125, 70, 150)
    inputs = [
        InputSpec("points", "Grid Points", SocketType.ANY, default=[], access=AccessMode.LIST, hide_widget=True),
        InputSpec("u", "U Count", SocketType.INT, default=10, min_val=2, max_val=200, step=1),
        InputSpec("v", "V Count", SocketType.INT, default=0, min_val=0, max_val=200, step=1),
        InputSpec("closed_u", "Closed U", SocketType.BOOL, default=False),
        InputSpec("closed_v", "Closed V", SocketType.BOOL, default=False),
        InputSpec("swap_uv", "Swap UV", SocketType.BOOL, default=False),
        InputSpec("triangulate", "Triangulate", SocketType.BOOL, default=False),
        InputSpec("flip_normals", "Flip Normals", SocketType.BOOL, default=False),
    ]
    outputs = [
        OutputSpec("mesh", "Mesh", SocketType.MESH),
    ]

    def compute(
        self,
        points: List[Any],
        u: int,
        v: int,
        closed_u: bool,
        closed_v: bool,
        swap_uv: bool,
        triangulate: bool,
        flip_normals: bool = False,
    ) -> Dict[str, Any]:
        return {
            "mesh": MeshData.create_from_points(
                pts=points,
                u_count=u,
                v_count=v,
                closed_u=closed_u,
                closed_v=closed_v,
                swap_uv=swap_uv,
                triangulate=triangulate,
                flip_normals=flip_normals,
                name="TerrainMesh",
            )
        }


# ============================================================================
# 4. TRANSFORMS & SCENE OUTPUT
# ============================================================================
@register_node
class TransformMeshNode(BaseNode):
    type_id = "transform.move_rot_scale"
    description = "Applies translation, rotation, and uniform scaling to 3D geometry."
    title = "Transform Solid"
    category = "Transforms"
    header_color = (90, 95, 135)
    inputs = [
        InputSpec("mesh", "Solid", SocketType.MESH, default=None, hide_widget=True),
        InputSpec("offset", "Move XYZ", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("rot_z", "Rotate Z (°)", SocketType.FLOAT, default=0.0, step=5.0),
        InputSpec("scale", "Uniform Scale", SocketType.FLOAT, default=1.0, min_val=0.01, step=0.1),
    ]
    outputs = [
        OutputSpec("mesh", "Solid", SocketType.MESH),
    ]

    def compute(self, mesh: MeshData, offset: Vec3, rot_z: float, scale: float) -> Dict[str, Any]:
        if not isinstance(mesh, MeshData):
            return {"mesh": MeshData()}
        s_vec = Vec3(scale, scale, scale)
        return {"mesh": mesh.transformed(offset=offset, rot_z_deg=rot_z, scale=s_vec)}


@register_node
class MergeMeshesNode(BaseNode):
    type_id = "transform.merge"
    description = "Merges multiple solids or meshes into a single compound geometry."
    title = "Merge Solids"
    category = "Transforms"
    header_color = (90, 95, 135)
    inputs = [
        InputSpec("meshes", "Solids List", SocketType.MESH, default=[], access=AccessMode.LIST, hide_widget=True),
    ]
    outputs = [
        OutputSpec("merged", "Merged Solid", SocketType.MESH),
    ]

    def compute(self, meshes: List[MeshData]) -> Dict[str, Any]:
        flat: List[MeshData] = []
        for item in meshes:
            if isinstance(item, list):
                flat.extend(x for x in item if isinstance(x, MeshData))
            elif isinstance(item, MeshData):
                flat.append(item)
        return {"merged": MeshData.merge(flat)}


@register_node
class IngeTrazoOutputNode(BaseNode):
    type_id = "scene.output"
    description = "Exports geometry and assemblies to the IngeTrazo 3D scene with BIM metadata (IfcColumn, IfcWall, etc.)."
    title = "IngeTrazo BIM Output"
    category = "Scene Output"
    header_color = (180, 65, 65)
    is_output_node = True

    inputs = [
        InputSpec("mesh", "Geometry", SocketType.MESH, default=[], access=AccessMode.LIST, hide_widget=True),
        InputSpec("group_name", "Group Name", SocketType.STRING, default="Parametric_Group"),
        InputSpec(
            "ifc_class",
            "BIM Tag",
            SocketType.STRING,
            default="",
            choices=["", "IfcWall", "IfcSlab", "IfcColumn", "IfcBeam", "IfcRoof", "IfcStair", "IfcBuildingElementProxy"],
        ),
        InputSpec("enabled", "Live Preview", SocketType.BOOL, default=True),
    ]
    outputs = [
        OutputSpec("mesh_out", "Baked", SocketType.MESH),
    ]

    def compute(self, mesh: List[MeshData], group_name: str, ifc_class: str, enabled: bool) -> Dict[str, Any]:
        out_list: List[MeshData] = []
        flat: List[MeshData] = []

        def _collect(x: Any) -> None:
            if x is None:
                return
            if isinstance(x, MeshData):
                if x.vertices or x.edges:
                    flat.append(x)
            elif isinstance(x, CurveData):
                if len(x.points) >= 3 and x.closed:
                    flat.append(x.to_mesh_face(name="Profile_Solid"))
                elif x.points:
                    flat.append(x.to_wire_mesh(name="Curve_Wire"))
            elif hasattr(x, "faces") or type(x).__name__ == "Brep":
                try:
                    from brep_engine import BRepEngine
                    if BRepEngine.is_available():
                        bm = BRepEngine.brep_to_mesh_data(x, name="BRep_Solid")
                        if bm and (bm.vertices or bm.edges):
                            flat.append(bm)
                except Exception:
                    pass
            elif hasattr(x, "parameter_range") or type(x).__name__ == "Curve":
                try:
                    from brep_engine import BRepEngine
                    if BRepEngine.is_available():
                        cd = BRepEngine.curve_to_curve_data(x)
                        if cd and len(cd.points) >= 3 and cd.closed:
                            flat.append(cd.to_mesh_face(name="BRep_Profile_Solid"))
                        elif cd and cd.points:
                            flat.append(cd.to_wire_mesh(name="BRep_Curve_Wire"))
                except Exception:
                    pass
            elif isinstance(x, (list, tuple)):
                for sub in x:
                    _collect(sub)

        _collect(mesh)

        for idx, item in enumerate(flat):
            copied = item.copy()
            copied.name = group_name if len(flat) == 1 else f"{group_name}_{idx + 1}"
            if ifc_class:
                copied.ifc_class = ifc_class
            out_list.append(copied)
        return {"mesh_out": out_list}


# ============================================================================
# XY Plane Node
# ============================================================================
@register_node
class XYPlaneNode(BaseNode):
    type_id = "plane.xy"
    title = "XY Plane"
    category = "Points & Vectors"
    description = (
        "Creates a standard World XY construction plane (Normal Z = [0, 0, 1], U = [1, 0, 0], V = [0, 1, 0]) at an origin point.\n"
        "Emits origin, unit normal, unit U, unit V, a visual boundary rectangle, and a standard plane frame."
    )
    header_color = (58, 125, 68)
    icon = "plane.xy.png"

    inputs = [
        InputSpec("origin", "Origin", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("size", "Preview Size (m)", SocketType.FLOAT, default=2.0, min_val=0.1, step=0.5),
    ]
    outputs = [
        OutputSpec("origin", "Origin", SocketType.VEC3),
        OutputSpec("normal", "Normal (Z)", SocketType.VEC3),
        OutputSpec("u_axis", "U Axis (X)", SocketType.VEC3),
        OutputSpec("v_axis", "V Axis (Y)", SocketType.VEC3),
        OutputSpec("preview", "Plane Preview", SocketType.CURVE),
        OutputSpec("plane", "Plane", SocketType.ANY),
    ]

    def compute(self, origin: Any = None, size: float = 2.0) -> Dict[str, Any]:
        p0 = origin if isinstance(origin, Vec3) else Vec3(0, 0, 0)
        n = Vec3(0, 0, 1)
        u = Vec3(1, 0, 0)
        v = Vec3(0, 1, 0)

        s = float(size) * 0.5
        c0 = p0 - u * s - v * s
        c1 = p0 + u * s - v * s
        c2 = p0 + u * s + v * s
        c3 = p0 - u * s + v * s
        preview_curve = CurveData(points=[c0, c1, c2, c3], closed=True)

        plane_dict = {
            "origin": (p0.x, p0.y, p0.z),
            "normal": (n.x, n.y, n.z),
            "u_axis": (u.x, u.y, u.z),
            "v_axis": (v.x, v.y, v.z),
            "name": "XY",
        }
        return {
            "origin": p0,
            "normal": n,
            "u_axis": u,
            "v_axis": v,
            "preview": preview_curve,
            "plane": plane_dict,
        }

NODE_REGISTRY["vec.plane_xy"] = XYPlaneNode


# ============================================================================
# XZ Plane Node
# ============================================================================
@register_node
class XZPlaneNode(BaseNode):
    type_id = "plane.xz"
    title = "XZ Plane"
    category = "Points & Vectors"
    description = (
        "Creates a standard World XZ construction plane (Normal Y = [0, -1, 0], U = [1, 0, 0], V = [0, 0, 1]) at an origin point.\n"
        "Emits origin, unit normal, unit U, unit V, a visual boundary rectangle, and a standard plane frame."
    )
    header_color = (58, 125, 68)
    icon = "plane.xz.png"

    inputs = [
        InputSpec("origin", "Origin", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("size", "Preview Size (m)", SocketType.FLOAT, default=2.0, min_val=0.1, step=0.5),
    ]
    outputs = [
        OutputSpec("origin", "Origin", SocketType.VEC3),
        OutputSpec("normal", "Normal", SocketType.VEC3),
        OutputSpec("u_axis", "U Axis (X)", SocketType.VEC3),
        OutputSpec("v_axis", "V Axis (Z)", SocketType.VEC3),
        OutputSpec("preview", "Plane Preview", SocketType.CURVE),
        OutputSpec("plane", "Plane", SocketType.ANY),
    ]

    def compute(self, origin: Any = None, size: float = 2.0) -> Dict[str, Any]:
        p0 = origin if isinstance(origin, Vec3) else Vec3(0, 0, 0)
        u = Vec3(1, 0, 0)
        v = Vec3(0, 0, 1)
        n = Vec3(0, -1, 0)

        s = float(size) * 0.5
        c0 = p0 - u * s - v * s
        c1 = p0 + u * s - v * s
        c2 = p0 + u * s + v * s
        c3 = p0 - u * s + v * s
        preview_curve = CurveData(points=[c0, c1, c2, c3], closed=True)

        plane_dict = {
            "origin": (p0.x, p0.y, p0.z),
            "normal": (n.x, n.y, n.z),
            "u_axis": (u.x, u.y, u.z),
            "v_axis": (v.x, v.y, v.z),
            "name": "XZ",
        }
        return {
            "origin": p0,
            "normal": n,
            "u_axis": u,
            "v_axis": v,
            "preview": preview_curve,
            "plane": plane_dict,
        }

NODE_REGISTRY["vec.plane_xz"] = XZPlaneNode


# ============================================================================
# YZ Plane Node
# ============================================================================
@register_node
class YZPlaneNode(BaseNode):
    type_id = "plane.yz"
    title = "YZ Plane"
    category = "Points & Vectors"
    description = (
        "Creates a standard World YZ construction plane (Normal X = [1, 0, 0], U = [0, 1, 0], V = [0, 0, 1]) at an origin point.\n"
        "Emits origin, unit normal, unit U, unit V, a visual boundary rectangle, and a standard plane frame."
    )
    header_color = (58, 125, 68)
    icon = "plane.yz.png"

    inputs = [
        InputSpec("origin", "Origin", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("size", "Preview Size (m)", SocketType.FLOAT, default=2.0, min_val=0.1, step=0.5),
    ]
    outputs = [
        OutputSpec("origin", "Origin", SocketType.VEC3),
        OutputSpec("normal", "Normal", SocketType.VEC3),
        OutputSpec("u_axis", "U Axis (Y)", SocketType.VEC3),
        OutputSpec("v_axis", "V Axis (Z)", SocketType.VEC3),
        OutputSpec("preview", "Plane Preview", SocketType.CURVE),
        OutputSpec("plane", "Plane", SocketType.ANY),
    ]

    def compute(self, origin: Any = None, size: float = 2.0) -> Dict[str, Any]:
        p0 = origin if isinstance(origin, Vec3) else Vec3(0, 0, 0)
        u = Vec3(0, 1, 0)
        v = Vec3(0, 0, 1)
        n = Vec3(1, 0, 0)

        s = float(size) * 0.5
        c0 = p0 - u * s - v * s
        c1 = p0 + u * s - v * s
        c2 = p0 + u * s + v * s
        c3 = p0 - u * s + v * s
        preview_curve = CurveData(points=[c0, c1, c2, c3], closed=True)

        plane_dict = {
            "origin": (p0.x, p0.y, p0.z),
            "normal": (n.x, n.y, n.z),
            "u_axis": (u.x, u.y, u.z),
            "v_axis": (v.x, v.y, v.z),
            "name": "YZ",
        }
        return {
            "origin": p0,
            "normal": n,
            "u_axis": u,
            "v_axis": v,
            "preview": preview_curve,
            "plane": plane_dict,
        }

NODE_REGISTRY["vec.plane_yz"] = YZPlaneNode


# ============================================================================
# Center Node (Area / Volume / Centroid)
# ============================================================================
@register_node
class CenterNode(BaseNode):
    type_id = "point.center"
    title = "Center"
    category = "Points & Vectors"
    description = (
        "Computes the geometric centroid (center of mass), surface area, 3D volume, and alignment plane\n"
        "for closed planar curves, polygons, 3D surface meshes, or solid bodies."
    )
    header_color = (58, 125, 68)
    icon = "point.center.png"

    inputs = [
        InputSpec("geometry", "Geometry", SocketType.ANY, default=None, hide_widget=True),
    ]
    outputs = [
        OutputSpec("center", "Centroid", SocketType.VEC3),
        OutputSpec("area", "Area (m²)", SocketType.FLOAT),
        OutputSpec("volume", "Volume (m³)", SocketType.FLOAT),
        OutputSpec("centers", "Centers", SocketType.ANY),
        OutputSpec("plane", "Plane", SocketType.ANY),
    ]

    def compute(self, geometry: Any = None) -> Dict[str, Any]:
        if geometry is None:
            geometry = CurveData(
                points=[Vec3(0, 0, 0), Vec3(2, 0, 0), Vec3(2, 2, 0), Vec3(0, 2, 0)],
                closed=True,
            )

        def _compute_single(geom: Any) -> Tuple[Vec3, float, float, Dict[str, Any]]:
            if isinstance(geom, Vec3):
                p0 = geom
                return p0, 0.0, 0.0, {
                    "origin": (p0.x, p0.y, p0.z),
                    "normal": (0, 0, 1),
                    "u_axis": (1, 0, 0),
                    "v_axis": (0, 1, 0),
                }

            if isinstance(geom, CurveData):
                pts = geom.points
                if not pts:
                    p0 = Vec3(0, 0, 0)
                    return p0, 0.0, 0.0, {"origin": (0, 0, 0), "normal": (0, 0, 1), "u_axis": (1, 0, 0), "v_axis": (0, 1, 0)}

                if len(pts) <= 2:
                    p0 = (pts[0] + pts[-1]) * 0.5
                    length = (pts[-1] - pts[0]).length() if len(pts) == 2 else 0.0
                    return p0, length, 0.0, {"origin": (p0.x, p0.y, p0.z), "normal": (0, 0, 1), "u_axis": (1, 0, 0), "v_axis": (0, 1, 0)}

                total_area = 0.0
                cx, cy, cz = 0.0, 0.0, 0.0
                norm_accum = Vec3(0, 0, 0)
                p_base = pts[0]

                n_pts = len(pts)
                limit = n_pts - 1 if (geom.closed and (pts[-1] - pts[0]).length() < 1e-6) else n_pts

                for i in range(1, limit - 1):
                    p1 = pts[i]
                    p2 = pts[i + 1]
                    v1 = p1 - p_base
                    v2 = p2 - p_base
                    cross = Vec3(
                        v1.y * v2.z - v1.z * v2.y,
                        v1.z * v2.x - v1.x * v2.z,
                        v1.x * v2.y - v1.y * v2.x,
                    )
                    tri_norm_len = math.sqrt(cross.x * cross.x + cross.y * cross.y + cross.z * cross.z)
                    tri_area = 0.5 * tri_norm_len
                    norm_accum = norm_accum + cross

                    tri_center = (p_base + p1 + p2) * (1.0 / 3.0)
                    cx += tri_center.x * tri_area
                    cy += tri_center.y * tri_area
                    cz += tri_center.z * tri_area
                    total_area += tri_area

                if total_area > 1e-8:
                    inv_a = 1.0 / total_area
                    centroid = Vec3(cx * inv_a, cy * inv_a, cz * inv_a)
                else:
                    avg_x = sum(p.x for p in pts) / len(pts)
                    avg_y = sum(p.y for p in pts) / len(pts)
                    avg_z = sum(p.z for p in pts) / len(pts)
                    centroid = Vec3(avg_x, avg_y, avg_z)

                norm_len = math.sqrt(norm_accum.x * norm_accum.x + norm_accum.y * norm_accum.y + norm_accum.z * norm_accum.z)
                if norm_len > 1e-6:
                    unit_norm = Vec3(norm_accum.x / norm_len, norm_accum.y / norm_len, norm_accum.z / norm_len)
                elif getattr(geom, 'normal', None) is not None:
                    unit_norm = getattr(geom, 'normal')
                else:
                    unit_norm = Vec3(0, 0, 1)

                guide = Vec3(0, 0, 1) if abs(unit_norm.z) < 0.9 else Vec3(1, 0, 0)
                u_raw = Vec3(
                    guide.y * unit_norm.z - guide.z * unit_norm.y,
                    guide.z * unit_norm.x - guide.x * unit_norm.z,
                    guide.x * unit_norm.y - guide.y * unit_norm.x,
                )
                u_l = math.sqrt(u_raw.x * u_raw.x + u_raw.y * u_raw.y + u_raw.z * u_raw.z)
                u = Vec3(u_raw.x / u_l, u_raw.y / u_l, u_raw.z / u_l) if u_l > 1e-6 else Vec3(1, 0, 0)
                v = Vec3(
                    unit_norm.y * u.z - unit_norm.z * u.y,
                    unit_norm.z * u.x - unit_norm.x * u.z,
                    unit_norm.x * u.y - unit_norm.y * u.x,
                )

                plane_dict = {
                    "origin": (centroid.x, centroid.y, centroid.z),
                    "normal": (unit_norm.x, unit_norm.y, unit_norm.z),
                    "u_axis": (u.x, u.y, u.z),
                    "v_axis": (v.x, v.y, v.z),
                }
                return centroid, total_area, 0.0, plane_dict

            if isinstance(geom, MeshData):
                verts = [Vec3(v[0], v[1], v[2]) for v in geom.vertices]
                if not verts or not geom.faces:
                    p0 = Vec3(0, 0, 0)
                    return p0, 0.0, 0.0, {"origin": (0, 0, 0), "normal": (0, 0, 1), "u_axis": (1, 0, 0), "v_axis": (0, 1, 0)}

                total_surface_area = 0.0
                area_cx, area_cy, area_cz = 0.0, 0.0, 0.0

                signed_volume = 0.0
                vol_cx, vol_cy, vol_cz = 0.0, 0.0, 0.0

                for f in geom.faces:
                    if len(f) < 3:
                        continue
                    v0 = verts[f[0]]
                    for j in range(1, len(f) - 1):
                        v1 = verts[f[j]]
                        v2 = verts[f[j + 1]]

                        # 1. Surface area
                        e1 = v1 - v0
                        e2 = v2 - v0
                        cross = Vec3(
                            e1.y * e2.z - e1.z * e2.y,
                            e1.z * e2.x - e1.x * e2.z,
                            e1.x * e2.y - e1.y * e2.x,
                        )
                        tri_area = 0.5 * math.sqrt(cross.x * cross.x + cross.y * cross.y + cross.z * cross.z)
                        total_surface_area += tri_area

                        tri_c = (v0 + v1 + v2) * (1.0 / 3.0)
                        area_cx += tri_c.x * tri_area
                        area_cy += tri_c.y * tri_area
                        area_cz += tri_c.z * tri_area

                        # 2. Signed tetrahedron volume from origin (0,0,0)
                        cp = Vec3(
                            v1.y * v2.z - v1.z * v2.y,
                            v1.z * v2.x - v1.x * v2.z,
                            v1.x * v2.y - v1.y * v2.x,
                        )
                        tet_vol = (v0.x * cp.x + v0.y * cp.y + v0.z * cp.z) / 6.0
                        signed_volume += tet_vol

                        tet_c = (v0 + v1 + v2) * 0.25
                        vol_cx += tet_c.x * tet_vol
                        vol_cy += tet_c.y * tet_vol
                        vol_cz += tet_c.z * tet_vol

                abs_vol = abs(signed_volume)
                if abs_vol > 1e-5:
                    inv_v = 1.0 / signed_volume
                    centroid = Vec3(vol_cx * inv_v, vol_cy * inv_v, vol_cz * inv_v)
                elif total_surface_area > 1e-8:
                    inv_a = 1.0 / total_surface_area
                    centroid = Vec3(area_cx * inv_a, area_cy * inv_a, area_cz * inv_a)
                else:
                    avg_x = sum(v.x for v in verts) / len(verts)
                    avg_y = sum(v.y for v in verts) / len(verts)
                    avg_z = sum(v.z for v in verts) / len(verts)
                    centroid = Vec3(avg_x, avg_y, avg_z)

                plane_dict = {
                    "origin": (centroid.x, centroid.y, centroid.z),
                    "normal": (0, 0, 1),
                    "u_axis": (1, 0, 0),
                    "v_axis": (0, 1, 0),
                }
                return centroid, total_surface_area, abs_vol, plane_dict

            if isinstance(geom, (list, tuple)):
                pts = [p if isinstance(p, Vec3) else Vec3(float(p[0]), float(p[1]), float(p[2])) for p in geom if hasattr(p, '__iter__') or isinstance(p, Vec3)]
                if pts:
                    avg_x = sum(p.x for p in pts) / len(pts)
                    avg_y = sum(p.y for p in pts) / len(pts)
                    avg_z = sum(p.z for p in pts) / len(pts)
                    c = Vec3(avg_x, avg_y, avg_z)
                    return c, 0.0, 0.0, {"origin": (c.x, c.y, c.z), "normal": (0, 0, 1), "u_axis": (1, 0, 0), "v_axis": (0, 1, 0)}

            p0 = Vec3(0, 0, 0)
            return p0, 0.0, 0.0, {"origin": (0, 0, 0), "normal": (0, 0, 1), "u_axis": (1, 0, 0), "v_axis": (0, 1, 0)}

        if isinstance(geometry, list) and geometry and not isinstance(geometry[0], (int, float)):
            all_res = [_compute_single(item) for item in geometry]
            centers = [r[0] for r in all_res]
            total_a = sum(r[1] for r in all_res)
            total_v = sum(r[2] for r in all_res)
            first_c = centers[0] if centers else Vec3(0, 0, 0)
            first_plane = all_res[0][3] if all_res else {}
            return {
                "center": first_c,
                "area": total_a,
                "volume": total_v,
                "centers": centers,
                "plane": first_plane,
            }

        c, a, v, plane = _compute_single(geometry)
        return {
            "center": c,
            "area": a,
            "volume": v,
            "centers": [c],
            "plane": plane,
        }

NODE_REGISTRY["geometry.center"] = CenterNode
NODE_REGISTRY["point.center"] = CenterNode
