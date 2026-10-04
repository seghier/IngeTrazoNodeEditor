# SPDX-License-Identifier: GPL-3.0-or-later
"""Comprehensive catalog of parametric modeling nodes for IngeTrazo."""
from __future__ import annotations

import ast
import math
import copy
from typing import List, Dict, Any, Optional, Union

from .engine import NodeBase, PortType, Port
from .models import (
    Point3D, Vector3D, PolylineData, FaceData, EdgeData, MeshData,
    Domain, Domain2D,
    create_box, create_cylinder, create_sphere, extrude_profile
)

try:
    from .py_straight_skeleton import compute_skeleton
except Exception:
    try:
        from py_straight_skeleton import compute_skeleton
    except Exception:
        compute_skeleton = None

try:
    from shapely.geometry import Polygon, MultiPolygon
except ImportError:
    Polygon = None
    MultiPolygon = None


# Registry of all available nodes: {Class.__name__: Class}
NODE_REGISTRY: Dict[str, type] = {}


def register_node(cls: type) -> type:
    NODE_REGISTRY[cls.__name__] = cls
    return cls


def _safe_ln(v: float) -> float:
    try:
        fv = float(v)
        if fv > 1e-15:
            return math.log(fv)
        elif fv < -1e-15:
            return math.log(abs(fv))
        return -34.54
    except Exception:
        return 0.0


def _safe_log(v: float, base: Optional[float] = None) -> float:
    try:
        fv = float(v)
        val = fv if fv > 1e-15 else (abs(fv) if abs(fv) > 1e-15 else 1e-15)
        if base is not None:
            return math.log(val, float(base))
        return math.log(val)
    except Exception:
        return 0.0


def _safe_sqrt(v: float) -> float:
    try:
        fv = float(v)
        return math.sqrt(fv if fv >= 0 else abs(fv))
    except Exception:
        return 0.0


def _safe_asin(v: float) -> float:
    try:
        return math.asin(max(-1.0, min(1.0, float(v))))
    except Exception:
        return 0.0


def _safe_acos(v: float) -> float:
    try:
        return math.acos(max(-1.0, min(1.0, float(v))))
    except Exception:
        return 0.0


# Safe evaluation environment for math expressions
MATH_ENV: Dict[str, Any] = {
    # Constants
    "pi": math.pi,
    "PI": math.pi,
    "e": math.e,
    "E": math.e,
    "tau": math.tau,
    "TAU": math.tau,
    "phi": (1.0 + math.sqrt(5.0)) / 2.0,
    # Trigonometric functions
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": _safe_asin,
    "acos": _safe_acos,
    "atan": math.atan,
    "atan2": math.atan2,
    "sinh": math.sinh,
    "cosh": math.cosh,
    "tanh": math.tanh,
    "SIN": math.sin,
    "COS": math.cos,
    "TAN": math.tan,
    # Logarithmic & Exponential
    "ln": _safe_ln,
    "LN": _safe_ln,
    "log": _safe_log,
    "LOG": _safe_log,
    "log10": (lambda v: math.log10(v if v > 1e-15 else (abs(v) if abs(v) > 1e-15 else 1e-15))),
    "LOG10": (lambda v: math.log10(v if v > 1e-15 else (abs(v) if abs(v) > 1e-15 else 1e-15))),
    "log2": (lambda v: math.log2(v if v > 1e-15 else (abs(v) if abs(v) > 1e-15 else 1e-15))),
    "LOG2": (lambda v: math.log2(v if v > 1e-15 else (abs(v) if abs(v) > 1e-15 else 1e-15))),
    "exp": math.exp,
    "EXP": math.exp,
    # Powers & Roots
    "sqrt": _safe_sqrt,
    "SQRT": _safe_sqrt,
    "cbrt": (lambda v: math.copysign(abs(v) ** (1.0 / 3.0), v)),
    "pow": pow,
    "sq": (lambda v: float(v) * float(v)),
    # Rounding & Signs
    "abs": abs,
    "ABS": abs,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "min": min,
    "max": max,
    "clamp": (lambda v, mn, mx: max(mn, min(mx, v))),
    "lerp": (lambda a, b, t: a + (b - a) * t),
    # Geometric utilities
    "hypot": math.hypot,
    "deg": math.degrees,
    "rad": math.radians,
    "degrees": math.degrees,
    "radians": math.radians,
}

_EXPR_CACHE: Dict[str, Any] = {}


def _prepare_expression(expr_str: str) -> str:
    """Normalize mathematical expression syntax for Python evaluation."""
    s = expr_str.strip()
    s = s.replace("^", "**")
    return s


def _safe_compile(expr_str: str):
    """Compile an expression string safely after validating AST nodes."""
    clean = _prepare_expression(expr_str)
    if clean in _EXPR_CACHE:
        return _EXPR_CACHE[clean]

    tree = ast.parse(clean, mode="eval")

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Attribute)):
            raise ValueError("Imports and attribute accesses are forbidden in expressions")
        if isinstance(node, ast.Call) and not isinstance(node.func, ast.Name):
            raise ValueError("Only direct math function calls are allowed")

    code = compile(tree, "<expression>", "eval")
    _EXPR_CACHE[clean] = code
    return code


# =====================================================================================
# 1. INPUT NODES
# =====================================================================================

@register_node
class NumberSliderNode(NodeBase):
    name = "Number Slider"
    category = "Input"
    description = "Interactive numeric slider emitting a floating-point value."
    header_color = "#205493"

    def setup_ports(self) -> None:
        self.add_output("Value", PortType.NUMBER, "Output number")
        self.widget_values.setdefault("value", 5.0)
        self.widget_values.setdefault("min", 0.0)
        self.widget_values.setdefault("max", 50.0)
        self.widget_values.setdefault("step", 0.1)

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        val = float(self.widget_values.get("value", 0.0))
        self.set_output("Value", val)


@register_node
class IntegerSliderNode(NodeBase):
    name = "Integer Slider"
    category = "Input"
    description = "Interactive slider emitting an integer value."
    header_color = "#205493"

    def setup_ports(self) -> None:
        self.add_output("Value", PortType.INTEGER, "Output integer")
        self.widget_values.setdefault("value", 10)
        self.widget_values.setdefault("min", 1)
        self.widget_values.setdefault("max", 100)
        self.widget_values.setdefault("step", 1)

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        val = int(round(float(self.widget_values.get("value", 1))))
        self.set_output("Value", val)


@register_node
class ToggleNode(NodeBase):
    name = "Toggle (Boolean)"
    category = "Input"
    description = "True/False switch toggle."
    header_color = "#205493"

    def setup_ports(self) -> None:
        self.add_output("Value", PortType.BOOLEAN, "Output boolean")
        self.widget_values.setdefault("value", True)

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        self.set_output("Value", bool(self.widget_values.get("value", True)))


@register_node
class VectorInputNode(NodeBase):
    name = "Vector XYZ"
    category = "Input"
    description = "Construct a 3D directional vector from X, Y, Z numbers."
    header_color = "#205493"

    def setup_ports(self) -> None:
        self.add_input("X", PortType.NUMBER, 0.0)
        self.add_input("Y", PortType.NUMBER, 0.0)
        self.add_input("Z", PortType.NUMBER, 1.0)
        self.add_output("Vector", PortType.VECTOR, "3D vector")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        x = float(self.get_input("X", 0.0))
        y = float(self.get_input("Y", 0.0))
        z = float(self.get_input("Z", 1.0))
        self.set_output("Vector", Vector3D(x, y, z))


@register_node
class StringNode(NodeBase):
    name = "Text"
    category = "Input"
    description = "Text string constant (for names, layers, materials)."
    header_color = "#205493"

    def setup_ports(self) -> None:
        self.add_output("Text", PortType.STRING, "Output text")
        self.widget_values.setdefault("value", "Parametric")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        self.set_output("Text", str(self.widget_values.get("value", "")))


def format_panel_value(val: Any, max_items: int = 150) -> str:
    """Format any data structure for display inside a Panel node."""
    if val is None:
        return "None"

    # Point3D
    if isinstance(val, Point3D):
        return f"Point3D({val.x:.3f}, {val.y:.3f}, {val.z:.3f})"

    # Vector3D
    if isinstance(val, Vector3D):
        return f"Vector3D({val.x:.3f}, {val.y:.3f}, {val.z:.3f})"

    # MeshData
    if isinstance(val, MeshData):
        f_cnt = len(val.faces)
        e_cnt = len(val.edges)
        name_str = f" '{val.name}'" if val.name else ""
        return f"MeshData{name_str} ({f_cnt} faces, {e_cnt} edges)"

    # PolylineData
    if isinstance(val, PolylineData):
        closed_str = "closed" if val.closed else "open"
        return f"Polyline ({len(val.points)} pts, {closed_str})"

    # FaceData
    if isinstance(val, FaceData):
        return f"Face ({len(val.vertices)} vertices)"

    # EdgeData
    if isinstance(val, EdgeData):
        return f"Edge ({val.start} -> {val.end})"

    # Lists or tuples
    if isinstance(val, (list, tuple)):
        if len(val) == 0:
            return "[Empty List]"

        lines: List[str] = []
        show_count = min(len(val), max_items)
        for i in range(show_count):
            item = val[i]
            formatted_item = _format_single_item(item)
            lines.append(f"[{i}] {formatted_item}")

        if len(val) > max_items:
            lines.append(f"... ({len(val) - max_items} more items, total {len(val)})")

        return "\n".join(lines)

    # Boolean
    if isinstance(val, bool):
        return str(val)

    # Integer
    if isinstance(val, int):
        return str(val)

    # Float
    if isinstance(val, float):
        formatted = f"{val:.4f}".rstrip("0").rstrip(".")
        return formatted if formatted != "-0" else "0"

    # String or other
    return str(val)


def _format_single_item(item: Any) -> str:
    """Format an individual element within a list for compact panel display."""
    if item is None:
        return "None"
    if isinstance(item, Point3D):
        return f"Point3D({item.x:.2f}, {item.y:.2f}, {item.z:.2f})"
    if isinstance(item, Vector3D):
        return f"Vector3D({item.x:.2f}, {item.y:.2f}, {item.z:.2f})"
    if isinstance(item, MeshData):
        return f"Mesh ({len(item.faces)} faces, {len(item.edges)} edges)"
    if isinstance(item, PolylineData):
        return f"Polyline ({len(item.points)} pts)"
    if isinstance(item, (list, tuple)):
        return f"List ({len(item)} items)"
    if isinstance(item, float):
        formatted = f"{item:.4f}".rstrip("0").rstrip(".")
        return formatted if formatted != "-0" else "0"
    return str(item)


def parse_panel_input(text: str) -> Any:
    """Parse text entered into a disconnected Panel node."""
    if not text or not text.strip():
        return ""

    raw_lines = [ln.strip() for ln in text.splitlines()]
    non_empty = [ln for ln in raw_lines if ln]

    if not non_empty:
        return ""

    parsed_items: List[Any] = []
    for line in non_empty:
        low = line.lower()
        if low == "true":
            parsed_items.append(True)
        elif low == "false":
            parsed_items.append(False)
        else:
            try:
                parsed_items.append(int(line))
                continue
            except ValueError:
                pass
            try:
                parsed_items.append(float(line))
                continue
            except ValueError:
                pass
            parsed_items.append(line)

    if len(raw_lines) == 1 and "\n" not in text and "\r" not in text:
        return parsed_items[0]
    return parsed_items


@register_node
class PanelNode(NodeBase):
    name = "Panel"
    category = "Input"
    description = "Inspect and view any data (numbers, points, lists, meshes) with indexed output, or enter multiline text and constants."
    header_color = "#ebcb8b"

    def __init__(self, node_id: Optional[str] = None):
        self.on_display_updated: Optional[Any] = None
        super().__init__(node_id)

    def setup_ports(self) -> None:
        self.add_input("Data", PortType.ANY, description="Incoming data to inspect/view")
        self.add_output("Data", PortType.ANY, description="Pass-through data or entered text/numbers")
        self.widget_values.setdefault("text", "")
        self.widget_values.setdefault("display", "")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        self.error = None
        data_port = self.inputs[0] if self.inputs else None

        if data_port and data_port.has_connection:
            src_val = self.get_input("Data")
            self.set_output("Data", src_val)
            display_str = format_panel_value(src_val)
            self.widget_values["display"] = display_str
            if self.on_display_updated:
                try:
                    self.on_display_updated(display_str)
                except Exception:
                    pass
        else:
            text = str(self.widget_values.get("text", ""))
            parsed = parse_panel_input(text)
            self.set_output("Data", parsed)
            self.widget_values["display"] = text
            if self.on_display_updated:
                try:
                    self.on_display_updated(text)
                except Exception:
                    pass


# =====================================================================================
# 2. MATH NODES
# =====================================================================================

@register_node
class AddNode(NodeBase):
    name = "Add"
    category = "Math"
    description = "Add two numbers (A + B)."
    header_color = "#d08770"

    def setup_ports(self) -> None:
        self.add_input("A", PortType.NUMBER, 0.0)
        self.add_input("B", PortType.NUMBER, 0.0)
        self.add_output("Result", PortType.NUMBER)

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        a = float(self.get_input("A", 0.0))
        b = float(self.get_input("B", 0.0))
        self.set_output("Result", a + b)


@register_node
class SubtractNode(NodeBase):
    name = "Subtract"
    category = "Math"
    description = "Subtract two numbers (A - B)."
    header_color = "#d08770"

    def setup_ports(self) -> None:
        self.add_input("A", PortType.NUMBER, 0.0)
        self.add_input("B", PortType.NUMBER, 0.0)
        self.add_output("Result", PortType.NUMBER)

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        a = float(self.get_input("A", 0.0))
        b = float(self.get_input("B", 0.0))
        self.set_output("Result", a - b)


@register_node
class MultiplyNode(NodeBase):
    name = "Multiply"
    category = "Math"
    description = "Multiply two numbers (A * B)."
    header_color = "#d08770"

    def setup_ports(self) -> None:
        self.add_input("A", PortType.NUMBER, 1.0)
        self.add_input("B", PortType.NUMBER, 1.0)
        self.add_output("Result", PortType.NUMBER)

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        a = float(self.get_input("A", 1.0))
        b = float(self.get_input("B", 1.0))
        self.set_output("Result", a * b)


@register_node
class DivideNode(NodeBase):
    name = "Divide"
    category = "Math"
    description = "Divide two numbers (A / B)."
    header_color = "#d08770"

    def setup_ports(self) -> None:
        self.add_input("A", PortType.NUMBER, 1.0)
        self.add_input("B", PortType.NUMBER, 1.0)
        self.add_output("Result", PortType.NUMBER)

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        a = float(self.get_input("A", 1.0))
        b = float(self.get_input("B", 1.0))
        self.set_output("Result", a / b if abs(b) > 1e-12 else 0.0)


@register_node
class RangeSeriesNode(NodeBase):
    name = "Series / Range"
    category = "Math"
    description = "Generate a series of numbers [Start, Start + Step, ...]."
    header_color = "#d08770"

    def setup_ports(self) -> None:
        self.add_input("Start", PortType.NUMBER, 0.0)
        self.add_input("Step", PortType.NUMBER, 1.0)
        self.add_input("Count", PortType.INTEGER, 10)
        self.add_output("List", PortType.ANY, "List of numbers")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        start = float(self.get_input("Start", 0.0))
        step = float(self.get_input("Step", 1.0))
        count = max(1, int(self.get_input("Count", 10)))
        series = [start + i * step for i in range(count)]
        self.set_output("List", series)


@register_node
class DivideRangeNode(NodeBase):
    name = "Divide Range"
    category = "Math"
    description = "Divide a domain [Start, End] into evenly spaced numbers using Count (Linear Space / Linspace)."
    header_color = "#d08770"

    def setup_ports(self) -> None:
        self.add_input("Start", PortType.NUMBER, 0.0, "Start value of domain")
        self.add_input("End", PortType.NUMBER, 1.0, "End value of domain")
        self.add_input("Count", PortType.INTEGER, 10, "Number of steps / points in range")
        self.add_output("List", PortType.ANY, "Evenly spaced list of numbers")
        self.add_output("Step", PortType.NUMBER, "Step size between adjacent values")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        s_in = self.get_input("Start", 0.0)
        e_in = self.get_input("End", 1.0)
        c_in = self.get_input("Count", 10)

        # Allow Domain object into Start port
        if hasattr(s_in, "start") and hasattr(s_in, "end"):
            e_in = s_in.end
            s_in = s_in.start
        elif isinstance(s_in, (list, tuple)) and len(s_in) == 2 and not isinstance(s_in[0], (list, tuple)):
            e_in = s_in[1]
            s_in = s_in[0]

        is_list = any(isinstance(v, (list, tuple)) for v in [s_in, e_in, c_in])
        if not is_list:
            try:
                start = float(s_in)
            except Exception:
                start = 0.0
            try:
                end = float(e_in)
            except Exception:
                end = 1.0
            try:
                count = max(1, int(c_in))
            except Exception:
                count = 10

            if count == 1:
                self.set_output("List", [start])
                self.set_output("Step", 0.0)
            else:
                step = (end - start) / (count - 1)
                series = [(start + i * step) for i in range(count - 1)] + [end]
                self.set_output("List", series)
                self.set_output("Step", step)
        else:
            starts = s_in if isinstance(s_in, (list, tuple)) else [s_in]
            ends = e_in if isinstance(e_in, (list, tuple)) else [e_in]
            counts = c_in if isinstance(c_in, (list, tuple)) else [c_in]
            n_items = max(len(starts), len(ends), len(counts))

            all_series: List[List[float]] = []
            all_steps: List[float] = []
            for i in range(n_items):
                raw_st = starts[min(i, len(starts) - 1)]
                raw_en = ends[min(i, len(ends) - 1)]
                if hasattr(raw_st, "start") and hasattr(raw_st, "end"):
                    raw_en = raw_st.end
                    raw_st = raw_st.start
                try:
                    st = float(raw_st)
                except Exception:
                    st = 0.0
                try:
                    en = float(raw_en)
                except Exception:
                    en = 1.0
                try:
                    cnt = max(1, int(counts[min(i, len(counts) - 1)]))
                except Exception:
                    cnt = 10

                if cnt == 1:
                    all_series.append([st])
                    all_steps.append(0.0)
                else:
                    stp = (en - st) / (cnt - 1)
                    s = [(st + j * stp) for j in range(cnt - 1)] + [en]
                    all_series.append(s)
                    all_steps.append(stp)

            if len(all_series) == 1:
                self.set_output("List", all_series[0])
                self.set_output("Step", all_steps[0])
            else:
                self.set_output("List", all_series)
                self.set_output("Step", all_steps)


@register_node
class ConstructDomainNode(NodeBase):
    name = "Domain"
    category = "Math"
    description = (
        "Create a 1-dimensional domain interval [Start, End].\n"
        "Outputs a Domain object, length, and midpoint span.\n"
        "Supports scalar numbers, domains, and list broadcasting."
    )
    header_color = "#d08770"

    def setup_ports(self) -> None:
        self.add_input("Start", PortType.NUMBER, 0.0, "Start value of the numeric domain")
        self.add_input("End", PortType.NUMBER, 1.0, "End value of the numeric domain")
        self.add_output("Domain", PortType.ANY, "1D numeric domain interval")
        self.add_output("Length", PortType.NUMBER, "Span / length of interval abs(End - Start)")
        self.add_output("Mid", PortType.NUMBER, "Midpoint of interval (Start + End) / 2")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        s_in = self.get_input("Start", 0.0)
        e_in = self.get_input("End", 1.0)

        is_list = any(isinstance(v, (list, tuple)) for v in [s_in, e_in])
        if not is_list:
            try:
                s = float(s_in)
            except Exception:
                s = 0.0
            try:
                e = float(e_in)
            except Exception:
                e = 1.0
            dom = Domain(s, e)
            self.set_output("Domain", dom)
            self.set_output("Length", dom.length)
            self.set_output("Mid", dom.mid)
        else:
            starts = s_in if isinstance(s_in, (list, tuple)) else [s_in]
            ends = e_in if isinstance(e_in, (list, tuple)) else [e_in]
            n = max(len(starts), len(ends))
            domains: List[Domain] = []
            lengths: List[float] = []
            mids: List[float] = []
            for i in range(n):
                try:
                    s = float(starts[min(i, len(starts) - 1)])
                except Exception:
                    s = 0.0
                try:
                    e = float(ends[min(i, len(ends) - 1)])
                except Exception:
                    e = 1.0
                d = Domain(s, e)
                domains.append(d)
                lengths.append(d.length)
                mids.append(d.mid)
            self.set_output("Domain", domains)
            self.set_output("Length", lengths)
            self.set_output("Mid", mids)


@register_node
class ConstructDomainAliasNode(ConstructDomainNode):
    name = "Construct Domain"
    category = "Math"
    description = (
        "Construct a numeric domain interval [Start, End].\n"
        "Alias for 'Domain'."
    )


@register_node
class DeconstructDomainNode(NodeBase):
    name = "Deconstruct Domain"
    category = "Math"
    description = (
        "Deconstruct a numeric domain interval into its Start, End, Length, and Midpoint components."
    )
    header_color = "#d08770"

    def setup_ports(self) -> None:
        self.add_input("Domain", PortType.ANY, description="1D domain or (start, end) pair")
        self.add_output("Start", PortType.NUMBER, "Start value")
        self.add_output("End", PortType.NUMBER, "End value")
        self.add_output("Length", PortType.NUMBER, "Total span / length")
        self.add_output("Mid", PortType.NUMBER, "Midpoint")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        d_in = self.get_input("Domain")
        if d_in is None:
            return

        def _unpack(d: Any) -> Tuple[float, float, float, float]:
            if isinstance(d, Domain):
                return d.start, d.end, d.length, d.mid
            if hasattr(d, "start") and hasattr(d, "end"):
                s, e = float(d.start), float(d.end)
                return s, e, abs(e - s), (s + e) * 0.5
            if isinstance(d, (list, tuple)) and len(d) >= 2:
                try:
                    s, e = float(d[0]), float(d[1])
                    return s, e, abs(e - s), (s + e) * 0.5
                except Exception:
                    pass
            try:
                v = float(d)
                return 0.0, v, abs(v), v * 0.5
            except Exception:
                return 0.0, 1.0, 1.0, 0.5

        if isinstance(d_in, (list, tuple)) and (len(d_in) == 0 or not isinstance(d_in[0], (int, float))):
            starts, ends, lengths, mids = [], [], [], []
            for item in d_in:
                s, e, l, m = _unpack(item)
                starts.append(s)
                ends.append(e)
                lengths.append(l)
                mids.append(m)
            self.set_output("Start", starts)
            self.set_output("End", ends)
            self.set_output("Length", lengths)
            self.set_output("Mid", mids)
        else:
            s, e, l, m = _unpack(d_in)
            self.set_output("Start", s)
            self.set_output("End", e)
            self.set_output("Length", l)
            self.set_output("Mid", m)


@register_node
class ConstructDomain2DNode(NodeBase):
    name = "Domain 2D"
    category = "Math"
    description = (
        "Create a 2-dimensional domain [U, V] from two 1D domains or numeric ranges.\n"
        "Ideal for surfaces, grids, and image sampling."
    )
    header_color = "#d08770"

    def setup_ports(self) -> None:
        self.add_input("U", PortType.ANY, description="Domain U (Domain or number)")
        self.add_input("V", PortType.ANY, description="Domain V (Domain or number)")
        self.add_output("Domain 2D", PortType.ANY, "2D domain interval")
        self.add_output("U Span", PortType.NUMBER, "Length of U domain")
        self.add_output("V Span", PortType.NUMBER, "Length of V domain")
        self.add_output("Area", PortType.NUMBER, "Area (U length * V length)")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        def _to_domain(val: Any, default_val: float = 1.0) -> Domain:
            if isinstance(val, Domain):
                return val
            if hasattr(val, "start") and hasattr(val, "end"):
                return Domain(float(val.start), float(val.end))
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                try:
                    return Domain(float(val[0]), float(val[1]))
                except Exception:
                    pass
            try:
                v = float(val) if val is not None else default_val
                return Domain(0.0, v)
            except Exception:
                return Domain(0.0, default_val)

        u_dom = _to_domain(self.get_input("U"), 10.0)
        v_dom = _to_domain(self.get_input("V"), 10.0)
        dom2d = Domain2D(u=u_dom, v=v_dom)

        self.set_output("Domain 2D", dom2d)
        self.set_output("U Span", dom2d.u_span)
        self.set_output("V Span", dom2d.v_span)
        self.set_output("Area", dom2d.u_span * dom2d.v_span)



VARIABLE_NAMES = [
    "x", "y", "z", "w", "a", "b", "c", "d", "e", "f",
    "g", "h", "k", "m", "n", "p", "q", "r", "s", "t", "u", "v"
]


@register_node
class ExpressionNode(NodeBase):
    name = "Expression"
    category = "Math"
    description = "Evaluate mathematical expressions (e.g. sin(x)*cos(y), x^2 + y^2, sqrt(x*x + y*y)). Supports dynamic variable inputs, lists, broadcasting, and trigonometry."
    header_color = "#b48ead"

    def setup_ports(self) -> None:
        self.add_input("x", PortType.ANY, 1.0, "Input variable x")
        self.add_input("Expr", PortType.STRING, "", "Formula override wire")
        self.add_output("Result", PortType.ANY, "Evaluated result (number or list)")
        self.widget_values.setdefault("expr", "x + y")

    def get_formula_variables(self) -> List[str]:
        """Extract variable names required by the expression formula in left-to-right order."""
        wire_expr = self.get_input("Expr", "")
        if wire_expr and str(wire_expr).strip():
            expr_str = str(wire_expr).strip()
        else:
            expr_str = str(self.widget_values.get("expr", "x + y")).strip()
        if not expr_str:
            return []
        try:
            clean = _prepare_expression(expr_str)
            tree = ast.parse(clean, mode="eval")
            name_nodes: List[ast.Name] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    name_nodes.append(node)
            name_nodes.sort(key=lambda n: (getattr(n, "lineno", 0), getattr(n, "col_offset", 0)))
            names: List[str] = []
            for node in name_nodes:
                nid = node.id
                if (nid not in MATH_ENV and nid.lower() not in MATH_ENV
                        and nid not in ("i", "I", "True", "False", "None")):
                    if nid not in names:
                        names.append(nid)
            return names
        except Exception:
            return []

    def sync_dynamic_ports(self) -> bool:
        """
        Maintains the invariant:
        - At least 1 variable input exists (starts at 'x').
        - All variables referenced in the formula are guaranteed to have input ports.
        - Exactly ONE unused (disconnected) variable input is reserved at the end.
        - When all variable inputs are connected, a new one is created from VARIABLE_NAMES.
        - When wires are sliced/disconnected, trailing unused inputs are removed,
          always leaving exactly one disconnected input, without ever removing variables needed by the formula.
        Returns True if ports were added or removed.
        """
        changed = False
        formula_vars = self.get_formula_variables()
        var_ports = [p for p in self.inputs if p.name != "Expr"]

        # Ensure all variables present in the formula have an input port
        existing_names = {p.name for p in var_ports}
        for vname in formula_vars:
            if vname not in existing_names:
                new_p = Port(self, vname, PortType.ANY, is_input=True, default_value=1.0 if vname in ("x", "a") else 0.0, description=f"Input variable {vname}")
                expr_idx = next((i for i, port in enumerate(self.inputs) if port.name == "Expr"), len(self.inputs))
                self.inputs.insert(expr_idx, new_p)
                var_ports.append(new_p)
                existing_names.add(vname)
                changed = True

        # Ensure at least 1 variable port
        if not var_ports:
            p = Port(self, "x", PortType.ANY, is_input=True, default_value=1.0, description="Input variable x")
            expr_idx = next((i for i, port in enumerate(self.inputs) if port.name == "Expr"), len(self.inputs))
            self.inputs.insert(expr_idx, p)
            var_ports = [p]
            changed = True

        # Rule 1: If the last variable port has a connection, add the next unused variable port
        if var_ports[-1].has_connection:
            existing_names = {p.name for p in var_ports}
            next_name = None
            for name in VARIABLE_NAMES:
                if name not in existing_names and name not in formula_vars:
                    next_name = name
                    break
            if not next_name:
                next_name = f"v{len(var_ports)}"

            new_p = Port(self, next_name, PortType.ANY, is_input=True, default_value=0.0, description=f"Input variable {next_name}")
            expr_idx = next((i for i, port in enumerate(self.inputs) if port.name == "Expr"), len(self.inputs))
            self.inputs.insert(expr_idx, new_p)
            var_ports.append(new_p)
            changed = True

        # Rule 2: If multiple trailing ports are disconnected, pop trailing ports
        # so we always leave exactly ONE disconnected input,
        # but NEVER remove a port if its name is in the formula!
        while (len(var_ports) > 1
               and not var_ports[-1].has_connection
               and not var_ports[-2].has_connection
               and var_ports[-1].name not in formula_vars):
            to_remove = var_ports.pop()
            if to_remove in self.inputs:
                self.inputs.remove(to_remove)
            changed = True

        return changed

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        self.error = None
        # Wire input overrides on-node widget if provided and non-empty
        wire_expr = self.get_input("Expr", "")
        if wire_expr and str(wire_expr).strip():
            expr_str = str(wire_expr).strip()
        else:
            expr_str = str(self.widget_values.get("expr", "x + y")).strip()

        if not expr_str:
            self.set_output("Result", 0.0)
            return

        try:
            code = _safe_compile(expr_str)
        except Exception as ex:
            self.error = f"Expression syntax error: {ex}"
            self.set_output("Result", 0.0)
            return

        # Dynamically read all variable ports
        var_ports = [p for p in self.inputs if p.name != "Expr"]
        var_values: Dict[str, Any] = {}
        for p in var_ports:
            var_values[p.name] = self.get_input(p.name, p.default_value or 0.0)

        # Check if any input is a list/tuple
        has_list = any(isinstance(v, (list, tuple)) for v in var_values.values())

        if has_list:
            n_items = max(len(v) if isinstance(v, (list, tuple)) else 1 for v in var_values.values())
            results: List[float] = []
            for i in range(n_items):
                scope = dict(MATH_ENV)
                for name, val in var_values.items():
                    if isinstance(val, (list, tuple)):
                        item_val = float(val[i % len(val)]) if len(val) > 0 else 0.0
                    else:
                        try:
                            item_val = float(val)
                        except Exception:
                            item_val = 0.0
                    scope[name] = item_val
                    scope[name.lower()] = item_val
                    scope[name.upper()] = item_val

                # Extra aliases for convenience: x <-> u, y <-> v, z <-> w
                if "x" in var_values and "u" not in var_values:
                    xv = scope.get("x", 0.0)
                    scope.setdefault("u", xv)
                    scope.setdefault("U", xv)
                elif "u" in var_values and "x" not in var_values:
                    uv = scope.get("u", 0.0)
                    scope.setdefault("x", uv)
                    scope.setdefault("X", uv)

                if "y" in var_values and "v" not in var_values:
                    yv = scope.get("y", 0.0)
                    scope.setdefault("v", yv)
                    scope.setdefault("V", yv)
                elif "v" in var_values and "y" not in var_values:
                    vv = scope.get("v", 0.0)
                    scope.setdefault("y", vv)
                    scope.setdefault("Y", vv)

                if "z" in var_values and "w" not in var_values:
                    zv = scope.get("z", 0.0)
                    scope.setdefault("w", zv)
                    scope.setdefault("W", zv)
                elif "w" in var_values and "z" not in var_values:
                    wv = scope.get("w", 0.0)
                    scope.setdefault("z", wv)
                    scope.setdefault("Z", wv)

                scope["i"] = float(i)
                try:
                    res = eval(code, {"__builtins__": {}}, scope)
                    results.append(float(res))
                except Exception as ex:
                    self.error = f"Eval error at [{i}]: {ex}"
                    results.append(0.0)

            self.set_output("Result", results)
        else:
            scope = dict(MATH_ENV)
            for name, val in var_values.items():
                try:
                    item_val = float(val)
                except Exception:
                    item_val = 0.0
                scope[name] = item_val
                scope[name.lower()] = item_val
                scope[name.upper()] = item_val

            if "x" in var_values and "u" not in var_values:
                xv = scope.get("x", 0.0)
                scope.setdefault("u", xv)
                scope.setdefault("U", xv)
            elif "u" in var_values and "x" not in var_values:
                uv = scope.get("u", 0.0)
                scope.setdefault("x", uv)
                scope.setdefault("X", uv)

            if "y" in var_values and "v" not in var_values:
                yv = scope.get("y", 0.0)
                scope.setdefault("v", yv)
                scope.setdefault("V", yv)
            elif "v" in var_values and "y" not in var_values:
                vv = scope.get("v", 0.0)
                scope.setdefault("y", vv)
                scope.setdefault("Y", vv)

            if "z" in var_values and "w" not in var_values:
                zv = scope.get("z", 0.0)
                scope.setdefault("w", zv)
                scope.setdefault("W", zv)
            elif "w" in var_values and "z" not in var_values:
                wv = scope.get("w", 0.0)
                scope.setdefault("z", wv)
                scope.setdefault("Z", wv)

            scope["i"] = 0.0
            try:
                res = eval(code, {"__builtins__": {}}, scope)
                self.set_output("Result", float(res))
            except Exception as ex:
                self.error = f"Eval error: {ex}"
                self.set_output("Result", 0.0)


# =====================================================================================
# 3. LIST UTILITIES
# =====================================================================================

@register_node
class CrossReferenceNode(NodeBase):
    name = "Cross Reference"
    category = "List"
    description = "Compute the Cartesian product of two lists (A × B) to cross-reference every item of A with every item of B."
    header_color = "#5e81ac"

    def setup_ports(self) -> None:
        self.add_input("A", PortType.ANY, description="First list of items")
        self.add_input("B", PortType.ANY, description="Second list of items")
        self.add_output("A", PortType.ANY, description="Cross-referenced elements of list A")
        self.add_output("B", PortType.ANY, description="Cross-referenced elements of list B")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        raw_a = self.get_input("A")
        raw_b = self.get_input("B")

        if raw_a is None or raw_b is None:
            self.set_output("A", [])
            self.set_output("B", [])
            return

        list_a = list(raw_a) if isinstance(raw_a, (list, tuple)) else [raw_a]
        list_b = list(raw_b) if isinstance(raw_b, (list, tuple)) else [raw_b]

        if not list_a or not list_b:
            self.set_output("A", [])
            self.set_output("B", [])
            return

        out_a: List[Any] = []
        out_b: List[Any] = []

        for a in list_a:
            for b in list_b:
                out_a.append(a)
                out_b.append(b)

        self.set_output("A", out_a)
        self.set_output("B", out_b)


# =====================================================================================
# 4. VECTOR & POINTS
# =====================================================================================

@register_node
class ConstructPointNode(NodeBase):
    name = "Construct Point"
    category = "Point"
    description = "Create a 3D point (or list of points) from X, Y, Z coordinates."
    header_color = "#a3be8c"

    def setup_ports(self) -> None:
        self.add_input("X", PortType.ANY, 0.0)
        self.add_input("Y", PortType.ANY, 0.0)
        self.add_input("Z", PortType.ANY, 0.0)
        self.add_output("Point", PortType.POINT, "Constructed Point3D")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        x_in = self.get_input("X", 0.0)
        y_in = self.get_input("Y", 0.0)
        z_in = self.get_input("Z", 0.0)

        # If any input is a list, generate a list of points
        is_list = any(isinstance(v, (list, tuple)) for v in [x_in, y_in, z_in])
        if is_list:
            xs = x_in if isinstance(x_in, (list, tuple)) else [x_in]
            ys = y_in if isinstance(y_in, (list, tuple)) else [y_in]
            zs = z_in if isinstance(z_in, (list, tuple)) else [z_in]
            max_len = max(len(xs), len(ys), len(zs))
            pts = []
            for i in range(max_len):
                x = float(xs[min(i, len(xs) - 1)])
                y = float(ys[min(i, len(ys) - 1)])
                z = float(zs[min(i, len(zs) - 1)])
                pts.append(Point3D(x, y, z))
            self.set_output("Point", pts)
        else:
            self.set_output("Point", Point3D(float(x_in), float(y_in), float(z_in)))


@register_node
class DeconstructPointNode(NodeBase):
    name = "Deconstruct Point"
    category = "Point"
    description = "Break a Point3D into its X, Y, Z coordinate values."
    header_color = "#a3be8c"

    def setup_ports(self) -> None:
        self.add_input("Point", PortType.POINT)
        self.add_output("X", PortType.NUMBER)
        self.add_output("Y", PortType.NUMBER)
        self.add_output("Z", PortType.NUMBER)

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        pt = self.get_input("Point")
        if isinstance(pt, Point3D):
            self.set_output("X", pt.x)
            self.set_output("Y", pt.y)
            self.set_output("Z", pt.z)
        elif isinstance(pt, (list, tuple)):
            if pt and isinstance(pt[0], Point3D):
                self.set_output("X", [p.x for p in pt if isinstance(p, Point3D)])
                self.set_output("Y", [p.y for p in pt if isinstance(p, Point3D)])
                self.set_output("Z", [p.z for p in pt if isinstance(p, Point3D)])
            elif len(pt) >= 3 and all(isinstance(v, (int, float)) for v in pt[:3]):
                self.set_output("X", float(pt[0]))
                self.set_output("Y", float(pt[1]))
                self.set_output("Z", float(pt[2]))


@register_node
class DistanceNode(NodeBase):
    name = "Distance"
    category = "Point"
    description = "Euclidean distance between Point A and Point B."
    header_color = "#a3be8c"

    def setup_ports(self) -> None:
        self.add_input("A", PortType.POINT)
        self.add_input("B", PortType.POINT)
        self.add_output("Distance", PortType.NUMBER)

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        a_in = self.get_input("A", Point3D(0, 0, 0))
        b_in = self.get_input("B", Point3D(0, 0, 0))
        if isinstance(a_in, Point3D) and isinstance(b_in, Point3D):
            self.set_output("Distance", a_in.distance_to(b_in))
        elif isinstance(a_in, (list, tuple)) or isinstance(b_in, (list, tuple)):
            as_ = a_in if isinstance(a_in, (list, tuple)) else [a_in]
            bs_ = b_in if isinstance(b_in, (list, tuple)) else [b_in]
            cnt = max(len(as_), len(bs_))
            dists = []
            for i in range(cnt):
                pa = as_[min(i, len(as_) - 1)]
                pb = bs_[min(i, len(bs_) - 1)]
                if isinstance(pa, Point3D) and isinstance(pb, Point3D):
                    dists.append(pa.distance_to(pb))
                else:
                    dists.append(0.0)
            self.set_output("Distance", dists)


@register_node
class GridPointsNode(NodeBase):
    name = "Point Grid (2D)"
    category = "Point"
    description = "Generate an X-Y grid array of points."
    header_color = "#a3be8c"

    def setup_ports(self) -> None:
        self.add_input("Count X", PortType.INTEGER, 5)
        self.add_input("Count Y", PortType.INTEGER, 5)
        self.add_input("Step X", PortType.NUMBER, 1.0)
        self.add_input("Step Y", PortType.NUMBER, 1.0)
        self.add_output("Points", PortType.ANY, "List of Point3D")
        self.add_output("Mesh", PortType.MESH, "Point Markers Mesh")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        nx = max(1, int(self.get_input("Count X", 5)))
        ny = max(1, int(self.get_input("Count Y", 5)))
        dx = float(self.get_input("Step X", 1.0))
        dy = float(self.get_input("Step Y", 1.0))

        pts: List[Point3D] = []
        for j in range(ny):
            for i in range(nx):
                pts.append(Point3D(i * dx, j * dy, 0.0))
        self.set_output("Points", pts)
        self.set_output("Mesh", _to_mesh_data(pts))


# =====================================================================================
# 4. CURVES & PROFILES
# =====================================================================================

@register_node
class LineNode(NodeBase):
    name = "Line"
    category = "Curve"
    description = "Line segment connecting two points."
    header_color = "#ebcb8b"

    def setup_ports(self) -> None:
        self.add_input("A", PortType.POINT, Point3D(0, 0, 0))
        self.add_input("B", PortType.POINT, Point3D(1, 0, 0))
        self.add_output("Line", PortType.CURVE, "Line curve")
        self.add_output("Mesh", PortType.MESH, "Wireframe Edge Mesh")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        a_in = self.get_input("A", Point3D(0, 0, 0))
        b_in = self.get_input("B", Point3D(1, 0, 0))

        as_ = a_in if isinstance(a_in, (list, tuple)) else [a_in]
        bs_ = b_in if isinstance(b_in, (list, tuple)) else [b_in]

        count = max(len(as_), len(bs_))
        all_lines: List[PolylineData] = []
        all_edges: List[EdgeData] = []

        for i in range(count):
            a = as_[min(i, len(as_) - 1)]
            b = bs_[min(i, len(bs_) - 1)]
            if isinstance(a, Point3D) and isinstance(b, Point3D):
                all_lines.append(PolylineData(points=[a, b], closed=False))
                all_edges.append(EdgeData(a, b))

        if len(all_lines) == 1:
            self.set_output("Line", all_lines[0])
        else:
            self.set_output("Line", all_lines)
        self.set_output("Mesh", MeshData(edges=all_edges, name="Line"))


@register_node
class RectangleNode(NodeBase):
    name = "Rectangle"
    category = "Curve"
    description = "Planar rectangle profile / face."
    header_color = "#ebcb8b"

    def setup_ports(self) -> None:
        self.add_input("Origin", PortType.POINT, Point3D(0, 0, 0))
        self.add_input("Width", PortType.NUMBER, 4.0)
        self.add_input("Length", PortType.NUMBER, 6.0)
        self.add_input("Centered", PortType.BOOLEAN, True)
        self.add_output("Profile", PortType.CURVE, "Closed 4-point polygon")
        self.add_output("Mesh", PortType.MESH, "Planar Face Mesh")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        orig_in = self.get_input("Origin", Point3D(0, 0, 0))
        w_in = self.get_input("Width", 4.0)
        l_in = self.get_input("Length", 6.0)
        centered = bool(self.get_input("Centered", True))

        if isinstance(orig_in, (list, tuple)):
            origins = [p for p in orig_in if isinstance(p, Point3D)]
        elif isinstance(orig_in, Point3D):
            origins = [orig_in]
        else:
            origins = [Point3D(0, 0, 0)]

        ws = w_in if isinstance(w_in, (list, tuple)) else [w_in]
        ls = l_in if isinstance(l_in, (list, tuple)) else [l_in]

        all_polylines: List[PolylineData] = []
        all_faces: List[FaceData] = []
        all_edges: List[EdgeData] = []

        for idx, o in enumerate(origins):
            w = float(ws[min(idx, len(ws) - 1)])
            l = float(ls[min(idx, len(ls) - 1)])

            if centered:
                x0, x1 = o.x - w / 2, o.x + w / 2
                y0, y1 = o.y - l / 2, o.y + l / 2
            else:
                x0, x1 = o.x, o.x + w
                y0, y1 = o.y, o.y + l

            pts = [
                Point3D(x0, y0, o.z),
                Point3D(x1, y0, o.z),
                Point3D(x1, y1, o.z),
                Point3D(x0, y1, o.z),
            ]
            all_polylines.append(PolylineData(points=pts, closed=True))
            all_faces.append(FaceData(vertices=pts))
            all_edges.extend([EdgeData(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))])

        if len(all_polylines) == 1:
            self.set_output("Profile", all_polylines[0])
        else:
            self.set_output("Profile", all_polylines)
        self.set_output("Mesh", MeshData(faces=all_faces, edges=all_edges, name="Rectangle"))


@register_node
class CirclePolygonNode(NodeBase):
    name = "Circle / Polygon"
    category = "Curve"
    description = "Circular profile or regular n-gon."
    header_color = "#ebcb8b"

    def setup_ports(self) -> None:
        self.add_input("Center", PortType.POINT, Point3D(0, 0, 0))
        self.add_input("Radius", PortType.NUMBER, 2.0)
        self.add_input("Segments", PortType.INTEGER, 24)
        self.add_output("Profile", PortType.CURVE, "Circular polygon")
        self.add_output("Mesh", PortType.MESH, "Planar Face Mesh")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        center_in = self.get_input("Center", Point3D(0, 0, 0))
        r_in = self.get_input("Radius", 2.0)
        segs_in = self.get_input("Segments", 24)

        if isinstance(center_in, (list, tuple)):
            centers = [p for p in center_in if isinstance(p, Point3D)]
        elif isinstance(center_in, Point3D):
            centers = [center_in]
        else:
            centers = [Point3D(0, 0, 0)]

        radii = r_in if isinstance(r_in, (list, tuple)) else [r_in]
        segments = segs_in if isinstance(segs_in, (list, tuple)) else [segs_in]

        all_polylines: List[PolylineData] = []
        all_faces: List[FaceData] = []
        all_edges: List[EdgeData] = []

        for idx, c in enumerate(centers):
            r = float(radii[min(idx, len(radii) - 1)])
            segs = max(3, int(segments[min(idx, len(segments) - 1)]))

            pts: List[Point3D] = []
            for i in range(segs):
                angle = 2.0 * math.pi * i / segs
                pts.append(Point3D(c.x + r * math.cos(angle), c.y + r * math.sin(angle), c.z))

            all_polylines.append(PolylineData(points=pts, closed=True))
            all_faces.append(FaceData(vertices=pts))
            all_edges.extend([EdgeData(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))])

        if len(all_polylines) == 1:
            self.set_output("Profile", all_polylines[0])
        else:
            self.set_output("Profile", all_polylines)
        self.set_output("Mesh", MeshData(faces=all_faces, edges=all_edges, name="Circle"))


# =====================================================================================
# 5. SOLIDS & 3D GEOMETRY
# =====================================================================================

@register_node
class BoxNode(NodeBase):
    name = "Box (Solid)"
    category = "Solids"
    description = "Parametric 6-sided solid box cuboid."
    header_color = "#b48ead"

    def setup_ports(self) -> None:
        self.add_input("Center", PortType.POINT, Point3D(0, 0, 0))
        self.add_input("Size X", PortType.NUMBER, 3.0)
        self.add_input("Size Y", PortType.NUMBER, 4.0)
        self.add_input("Size Z", PortType.NUMBER, 2.5)
        self.add_input("Centered", PortType.BOOLEAN, False)
        self.add_output("Mesh", PortType.MESH, "Solid Box Mesh")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        center_in = self.get_input("Center", Point3D(0, 0, 0))
        dx_in = self.get_input("Size X", 3.0)
        dy_in = self.get_input("Size Y", 4.0)
        dz_in = self.get_input("Size Z", 2.5)
        centered = bool(self.get_input("Centered", False))

        if isinstance(center_in, (list, tuple)):
            centers = [p for p in center_in if isinstance(p, Point3D)]
        elif isinstance(center_in, Point3D):
            centers = [center_in]
        else:
            centers = [Point3D(0, 0, 0)]

        dxs = dx_in if isinstance(dx_in, (list, tuple)) else [dx_in]
        dys = dy_in if isinstance(dy_in, (list, tuple)) else [dy_in]
        dzs = dz_in if isinstance(dz_in, (list, tuple)) else [dz_in]

        all_faces: List[FaceData] = []
        all_edges: List[EdgeData] = []

        for idx, c in enumerate(centers):
            dx = float(dxs[min(idx, len(dxs) - 1)])
            dy = float(dys[min(idx, len(dys) - 1)])
            dz = float(dzs[min(idx, len(dzs) - 1)])
            b_mesh = create_box(c, dx, dy, dz, centered=centered)
            all_faces.extend(b_mesh.faces)
            all_edges.extend(b_mesh.edges)

        self.set_output("Mesh", MeshData(faces=all_faces, edges=all_edges, name="Box"))


@register_node
class CylinderNode(NodeBase):
    name = "Cylinder (Solid)"
    category = "Solids"
    description = "Parametric solid cylinder with top/bottom caps."
    header_color = "#b48ead"

    def setup_ports(self) -> None:
        self.add_input("Base", PortType.POINT, Point3D(0, 0, 0))
        self.add_input("Radius", PortType.NUMBER, 1.0)
        self.add_input("Height", PortType.NUMBER, 3.0)
        self.add_input("Segments", PortType.INTEGER, 24)
        self.add_output("Mesh", PortType.MESH, "Solid Cylinder Mesh")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        base_in = self.get_input("Base", Point3D(0, 0, 0))
        r_in = self.get_input("Radius", 1.0)
        h_in = self.get_input("Height", 3.0)
        segs_in = self.get_input("Segments", 24)

        if isinstance(base_in, (list, tuple)):
            bases = [p for p in base_in if isinstance(p, Point3D)]
        elif isinstance(base_in, Point3D):
            bases = [base_in]
        else:
            bases = [Point3D(0, 0, 0)]

        radii = r_in if isinstance(r_in, (list, tuple)) else [r_in]
        heights = h_in if isinstance(h_in, (list, tuple)) else [h_in]
        segments = segs_in if isinstance(segs_in, (list, tuple)) else [segs_in]

        all_faces: List[FaceData] = []
        all_edges: List[EdgeData] = []

        for idx, base in enumerate(bases):
            r = float(radii[min(idx, len(radii) - 1)])
            h = float(heights[min(idx, len(heights) - 1)])
            segs = max(3, int(segments[min(idx, len(segments) - 1)]))

            c_mesh = create_cylinder(base, r, h, segments=segs)
            all_faces.extend(c_mesh.faces)
            all_edges.extend(c_mesh.edges)

        self.set_output("Mesh", MeshData(faces=all_faces, edges=all_edges, name="Cylinder"))


@register_node
class SphereNode(NodeBase):
    name = "Sphere (Solid)"
    category = "Solids"
    description = "Parametric UV sphere mesh."
    header_color = "#b48ead"

    def setup_ports(self) -> None:
        self.add_input("Center", PortType.POINT, Point3D(0, 0, 0))
        self.add_input("Radius", PortType.NUMBER, 1.5)
        self.add_input("Rings", PortType.INTEGER, 12)
        self.add_input("Segments", PortType.INTEGER, 24)
        self.add_output("Mesh", PortType.MESH, "Solid Sphere Mesh")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        center_in = self.get_input("Center", Point3D(0, 0, 0))
        r_in = self.get_input("Radius", 1.5)
        rings_in = self.get_input("Rings", 12)
        segs_in = self.get_input("Segments", 24)

        if isinstance(center_in, (list, tuple)):
            centers = [p for p in center_in if isinstance(p, Point3D)]
        elif isinstance(center_in, Point3D):
            centers = [center_in]
        else:
            centers = [Point3D(0, 0, 0)]

        radii = r_in if isinstance(r_in, (list, tuple)) else [r_in]
        rings_l = rings_in if isinstance(rings_in, (list, tuple)) else [rings_in]
        segs_l = segs_in if isinstance(segs_in, (list, tuple)) else [segs_in]

        all_faces: List[FaceData] = []
        all_edges: List[EdgeData] = []

        for idx, c in enumerate(centers):
            r = float(radii[min(idx, len(radii) - 1)])
            rings = int(rings_l[min(idx, len(rings_l) - 1)])
            segs = int(segs_l[min(idx, len(segs_l) - 1)])
            s_mesh = create_sphere(c, r, rings=rings, segments=segs)
            all_faces.extend(s_mesh.faces)
            all_edges.extend(s_mesh.edges)

        self.set_output("Mesh", MeshData(faces=all_faces, edges=all_edges, name="Sphere"))


@register_node
class ExtrudeNode(NodeBase):
    name = "Extrude Profile"
    category = "Solids"
    description = "Extrude a planar polygon curve, face, or points along a height/vector into a 3D solid."
    header_color = "#b48ead"

    def setup_ports(self) -> None:
        self.add_input("Profile", PortType.ANY, description="FaceData, MeshData, PolylineData, or List[Point3D]")
        self.add_input("Height", PortType.NUMBER, 3.0)
        self.add_input("Direction", PortType.VECTOR, Vector3D(0, 0, 1))
        self.add_output("Mesh", PortType.MESH, "Extruded solid mesh")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        prof = self.get_input("Profile")
        h = float(self.get_input("Height", 3.0))
        v_dir = self.get_input("Direction", Vector3D(0, 0, 1))

        if isinstance(v_dir, Vector3D):
            v = v_dir.normalized() * h
        else:
            v = Vector3D(0, 0, h)

        # 1. Direct FaceData extrusion (with holes)
        if isinstance(prof, FaceData) and len(prof.vertices) >= 3:
            all_faces = [
                FaceData(vertices=list(reversed(prof.vertices)), holes=[list(reversed(h_loop)) for h_loop in prof.holes]),
                FaceData(vertices=[p.translated(v) for p in prof.vertices], holes=[[p.translated(v) for p in h_loop] for h_loop in prof.holes])
            ]
            all_edges = []
            n_o = len(prof.vertices)
            for i in range(n_o):
                nxt = (i + 1) % n_o
                p0, p1 = prof.vertices[i], prof.vertices[nxt]
                all_faces.append(FaceData([p0, p1, p1.translated(v), p0.translated(v)]))
                all_edges.append(EdgeData(p0, p1))
                all_edges.append(EdgeData(p0.translated(v), p1.translated(v)))
                all_edges.append(EdgeData(p0, p0.translated(v)))
            for h_loop in prof.holes:
                n_h = len(h_loop)
                for i in range(n_h):
                    nxt = (i + 1) % n_h
                    p0, p1 = h_loop[i], h_loop[nxt]
                    all_faces.append(FaceData([p1, p0, p0.translated(v), p1.translated(v)]))
                    all_edges.append(EdgeData(p0, p1))
                    all_edges.append(EdgeData(p0.translated(v), p1.translated(v)))
                    all_edges.append(EdgeData(p0, p0.translated(v)))
            self.set_output("Mesh", MeshData(faces=all_faces, edges=all_edges, name="Extrusion"))
            return

        # 2. MeshData containing FaceData
        if isinstance(prof, MeshData) and prof.faces:
            all_faces = []
            all_edges = []
            for face in prof.faces:
                if len(face.vertices) < 3:
                    continue
                all_faces.append(FaceData(vertices=list(reversed(face.vertices)), holes=[list(reversed(h_loop)) for h_loop in face.holes]))
                all_faces.append(FaceData(vertices=[p.translated(v) for p in face.vertices], holes=[[p.translated(v) for p in h_loop] for h_loop in face.holes]))
                n_o = len(face.vertices)
                for i in range(n_o):
                    nxt = (i + 1) % n_o
                    p0, p1 = face.vertices[i], face.vertices[nxt]
                    all_faces.append(FaceData([p0, p1, p1.translated(v), p0.translated(v)]))
                    all_edges.append(EdgeData(p0, p1))
                    all_edges.append(EdgeData(p0.translated(v), p1.translated(v)))
                for h_loop in face.holes:
                    n_h = len(h_loop)
                    for i in range(n_h):
                        nxt = (i + 1) % n_h
                        p0, p1 = h_loop[i], h_loop[nxt]
                        all_faces.append(FaceData([p1, p0, p0.translated(v), p1.translated(v)]))
                        all_edges.append(EdgeData(p0, p1))
                        all_edges.append(EdgeData(p0.translated(v), p1.translated(v)))
            self.set_output("Mesh", MeshData(faces=all_faces, edges=all_edges, name="Extrusion"))
            return

        # 3. PolylineData or list of points
        profiles: List[PolylineData] = []
        if isinstance(prof, PolylineData):
            profiles = [prof]
        elif isinstance(prof, (list, tuple)):
            if prof and isinstance(prof[0], PolylineData):
                profiles = [p for p in prof if isinstance(p, PolylineData)]
            elif prof and isinstance(prof[0], Point3D):
                profiles = [PolylineData(points=[p for p in prof if isinstance(p, Point3D)], closed=True)]
            elif prof and isinstance(prof[0], (list, tuple)):
                for sub in prof:
                    pts = [p for p in sub if isinstance(p, Point3D)]
                    if len(pts) >= 3:
                        profiles.append(PolylineData(points=pts, closed=True))

        all_faces: List[FaceData] = []
        all_edges: List[EdgeData] = []

        for p in profiles:
            if len(p.points) >= 3:
                m = extrude_profile(p.points, v)
                all_faces.extend(m.faces)
                all_edges.extend(m.edges)

        self.set_output("Mesh", MeshData(faces=all_faces, edges=all_edges, name="Extrusion"))


# -------------------------------------------------------------------------------------
# Roof & Face Extraction Helpers
# -------------------------------------------------------------------------------------

def _extract_surface_boundary_and_holes(
    surface_raw: Any, extra_holes_raw: Any = None
) -> Tuple[List[Point3D], List[List[Point3D]]]:
    """Extract outer boundary vertices and interior hole loops from any surface, face, or curve format."""
    outer: List[Point3D] = []
    holes: List[List[Point3D]] = []

    def to_pt3d(v: Any) -> Optional[Point3D]:
        if isinstance(v, Point3D):
            return v
        if hasattr(v, "x") and hasattr(v, "y"):
            x = v.x() if callable(v.x) else v.x
            y = v.y() if callable(v.y) else v.y
            z = (v.z() if callable(v.z) else v.z) if hasattr(v, "z") else 0.0
            return Point3D(float(x), float(y), float(z))
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            return Point3D(float(v[0]), float(v[1]), float(v[2]) if len(v) > 2 else 0.0)
        return None

    def extract_pts(seq: Any) -> List[Point3D]:
        if isinstance(seq, PolylineData):
            return list(seq.points)
        if isinstance(seq, FaceData):
            return list(seq.vertices)
        if isinstance(seq, (list, tuple)):
            res: List[Point3D] = []
            for item in seq:
                p = to_pt3d(item)
                if p:
                    res.append(p)
            return res
        return []

    # 1. Primary surface input
    if isinstance(surface_raw, FaceData):
        outer = list(surface_raw.vertices)
        holes = [extract_pts(h) for h in surface_raw.holes if len(extract_pts(h)) >= 3]
    elif isinstance(surface_raw, MeshData):
        if surface_raw.faces:
            outer = list(surface_raw.faces[0].vertices)
            holes = [extract_pts(h) for h in surface_raw.faces[0].holes if len(extract_pts(h)) >= 3]
            for extra_face in surface_raw.faces[1:]:
                f_pts = extract_pts(extra_face.vertices)
                if len(f_pts) >= 3:
                    holes.append(f_pts)
    elif isinstance(surface_raw, PolylineData):
        outer = list(surface_raw.points)
    elif isinstance(surface_raw, (list, tuple)):
        if surface_raw and isinstance(surface_raw[0], (FaceData, PolylineData)):
            first = surface_raw[0]
            if isinstance(first, FaceData):
                outer = list(first.vertices)
                holes = [extract_pts(h) for h in first.holes if len(extract_pts(h)) >= 3]
            else:
                outer = list(first.points)
            for item in surface_raw[1:]:
                pts = extract_pts(item)
                if len(pts) >= 3:
                    holes.append(pts)
        else:
            outer = extract_pts(surface_raw)
    elif hasattr(surface_raw, "vertices"):
        outer = extract_pts(surface_raw.vertices)
        if hasattr(surface_raw, "holes") and surface_raw.holes:
            for h in surface_raw.holes:
                pts = extract_pts(h)
                if len(pts) >= 3:
                    holes.append(pts)

    # 2. Extra holes input
    if extra_holes_raw:
        if isinstance(extra_holes_raw, (FaceData, PolylineData)):
            pts = extract_pts(extra_holes_raw)
            if len(pts) >= 3:
                holes.append(pts)
        elif isinstance(extra_holes_raw, MeshData):
            for f in extra_holes_raw.faces:
                pts = extract_pts(f.vertices)
                if len(pts) >= 3:
                    holes.append(pts)
        elif isinstance(extra_holes_raw, (list, tuple)):
            if (
                extra_holes_raw
                and isinstance(extra_holes_raw[0], (Point3D, tuple, list))
                and len(extra_holes_raw[0]) in (2, 3)
                and isinstance(extra_holes_raw[0][0], (int, float))
            ):
                pts = extract_pts(extra_holes_raw)
                if len(pts) >= 3:
                    holes.append(pts)
            else:
                for item in extra_holes_raw:
                    pts = extract_pts(item)
                    if len(pts) >= 3:
                        holes.append(pts)

    return outer, holes


def _clean_and_orient_rings(
    outer: List[Tuple[float, float]],
    holes: List[List[Tuple[float, float]]],
    tol: float = 1e-4
) -> Tuple[List[Tuple[float, float]], List[List[Tuple[float, float]]]]:
    """Clean duplicate and collinear points, and enforce Counter-Clockwise (CCW) for exterior, Clockwise (CW) for holes."""
    def clean_ring(pts: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        if len(pts) < 3:
            return pts
        res = [pts[0]]
        for p in pts[1:]:
            if (p[0] - res[-1][0]) ** 2 + (p[1] - res[-1][1]) ** 2 > tol * tol:
                res.append(p)
        if len(res) > 2 and (res[0][0] - res[-1][0]) ** 2 + (res[0][1] - res[-1][1]) ** 2 <= tol * tol:
            res.pop()

        cleaned = []
        n = len(res)
        for i in range(n):
            p_prev = res[(i - 1) % n]
            p_curr = res[i]
            p_next = res[(i + 1) % n]
            dx1 = p_curr[0] - p_prev[0]
            dy1 = p_curr[1] - p_prev[1]
            dx2 = p_next[0] - p_curr[0]
            dy2 = p_next[1] - p_curr[1]
            cross = dx1 * dy2 - dy1 * dx2
            l1 = math.hypot(dx1, dy1)
            l2 = math.hypot(dx2, dy2)
            if l1 > tol and l2 > tol:
                sin_a = abs(cross) / (l1 * l2)
                if sin_a > 1e-4:
                    cleaned.append(p_curr)
            else:
                cleaned.append(p_curr)
        return cleaned if len(cleaned) >= 3 else res

    def ensure_winding(pts: List[Tuple[float, float]], ccw: bool = True) -> List[Tuple[float, float]]:
        if len(pts) < 3:
            return pts
        area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts))) * 0.5
        if (ccw and area < 0) or (not ccw and area > 0):
            return list(reversed(pts))
        return pts

    c_outer = ensure_winding(clean_ring(outer), ccw=True)
    c_holes: List[List[Tuple[float, float]]] = []
    for h in holes:
        cl_h = clean_ring(h)
        if len(cl_h) >= 3:
            c_holes.append(ensure_winding(cl_h, ccw=False))

    return c_outer, c_holes


def _offset_ring(
    pts: List[Tuple[float, float]],
    dist: float,
    miter_limit: float = 3.0
) -> List[Tuple[float, float]]:
    """Offset a 2D polygon ring by distance `dist`.
    For a CCW ring: positive `dist` expands outward, negative shrinks inward.
    For a CW ring (hole): positive `dist` expands into the hole (shrinks hole size).
    Pure Python with zero external C-dependencies.
    """
    n = len(pts)
    if n < 3 or abs(dist) < 1e-6:
        return list(pts)

    normals: List[Tuple[float, float]] = []
    for i in range(n):
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        L = math.hypot(dx, dy)
        if L < 1e-7:
            normals.append((0.0, 0.0))
        else:
            normals.append((dy / L, -dx / L))

    res: List[Tuple[float, float]] = []
    for i in range(n):
        prev = (i - 1 + n) % n
        n1 = normals[prev]
        n2 = normals[i]
        p = pts[i]

        det = n1[0] * n2[1] - n1[1] * n2[0]
        if abs(det) < 1e-5:
            res.append((p[0] + dist * n2[0], p[1] + dist * n2[1]))
            continue

        u = dist * (n2[1] - n1[1]) / det
        v = dist * (n1[0] - n2[0]) / det
        miter_len = math.hypot(u, v)
        max_len = abs(dist) * miter_limit
        if miter_len > max_len and miter_len > 1e-6:
            scale = max_len / miter_len
            u *= scale
            v *= scale
        res.append((p[0] + u, p[1] + v))

    return res


@register_node
class FaceFromPointsNode(NodeBase):
    name = "Face from Points"
    category = "Solids"
    description = "Create a planar polygonal face from a closed boundary loop of points and optional hole loops."
    header_color = "#b48ead"

    def setup_ports(self) -> None:
        self.add_input("Points", PortType.ANY, description="Outer boundary (PolylineData or List[Point3D])")
        self.add_input("Holes", PortType.ANY, description="Optional hole loops (FaceData, PolylineData, or List[Point3D])")
        self.add_output("Mesh", PortType.MESH, "Face mesh representation")
        self.add_output("Face", PortType.ANY, "FaceData object with vertices and holes")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        pts_in = self.get_input("Points")
        holes_in = self.get_input("Holes")
        outer_pts, holes_pts = _extract_surface_boundary_and_holes(pts_in, holes_in)

        if len(outer_pts) >= 3:
            face = FaceData(vertices=outer_pts, holes=holes_pts)
            self.set_output("Mesh", MeshData(faces=[face], name="FaceMesh"))
            self.set_output("Face", face)
        else:
            self.set_output("Mesh", MeshData())
            self.set_output("Face", None)


@register_node
class RoofFromSurfaceNode(NodeBase):
    name = "Roof from Surface"
    category = "Solids"
    description = (
        "Generate a 3D parametric roof (Hip / Straight Skeleton, Gable, Shed, Flat/Parapet, Mansard) "
        "from a planar surface or face with optional courtyard/interior holes. "
        "Computes exact ridges, hips, valleys, eaves, and 3D watertight solid mesh."
    )
    header_color = "#bf616a"

    def setup_ports(self) -> None:
        self.add_input("Surface", PortType.ANY, description="Planar surface/face (FaceData, MeshData, or Polyline) with optional holes")
        self.add_input("Holes", PortType.ANY, description="Optional extra hole loops (FaceData, Polyline, or List[Point3D])")
        self.add_input("Angle", PortType.NUMBER, 35.0, "Roof pitch / slope angle in degrees (e.g. 30° to 45°)")
        self.add_input("Style", PortType.INTEGER, 0, "0: Hip (Straight Skeleton), 1: Gable, 2: Shed, 3: Flat / Parapet, 4: Mansard")
        self.add_input("Overhang", PortType.NUMBER, 0.3, "Eave overhang distance outside wall boundary (m)")
        self.add_input("Thickness", PortType.NUMBER, 0.2, "Roof fascia and slab thickness to generate 3D solid (m)")
        self.add_input("Elevation", PortType.NUMBER, 0.0, "Base elevation offset (m)")

        self.add_output("Mesh", PortType.MESH, "3D solid watertight roof mesh")
        self.add_output("3D Regions", PortType.ANY, "Individual 3D sloped roof facets (List[PolylineData])")
        self.add_output("Ridges", PortType.ANY, "Horizontal and upper ridge lines (List[PolylineData])")
        self.add_output("Hips & Valleys", PortType.ANY, "Diagonal hip and valley crease lines (List[PolylineData])")
        self.add_output("Eaves", PortType.ANY, "Perimeter eave boundary lines (List[PolylineData])")
        self.add_output("Roof Points", PortType.ANY, "Top ridge and peak points (List[Point3D])")
        self.add_output("Heights", PortType.ANY, "Ridge and peak heights above base")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        self.error = None
        surf_raw = self.get_input("Surface")
        holes_raw = self.get_input("Holes")
        angle = max(1.0, min(89.0, float(self.get_input("Angle", 35.0))))
        style = int(self.get_input("Style", 0))
        overhang = max(0.0, float(self.get_input("Overhang", 0.3)))
        thickness = max(0.0, float(self.get_input("Thickness", 0.2)))
        elevation = float(self.get_input("Elevation", 0.0))

        outer_pts, holes_pts = _extract_surface_boundary_and_holes(surf_raw, holes_raw)

        # Default fallback if disconnected: 24x16m house with an 8x6m courtyard
        if len(outer_pts) < 3:
            outer_pts = [
                Point3D(0.0, 0.0, 3.0),
                Point3D(24.0, 0.0, 3.0),
                Point3D(24.0, 16.0, 3.0),
                Point3D(0.0, 16.0, 3.0)
            ]
            holes_pts = [[
                Point3D(8.0, 5.0, 3.0),
                Point3D(16.0, 5.0, 3.0),
                Point3D(16.0, 11.0, 3.0),
                Point3D(8.0, 11.0, 3.0)
            ]]

        z_vals = [p.z for p in outer_pts]
        avg_z = sum(z_vals) / len(z_vals)
        is_xy = all(abs(p.z - avg_z) < 1e-3 for p in outer_pts)

        if is_xy:
            z_base = avg_z + elevation
            u_axis = Vector3D(1, 0, 0)
            v_axis = Vector3D(0, 1, 0)
            w_axis = Vector3D(0, 0, 1)
            origin_3d = Point3D(0, 0, z_base)
            outer_2d = [(p.x, p.y) for p in outer_pts]
            holes_2d = [[(p.x, p.y) for p in h] for h in holes_pts]
        else:
            normal = FaceData(vertices=outer_pts).normal()
            if normal.z < 0:
                normal = Vector3D(-normal.x, -normal.y, -normal.z)
            w_axis = normal
            ref = Vector3D(0, 0, 1) if abs(normal.z) < 0.9 else Vector3D(1, 0, 0)
            u_axis = w_axis.cross(ref).normalized()
            v_axis = w_axis.cross(u_axis).normalized()
            origin_3d = outer_pts[0].translated(w_axis * elevation)

            def to_2d(p: Point3D) -> Tuple[float, float]:
                d = p - origin_3d
                return (d.dot(u_axis), d.dot(v_axis))

            outer_2d = [to_2d(p) for p in outer_pts]
            holes_2d = [[to_2d(p) for p in h] for h in holes_pts]

        def to_3d(u: float, v: float, h: float) -> Point3D:
            return origin_3d + (u_axis * u) + (v_axis * v) + (w_axis * h)

        c_outer, c_holes = _clean_and_orient_rings(outer_2d, holes_2d)

        # Apply overhang buffer if requested
        if overhang > 1e-4:
            buffered = False
            if Polygon is not None:
                try:
                    poly_ext = Polygon(c_outer).buffer(overhang, join_style="mitre", mitre_limit=3.0)
                    if not poly_ext.is_empty and poly_ext.geom_type == "Polygon":
                        c_outer = list(poly_ext.exterior.coords)[:-1]

                    new_holes = []
                    for h_ring in c_holes:
                        h_poly = Polygon(h_ring).buffer(-overhang, join_style="mitre", mitre_limit=3.0)
                        if not h_poly.is_empty and h_poly.geom_type == "Polygon" and h_poly.area > 0.1:
                            new_holes.append(list(h_poly.exterior.coords)[:-1])
                        elif h_poly.is_empty or h_poly.area <= 0.1:
                            pass
                        else:
                            new_holes.append(h_ring)
                    c_holes = new_holes
                    c_outer, c_holes = _clean_and_orient_rings(c_outer, c_holes)
                    buffered = True
                except Exception:
                    buffered = False

            if not buffered:
                try:
                    c_outer = _offset_ring(c_outer, overhang)
                    new_holes = []
                    for h_ring in c_holes:
                        h_off = _offset_ring(h_ring, overhang)
                        # Check remaining hole area
                        a = sum(h_off[i][0] * h_off[(i + 1) % len(h_off)][1] - h_off[(i + 1) % len(h_off)][0] * h_off[i][1] for i in range(len(h_off))) * 0.5
                        if abs(a) > 0.1:
                            new_holes.append(h_off)
                    c_holes = new_holes
                    c_outer, c_holes = _clean_and_orient_rings(c_outer, c_holes)
                except Exception:
                    pass

        top_faces: List[FaceData] = []
        ridge_lines: List[PolylineData] = []
        hip_lines: List[PolylineData] = []
        eave_lines: List[PolylineData] = []
        roof_points: List[Point3D] = []
        heights_out: List[float] = []
        regions_3d: List[PolylineData] = []
        explicit_edges: List[EdgeData] = []

        rad = math.radians(angle)
        tan_a = math.tan(rad)

        # -----------------------------------------------------------------------------
        # Style 0: Hip (Straight Skeleton)
        # -----------------------------------------------------------------------------
        if style == 0 and compute_skeleton is not None:
            try:
                skel = compute_skeleton(c_outer, c_holes)
                skel_faces = skel.get_faces()

                for face_indices in skel_faces:
                    facet_pts_3d: List[Point3D] = []
                    for idx in face_indices:
                        node = skel.nodes[idx]
                        dist_val = max(0.0, float(node.time))
                        h = dist_val * tan_a
                        pt3d = to_3d(node.position.x, node.position.y, h)
                        facet_pts_3d.append(pt3d)

                    cleaned_facet: List[Point3D] = []
                    for p in facet_pts_3d:
                        if not cleaned_facet or cleaned_facet[-1].distance_to(p) > 1e-4:
                            cleaned_facet.append(p)
                    if len(cleaned_facet) > 2 and cleaned_facet[0].distance_to(cleaned_facet[-1]) <= 1e-4:
                        cleaned_facet.pop()

                    if len(cleaned_facet) >= 3:
                        top_faces.append(FaceData(vertices=cleaned_facet, color=(0.78, 0.38, 0.28)))
                        regions_3d.append(PolylineData(points=cleaned_facet, closed=True))

                for a_node, b_node in skel.arc_iterator():
                    pA = to_3d(a_node.position.x, a_node.position.y, max(0.0, a_node.time) * tan_a)
                    pB = to_3d(b_node.position.x, b_node.position.y, max(0.0, b_node.time) * tan_a)
                    if pA.distance_to(pB) < 1e-4:
                        continue

                    if a_node.time > 1e-4 and b_node.time > 1e-4:
                        ridge_lines.append(PolylineData(points=[pA, pB], closed=False))
                        explicit_edges.append(EdgeData(pA, pB))
                    else:
                        hip_lines.append(PolylineData(points=[pA, pB], closed=False))
                        explicit_edges.append(EdgeData(pA, pB))

                seen_pts = set()
                for node in skel.nodes:
                    if node.time > 1e-4:
                        h = node.time * tan_a
                        pt = to_3d(node.position.x, node.position.y, h)
                        k = (round(pt.x, 3), round(pt.y, 3), round(pt.z, 3))
                        if k not in seen_pts:
                            seen_pts.add(k)
                            roof_points.append(pt)
                            heights_out.append(h)

            except Exception as ex:
                self.error = f"Straight skeleton notice: {ex}"
                style = 1  # Fallback to Gable

        # -----------------------------------------------------------------------------
        # Style 1: Gable
        # -----------------------------------------------------------------------------
        if (style == 1 or not top_faces) and style != 2 and style != 3 and style != 4:
            xs = [p[0] for p in c_outer]
            ys = [p[1] for p in c_outer]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            dx = max_x - min_x
            dy = max_y - min_y

            along_x = dx >= dy
            if along_x:
                mid_v = (min_y + max_y) * 0.5
                half_span = dy * 0.5
                ridge_h = half_span * tan_a
                p_r1 = to_3d(min_x - overhang, mid_v, ridge_h)
                p_r2 = to_3d(max_x + overhang, mid_v, ridge_h)
            else:
                mid_v = (min_x + max_x) * 0.5
                half_span = dx * 0.5
                ridge_h = half_span * tan_a
                p_r1 = to_3d(mid_v, min_y - overhang, ridge_h)
                p_r2 = to_3d(mid_v, max_y + overhang, ridge_h)

            ridge_lines.append(PolylineData(points=[p_r1, p_r2], closed=False))
            explicit_edges.append(EdgeData(p_r1, p_r2))
            roof_points.extend([p_r1, p_r2])
            heights_out.extend([ridge_h, ridge_h])

            if along_x:
                p_sw = to_3d(min_x - overhang, min_y, 0.0)
                p_se = to_3d(max_x + overhang, min_y, 0.0)
                s_facet = [p_sw, p_se, p_r2, p_r1]
                top_faces.append(FaceData(vertices=s_facet, color=(0.78, 0.38, 0.28)))
                regions_3d.append(PolylineData(points=s_facet, closed=True))

                p_nw = to_3d(min_x - overhang, max_y, 0.0)
                p_ne = to_3d(max_x + overhang, max_y, 0.0)
                n_facet = [p_r1, p_r2, p_ne, p_nw]
                top_faces.append(FaceData(vertices=n_facet, color=(0.78, 0.38, 0.28)))
                regions_3d.append(PolylineData(points=n_facet, closed=True))

                top_faces.append(FaceData(vertices=[p_sw, p_r1, p_nw], color=(0.75, 0.72, 0.70)))
                top_faces.append(FaceData(vertices=[p_se, p_ne, p_r2], color=(0.75, 0.72, 0.70)))
            else:
                p_sw = to_3d(min_x, min_y - overhang, 0.0)
                p_nw = to_3d(min_x, max_y + overhang, 0.0)
                w_facet = [p_sw, p_r1, p_r2, p_nw]
                top_faces.append(FaceData(vertices=w_facet, color=(0.78, 0.38, 0.28)))
                regions_3d.append(PolylineData(points=w_facet, closed=True))

                p_se = to_3d(max_x, min_y - overhang, 0.0)
                p_ne = to_3d(max_x, max_y + overhang, 0.0)
                e_facet = [p_r1, p_se, p_ne, p_r2]
                top_faces.append(FaceData(vertices=e_facet, color=(0.78, 0.38, 0.28)))
                regions_3d.append(PolylineData(points=e_facet, closed=True))

                top_faces.append(FaceData(vertices=[p_sw, p_se, p_r1], color=(0.75, 0.72, 0.70)))
                top_faces.append(FaceData(vertices=[p_nw, p_r2, p_ne], color=(0.75, 0.72, 0.70)))

        # -----------------------------------------------------------------------------
        # Style 2: Shed / Mono-Pitch
        # -----------------------------------------------------------------------------
        elif style == 2:
            xs = [p[0] for p in c_outer]
            ys = [p[1] for p in c_outer]
            min_y, max_y = min(ys), max(ys)
            span_y = max(1.0, max_y - min_y)

            lifted_outer = [to_3d(p[0], p[1], ((p[1] - min_y) / span_y) * span_y * tan_a) for p in c_outer]
            lifted_holes = [
                [to_3d(p[0], p[1], ((p[1] - min_y) / span_y) * span_y * tan_a) for p in h_ring]
                for h_ring in c_holes
            ]
            top_faces.append(FaceData(vertices=lifted_outer, holes=lifted_holes, color=(0.78, 0.38, 0.28)))
            regions_3d.append(PolylineData(points=lifted_outer, closed=True))
            high_pts = [p for p in lifted_outer if p.z >= avg_z + elevation + span_y * tan_a * 0.9]
            if len(high_pts) >= 2:
                ridge_lines.append(PolylineData(points=[high_pts[0], high_pts[-1]], closed=False))
            roof_points.extend(lifted_outer)
            heights_out.append(span_y * tan_a)

        # -----------------------------------------------------------------------------
        # Style 3: Flat / Parapet
        # -----------------------------------------------------------------------------
        elif style == 3:
            parapet_h = max(0.3, thickness * 2.0)
            slab_outer = [to_3d(p[0], p[1], thickness) for p in c_outer]
            slab_holes = [[to_3d(p[0], p[1], thickness) for p in h_ring] for h_ring in c_holes]
            top_faces.append(FaceData(vertices=slab_outer, holes=slab_holes, color=(0.65, 0.68, 0.70)))
            regions_3d.append(PolylineData(points=slab_outer, closed=True))

            p_top_outer = [to_3d(p[0], p[1], thickness + parapet_h) for p in c_outer]
            n_o = len(c_outer)
            for i in range(n_o):
                nxt = (i + 1) % n_o
                p0 = slab_outer[i]
                p1 = slab_outer[nxt]
                t1 = p_top_outer[nxt]
                t0 = p_top_outer[i]
                top_faces.append(FaceData(vertices=[p0, p1, t1, t0], color=(0.55, 0.58, 0.60)))
                explicit_edges.append(EdgeData(t0, t1))
            roof_points.extend(p_top_outer)
            heights_out.append(parapet_h)

        # -----------------------------------------------------------------------------
        # Style 4: Mansard / Gambrel
        # -----------------------------------------------------------------------------
        elif style == 4 and compute_skeleton is not None:
            try:
                skel = compute_skeleton(c_outer, c_holes)
                skel_faces = skel.get_faces()
                max_d = max(node.time for node in skel.nodes) if skel.nodes else 1.0
                d_trans = max_d * 0.45
                h_trans = d_trans * math.tan(math.radians(65.0))

                for face_indices in skel_faces:
                    facet_pts_3d: List[Point3D] = []
                    for idx in face_indices:
                        node = skel.nodes[idx]
                        dist_val = max(0.0, float(node.time))
                        if dist_val <= d_trans:
                            h = dist_val * math.tan(math.radians(65.0))
                        else:
                            h = h_trans + (dist_val - d_trans) * math.tan(math.radians(22.0))
                        facet_pts_3d.append(to_3d(node.position.x, node.position.y, h))

                    cleaned_facet: List[Point3D] = []
                    for p in facet_pts_3d:
                        if not cleaned_facet or cleaned_facet[-1].distance_to(p) > 1e-4:
                            cleaned_facet.append(p)
                    if len(cleaned_facet) > 2 and cleaned_facet[0].distance_to(cleaned_facet[-1]) <= 1e-4:
                        cleaned_facet.pop()

                    if len(cleaned_facet) >= 3:
                        top_faces.append(FaceData(vertices=cleaned_facet, color=(0.72, 0.32, 0.25)))
                        regions_3d.append(PolylineData(points=cleaned_facet, closed=True))

                for a_node, b_node in skel.arc_iterator():
                    distA = max(0.0, a_node.time)
                    hA = distA * math.tan(math.radians(65.0)) if distA <= d_trans else h_trans + (distA - d_trans) * math.tan(math.radians(22.0))
                    distB = max(0.0, b_node.time)
                    hB = distB * math.tan(math.radians(65.0)) if distB <= d_trans else h_trans + (distB - d_trans) * math.tan(math.radians(22.0))

                    pA = to_3d(a_node.position.x, a_node.position.y, hA)
                    pB = to_3d(b_node.position.x, b_node.position.y, hB)
                    if a_node.time > d_trans and b_node.time > d_trans:
                        ridge_lines.append(PolylineData(points=[pA, pB], closed=False))
                        explicit_edges.append(EdgeData(pA, pB))
                    else:
                        hip_lines.append(PolylineData(points=[pA, pB], closed=False))
                        explicit_edges.append(EdgeData(pA, pB))
            except Exception as ex:
                self.error = f"Mansard notice: {ex}"

        # -----------------------------------------------------------------------------
        # Eave Lines (Outer Perimeter and Holes)
        # -----------------------------------------------------------------------------
        outer_eave_pts = [to_3d(p[0], p[1], 0.0) for p in c_outer]
        eave_lines.append(PolylineData(points=outer_eave_pts, closed=True))
        for h_ring in c_holes:
            h_eave_pts = [to_3d(p[0], p[1], 0.0) for p in h_ring]
            eave_lines.append(PolylineData(points=h_eave_pts, closed=True))

        for ev in eave_lines:
            for i in range(len(ev.points)):
                nxt = (i + 1) % len(ev.points)
                explicit_edges.append(EdgeData(ev.points[i], ev.points[nxt]))

        # -----------------------------------------------------------------------------
        # Watertight Solid Generation (Thickness > 0)
        # -----------------------------------------------------------------------------
        all_mesh_faces: List[FaceData] = list(top_faces)
        if thickness > 1e-4:
            soffit_faces: List[FaceData] = []
            for tf in top_faces:
                soffit_verts = [p.translated(w_axis * (-thickness)) for p in reversed(tf.vertices)]
                soffit_holes = [[p.translated(w_axis * (-thickness)) for p in reversed(h)] for h in tf.holes] if tf.holes else []
                soffit_faces.append(FaceData(vertices=soffit_verts, holes=soffit_holes, color=(0.82, 0.82, 0.80)))

            all_mesh_faces.extend(soffit_faces)

            # Fascia along outer perimeter
            n_o = len(outer_eave_pts)
            for i in range(n_o):
                nxt = (i + 1) % n_o
                p0 = outer_eave_pts[i]
                p1 = outer_eave_pts[nxt]
                p0_b = p0.translated(w_axis * (-thickness))
                p1_b = p1.translated(w_axis * (-thickness))
                all_mesh_faces.append(FaceData(vertices=[p0, p1, p1_b, p0_b], color=(0.35, 0.35, 0.38)))
                explicit_edges.append(EdgeData(p0, p0_b))
                explicit_edges.append(EdgeData(p0_b, p1_b))

            # Fascia along courtyard hole eaves
            for h_ring in c_holes:
                h_eave_pts = [to_3d(p[0], p[1], 0.0) for p in h_ring]
                n_h = len(h_eave_pts)
                for i in range(n_h):
                    nxt = (i + 1) % n_h
                    p0 = h_eave_pts[i]
                    p1 = h_eave_pts[nxt]
                    p0_b = p0.translated(w_axis * (-thickness))
                    p1_b = p1.translated(w_axis * (-thickness))
                    all_mesh_faces.append(FaceData(vertices=[p1, p0, p0_b, p1_b], color=(0.35, 0.35, 0.38)))
                    explicit_edges.append(EdgeData(p0, p0_b))
                    explicit_edges.append(EdgeData(p0_b, p1_b))

        solid_mesh = MeshData(
            faces=all_mesh_faces,
            edges=explicit_edges,
            name="ParametricRoof",
            layer="Roof"
        )

        self.set_output("Mesh", solid_mesh)
        self.set_output("3D Regions", regions_3d)
        self.set_output("Ridges", ridge_lines)
        self.set_output("Hips & Valleys", hip_lines)
        self.set_output("Eaves", eave_lines)
        self.set_output("Roof Points", roof_points)
        self.set_output("Heights", heights_out)



@register_node
class MeshFromPointsNode(NodeBase):
    name = "Mesh from Points"
    category = "Solids"
    description = "Create a 3D quad or triangulated mesh surface from a structured grid of points with U and V counts."
    header_color = "#d08770"

    def setup_ports(self) -> None:
        self.add_input("Points", PortType.ANY, description="Grid points (List of Point3D or PolylineData)")
        self.add_input("U", PortType.INTEGER, 10, "Points count along U direction (must be >= 2)")
        self.add_input("V", PortType.INTEGER, 0, "Points count along V direction (0 for auto: total / U)")
        self.add_input("Closed U", PortType.BOOLEAN, False, "Wrap mesh in U direction (tube / cylinder)")
        self.add_input("Closed V", PortType.BOOLEAN, False, "Wrap mesh in V direction (torus)")
        self.add_input("Swap UV", PortType.BOOLEAN, False, "Transpose grid order (row-major vs column-major)")
        self.add_input("Triangulate", PortType.BOOLEAN, False, "Split quads into triangles (guarantees planar faces)")
        self.add_output("Mesh", PortType.MESH, "Generated 3D mesh surface")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        self.error = None
        pts_raw = self.get_input("Points")
        if not pts_raw:
            self.set_output("Mesh", MeshData())
            return

        # Extract 1D list of Point3D
        pts: List[Point3D] = []
        u_override: Optional[int] = None
        v_override: Optional[int] = None

        if isinstance(pts_raw, PolylineData):
            pts = list(pts_raw.points)
        elif isinstance(pts_raw, (list, tuple)):
            if len(pts_raw) > 0 and isinstance(pts_raw[0], (list, tuple)):
                # 2D list of points: row-by-row
                u_override = len(pts_raw)
                v_override = len(pts_raw[0])
                for row in pts_raw:
                    for p in row:
                        if isinstance(p, Point3D):
                            pts.append(p)
                        elif isinstance(p, (list, tuple)) and len(p) >= 3:
                            pts.append(Point3D(float(p[0]), float(p[1]), float(p[2])))
            else:
                for p in pts_raw:
                    if isinstance(p, Point3D):
                        pts.append(p)
                    elif isinstance(p, (list, tuple)) and len(p) >= 3:
                        pts.append(Point3D(float(p[0]), float(p[1]), float(p[2])))

        total = len(pts)
        if total < 4:
            self.error = f"At least 4 points required to form a mesh surface (got {total})"
            self.set_output("Mesh", MeshData())
            return

        u_count = u_override if u_override is not None else max(2, int(self.get_input("U", 10)))
        v_count = v_override if v_override is not None else int(self.get_input("V", 0))

        if v_count <= 0:
            v_count = max(2, total // u_count)

        if total < u_count * v_count:
            self.error = f"Point count ({total}) is less than U ({u_count}) * V ({v_count}) = {u_count * v_count}"
            self.set_output("Mesh", MeshData())
            return

        closed_u = bool(self.get_input("Closed U", False))
        closed_v = bool(self.get_input("Closed V", False))
        swap_uv = bool(self.get_input("Swap UV", False))
        triangulate = bool(self.get_input("Triangulate", False))

        def get_pt(u_idx: int, v_idx: int) -> Point3D:
            if swap_uv:
                idx = v_idx * u_count + u_idx
            else:
                idx = u_idx * v_count + v_idx
            return pts[idx]

        faces: List[FaceData] = []
        edges: List[EdgeData] = []
        seen_edges = set()

        def add_edge(p_a: Point3D, p_b: Point3D, soft: bool = False) -> None:
            k1 = (round(p_a.x, 4), round(p_a.y, 4), round(p_a.z, 4))
            k2 = (round(p_b.x, 4), round(p_b.y, 4), round(p_b.z, 4))
            ek = (min(k1, k2), max(k1, k2))
            if ek not in seen_edges:
                seen_edges.add(ek)
                edges.append(EdgeData(p_a, p_b, soft=soft))

        u_cells = u_count if closed_u else u_count - 1
        v_cells = v_count if closed_v else v_count - 1

        for u in range(u_cells):
            u_next = (u + 1) % u_count
            for v in range(v_cells):
                v_next = (v + 1) % v_count

                p00 = get_pt(u, v)
                p10 = get_pt(u_next, v)
                p11 = get_pt(u_next, v_next)
                p01 = get_pt(u, v_next)

                if triangulate:
                    faces.append(FaceData(vertices=[p00, p10, p11]))
                    faces.append(FaceData(vertices=[p00, p11, p01]))
                    add_edge(p00, p10)
                    add_edge(p10, p11)
                    add_edge(p11, p00, soft=True)
                    add_edge(p11, p01)
                    add_edge(p01, p00)
                else:
                    faces.append(FaceData(vertices=[p00, p10, p11, p01]))
                    add_edge(p00, p10)
                    add_edge(p10, p11)
                    add_edge(p11, p01)
                    add_edge(p01, p00)

        mesh = MeshData(faces=faces, edges=edges, name="MeshFromPoints")
        self.set_output("Mesh", mesh)


# =====================================================================================
# 6. TRANSFORMS & MERGE
# =====================================================================================

@register_node
class MoveNode(NodeBase):
    name = "Move / Translate"
    category = "Transform"
    description = "Translate geometry by a 3D displacement vector."
    header_color = "#88c0d0"

    def setup_ports(self) -> None:
        self.add_input("Geometry", PortType.ANY)
        self.add_input("Vector", PortType.VECTOR, Vector3D(0, 0, 1))
        self.add_output("Result", PortType.ANY)

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        geom = self.get_input("Geometry")
        v = self.get_input("Vector", Vector3D(0, 0, 0))

        if isinstance(geom, MeshData):
            self.set_output("Result", geom.translated(v))
        elif isinstance(geom, Point3D):
            self.set_output("Result", geom.translated(v))
        elif isinstance(geom, PolylineData):
            self.set_output("Result", PolylineData([p.translated(v) for p in geom.points], geom.closed))
        elif isinstance(geom, list):
            res = []
            for item in geom:
                if isinstance(item, (MeshData, Point3D)):
                    res.append(item.translated(v))
                else:
                    res.append(item)
            self.set_output("Result", res)


@register_node
class RotateZNode(NodeBase):
    name = "Rotate (Z Axis)"
    category = "Transform"
    description = "Rotate geometry around Z axis by degrees."
    header_color = "#88c0d0"

    def setup_ports(self) -> None:
        self.add_input("Geometry", PortType.ANY)
        self.add_input("Angle Deg", PortType.NUMBER, 45.0)
        self.add_input("Origin", PortType.POINT, Point3D(0, 0, 0))
        self.add_output("Result", PortType.ANY)

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        geom = self.get_input("Geometry")
        deg = float(self.get_input("Angle Deg", 45.0))
        orig = self.get_input("Origin", Point3D(0, 0, 0))

        if isinstance(geom, MeshData):
            self.set_output("Result", geom.rotated_z(deg, orig))
        elif isinstance(geom, Point3D):
            self.set_output("Result", geom.rotated_z(deg, orig))


@register_node
class MergeMeshesNode(NodeBase):
    name = "Merge Meshes"
    category = "Transform"
    description = "Combine multiple meshes into one."
    header_color = "#88c0d0"

    def setup_ports(self) -> None:
        self.add_input("Mesh A", PortType.MESH)
        self.add_input("Mesh B", PortType.MESH)
        self.add_output("Merged", PortType.MESH)

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        a = self.get_input("Mesh A")
        b = self.get_input("Mesh B")

        res = MeshData()
        if isinstance(a, MeshData):
            res = res.merge(a)
        elif isinstance(a, list):
            for item in a:
                if isinstance(item, MeshData):
                    res = res.merge(item)

        if isinstance(b, MeshData):
            res = res.merge(b)
        elif isinstance(b, list):
            for item in b:
                if isinstance(item, MeshData):
                    res = res.merge(item)

        self.set_output("Merged", res)


# =====================================================================================
# 7. INGETRAZO SCENE OUTPUT & BAKE
# =====================================================================================

def _point_to_marker(pt: Point3D, size: float = 0.08) -> MeshData:
    """Generate a clean, visible 3D crosshair and diamond point marker for CAD viewport."""
    s = size
    # 3D Crosshair edges (X, Y, Z axes)
    edges = [
        EdgeData(Point3D(pt.x - s, pt.y, pt.z), Point3D(pt.x + s, pt.y, pt.z)),
        EdgeData(Point3D(pt.x, pt.y - s, pt.z), Point3D(pt.x, pt.y + s, pt.z)),
        EdgeData(Point3D(pt.x, pt.y, pt.z - s), Point3D(pt.x, pt.y, pt.z + s)),
    ]
    # Small diamond face in XY plane for solid surface visibility
    d_s = s * 0.7
    diamond_pts = [
        Point3D(pt.x - d_s, pt.y, pt.z),
        Point3D(pt.x, pt.y - d_s, pt.z),
        Point3D(pt.x + d_s, pt.y, pt.z),
        Point3D(pt.x, pt.y + d_s, pt.z),
    ]
    face = FaceData(vertices=diamond_pts)
    d_edges = [
        EdgeData(diamond_pts[0], diamond_pts[1]),
        EdgeData(diamond_pts[1], diamond_pts[2]),
        EdgeData(diamond_pts[2], diamond_pts[3]),
        EdgeData(diamond_pts[3], diamond_pts[0]),
    ]
    return MeshData(faces=[face], edges=edges + d_edges, name="Point")


def _to_mesh_data(geom: Any) -> Optional[MeshData]:
    if geom is None:
        return None
    if isinstance(geom, MeshData):
        return geom
    elif hasattr(geom, "vertices") and hasattr(geom, "triangles") and hasattr(geom, "uvs"):
        m = MeshData(name="Terrain")
        m.terrain_obj = geom
        m.is_terrain = True
        return m
    elif isinstance(geom, Point3D):
        return _point_to_marker(geom)
    elif isinstance(geom, PolylineData):
        if geom.closed and len(geom.points) >= 3:
            face = FaceData(vertices=geom.points)
            edges = [EdgeData(geom.points[i], geom.points[(i + 1) % len(geom.points)]) for i in range(len(geom.points))]
            return MeshData(faces=[face], edges=edges, name="Profile")
        else:
            edges = [EdgeData(geom.points[i], geom.points[i + 1]) for i in range(len(geom.points) - 1)]
            return MeshData(faces=[], edges=edges, name="Curve")
    elif isinstance(geom, FaceData):
        edges = [EdgeData(geom.vertices[i], geom.vertices[(i + 1) % len(geom.vertices)]) for i in range(len(geom.vertices))]
        return MeshData(faces=[geom], edges=edges, name="Face")
    elif isinstance(geom, EdgeData):
        return MeshData(faces=[], edges=[geom], name="Edge")
    elif isinstance(geom, (list, tuple)):
        all_faces: List[FaceData] = []
        all_edges: List[EdgeData] = []
        name = "ParametricModel"

        # Check if list of points: calculate adaptive marker size from point spacing
        pts = [p for p in geom if isinstance(p, Point3D)]
        if pts and len(pts) == len(geom):
            marker_size = 0.08
            if len(pts) >= 2:
                min_d = 1e9
                for i in range(min(10, len(pts) - 1)):
                    d = pts[i].distance_to(pts[i + 1])
                    if d > 1e-4:
                        min_d = min(min_d, d)
                if min_d < 1e8:
                    marker_size = max(0.01, min(0.08, min_d * 0.18))
            for p in pts:
                m = _point_to_marker(p, size=marker_size)
                all_faces.extend(m.faces)
                all_edges.extend(m.edges)
            return MeshData(faces=all_faces, edges=all_edges, name="Points")

        for sub in geom:
            m = _to_mesh_data(sub)
            if m:
                if m.faces:
                    all_faces.extend(m.faces)
                if m.edges:
                    all_edges.extend(m.edges)
                name = m.name or name
        return MeshData(faces=all_faces, edges=all_edges, name=name)
    return None


@register_node
class IngeTrazoOutputNode(NodeBase):
    name = "IngeTrazo Output"
    category = "Scene"
    description = "Stream geometry directly into the active IngeTrazo 3D scene (Live or Bake)."
    header_color = "#bf616a"

    def setup_ports(self) -> None:
        self.add_input("Geometry", PortType.ANY, description="MeshData, Terrain, faces, curves, or points")
        self.add_input("Texture", PortType.BOOLEAN, description="Enable photo texture drape", default_value=True)
        self.add_input("Group Name", PortType.STRING, "ParametricModel")
        self.add_input("Layer", PortType.STRING, "Layer 0")
        self.add_input("Material", PortType.STRING, "")
        self.widget_values.setdefault("live_update", True)
        self.last_mesh_data: Optional[MeshData] = None
        self._last_geom_sig: Any = None
        self._is_terrain_active: bool = False

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        geom = self.get_input("Geometry")
        use_texture = bool(self.get_input("Texture", True))
        grp_name = str(self.get_input("Group Name", "ParametricModel"))
        layer_name = str(self.get_input("Layer", "Layer 0"))
        mat_name = str(self.get_input("Material", ""))

        terrain_obj = None
        if hasattr(geom, "vertices") and hasattr(geom, "triangles") and hasattr(geom, "uvs"):
            terrain_obj = geom
        elif isinstance(geom, MeshData) and getattr(geom, "terrain_obj", None):
            terrain_obj = geom.terrain_obj

        mesh = _to_mesh_data(geom)
        if mesh is None:
            mesh = MeshData()
        if terrain_obj:
            mesh.terrain_obj = terrain_obj
            mesh.is_terrain = True

        if not use_texture:
            if terrain_obj is not None:
                terrain_obj.texture_image = None
            if mesh is not None:
                mesh.texture_image = None

        mesh.name = grp_name
        if layer_name:
            mesh.layer = layer_name
        if mat_name:
            mesh.material = mat_name

        self.last_mesh_data = mesh

        # Signature check for caching: prevent redundant viewport invalidation
        geom_sig = (
            id(geom),
            id(terrain_obj) if terrain_obj else None,
            getattr(geom, "_version", None),
            len(getattr(mesh, "faces", [])),
            len(getattr(mesh, "edges", [])),
            use_texture,
            getattr(terrain_obj, "texture_image", None) is not None,
            grp_name,
            layer_name,
            mat_name,
        )
        if geom_sig == self._last_geom_sig:
            return

        self._last_geom_sig = geom_sig

        live = bool(self.widget_values.get("live_update", True))
        if live and context and "app" in context:
            self.bake(context["app"], is_live=True)

    def bake(self, app: Any, is_live: bool = False) -> None:
        """Inject geometry into the IngeTrazo document."""
        mesh_data = self.last_mesh_data
        terrain_obj = getattr(mesh_data, "terrain_obj", None) if mesh_data else None

        try:
            from PySide6.QtGui import QVector3D
            from core.mesh import Mesh
            from core.group import Group
            from core.history import SnapshotImport

            viewport = getattr(app, "viewport", None)
            if not viewport:
                return
            scene = getattr(viewport, "scene", None)
            if not scene:
                return

            # Auto-synthesize fast hardware TerrainObject for ANY dense mesh during live preview
            if is_live and terrain_obj is None and mesh_data and len(mesh_data.faces) > 50:
                try:
                    import numpy as np
                    from georef.terrain import TerrainObject
                    raw_floats = []
                    qv_pts = []
                    all_tris = []
                    vert_idx = 0
                    for f in mesh_data.faces:
                        pts = f.vertices
                        if len(pts) == 4:
                            for idx in (0, 1, 2, 0, 2, 3):
                                p = pts[idx]
                                raw_floats.extend([float(p.x), float(p.y), float(p.z), 0.0, 0.0])
                                qv_pts.append(QVector3D(float(p.x), float(p.y), float(p.z)))
                            all_tris.append((vert_idx, vert_idx + 1, vert_idx + 2))
                            all_tris.append((vert_idx + 3, vert_idx + 4, vert_idx + 5))
                            vert_idx += 6
                        elif len(pts) >= 3:
                            p0 = pts[0]
                            for i in range(1, len(pts) - 1):
                                p1, p2 = pts[i], pts[i + 1]
                                for p in (p0, p1, p2):
                                    raw_floats.extend([float(p.x), float(p.y), float(p.z), 0.0, 0.0])
                                    qv_pts.append(QVector3D(float(p.x), float(p.y), float(p.z)))
                                all_tris.append((vert_idx, vert_idx + 1, vert_idx + 2))
                                vert_idx += 3
                    vbo_bytes = np.array(raw_floats, dtype=np.float32).tobytes()
                    uvs_dummy = [(0.0, 0.0)] * len(qv_pts)
                    xs = [v.x() for v in qv_pts]
                    ys = [v.y() for v in qv_pts]
                    bbox = (min(xs), min(ys), max(xs), max(ys)) if xs else (0.0, 0.0, 0.0, 0.0)
                    terrain_obj = TerrainObject(qv_pts, uvs_dummy, all_tris, (0, 0, 1, 1, 0), nx=0, ny=0, bbox=bbox)
                    terrain_obj._vbo_bytes = vbo_bytes
                    terrain_obj._vbo_count = len(raw_floats) // 5
                except Exception:
                    pass

            # 1. TERRAIN STREAMING / BAKING (Hardware-accelerated OpenGL VBO, zero CPU orbit lag)
            if terrain_obj is not None:
                # Remove any existing B-Rep group from scene.groups
                sc_groups = getattr(scene, "groups", [])
                to_remove = [g for g in sc_groups if isinstance(getattr(g, "ext", None), dict) and g.ext.get("node_editor_id") == self.id]
                for g in to_remove:
                    sc_groups.remove(g)

                first_terrain = scene.terrain is None
                scene.terrain = terrain_obj
                viewport.upload_terrain(terrain_obj)
                self._is_terrain_active = True
                if first_terrain and hasattr(terrain_obj, "bounds"):
                    mn, mx = terrain_obj.bounds()
                    if mn is not None and hasattr(viewport, "camera") and hasattr(viewport.camera, "fit_to"):
                        viewport.camera.fit_to(mn, mx)

                if not is_live:
                    notify = getattr(viewport, "notify_scene_changed", None)
                    if callable(notify):
                        notify()
                    if hasattr(viewport, "flash_status"):
                        viewport.flash_status(f"Baked terrain '{mesh_data.name if mesh_data else 'Terrain'}' to IngeTrazo", 3000)

                viewport.update()
                return

            # If switching away from terrain mode (or clearing)
            if getattr(self, "_is_terrain_active", False) and terrain_obj is None:
                if getattr(scene, "terrain", None) is not None:
                    scene.terrain = None
                    viewport.upload_terrain(None)
                self._is_terrain_active = False

            if not mesh_data or (not mesh_data.faces and not mesh_data.edges):
                # Clean up any leftover group for this node
                sc_groups = getattr(scene, "groups", [])
                to_remove = [g for g in sc_groups if isinstance(getattr(g, "ext", None), dict) and g.ext.get("node_editor_id") == self.id]
                if to_remove:
                    for g in to_remove:
                        sc_groups.remove(g)
                    scene.version += 1
                    viewport.update()
                return

            grp_name = mesh_data.name or "ParametricModel"
            layer_name = mesh_data.layer or "Layer 0"
            mat_name = mesh_data.material

            def mutate(sc):
                native_mesh = Mesh()
                for idx, face in enumerate(mesh_data.faces):
                    if len(face.vertices) < 3:
                        continue
                    try:
                        verts = [QVector3D(float(p.x), float(p.y), float(p.z)) for p in face.vertices]
                        holes = (
                            [[QVector3D(float(p.x), float(p.y), float(p.z)) for p in h] for h in face.holes]
                            if face.holes else None
                        )
                        f = native_mesh.add_face(verts, holes)
                        if f is not None and getattr(f, "attrs", None) is not None:
                            if face.color:
                                f.attrs["color"] = list(face.color)
                            if mat_name:
                                f.attrs["mat"] = mat_name
                            if layer_name:
                                f.attrs["layer"] = layer_name
                    except Exception:
                        try:
                            if len(face.vertices) == 4:
                                p0, p1, p2, p3 = face.vertices
                                v0 = QVector3D(float(p0.x), float(p0.y), float(p0.z))
                                v1 = QVector3D(float(p1.x), float(p1.y), float(p1.z))
                                v2 = QVector3D(float(p2.x), float(p2.y), float(p2.z))
                                v3 = QVector3D(float(p3.x), float(p3.y), float(p3.z))
                                f1 = native_mesh.add_face([v0, v1, v2])
                                f2 = native_mesh.add_face([v0, v2, v3])
                                if face.color:
                                    if f1 and getattr(f1, "attrs", None) is not None:
                                        f1.attrs["color"] = list(face.color)
                                    if f2 and getattr(f2, "attrs", None) is not None:
                                        f2.attrs["color"] = list(face.color)
                        except Exception:
                            pass

                # Add explicit edges
                for edge in mesh_data.edges:
                    try:
                        e = native_mesh.add_edge(
                            QVector3D(float(edge.a.x), float(edge.a.y), float(edge.a.z)),
                            QVector3D(float(edge.b.x), float(edge.b.y), float(edge.b.z))
                        )
                        if e and edge.soft:
                            e.soft = True
                    except Exception:
                        pass

                # If dense mesh/terrain, mark edges soft and hidden to prevent _sync_edges overhead
                if getattr(mesh_data, "is_terrain", False) or len(mesh_data.faces) > 100:
                    for e in getattr(native_mesh, "edges", []):
                        e.soft = True
                        e.hidden = True

                native_mesh._chunk_dirty = True
                native_mesh._mut_serial += 1

                # Check if parametric group exists
                target_group = None
                for g in getattr(sc, "groups", []):
                    ext = getattr(g, "ext", None)
                    if isinstance(ext, dict) and ext.get("node_editor_id") == self.id:
                        target_group = g
                        break

                if target_group is not None:
                    target_group.mesh = native_mesh
                    target_group.name = grp_name
                    if layer_name:
                        target_group.layer = layer_name
                else:
                    g = Group(native_mesh, name=grp_name)
                    g.component = False
                    if layer_name:
                        g.layer = layer_name
                    g.ext = {"node_editor_id": self.id}
                    sc.groups.append(g)

                sc.version += 1

            if is_live:
                mutate(scene)
                notify = getattr(viewport, "notify_scene_changed", None)
                if callable(notify):
                    notify()
                viewport.update()
            else:
                # If manual bake, clear live terrain display since it is now baked into scene.groups
                if getattr(self, "_is_terrain_active", False):
                    scene.terrain = None
                    viewport.upload_terrain(None)
                    self._is_terrain_active = False

                if hasattr(viewport, "history") and hasattr(viewport.history, "execute"):
                    viewport.history.execute(SnapshotImport(mutate))
                else:
                    mutate(scene)
                notify = getattr(viewport, "notify_scene_changed", None)
                if callable(notify):
                    notify()
                viewport.update()
                if hasattr(viewport, "flash_status"):
                    viewport.flash_status(f"Baked '{grp_name}' to IngeTrazo", 3000)

        except Exception as ex:
            import logging
            logging.getLogger("ingetrazo.plugins.node_editor").error(f"Error baking to IngeTrazo: {ex}", exc_info=True)


@register_node
class ReferenceFaceNode(NodeBase):
    name = "Reference Face"
    category = "Scene"
    description = (
        "Reference a face or surface from the IngeTrazo 3D viewport into the node graph.\n"
        "Click '📌 Set Selected Face' on the node to store the currently selected face.\n"
        "Automatically extracts the outer perimeter and all courtyard/interior holes.\n"
        "The referenced face is saved directly in the file (.itgraph) so it is remembered\n"
        "when reopening. Each Reference Face node can store a different face for different roofs."
    )
    header_color = "#5e81ac"

    def setup_ports(self) -> None:
        self.add_output("Surface", PortType.ANY, "FaceData with outer boundary and all holes")
        self.add_output("Mesh", PortType.MESH, "Preview mesh of the referenced face")
        self.add_output("Outer", PortType.CURVE, "Outer boundary polyline")
        self.add_output("Holes", PortType.ANY, "List of interior hole polylines")

    # ------------------------------------------------------------------
    # Point Conversion and Geometry Extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _to_pt3d(p: Any) -> Optional[Point3D]:
        """Convert any IngeTrazo Vertex, QVector3D, or coordinate tuple to Point3D."""
        if p is None:
            return None
        if isinstance(p, Point3D):
            return p
        if hasattr(p, "position"):
            pos = p.position
            return Point3D(float(pos.x()), float(pos.y()), float(pos.z()))
        if hasattr(p, "x"):
            x = float(p.x() if callable(p.x) else p.x)
            y = float(p.y() if callable(p.y) else p.y)
            z = float(p.z() if callable(p.z) else p.z)
            return Point3D(x, y, z)
        if isinstance(p, (list, tuple)) and len(p) >= 3:
            return Point3D(float(p[0]), float(p[1]), float(p[2]))
        return None

    @staticmethod
    def _extract_face_loops(f: Any) -> Tuple[List[Point3D], List[List[Point3D]]]:
        """Extract outer vertices and holes from an IngeTrazo Face object."""
        _to = ReferenceFaceNode._to_pt3d
        outer: List[Point3D] = []
        holes: List[List[Point3D]] = []

        # 1. Outer boundary
        raw_verts = getattr(f, "vertices", None)
        if raw_verts is None:
            raw_loop = getattr(f, "loop", None)
            raw_verts = [getattr(v, "position", v) for v in raw_loop] if raw_loop else []

        if raw_verts:
            for v in raw_verts:
                pt = _to(v)
                if pt:
                    outer.append(pt)

        # 2. Native holes
        raw_holes = getattr(f, "holes", None) or []
        for h_ring in raw_holes:
            h_pts = []
            for hv in h_ring:
                pt = _to(hv)
                if pt:
                    h_pts.append(pt)
            if len(h_pts) >= 3:
                holes.append(h_pts)

        return outer, holes

    def reference_from_selection(self, app: Any = None) -> Tuple[str, bool]:
        """Extract the selected face/group from the active IngeTrazo viewport and save it into widget_values."""
        if app is None:
            try:
                from PySide6.QtWidgets import QApplication
                win = getattr(QApplication.instance(), "_extension_app_handle", None)
                app = win
            except Exception:
                app = None

        if not app:
            return ("No IngeTrazo app handle", False)

        viewport = getattr(app, "viewport", None)
        if not viewport:
            return ("No viewport found", False)
        scene = getattr(viewport, "scene", None)
        if not scene:
            return ("No scene found", False)

        sel = getattr(scene, "selection", None) or getattr(viewport, "selection", None)
        if not sel:
            return ("Please select a face in 3D first!", False)

        collected_faces: List[Tuple[List[Point3D], List[List[Point3D]]]] = []

        for item in sel:
            # Direct Face object
            if hasattr(item, "vertices") or hasattr(item, "loop"):
                o, h = self._extract_face_loops(item)
                if len(o) >= 3:
                    collected_faces.append((o, h))
            # Group object
            elif hasattr(item, "mesh") and hasattr(item.mesh, "faces"):
                for gf in item.mesh.faces:
                    o, h = self._extract_face_loops(gf)
                    if len(o) >= 3:
                        collected_faces.append((o, h))

        if not collected_faces:
            return ("Selected item has no planar faces", False)

        # If a single face with native holes was selected:
        if len(collected_faces) == 1:
            outer, holes = collected_faces[0]
        else:
            # Multiple coplanar faces selected (e.g. drawn in pieces or outer + inner loop)
            # Find largest face as outer boundary
            def face_area(pts: List[Point3D]) -> float:
                if len(pts) < 3:
                    return 0.0
                nx = ny = nz = 0.0
                n = len(pts)
                for i in range(n):
                    a, b = pts[i], pts[(i + 1) % n]
                    nx += (a.y - b.y) * (a.z + b.z)
                    ny += (a.z - b.z) * (a.x + b.x)
                    nz += (a.x - b.x) * (a.y + b.y)
                return (nx * nx + ny * ny + nz * nz) ** 0.5 * 0.5

            collected_faces.sort(key=lambda item: face_area(item[0]), reverse=True)
            outer, holes = collected_faces[0]
            # Extra faces inside the outer boundary are interior holes
            for extra_o, extra_h in collected_faces[1:]:
                holes.append(extra_o)
                holes.extend(extra_h)

        # Store serialized plain coordinates into widget_values for file persistence
        summary_txt = f"{len(outer)} pts" + (f", {len(holes)} hole(s)" if holes else "")
        self.widget_values["referenced_face"] = {
            "outer": [[p.x, p.y, p.z] for p in outer],
            "holes": [[[p.x, p.y, p.z] for p in h] for h in holes],
            "summary": summary_txt
        }
        self.dirty = True
        return (f"Saved: {summary_txt}", True)

    def clear_reference(self) -> None:
        """Clear stored referenced face."""
        if "referenced_face" in self.widget_values:
            del self.widget_values["referenced_face"]
        self.dirty = True

    # ------------------------------------------------------------------
    # Node compute
    # ------------------------------------------------------------------

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        outer: List[Point3D] = []
        holes: List[List[Point3D]] = []

        # 1. Use stored referenced face from widget_values (persisted across save/reopen)
        saved = self.widget_values.get("referenced_face")
        if saved and isinstance(saved, dict) and "outer" in saved:
            outer = [Point3D(float(pt[0]), float(pt[1]), float(pt[2])) for pt in saved.get("outer", [])]
            holes = [
                [Point3D(float(pt[0]), float(pt[1]), float(pt[2])) for pt in h_ring]
                for h_ring in saved.get("holes", [])
            ]

        # 2. If nothing stored yet, attempt reading active live selection
        if len(outer) < 3 and context and "app" in context:
            self.reference_from_selection(context["app"])
            saved = self.widget_values.get("referenced_face")
            if saved and isinstance(saved, dict) and "outer" in saved:
                outer = [Point3D(float(pt[0]), float(pt[1]), float(pt[2])) for pt in saved.get("outer", [])]
                holes = [
                    [Point3D(float(pt[0]), float(pt[1]), float(pt[2])) for pt in h_ring]
                    for h_ring in saved.get("holes", [])
                ]

        # 3. Fallback: courtyard house (24x16m with 8x6m hole)
        if len(outer) < 3:
            outer = [
                Point3D(0.0, 0.0, 0.0),
                Point3D(24.0, 0.0, 0.0),
                Point3D(24.0, 16.0, 0.0),
                Point3D(0.0, 16.0, 0.0),
            ]
            holes = [[
                Point3D(8.0, 5.0, 0.0),
                Point3D(16.0, 5.0, 0.0),
                Point3D(16.0, 11.0, 0.0),
                Point3D(8.0, 11.0, 0.0),
            ]]

        face = FaceData(vertices=outer, holes=holes, color=(0.82, 0.86, 0.90))
        outer_poly = PolylineData(points=outer, closed=True)
        holes_poly = [PolylineData(points=h, closed=True) for h in holes]

        self.set_output("Surface", face)
        self.set_output("Mesh", MeshData(faces=[face], name="ReferencedFace"))
        self.set_output("Outer", outer_poly)
        self.set_output("Holes", holes_poly)


# -----------------------------------------------------------------------------
# Image Nodes (Image File, Image Preview, Image Sampler, Mesh From Points)
# -----------------------------------------------------------------------------

def _sample_image_data(
    image_path: str = "",
    qimg_override: Any = None,
    domain_u: Any = 10.0,
    domain_v: Any = 10.0,
    min_h: Any = 0.0,
    max_h: Any = 2.0,
    count_u: int = 80,
    count_v: int = 80,
    invert: bool = False,
    channel: str = "Grayscale",
    filter_mode: str = "Bilinear",
    use_texture: bool = True
):
    import os
    try:
        from PySide6.QtGui import QImage, QColor
    except ImportError:
        QImage = None
        QColor = None

    count_u = max(2, min(300, int(count_u)))
    count_v = max(2, min(300, int(count_v)))

    # Domain 2D or 1D Domain handling
    if hasattr(domain_u, "u_span") and hasattr(domain_u, "v_span"):
        size_x = float(domain_u.u_span)
        size_y = float(domain_u.v_span)
    elif hasattr(domain_u, "span"):
        size_x = float(domain_u.span)
        size_y = float(domain_v.span) if hasattr(domain_v, "span") else (float(domain_v.length) if hasattr(domain_v, "length") else float(domain_v))
    elif hasattr(domain_u, "length"):
        size_x = float(domain_u.length)
        size_y = float(domain_v.length) if hasattr(domain_v, "length") else (float(domain_v.span) if hasattr(domain_v, "span") else float(domain_v))
    elif isinstance(domain_u, (tuple, list)) and len(domain_u) >= 2:
        size_x = float(domain_u[1]) - float(domain_u[0])
        size_y = (float(domain_v[1]) - float(domain_v[0])) if isinstance(domain_v, (tuple, list)) and len(domain_v) >= 2 else float(domain_v)
    else:
        try:
            size_x = float(domain_u)
        except Exception:
            size_x = 10.0
        try:
            size_y = float(domain_v)
        except Exception:
            size_y = size_x

    # Min / Max height handling (can be separate or from a Domain in min_h)
    if hasattr(min_h, "min") and hasattr(min_h, "max"):
        real_min = float(min_h.min)
        real_max = float(min_h.max)
    elif isinstance(min_h, (tuple, list)) and len(min_h) >= 2:
        real_min = float(min_h[0])
        real_max = float(min_h[1])
    else:
        try:
            real_min = float(min_h)
        except Exception:
            real_min = 0.0
        try:
            real_max = float(max_h)
        except Exception:
            real_max = 2.0

    if QImage is None:
        # Fallback if Qt is not installed in the current environment
        pts_fallback: List[Point3D] = []
        vals_fallback: List[float] = []
        cols_fallback: List[Tuple[float, float, float]] = []
        for j in range(count_v):
            v = j / float(count_v - 1)
            y = v * size_y
            for i in range(count_u):
                u = i / float(count_u - 1)
                x = u * size_x
                nx = u * 2.0 - 1.0
                ny = v * 2.0 - 1.0
                r = math.sqrt(nx * nx + ny * ny) * math.pi * 3.0
                bright = math.sin(r) * 0.5 + 0.5
                if invert:
                    bright = 1.0 - bright
                z = real_min + bright * (real_max - real_min)
                pts_fallback.append(Point3D(x, y, z))
                vals_fallback.append(bright)
                cols_fallback.append((bright, bright, bright))
        faces_fallback: List[FaceData] = []
        for j in range(count_v - 1):
            for i in range(count_u - 1):
                idx00 = j * count_u + i
                idx10 = j * count_u + (i + 1)
                idx11 = (j + 1) * count_u + (i + 1)
                idx01 = (j + 1) * count_u + i
                faces_fallback.append(FaceData(vertices=[pts_fallback[idx00], pts_fallback[idx10], pts_fallback[idx11], pts_fallback[idx01]], color=cols_fallback[idx00]))
        mesh_fallback = MeshData(faces=faces_fallback, name="DisplacementMesh")
        return pts_fallback, vals_fallback, cols_fallback, mesh_fallback, 128, 128, None, None

    qimg = None
    if qimg_override and hasattr(qimg_override, "pixelColor") and not qimg_override.isNull():
        qimg = qimg_override
    elif image_path and isinstance(image_path, str) and os.path.exists(image_path):
        qimg = QImage(image_path)

    if not qimg or qimg.isNull():
        # Procedural default test ripple if no image is loaded yet
        w, h = 128, 128
        qimg = QImage(w, h, QImage.Format_RGB32)
        for y in range(h):
            for x in range(w):
                nx = (x - w / 2.0) / (w / 2.0)
                ny = (y - h / 2.0) / (h / 2.0)
                r = math.sqrt(nx * nx + ny * ny) * math.pi * 3.0
                val = int(max(0, min(255, (math.sin(r) * 0.5 + 0.5) * 255)))
                qimg.setPixelColor(x, y, QColor(val, val, val))

    img_w = qimg.width()
    img_h = qimg.height()

    if abs(size_y - size_x) < 1e-4 and img_w > 0:
        size_y = size_x * (float(img_h) / float(img_w))

    try:
        import numpy as np
    except ImportError:
        np = None

    from PySide6.QtCore import Qt
    smooth = Qt.SmoothTransformation if filter_mode != "Nearest" else Qt.FastTransformation

    if np is not None:
        scaled_qimg = qimg.scaled(count_u, count_v, Qt.IgnoreAspectRatio, smooth).convertToFormat(QImage.Format_RGBA8888)
        buf = np.frombuffer(scaled_qimg.constBits(), dtype=np.uint8).reshape((count_v, count_u, 4))
        py_buf = np.flipud(buf)  # bottom-to-top 3D alignment

        if channel == "Red":
            bright = py_buf[..., 0].astype(np.float32) / 255.0
        elif channel == "Green":
            bright = py_buf[..., 1].astype(np.float32) / 255.0
        elif channel == "Blue":
            bright = py_buf[..., 2].astype(np.float32) / 255.0
        elif channel == "Alpha":
            bright = py_buf[..., 3].astype(np.float32) / 255.0
        else:  # Grayscale (Luminance)
            bright = (py_buf[..., 0].astype(np.float32) * 0.299 + py_buf[..., 1].astype(np.float32) * 0.587 + py_buf[..., 2].astype(np.float32) * 0.114) / 255.0

        if invert:
            bright = 1.0 - bright

        xs = np.linspace(0.0, size_x, count_u, dtype=np.float32)
        ys = np.linspace(0.0, size_y, count_v, dtype=np.float32)
        X, Y = np.meshgrid(xs, ys)
        Z = real_min + bright * (real_max - real_min)

        us = np.linspace(0.0, 1.0, count_u, dtype=np.float32)
        vs = np.linspace(1.0, 0.0, count_v, dtype=np.float32)
        U, V = np.meshgrid(us, vs)

        # Packed OpenGL VBO layout: (x, y, z, u, v)
        v_uv = np.stack([X, Y, Z, U, V], axis=-1)
        i_grid, j_grid = np.meshgrid(np.arange(count_u - 1), np.arange(count_v - 1))
        idx00 = j_grid * count_u + i_grid
        idx10 = j_grid * count_u + (i_grid + 1)
        idx11 = (j_grid + 1) * count_u + (i_grid + 1)
        idx01 = (j_grid + 1) * count_u + i_grid
        t1 = np.stack([idx00, idx10, idx11], axis=-1).reshape(-1, 3)
        t2 = np.stack([idx00, idx11, idx01], axis=-1).reshape(-1, 3)
        tris = np.concatenate([t1, t2], axis=0)

        flat_v_uv = v_uv.reshape(-1, 5)
        tri_verts = flat_v_uv[tris.ravel()]
        vbo_bytes = tri_verts.tobytes()
        vbo_count = len(tris) * 3

        values = bright.ravel().tolist()
        pts_xyz = np.stack([X, Y, Z], axis=-1).reshape(-1, 3)
        points = [Point3D(float(p[0]), float(p[1]), float(p[2])) for p in pts_xyz]
        cols_rgb = (py_buf[..., :3].astype(np.float32) / 255.0).reshape(-1, 3)
        colors = [(float(c[0]), float(c[1]), float(c[2])) for c in cols_rgb] if use_texture else []

        faces: List[FaceData] = []
        for j in range(count_v - 1):
            for i in range(count_u - 1):
                i00 = j * count_u + i
                i10 = j * count_u + (i + 1)
                i11 = (j + 1) * count_u + (i + 1)
                i01 = (j + 1) * count_u + i
                if use_texture and colors:
                    c0 = colors[i00]
                    c1 = colors[i10]
                    c2 = colors[i11]
                    c3 = colors[i01]
                    avg_c = ((c0[0]+c1[0]+c2[0]+c3[0])*0.25, (c0[1]+c1[1]+c2[1]+c3[1])*0.25, (c0[2]+c1[2]+c2[2]+c3[2])*0.25)
                else:
                    avg_c = None
                faces.append(FaceData(vertices=[points[i00], points[i10], points[i11], points[i01]], color=avg_c))

        # Vectorized wireframe grid line segments (horizontal and vertical quad edges)
        pts_grid = np.stack([X, Y, Z], axis=-1)  # (count_v, count_u, 3)
        h_starts = pts_grid[:, :-1, :]            # (count_v, count_u - 1, 3)
        h_ends   = pts_grid[:, 1:, :]             # (count_v, count_u - 1, 3)
        h_lines  = np.stack([h_starts, h_ends], axis=2).reshape(-1, 3)

        v_starts = pts_grid[:-1, :, :]            # (count_v - 1, count_u, 3)
        v_ends   = pts_grid[1:, :, :]             # (count_v - 1, count_u, 3)
        v_lines  = np.stack([v_starts, v_ends], axis=2).reshape(-1, 3)

        line_pts = np.concatenate([h_lines, v_lines], axis=0).astype(np.float32)
        line_vbo_bytes = line_pts.tobytes()
        line_vbo_count = len(line_pts)

        terrain_obj = None
        try:
            from PySide6.QtGui import QVector3D
            try:
                from georef.terrain import TerrainObject
            except ImportError:
                TerrainObject = None

            qv_points = [QVector3D(float(p[0]), float(p[1]), float(p[2])) for p in pts_xyz]
            uv_tuples = [(float(u), float(v)) for u, v in np.stack([U, V], axis=-1).reshape(-1, 2)]
            tri_tuples = [tuple(t) for t in tris]
            if TerrainObject is not None:
                terrain_obj = TerrainObject(
                    vertices=qv_points,
                    uvs=uv_tuples,
                    triangles=tri_tuples,
                    tile_range=(0, 0, 1, 1, 0),
                    nx=count_u,
                    ny=count_v,
                    bbox=(0.0, 0.0, size_x, size_y)
                )
            else:
                class FallbackTerrain:
                    def __init__(self, verts, uvs_list, tri_list, nx, ny, bbox, img):
                        self.vertices = verts
                        self.uvs = uvs_list
                        self.triangles = tri_list
                        self.tile_range = (0, 0, 1, 1, 0)
                        self.nx = nx
                        self.ny = ny
                        self.bbox = bbox
                        self.visible = True
                        self.texture_image = img
                    def bounds(self):
                        if not self.vertices:
                            return None, None
                        xs = [v.x() for v in self.vertices]
                        ys = [v.y() for v in self.vertices]
                        zs = [v.z() for v in self.vertices]
                        return (QVector3D(min(xs), min(ys), min(zs)),
                                QVector3D(max(xs), max(ys), max(zs)))
                terrain_obj = FallbackTerrain(qv_points, uv_tuples, tri_tuples, count_u, count_v, (0.0, 0.0, size_x, size_y), (qimg if use_texture else None))

            terrain_obj._vbo_bytes = vbo_bytes
            terrain_obj._vbo_count = vbo_count
            terrain_obj._line_vbo_bytes = line_vbo_bytes
            terrain_obj._line_vbo_count = line_vbo_count
            terrain_obj.texture_image = qimg if use_texture else None
        except Exception as ex:
            import logging
            logging.getLogger("ingetrazo.plugins.node_editor").debug(f"Could not construct terrain_obj: {ex}")

        mesh = MeshData(faces=faces, name="DisplacementMesh")
        mesh.terrain_obj = terrain_obj
        mesh.is_terrain = True
        mesh.texture_image = qimg if use_texture else None
        return points, values, colors, mesh, img_w, img_h, qimg, terrain_obj

    # Pure Python fallback if numpy is unavailable
    points: List[Point3D] = []
    values: List[float] = []
    colors: List[Tuple[float, float, float]] = []

    scaled_qimg = qimg.scaled(count_u, count_v, Qt.IgnoreAspectRatio, smooth)

    for j in range(count_v):
        v = j / float(count_v - 1)
        y = v * size_y
        py = (count_v - 1) - j  # bottom-to-top 3D alignment

        for i in range(count_u):
            u = i / float(count_u - 1)
            x = u * size_x
            col = scaled_qimg.pixelColor(i, py)
            rf, gf, bf, af = col.redF(), col.greenF(), col.blueF(), col.alphaF()

            if channel == "Red":
                bright = rf
            elif channel == "Green":
                bright = gf
            elif channel == "Blue":
                bright = bf
            elif channel == "Alpha":
                bright = af
            else:  # Grayscale (Luminance)
                bright = 0.299 * rf + 0.587 * gf + 0.114 * bf

            if invert:
                bright = 1.0 - bright

            z = real_min + bright * (real_max - real_min)
            points.append(Point3D(x, y, z))
            values.append(bright)
            colors.append((rf, gf, bf))

    faces: List[FaceData] = []
    triangles: List[Tuple[int, int, int]] = []
    for j in range(count_v - 1):
        for i in range(count_u - 1):
            idx00 = j * count_u + i
            idx10 = j * count_u + (i + 1)
            idx11 = (j + 1) * count_u + (i + 1)
            idx01 = (j + 1) * count_u + i

            p0 = points[idx00]
            p1 = points[idx10]
            p2 = points[idx11]
            p3 = points[idx01]

            if use_texture and colors:
                avg_c = (
                    (colors[idx00][0] + colors[idx10][0] + colors[idx11][0] + colors[idx01][0]) * 0.25,
                    (colors[idx00][1] + colors[idx10][1] + colors[idx11][1] + colors[idx01][1]) * 0.25,
                    (colors[idx00][2] + colors[idx10][2] + colors[idx11][2] + colors[idx01][2]) * 0.25
                )
            else:
                avg_c = None
            faces.append(FaceData(vertices=[p0, p1, p2, p3], color=avg_c))
            triangles.append((idx00, idx10, idx11))
            triangles.append((idx00, idx11, idx01))

    # Build TerrainObject for hardware-accelerated OpenGL relief rendering (120+ FPS)
    terrain_obj = None
    try:
        from PySide6.QtGui import QVector3D
        try:
            from georef.terrain import TerrainObject
        except ImportError:
            TerrainObject = None

        qv_points = [QVector3D(p.x, p.y, p.z) for p in points]
        uvs = [(i / float(count_u - 1), 1.0 - (j / float(count_v - 1))) for j in range(count_v) for i in range(count_u)]

        if TerrainObject is not None:
            terrain_obj = TerrainObject(
                vertices=qv_points,
                uvs=uvs,
                triangles=triangles,
                tile_range=(0, 0, 1, 1, 0),
                nx=count_u,
                ny=count_v,
                bbox=(0.0, 0.0, size_x, size_y)
            )
            terrain_obj.texture_image = qimg if use_texture else None
        else:
            class FallbackTerrain:
                def __init__(self, verts, uvs_list, tris, nx, ny, bbox, img):
                    self.vertices = verts
                    self.uvs = uvs_list
                    self.triangles = tris
                    self.tile_range = (0, 0, 1, 1, 0)
                    self.nx = nx
                    self.ny = ny
                    self.bbox = bbox
                    self.visible = True
                    self.texture_image = img
                def bounds(self):
                    if not self.vertices:
                        return None, None
                    xs = [v.x() for v in self.vertices]
                    ys = [v.y() for v in self.vertices]
                    zs = [v.z() for v in self.vertices]
                    return (QVector3D(min(xs), min(ys), min(zs)),
                            QVector3D(max(xs), max(ys), max(zs)))
            terrain_obj = FallbackTerrain(qv_points, uvs, triangles, count_u, count_v, (0.0, 0.0, size_x, size_y), (qimg if use_texture else None))

        from array import array
        line_floats = array("f")
        for j in range(count_v):
            for i in range(count_u - 1):
                p1, p2 = points[j * count_u + i], points[j * count_u + i + 1]
                line_floats.extend([p1.x, p1.y, p1.z, p2.x, p2.y, p2.z])
        for i in range(count_u):
            for j in range(count_v - 1):
                p1, p2 = points[j * count_u + i], points[(j + 1) * count_u + i]
                line_floats.extend([p1.x, p1.y, p1.z, p2.x, p2.y, p2.z])
        terrain_obj._line_vbo_bytes = line_floats.tobytes()
        terrain_obj._line_vbo_count = len(line_floats) // 3
    except Exception as ex:
        import logging
        logging.getLogger("ingetrazo.plugins.node_editor").debug(f"Could not construct terrain_obj: {ex}")

    mesh = MeshData(faces=faces, name="DisplacementMesh")
    mesh.terrain_obj = terrain_obj
    mesh.is_terrain = True
    mesh.texture_image = qimg if use_texture else None
    return points, values, colors, mesh, img_w, img_h, qimg, terrain_obj


@register_node
class ImageFileNode(NodeBase):
    name = "Image File"
    category = "Input"
    description = (
        "Open and select an image file (PNG, JPG, BMP, WEBP, TIF).\n"
        "Click '📂 Open Image...' on the node tile to browse.\n"
        "Outputs the loaded QImage object, path, and dimensions."
    )
    header_color = "#5e81ac"

    def setup_ports(self) -> None:
        self.add_input("File Path", PortType.ANY, description="Optional path string", default_value="")
        self.add_output("Image", PortType.ANY, "Loaded QImage object")
        self.add_output("Path", PortType.ANY, "Absolute file path string")
        self.add_output("Width", PortType.INTEGER, "Image width in pixels")
        self.add_output("Height", PortType.INTEGER, "Image height in pixels")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        try:
            from PySide6.QtGui import QImage
        except ImportError:
            QImage = None
        import os
        in_path = self.get_input("File Path", "")
        file_path = str(in_path) if in_path else self.widget_values.get("image_path", "")

        qimg = None
        if QImage is not None and file_path and os.path.exists(file_path):
            qimg = QImage(file_path)

        w = qimg.width() if qimg and not qimg.isNull() else 0
        h = qimg.height() if qimg and not qimg.isNull() else 0

        self.widget_values["_cached_qimage"] = qimg
        self.set_output("Image", qimg)
        self.set_output("Path", file_path)
        self.set_output("Width", w)
        self.set_output("Height", h)
        if hasattr(self, "on_display_updated") and callable(self.on_display_updated):
            try:
                self.on_display_updated()
            except Exception:
                pass


@register_node
class ImagePreviewNode(NodeBase):
    name = "Image Preview"
    category = "Input"
    description = (
        "Displays a live visual image preview on the node tile on the canvas.\n"
        "Connect an Image object or file path."
    )
    header_color = "#4c566a"

    def setup_ports(self) -> None:
        self.add_input("Image", PortType.ANY, description="QImage or file path string")
        self.add_output("Image", PortType.ANY, "Pass-through QImage object")
        self.add_output("Width", PortType.INTEGER, "Image width")
        self.add_output("Height", PortType.INTEGER, "Image height")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        try:
            from PySide6.QtGui import QImage
        except ImportError:
            QImage = None
        import os
        val = self.get_input("Image", None)

        qimg = None
        if hasattr(val, "pixelColor"):
            qimg = val
        elif QImage is not None and isinstance(val, str) and val and os.path.exists(val):
            qimg = QImage(val)
        elif QImage is not None and self.widget_values.get("image_path"):
            p = self.widget_values.get("image_path")
            if os.path.exists(p):
                qimg = QImage(p)

        w = qimg.width() if qimg and not qimg.isNull() else 0
        h = qimg.height() if qimg and not qimg.isNull() else 0

        self.widget_values["_cached_qimage"] = qimg
        self.set_output("Image", qimg)
        self.set_output("Width", w)
        self.set_output("Height", h)
        if hasattr(self, "on_display_updated") and callable(self.on_display_updated):
            try:
                self.on_display_updated()
            except Exception:
                pass


@register_node
class ImageSamplerNode(NodeBase):
    name = "Image Sampler"
    category = "Input"
    description = (
        "Load an image file and create 3D heightfield displacement relief meshes, points, and values.\n"
        "Supports live thumbnail preview, custom domains, and min/max displacement scale.\n"
        "Outputs both a ready-to-bake 3D Mesh and point arrays."
    )
    header_color = "#3b4252"

    def setup_ports(self) -> None:
        self.add_input("Image", PortType.ANY, description="Image file path (str) or QImage", default_value="")
        self.add_input("Texture", PortType.BOOLEAN, description="Enable photo texture drape (or solid relief)", default_value=True)
        self.add_input("Domain U", PortType.ANY, description="Size along X (Domain or number)", default_value=10.0)
        self.add_input("Domain V", PortType.ANY, description="Size along Y (Domain or number)", default_value=10.0)
        self.add_input("Min", PortType.ANY, description="Minimum height (Domain or number)", default_value=0.0)
        self.add_input("Max", PortType.ANY, description="Displacement height scale", default_value=2.0)
        self.add_input("Count U", PortType.INTEGER, description="Resolution along X", default_value=30)
        self.add_input("Count V", PortType.INTEGER, description="Resolution along Y", default_value=30)

        self.add_output("Mesh", PortType.MESH, "3D relief mesh")
        self.add_output("Terrain", PortType.ANY, "Native GPU TerrainObject (zero-lag 120 FPS relief rendering)")
        self.add_output("Points", PortType.ANY, "Displaced 3D points (List[Point3D])")
        self.add_output("Values", PortType.ANY, "Brightness / height values (0.0 to 1.0)")
        self.add_output("Colors", PortType.ANY, "Sampled RGB colors")
        self.add_output("Width", PortType.INTEGER, "Image pixel width")
        self.add_output("Height", PortType.INTEGER, "Image pixel height")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        import os
        raw_img = self.get_input("Image", None)
        img_override = raw_img if hasattr(raw_img, "pixelColor") else None
        img_path = str(raw_img) if isinstance(raw_img, str) and raw_img else self.widget_values.get("image_path", "")

        dom_u = self.get_input("Domain U", 10.0)
        dom_v = self.get_input("Domain V", 10.0)
        min_h = self.get_input("Min", 0.0)
        max_h = self.get_input("Max", 2.0)
        cnt_u = int(self.get_input("Count U", 30))
        cnt_v = int(self.get_input("Count V", 30))

        port_tex = next((p for p in self.inputs if p.name == "Texture"), None)
        if port_tex and port_tex.has_connection:
            use_tex = bool(self.get_input("Texture", True))
        else:
            use_tex = bool(self.widget_values.get("Texture", self.widget_values.get("texture", True)))

        port_inv = next((p for p in self.inputs if p.name == "Invert"), None)
        if port_inv and port_inv.has_connection:
            invert = bool(self.get_input("Invert", False))
        else:
            invert = bool(self.widget_values.get("Invert", self.widget_values.get("invert", False)))
        channel = str(self.widget_values.get("channel", "Grayscale"))
        filter_mode = str(self.widget_values.get("filter", "Bilinear"))

        pts, vals, cols, mesh, w, h, qimg, terrain_obj = _sample_image_data(
            image_path=img_path,
            qimg_override=img_override,
            domain_u=dom_u,
            domain_v=dom_v,
            min_h=min_h,
            max_h=max_h,
            count_u=cnt_u,
            count_v=cnt_v,
            invert=invert,
            channel=channel,
            filter_mode=filter_mode,
            use_texture=use_tex
        )

        self.widget_values["_cached_qimage"] = qimg
        self.set_output("Mesh", mesh)
        self.set_output("Terrain", terrain_obj)
        self.set_output("Points", pts)
        self.set_output("Values", vals)
        self.set_output("Colors", cols)
        self.set_output("Width", w)
        self.set_output("Height", h)
        if hasattr(self, "on_display_updated") and callable(self.on_display_updated):
            try:
                self.on_display_updated()
            except Exception:
                pass


@register_node
class MeshFromPointsNode(NodeBase):
    name = "Mesh From Points"
    category = "Solids"
    description = "Create a structured 3D quad surface mesh from an ordered 2D grid of 3D points."
    header_color = "#b48ead"

    def setup_ports(self) -> None:
        self.add_input("Points", PortType.ANY, description="Grid points (List[Point3D])")
        self.add_input("U Count", PortType.INTEGER, description="Points per row in U", default_value=10)
        self.add_input("Closed U", PortType.BOOLEAN, description="Wrap mesh around U", default_value=False)
        self.add_input("Closed V", PortType.BOOLEAN, description="Wrap mesh around V", default_value=False)
        self.add_output("Mesh", PortType.MESH, "Generated 3D mesh")

    def compute(self, context: Optional[Dict[str, Any]] = None) -> None:
        raw_pts = self.get_input("Points", [])
        u_count = int(self.get_input("U Count", 10))
        closed_u = bool(self.get_input("Closed U", False))
        closed_v = bool(self.get_input("Closed V", False))

        if not raw_pts or u_count < 2:
            return

        pts: List[Point3D] = []
        for p in raw_pts:
            if isinstance(p, Point3D):
                pts.append(p)
            elif isinstance(p, (list, tuple)) and len(p) >= 3:
                pts.append(Point3D(float(p[0]), float(p[1]), float(p[2])))

        total = len(pts)
        if total < u_count:
            return

        v_count = total // u_count
        faces: List[FaceData] = []

        num_u_segments = u_count if closed_u else (u_count - 1)
        num_v_segments = v_count if closed_v else (v_count - 1)

        for j in range(num_v_segments):
            j_next = (j + 1) % v_count
            for i in range(num_u_segments):
                i_next = (i + 1) % u_count

                idx00 = j * u_count + i
                idx10 = j * u_count + i_next
                idx11 = j_next * u_count + i_next
                idx01 = j_next * u_count + i

                p0 = pts[idx00]
                p1 = pts[idx10]
                p2 = pts[idx11]
                p3 = pts[idx01]

                faces.append(FaceData(vertices=[p0, p1, p2, p3], color=(0.85, 0.65, 0.3)))

        terrain_obj = None
        try:
            from PySide6.QtGui import QVector3D
            try:
                from georef.terrain import TerrainObject
            except ImportError:
                TerrainObject = None

            qv_points = [QVector3D(float(p.x), float(p.y), float(p.z)) for p in pts]
            uv_tuples = [(i / float(u_count - 1), 1.0 - (j / float(v_count - 1))) for j in range(v_count) for i in range(u_count)]
            
            raw_floats = []
            tri_tuples = []
            for j in range(num_v_segments):
                j_next = (j + 1) % v_count
                for i in range(num_u_segments):
                    i_next = (i + 1) % u_count
                    idx00 = j * u_count + i
                    idx10 = j * u_count + i_next
                    idx11 = j_next * u_count + i_next
                    idx01 = j_next * u_count + i
                    p0 = pts[idx00]
                    p1 = pts[idx10]
                    p2 = pts[idx11]
                    p3 = pts[idx01]
                    raw_floats.extend([p0.x, p0.y, p0.z, uv_tuples[idx00][0], uv_tuples[idx00][1]])
                    raw_floats.extend([p1.x, p1.y, p1.z, uv_tuples[idx10][0], uv_tuples[idx10][1]])
                    raw_floats.extend([p2.x, p2.y, p2.z, uv_tuples[idx11][0], uv_tuples[idx11][1]])
                    raw_floats.extend([p0.x, p0.y, p0.z, uv_tuples[idx00][0], uv_tuples[idx00][1]])
                    raw_floats.extend([p2.x, p2.y, p2.z, uv_tuples[idx11][0], uv_tuples[idx11][1]])
                    raw_floats.extend([p3.x, p3.y, p3.z, uv_tuples[idx01][0], uv_tuples[idx01][1]])
                    tri_tuples.append((idx00, idx10, idx11))
                    tri_tuples.append((idx00, idx11, idx01))

            import numpy as np
            vbo_bytes = np.array(raw_floats, dtype=np.float32).tobytes()
            min_x, max_x = min(p.x for p in pts), max(p.x for p in pts)
            min_y, max_y = min(p.y for p in pts), max(p.y for p in pts)

            if TerrainObject is not None:
                terrain_obj = TerrainObject(
                    vertices=qv_points,
                    uvs=uv_tuples,
                    triangles=tri_tuples,
                    tile_range=(0, 0, 1, 1, 0),
                    nx=u_count,
                    ny=v_count,
                    bbox=(min_x, min_y, max_x, max_y)
                )
            else:
                class FallbackTerrain:
                    def __init__(self, verts, uvs_list, tri_list, nx, ny, bbox):
                        self.vertices = verts
                        self.uvs = uvs_list
                        self.triangles = tri_list
                        self.tile_range = (0, 0, 1, 1, 0)
                        self.nx = nx
                        self.ny = ny
                        self.bbox = bbox
                        self.visible = True
                        self.texture_image = None
                    def bounds(self):
                        if not self.vertices:
                            return None, None
                        xs = [v.x() for v in self.vertices]
                        ys = [v.y() for v in self.vertices]
                        zs = [v.z() for v in self.vertices]
                        return (QVector3D(min(xs), min(ys), min(zs)),
                                QVector3D(max(xs), max(ys), max(zs)))
                terrain_obj = FallbackTerrain(qv_points, uv_tuples, tri_tuples, u_count, v_count, (min_x, min_y, max_x, max_y))

            terrain_obj._vbo_bytes = vbo_bytes
            terrain_obj._vbo_count = len(raw_floats) // 5
        except Exception:
            pass

        mesh = MeshData(faces=faces, name="GridMesh")
        mesh.terrain_obj = terrain_obj
        mesh.is_terrain = True
        self.set_output("Mesh", mesh)

