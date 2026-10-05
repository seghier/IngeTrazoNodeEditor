# IngeTrazo Node Editor (Parametric Visual Modeler)

A visual parametric node editor extension for **[IngeTrazo](https://github.com/ingelibre/ingetrazo)** (Python + PySide6 / Qt), bringing Grasshopper / Geometry Nodes style generative modeling into IngeTrazo.

<p align="center">
  <a href="video/ing_node.mp4">
    <img src="video/demo_preview.gif" alt="IngeTrazo Node Editor Live Demo" width="100%">
  </a>
  <br>
  <em>📹 <b>Click the preview above to watch the full HD demo video</b> (<code>video/ing_node.mp4</code>)</em>
</p>

---

## 🎬 Video Demonstration

[![Watch Full Demo Video](video/thumbnail.png)](video/ing_node.mp4)

> 💡 **[▶️ Click here to watch the full HD walkthrough (`video/ing_node.mp4`)](video/ing_node.mp4)**
>
> **Demonstrated in the video:**
> - **Real-Time Viewport Sync:** Interactive sliders instantly update 3D geometry in IngeTrazo's viewport with zero lag.
> - **Point Grid Arrays:** Generating 2D coordinate matrices with `Point Grid (2D)` and dynamic crosshair markers.
> - **Multi-Instance Solids:** Instantiating parametric solid cylinders at all grid points simultaneously.
> - **Seamless Docking:** Native integration in IngeTrazo's navigation tabs with pop-out / floating window support.

---

## 🚀 Features

- **Interactive Node Canvas:**
  - Modern dark-themed UI matching IngeTrazo.
  - Infinite dotted grid canvas with smooth panning (Middle drag or Alt+Left drag) and zooming (Mouse wheel).
  - Smooth cubic Bezier wires with real-time port snapping and type-coded pins.
  - Quick-search node palette via **Double-Click**, **Space**, or **Tab**.
- **Real-Time Live Viewport Sync:**
  - Dragging sliders on the canvas live-streams parametric geometry directly into IngeTrazo's 3D viewport.
- **Parametric Node Catalog:**
  - **Inputs & Inspection:** Number Slider (live float/int), Value Box, Toggle Switch, Vector XYZ, Text String, **Panel** (inspect and view any data with indexed list formatting `[0] ...`, or input multiline text and constants with scrollable monospace editor).
  - **Math & Logic:** Add, Subtract, Multiply, Divide, Series/Range Generator, **Divide Range** (linear interpolation / linspace domain division with start, end, count, and step size output), **Expression Node** (safe AST evaluator supporting formulas like `sin(x)*cos(y)`, `sqrt(x*x + y*y)`, variable aliases `x/y/z`, `u/v/w`, `a/b/c`, list broadcasting, and on-node code widget).
  - **List Operations:** **Cross Reference** (Cartesian product of two lists $A \times B$ pairing every element of A with every element of B for grid and coordinate synthesis).
  - **Points & Vectors:** Construct Point (supports list inputs), Deconstruct Point, Vector Math, Distance, 2D Grid Array.
  - **2D Profiles:** Line, Rectangle, Circle/Polygon, Polyline.
  - **3D Solids:** Box (Cuboid), Cylinder, UV Sphere, Extrude Profile, Face from Points, **Mesh from Points** (generates quad and triangulated 3D mesh surfaces from structured point grids with U and V counts, periodic wrapping, and UV transposition).
  - **Transforms:** Move / Translate, Rotate Z, Scale, Merge Meshes.
  - **Scene Output:** `IngeTrazo Output` node with Live Sync toggle and Bake button.
- **Bake to IngeTrazo:**
  - Commits geometry into IngeTrazo native `Group` containers and layers (`shapes`, etc.) with full Ctrl+Z undo/redo support (`SnapshotImport`).
- **Presets & Serialization:**
  - Built-in presets: *Parametric Box*, *Gable Roof House*, *Spiral Staircase*, *Column Grid Array*, *Parametric Wave Surface*.
  - Save and load node graphs as `.itgraph` (JSON).

---

## 📥 Installation

IngeTrazo automatically discovers plugins in your user plugins directory:

```
%APPDATA%\ingetrazo\plugins\
```

1. Copy the `node_editor` folder to:
   ```
   C:\Users\<YourUser>\AppData\Roaming\ingetrazo\plugins\node_editor
   ```
2. Start or restart **IngeTrazo**.
3. Go to the menu:
   - **Extensions** ▸ **Node Editor** ▸ **Open Node Editor…** (or press **Ctrl+Shift+N**).

---

## ⌨️ Controls & Shortcuts

| Action | Shortcut / Mouse |
|:--|:--|
| **Open Node Search** | `Space`, `Tab`, or Double-Click empty canvas |
| **Pan Canvas** | Middle Mouse Drag or `Alt` + Left Click Drag |
| **Zoom Canvas** | Mouse Wheel |
| **Connect Ports** | Click & drag from an output socket to an input socket |
| **Delete Selected Nodes** | `Delete` or `Backspace` |
| **Evaluate Graph** | `F5` or click **⚡ Evaluate** |
| **Toggle Live Sync** | Checkbox **🔴 Live Sync** |
| **Bake to Scene** | Click **🥐 Bake to IngeTrazo** |

---

## 📚 Developing Custom Nodes & AI Guide

Looking to author your own nodes or configure AI agents to work on the codebase? Check out the **[`tutorial/`](tutorial/)** directory:

- **[`tutorial/node_template.py`](tutorial/node_template.py)**: Copy-pasteable boilerplate templates for math processors, 3D geometry/mesh creators, and list-aware nodes.
- **[`tutorial/create_simple_node.md`](tutorial/create_simple_node.md)**: A complete, beginner-friendly walkthrough on building a custom parametric node from scratch.
- **[`tutorial/ai_agent_guide.md`](tutorial/ai_agent_guide.md)**: Architectural invariants, performance gates (120 FPS GPU streaming vs CAD bake), and rules for AI assistants (Antigravity, Cursor, Copilot).

---

## 📄 License

Licensed under the [GNU General Public License v3.0 (GPL-3.0)](LICENSE), matching IngeTrazo's GPL-3.0 license.
