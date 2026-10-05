# SPDX-License-Identifier: GPL-3.0-or-later
"""
IngeTrazo Node Editor — Modular Nodes & Automatic Discovery Engine
==================================================================
This package automatically discovers and registers custom parametric nodes
placed in separate Python files inside this folder (or subfolders).

How to create a custom node in a separate file:
1. Create a new `.py` file inside the `nodes/` folder (e.g. `nodes/my_nodes.py`).
2. Subclass `NodeBase` and define `name`, `category`, `setup_ports()`, and `compute()`.
3. That's it! Any class inheriting from `NodeBase` is automatically detected and
   registered into the search palette and category menus upon launch.
"""
from __future__ import annotations

import os
import sys
import inspect
import logging
import importlib.util
from pathlib import Path
from typing import Dict, List, Optional, Type, Any, Union

# Re-export core classes for easy import in custom node files
try:
    from ..engine import NodeBase, PortType, Port
    from ..models import (
        Point3D, Vector3D, PolylineData, FaceData, EdgeData, MeshData,
        Domain, Domain2D,
        create_box, create_cylinder, create_sphere, extrude_profile
    )
except ImportError:
    from engine import NodeBase, PortType, Port
    from models import (
        Point3D, Vector3D, PolylineData, FaceData, EdgeData, MeshData,
        Domain, Domain2D,
        create_box, create_cylinder, create_sphere, extrude_profile
    )

log = logging.getLogger("ingetrazo.plugins.node_editor")

# Reference to the global NODE_REGISTRY in nodes_library
_REGISTRY_REF: Optional[Dict[str, Type[NodeBase]]] = None


def set_global_registry(registry: Dict[str, Type[NodeBase]]) -> None:
    """Attach the global NODE_REGISTRY dictionary from nodes_library."""
    global _REGISTRY_REF
    _REGISTRY_REF = registry


def register_node(cls: Type[NodeBase]) -> Type[NodeBase]:
    """
    Decorator to explicitly register a node class.
    (Optional, since any subclass of NodeBase is also auto-detected).
    """
    cls._is_registered_node = True
    if _REGISTRY_REF is not None:
        _REGISTRY_REF[cls.__name__] = cls
    return cls


def is_detectable_node(obj: Any) -> bool:
    """
    Determine if an object in a module is a valid detectable node.
    Criteria:
      1. Must be a Python class.
      2. Must be a subclass of NodeBase.
      3. Must not be NodeBase itself.
      4. Must have a real name (not the default 'BaseNode').
    """
    if not inspect.isclass(obj):
        return False
    if not issubclass(obj, NodeBase):
        return False
    if obj is NodeBase:
        return False
    name = getattr(obj, "name", "BaseNode")
    if name == "BaseNode":
        return False
    return True


def get_default_nodes_directories() -> List[Path]:
    """
    Return all standard directories to search for custom node files:
      1. <this_package>/nodes/ (the local nodes directory)
      2. %APPDATA%/ingetrazo/plugins/node_editor/nodes/ (user custom nodes directory)
    """
    dirs: List[Path] = []

    # 1. Local nodes folder
    local_dir = Path(__file__).resolve().parent
    if local_dir.is_dir():
        dirs.append(local_dir)

    # 2. User AppData nodes folder (Windows or Linux/Mac equivalent)
    try:
        if sys.platform == "win32":
            appdata = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        else:
            appdata = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
        user_nodes_dir = appdata / "ingetrazo" / "plugins" / "node_editor" / "nodes"
        if user_nodes_dir.is_dir():
            dirs.append(user_nodes_dir)
    except Exception:
        pass

    return dirs


def load_node_file(file_path: Path, registry: Optional[Dict[str, Type[NodeBase]]] = None) -> List[Type[NodeBase]]:
    """
    Dynamically import a Python file and register all detectable node classes found inside.
    Safe against syntax or runtime import errors.
    """
    target_registry = registry if registry is not None else _REGISTRY_REF
    discovered: List[Type[NodeBase]] = []

    if not file_path.is_file() or file_path.suffix != ".py":
        return []
    if file_path.name.startswith(("_", ".")):
        return []

    module_name = f"_custom_node_{file_path.stem}"

    try:
        spec = importlib.util.spec_from_file_location(module_name, str(file_path))
        if spec is None or spec.loader is None:
            return []

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        for attr_name, attr_value in vars(module).items():
            if is_detectable_node(attr_value):
                discovered.append(attr_value)
                if target_registry is not None:
                    target_registry[attr_value.__name__] = attr_value
                log.info(f"Discovered custom node: '{getattr(attr_value, 'name', attr_name)}' ({attr_value.__name__}) in {file_path.name}")

    except Exception as ex:
        log.warning(f"Could not load custom node file '{file_path.name}': {ex}", exc_info=True)

    return discovered


def discover_nodes(
    directories: Optional[List[Union[Path, str]]] = None,
    registry: Optional[Dict[str, Type[NodeBase]]] = None
) -> List[Type[NodeBase]]:
    """
    Scan all node directories, import all `.py` files, and automatically register nodes.
    Returns the list of newly discovered node classes.
    """
    target_registry = registry if registry is not None else _REGISTRY_REF
    search_dirs: List[Path] = []

    if directories:
        search_dirs.extend([Path(d) for d in directories if Path(d).is_dir()])
    else:
        search_dirs.extend(get_default_nodes_directories())

    all_discovered: List[Type[NodeBase]] = []
    seen_files: set[Path] = set()

    for base_dir in search_dirs:
        if not base_dir.is_dir():
            continue

        # Scan directory and all subdirectories
        for entry in sorted(base_dir.rglob("*.py")):
            if entry.name.startswith(("_", ".")):
                continue
            if entry in seen_files:
                continue
            seen_files.add(entry)

            found = load_node_file(entry, target_registry)
            all_discovered.extend(found)

    log.info(f"Node auto-discovery complete: found {len(all_discovered)} custom node classes across {len(seen_files)} files.")
    return all_discovered
