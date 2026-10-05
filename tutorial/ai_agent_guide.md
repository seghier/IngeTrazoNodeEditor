# IngeTrazo Node Editor — AI Agent Developer Guidelines

> **CRITICAL ARCHITECTURAL CONTRACT FOR ALL AI CODING AGENTS:**
> This repository provides the visual parametric node editor for [IngeTrazo CAD](https://ingetrazo.com).
> Read and strictly adhere to the invariants below before editing or adding code.

---

## 🚀 1. Core Architectural Invariants (DO NOT BREAK)

### 🏎️ Rule 1: Live Preview vs Permanent Bake Distinction
* **Live Viewport Preview (`is_live=True`)**:
  - High-density meshes (e.g. `Image Sampler` heightfields, terrain reliefs) **MUST** stream directly to the GPU as a virtual `TerrainObject` via `viewport.upload_terrain(terrain_obj)`.
  - Bypasses IngeTrazo's B-Rep topology graph (`Scene.mesh`), preserving 120+ FPS hardware OpenGL rotation.
  - Photo textures drape in real-time when `Texture` is enabled.
* **Manual Bake (`is_live=False`)**:
  - **CRITICAL USER DIRECTIVE: NEVER BAKE TEXTURE OR VERTEX COLORS.**
  - When baking to IngeTrazo document (`scene.groups`), geometry **must be 100% untextured CAD geometry**:
    - `attrs=None` (no face colors).
    - `baked_group.material = None` (no texture map material).
    - `e.soft = False` on all edges so wireframe lines are permanently visible in CAD.
    - Undo/redo must route through `SnapshotImport(do_bake)`.

### 📐 Rule 2: Coordinate Space & Unit Invariants
* All coordinates are in **local meters** with the ground reference plane at `Z = 0`.
* Surface normals must use the standard Newell method (`FaceData.normal()`) for correct 3D directional lighting in the viewport.
* Grid alignments for image heightfields follow bottom-to-top 3D coordinate convention (`np.flipud(buf)`).

### 🛡️ Rule 3: Zero-Crash & Error Isolation
* A failing node **MUST NEVER crash the graph solver or IngeTrazo application**.
* In `compute()`, always encapsulate user logic in `try...except`:
  ```python
  def compute(self, context=None):
      try:
          # computation logic
          self.error = None
          self.set_output("Out", result)
      except Exception as ex:
          self.error = str(ex)
          self.set_output("Out", fallback_default)
  ```
* Setting `self.error` automatically triggers a red error border on the canvas node item.

### 📋 Rule 4: Modular Node Authoring & Automatic Discovery
* **Modular File Architecture**:
  - Rather than bloating `nodes_library.py`, new nodes can be authored in dedicated Python files inside the **`nodes/`** folder (e.g. `nodes/my_feature.py`).
  - Subfolders (e.g. `nodes/civil/`, `nodes/structural/`) are automatically recursed.
  - User custom nodes can also reside in `%APPDATA%/ingetrazo/plugins/node_editor/nodes/`.
* **Automatic Detection Criteria**:
  - The discovery engine (`nodes.discover_nodes()`) automatically inspects imported files.
  - A class is **automatically detected and registered** if:
    1. It is a class inheriting from `NodeBase` (`issubclass(cls, NodeBase)`).
    2. It is not `NodeBase` itself.
    3. It defines a non-default `name` (e.g. `name = "My Feature"`).
    4. *(Optional)* It is decorated with `@register_node`.
* **Live Discovery**:
  - Runs automatically at startup.
  - Can be re-triggered live from the UI using the **🔄 Reload Nodes** toolbar button.
* Never duplicate node names across categories. The double-click search palette (`NodeSearchDialog`) dynamically reflects all entries registered in `NODE_REGISTRY`.

### 🔄 Rule 5: Pure Python Fallback Invariant
* Optional dependencies (like `numpy`, `shapely`, `py_straight_skeleton`) must always be wrapped in `try...except ImportError`.
* **Always provide a pure Python / Euclid fallback** so the node runs even when external C-libraries are unavailable in minimal environments.

### 💾 Rule 6: Serialization & Widget Hygiene
* The graph engine serializes `self.widget_values` to JSON during file save.
* **Rule**: Only store JSON-serializable primitives (`int`, `float`, `str`, `bool`, `list`, `dict`) in `self.widget_values`.
* Temporary/ephemeral objects (such as `QImage`, cached pixmaps, or VBO buffers) **must use keys starting with an underscore** (e.g. `_cached_qimage`), which are automatically ignored by `NodeBase.serialize()`.

### 🎛️ Rule 7: Clean Port Extraction & Fallbacks
* Always retrieve inputs using `self.get_input(port_name, fallback_value)`.
* `get_input()` automatically prioritizes:
  1. Incoming wire connection (`port.has_connection`).
  2. On-node widget matching the port name (`self.widget_values`).
  3. Static port default (`port.default_value`).
  4. Provided fallback value.

---

## 🎨 2. Standard Category Color Palette

Always use the Nord theme color codes for `header_color`:

```python
CATEGORY_COLORS = {
    "Input":     "#5e81ac",  # Nord Blue
    "Math":      "#d08770",  # Nord Orange
    "Logic":     "#d08770",  # Nord Orange
    "Point":     "#a3be8c",  # Nord Green
    "Vector":    "#8fbcbb",  # Nord Teal
    "Curve":     "#ebcb8b",  # Nord Yellow
    "Surface":   "#b48ead",  # Nord Purple
    "Solids":    "#b48ead",  # Nord Purple
    "Mesh":      "#f28b25",  # Deep Mesh Orange
    "Transform": "#88c0d0",  # Nord Cyan
    "Analysis":  "#88c0d0",  # Nord Cyan
    "Scene":     "#bf616a",  # Nord Red
}
```

---

## 🔌 3. Port Type Reference (`PortType`)

Defined in [`engine.py`](file:///C:/Users/pc/Documents/GitHub/IngeTrazoNodeEditor/engine.py#L16-L39):

| PortType | Visual Color | Expected Python Type | Description |
| :--- | :--- | :--- | :--- |
| `PortType.NUMBER` | `#4fc1ff` | `float` | Continuous numerical scalar |
| `PortType.INTEGER` | `#569cd6` | `int` | Discrete integer counter |
| `PortType.BOOLEAN` | `#c586c0` | `bool` | True/False toggle |
| `PortType.STRING` | `#ce9178` | `str` | Textual string |
| `PortType.POINT` | `#6a9955` | `Point3D` | 3D coordinate `(x, y, z)` |
| `PortType.VECTOR` | `#4ec9b0` | `Vector3D` | 3D direction vector `(x, y, z)` |
| `PortType.CURVE` | `#dcdcaa` | `PolylineData` | 2D/3D polylines and curves |
| `PortType.MESH` | `#f28b25` | `MeshData` | B-Rep surfaces, solids, and relief |
| `PortType.ANY` | `#d4d4d4` | `Any` / `List` | Polymorphic inputs, domains, lists |

---

## 📦 4. Release, Packaging & Catalog Update Workflow

When updating the plugin extension:

1. **Rebuild the Zip Package**:
   ```python
   import zipfile, os
   files = [
       '__init__.py', 'engine.py', 'nodes_library.py', 'models.py', 'euclid3.py', 'polyskel.py',
       'ui/canvas.py', 'ui/inspector.py', 'ui/node_item.py', 'ui/search_dialog.py'
   ]
   with zipfile.ZipFile('node_editor.zip', 'w', zipfile.ZIP_DEFLATED) as z:
       for f in files:
           if os.path.exists(f): z.write(f, f)
   ```
2. **Compute New SHA256**:
   ```powershell
   Get-FileHash -Path "node_editor.zip" -Algorithm SHA256
   ```
3. **Update Manifests**:
   - In `node_editor.toml` and `ingetrazo-extensions/extensions/node_editor.toml`:
     - Bump `version = "X.Y"`
     - Update `download = "https://github.com/seghier/IngeTrazoNodeEditor/releases/download/vX.Y/node_editor.zip"`
     - Update `sha256 = "<new_hash>"`
4. **Deploy Locally**:
   - Copy `nodes_library.py` to `%APPDATA%/IngeTrazo/plugins/node_editor/nodes_library.py`.
   - Clear `__pycache__` directories.
5. **Publish**:
   - Push commit and tag `vX.Y` to `origin`.
   - Create Release `vX.Y` on GitHub and attach `node_editor.zip`.
   - Submit PR to `ingelibre/ingetrazo-extensions`. The automerge robot validates the checksum and self-merges automatically.
