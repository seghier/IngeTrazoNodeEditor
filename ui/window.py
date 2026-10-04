# SPDX-License-Identifier: GPL-3.0-or-later
"""Main Node Editor widget with toolbar, presets, docking, and live viewport synchronization."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Any
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QFont, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QToolBar,
    QPushButton, QCheckBox, QComboBox, QLabel, QFileDialog, QMessageBox, QStatusBar,
    QDockWidget, QSplitter
)

from ..engine import NodeGraph
from ..nodes_library import NODE_REGISTRY
from .canvas import NodeGraphScene, NodeGraphView
from .node_item import NodeItem
from .inspector import NodeInspectorPanel


class NodeEditorWidget(QWidget):
    """The visual parametric modeling widget for IngeTrazo (dockable and floatable)."""

    def __init__(self, app: Any, parent=None):
        super().__init__(parent)
        self.app = app
        self.dock_widget: Optional[QDockWidget] = None

        self.graph = NodeGraph()
        self.scene = NodeGraphScene(self.graph)
        self.scene.app = self.app
        self.view = NodeGraphView(self.scene, self)
        self.view.app = self.app
        self.inspector = NodeInspectorPanel(self)
        self.inspector.hide()

        self.live_sync_enabled = True
        self._eval_timer = QTimer(self)
        self._eval_timer.setSingleShot(True)
        self._eval_timer.setInterval(40)  # Debounce slider updates (25 fps cap)
        self._eval_timer.timeout.connect(self.run_evaluation)

        self.setup_ui()
        self.setup_styling()

        # Listen to graph and selection changes
        self.graph.listeners.append(self.on_graph_structure_changed)
        self.scene.selectionChanged.connect(self.on_selection_changed)

        # Load default example on startup
        self.load_initial_graph()

    def set_dock_widget(self, dock: QDockWidget) -> None:
        self.dock_widget = dock
        if dock:
            dock.topLevelChanged.connect(self.on_dock_toplevel_changed)

    def on_dock_toplevel_changed(self, is_floating: bool) -> None:
        if hasattr(self, "btn_float"):
            self.btn_float.setText("📌 Dock in Tray" if is_floating else "⛶ Pop Out")

    def toggle_floating(self) -> None:
        if not self.dock_widget:
            return
        floating = not self.dock_widget.isFloating()
        self.dock_widget.setFloating(floating)
        if floating:
            self.dock_widget.resize(1100, 700)
            self.btn_float.setText("📌 Dock in Tray")
        else:
            self.btn_float.setText("⛶ Pop Out")

    def setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Toolbar
        toolbar = QToolBar("Editor Controls", self)
        toolbar.setMovable(False)
        main_layout.addWidget(toolbar)

        # Run button
        btn_run = QPushButton("⚡ Evaluate")
        btn_run.setToolTip("Execute the graph now (F5)")
        btn_run.clicked.connect(lambda: self.run_evaluation(force_all=True))
        toolbar.addWidget(btn_run)

        toolbar.addSeparator()

        # Live Sync Toggle
        self.chk_live = QCheckBox("🔴 Live Sync")
        self.chk_live.setChecked(True)
        self.chk_live.setToolTip("Automatically update IngeTrazo viewport in real-time when dragging sliders")
        self.chk_live.toggled.connect(self.on_live_toggle)
        toolbar.addWidget(self.chk_live)

        toolbar.addSeparator()

        # Bake button
        btn_bake = QPushButton("🥐 Bake")
        btn_bake.setToolTip("Commit the current parametric geometry to the IngeTrazo document (undoable)")
        btn_bake.clicked.connect(self.bake_to_scene)
        toolbar.addWidget(btn_bake)

        toolbar.addSeparator()

        # Pop Out / Float button
        self.btn_float = QPushButton("⛶ Pop Out")
        self.btn_float.setToolTip("Undock / float this editor into a full-sized window, or dock back into the tray")
        self.btn_float.clicked.connect(self.toggle_floating)
        toolbar.addWidget(self.btn_float)

        toolbar.addSeparator()

        # Preset Examples Dropdown
        lbl_preset = QLabel(" Presets: ")
        toolbar.addWidget(lbl_preset)

        self.combo_presets = QComboBox()
        self.combo_presets.addItem("Select Preset...")
        self.combo_presets.addItem("1. Parametric Box")
        self.combo_presets.addItem("2. Gable Roof House")
        self.combo_presets.addItem("3. Spiral Staircase")
        self.combo_presets.addItem("4. Column Grid Array")
        self.combo_presets.addItem("5. Parametric Wave Surface")
        self.combo_presets.addItem("6. Roof from Face")
        self.combo_presets.currentIndexChanged.connect(self.on_preset_selected)
        toolbar.addWidget(self.combo_presets)

        toolbar.addSeparator()

        # Save / Load / Clear
        btn_save = QPushButton("💾 Save")
        btn_save.clicked.connect(self.save_graph_file)
        toolbar.addWidget(btn_save)

        btn_load = QPushButton("📂 Load")
        btn_load.clicked.connect(self.load_graph_file)
        toolbar.addWidget(btn_load)

        btn_clear = QPushButton("🧹 Clear")
        btn_clear.clicked.connect(self.clear_graph)
        toolbar.addWidget(btn_clear)

        # Central Canvas View & Inspector Panel
        self.splitter = QSplitter(Qt.Horizontal, self)
        self.splitter.addWidget(self.view)
        self.splitter.addWidget(self.inspector)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, True)
        main_layout.addWidget(self.splitter, 1)

        # Status Bar
        self.status = QStatusBar(self)
        main_layout.addWidget(self.status)
        self.lbl_stats = QLabel("Nodes: 0 | Connections: 0 | Solve: 0.0 ms")
        self.status.addPermanentWidget(self.lbl_stats)
        self.status.showMessage("Double-click canvas or press Space/Tab to add nodes.")

    def setup_styling(self) -> None:
        self.setStyleSheet("""
            QWidget {
                background: #181a1f;
            }
            QToolBar {
                background: #21252b;
                border-bottom: 1px solid #282c34;
                spacing: 6px;
                padding: 4px 6px;
            }
            QPushButton {
                background: #282c34;
                color: #eceff4;
                border: 1px solid #3b4252;
                border-radius: 4px;
                padding: 4px 8px;
                font-weight: 500;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #3b4252;
                color: #ffffff;
            }
            QPushButton:pressed {
                background: #4c566a;
            }
            QCheckBox {
                color: #eceff4;
                font-size: 11px;
                font-weight: 500;
            }
            QComboBox {
                background: #282c34;
                color: #eceff4;
                border: 1px solid #3b4252;
                border-radius: 4px;
                padding: 3px 22px 3px 8px;
                font-size: 11px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: 1px solid #3b4252;
                background: #21252b;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
            }
            QComboBox::drop-down:hover {
                background: #3b4252;
            }
            QComboBox::down-arrow {
                width: 0;
                height: 0;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #eceff4;
            }
            QComboBox QAbstractItemView {
                background: #21252b;
                color: #eceff4;
                selection-background-color: #3b4252;
                selection-color: #88c0d0;
                border: 1px solid #3b4252;
            }

            QStatusBar {
                background: #21252b;
                color: #abb2bf;
                border-top: 1px solid #282c34;
                font-size: 11px;
            }
        """)

    def on_live_toggle(self, checked: bool) -> None:
        self.live_sync_enabled = checked
        if checked:
            self.run_evaluation()

    def on_graph_structure_changed(self) -> None:
        self.update_stats()
        if hasattr(self, "inspector") and self.inspector.current_node:
            if self.inspector.current_node not in self.graph.nodes:
                self.inspector.close_panel()
        if self.live_sync_enabled:
            self._eval_timer.start()

    def update_stats(self) -> None:
        n_count = len(self.graph.nodes)
        c_count = len(self.graph.connections)
        self.lbl_stats.setText(f"Nodes: {n_count} | Connections: {c_count}")

    def on_selection_changed(self) -> None:
        try:
            if not hasattr(self, "scene") or self.scene is None:
                return
            selected = [it for it in self.scene.selectedItems() if isinstance(it, NodeItem)]
        except RuntimeError:
            return

        if len(selected) == 1:
            item = selected[0]
            self.inspector.populate(item.node, item, self.scene)
            self.inspector.show()
        else:
            if not getattr(self.inspector, "is_pinned", False):
                self.inspector.hide()

    def run_evaluation(self, force_all: bool = False) -> None:
        context = {"app": self.app}
        elapsed_ms = self.graph.evaluate(context=context, force_all=force_all)
        self.lbl_stats.setText(
            f"Nodes: {len(self.graph.nodes)} | Connections: {len(self.graph.connections)} | Solve: {elapsed_ms:.1f} ms"
        )
        if hasattr(self, "inspector") and not self.inspector.isHidden():
            self.inspector.refresh_values()

        # Refresh visual previews on node items (e.g. Image Preview and Image Sampler tiles)
        if hasattr(self, "scene") and self.scene:
            for item in getattr(self.scene, "node_items", {}).values():
                if hasattr(item, "update_preview_pix") and callable(item.update_preview_pix):
                    try:
                        item.update_preview_pix()
                    except Exception:
                        pass

        self.status.showMessage("Evaluation completed.", 1500)

    def bake_to_scene(self) -> None:
        from ..nodes_library import IngeTrazoOutputNode
        outputs = [n for n in self.graph.nodes if isinstance(n, IngeTrazoOutputNode)]
        if not outputs:
            QMessageBox.information(
                self, "IngeTrazo Output",
                "Add an 'IngeTrazo Output' node to your graph to specify which geometry to bake into the model."
            )
            return

        for out_node in outputs:
            out_node.bake(self.app, is_live=False)

        self.status.showMessage("Geometry baked into IngeTrazo document!", 3000)

    def clear_graph(self) -> None:
        if hasattr(self, "inspector"):
            self.inspector.close_panel()
        self.graph.connections.clear()
        self.graph.nodes.clear()
        self.scene.clear()
        self.scene.node_items.clear()
        self.scene.wire_items.clear()
        self.update_stats()

    def save_graph_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Node Graph", "", "IngeTrazo Graph (*.itgraph);;JSON (*.json)")
        if path:
            data = self.graph.serialize()
            Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
            self.status.showMessage(f"Saved: {Path(path).name}", 3000)

    def load_graph_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Node Graph", "", "IngeTrazo Graph (*.itgraph);;JSON (*.json)")
        if path:
            try:
                if hasattr(self, "inspector"):
                    self.inspector.close_panel()
                data = json.loads(Path(path).read_text(encoding="utf-8"))
                self.graph.deserialize(data, NODE_REGISTRY)
                self.scene.sync_from_graph()
                self.run_evaluation()
                self.status.showMessage(f"Loaded: {Path(path).name}", 3000)
            except Exception as ex:
                QMessageBox.warning(self, "Error Loading Graph", str(ex))

    # ---------------------------------------------------------------------------------
    # Presets & Default Graph
    # ---------------------------------------------------------------------------------

    def load_initial_graph(self) -> None:
        """Load default box example on startup."""
        self.build_example_box()

    def on_preset_selected(self, index: int) -> None:
        if index == 1:
            self.build_example_box()
        elif index == 2:
            self.build_example_house()
        elif index == 3:
            self.build_example_spiral_staircase()
        elif index == 4:
            self.build_example_column_grid()
        elif index == 5:
            self.build_example_wave_surface()
        elif index == 6:
            self.build_example_roof_from_face()

    def build_example_box(self) -> None:
        self.clear_graph()
        from ..nodes_library import NumberSliderNode, BoxNode, IngeTrazoOutputNode

        s_dx = self.graph.add_node(NumberSliderNode())
        s_dx.x, s_dx.y = -350, -100
        s_dx.widget_values["value"] = 4.0

        s_dy = self.graph.add_node(NumberSliderNode())
        s_dy.x, s_dy.y = -350, 60
        s_dy.widget_values["value"] = 5.0

        s_dz = self.graph.add_node(NumberSliderNode())
        s_dz.x, s_dz.y = -350, 220
        s_dz.widget_values["value"] = 3.0

        box = self.graph.add_node(BoxNode())
        box.x, box.y = -80, 40

        out = self.graph.add_node(IngeTrazoOutputNode())
        out.x, out.y = 200, 40

        self.graph.connect(s_dx.outputs[0], box.inputs[1])  # dx -> Size X
        self.graph.connect(s_dy.outputs[0], box.inputs[2])  # dy -> Size Y
        self.graph.connect(s_dz.outputs[0], box.inputs[3])  # dz -> Size Z
        self.graph.connect(box.outputs[0], out.inputs[0])   # Box -> IngeTrazo Output

        self.scene.sync_from_graph()
        self.run_evaluation()

    def build_example_house(self) -> None:
        self.clear_graph()
        from ..nodes_library import (
            NumberSliderNode, RectangleNode, ExtrudeNode,
            RoofFromSurfaceNode, MergeMeshesNode, IngeTrazoOutputNode
        )

        w = self.graph.add_node(NumberSliderNode())
        w.x, w.y = -520, -100
        w.widget_values["value"] = 8.0

        l = self.graph.add_node(NumberSliderNode())
        l.x, l.y = -520, 60
        l.widget_values["value"] = 12.0

        h = self.graph.add_node(NumberSliderNode())
        h.x, h.y = -520, 220
        h.widget_values["value"] = 3.2

        rect = self.graph.add_node(RectangleNode())
        rect.x, rect.y = -260, 40

        ext = self.graph.add_node(ExtrudeNode())
        ext.x, ext.y = 0, -40

        roof = self.graph.add_node(RoofFromSurfaceNode())
        roof.x, roof.y = 0, 180
        roof.inputs[4].default_value = 0.4   # Overhang
        roof.inputs[5].default_value = 0.25  # Thickness

        merge = self.graph.add_node(MergeMeshesNode())
        merge.x, merge.y = 260, 60

        out = self.graph.add_node(IngeTrazoOutputNode())
        out.x, out.y = 500, 60

        self.graph.connect(w.outputs[0], rect.inputs[1])     # Width -> Rectangle
        self.graph.connect(l.outputs[0], rect.inputs[2])     # Length -> Rectangle
        self.graph.connect(rect.outputs[0], ext.inputs[0])   # Rectangle -> Wall Extrude
        self.graph.connect(h.outputs[0], ext.inputs[1])      # Height -> Wall Extrude
        self.graph.connect(rect.outputs[0], roof.inputs[0])  # Rectangle -> Roof Surface
        self.graph.connect(h.outputs[0], roof.inputs[6])     # Height -> Roof Elevation
        self.graph.connect(ext.outputs[0], merge.inputs[0])  # Walls -> Merge A
        self.graph.connect(roof.outputs[0], merge.inputs[1]) # Roof -> Merge B
        self.graph.connect(merge.outputs[0], out.inputs[0])  # Merged -> Output

        self.scene.sync_from_graph()
        self.run_evaluation()

    def build_example_spiral_staircase(self) -> None:
        self.clear_graph()
        from ..nodes_library import (
            NumberSliderNode, IntegerSliderNode, BoxNode, IngeTrazoOutputNode
        )
        steps = self.graph.add_node(IntegerSliderNode())
        steps.x, steps.y = -350, 0
        steps.widget_values["value"] = 16

        box = self.graph.add_node(BoxNode())
        box.x, box.y = -80, 50

        out = self.graph.add_node(IngeTrazoOutputNode())
        out.x, out.y = 220, 50

        self.graph.connect(box.outputs[0], out.inputs[0])
        self.scene.sync_from_graph()
        self.run_evaluation()

    def build_example_column_grid(self) -> None:
        self.clear_graph()
        from ..nodes_library import (
            NumberSliderNode, CylinderNode, IngeTrazoOutputNode
        )
        r = self.graph.add_node(NumberSliderNode())
        r.x, r.y = -350, -50
        r.widget_values["value"] = 0.4

        h = self.graph.add_node(NumberSliderNode())
        h.x, h.y = -350, 120
        h.widget_values["value"] = 4.0

        cyl = self.graph.add_node(CylinderNode())
        cyl.x, cyl.y = -80, 40

        out = self.graph.add_node(IngeTrazoOutputNode())
        out.x, out.y = 220, 40

        self.graph.connect(r.outputs[0], cyl.inputs[1])
        self.graph.connect(h.outputs[0], cyl.inputs[2])
        self.graph.connect(cyl.outputs[0], out.inputs[0])

        self.scene.sync_from_graph()
        self.run_evaluation()

    def build_example_wave_surface(self) -> None:
        self.clear_graph()
        from ..nodes_library import (
            GridPointsNode, DeconstructPointNode, ExpressionNode,
            ConstructPointNode, MeshFromPointsNode, IngeTrazoOutputNode
        )

        grid = self.graph.add_node(GridPointsNode())
        grid.x, grid.y = -620, 50
        grid.inputs[0].default_value = 16  # Count X
        grid.inputs[1].default_value = 16  # Count Y
        grid.inputs[2].default_value = 0.5 # Step X
        grid.inputs[3].default_value = 0.5 # Step Y

        decon = self.graph.add_node(DeconstructPointNode())
        decon.x, decon.y = -360, 50

        expr = self.graph.add_node(ExpressionNode())
        expr.x, expr.y = -100, 70
        expr.widget_values["expr"] = "sin(x * 0.8) * cos(y * 0.8) * 1.5"

        con = self.graph.add_node(ConstructPointNode())
        con.x, con.y = 180, 50

        mesh_pts = self.graph.add_node(MeshFromPointsNode())
        mesh_pts.x, mesh_pts.y = 440, 50
        mesh_pts.inputs[1].default_value = 16 # U = 16

        out = self.graph.add_node(IngeTrazoOutputNode())
        out.x, out.y = 700, 50
        out.inputs[1].default_value = "ParametricWave"

        # Connections:
        # 1. Grid Points -> Deconstruct Point
        self.graph.connect(grid.outputs[0], decon.inputs[0])
        # 2. Deconstruct X -> Expr x, Deconstruct Y -> Expr y
        self.graph.connect(decon.outputs[0], expr.inputs[0])
        self.graph.connect(decon.outputs[1], expr.inputs[1])
        # 3. Construct Point: X from decon, Y from decon, Z from expr result!
        self.graph.connect(decon.outputs[0], con.inputs[0])
        self.graph.connect(decon.outputs[1], con.inputs[1])
        self.graph.connect(expr.outputs[0], con.inputs[2])
        # 4. Construct Point -> Mesh from Points
        self.graph.connect(con.outputs[0], mesh_pts.inputs[0])
        # 5. Mesh from Points -> IngeTrazo Output
        self.graph.connect(mesh_pts.outputs[0], out.inputs[0])

        self.scene.sync_from_graph()
        self.run_evaluation()

    def build_example_roof_from_face(self) -> None:
        """Preset: reads active selection as a surface (with holes) → roof generator.

        Wire layout:
            ReferenceFaceNode ──surface──► RoofFromSurfaceNode ──mesh──► IngeTrazoOutputNode
            NumberSliderNode  ──angle────►  (input 2)
            IntegerSliderNode ──style────►  (input 3)
            NumberSliderNode  ──overhang─►  (input 4)
            NumberSliderNode  ──thickness►  (input 5)
        """
        self.clear_graph()
        from ..nodes_library import (
            NumberSliderNode, IntegerSliderNode,
            ReferenceFaceNode, RoofFromSurfaceNode, IngeTrazoOutputNode,
        )

        # Reference Face (reads active selection or falls back to demo courtyard house)
        ref = self.graph.add_node(ReferenceFaceNode())
        ref.x, ref.y = -320, 60

        # Angle slider  (degrees, e.g. 30 deg)
        s_angle = self.graph.add_node(NumberSliderNode())
        s_angle.x, s_angle.y = -320, -160
        s_angle.widget_values["value"] = 30.0
        s_angle.widget_values["min"] = 5.0
        s_angle.widget_values["max"] = 75.0
        s_angle.inputs[0].default_value = 5.0
        s_angle.inputs[1].default_value = 75.0

        # Style slider  (0=Hip  1=Gable  2=Shed  3=Flat  4=Mansard)
        s_style = self.graph.add_node(IntegerSliderNode())
        s_style.x, s_style.y = -320, -40
        s_style.widget_values["value"] = 0
        s_style.widget_values["min"] = 0
        s_style.widget_values["max"] = 4

        # Overhang slider
        s_over = self.graph.add_node(NumberSliderNode())
        s_over.x, s_over.y = -320, 220
        s_over.widget_values["value"] = 0.4
        s_over.widget_values["min"] = 0.0
        s_over.widget_values["max"] = 1.5

        # Thickness slider
        s_thick = self.graph.add_node(NumberSliderNode())
        s_thick.x, s_thick.y = -320, 340
        s_thick.widget_values["value"] = 0.2
        s_thick.widget_values["min"] = 0.0
        s_thick.widget_values["max"] = 0.6

        # Roof node
        roof = self.graph.add_node(RoofFromSurfaceNode())
        roof.x, roof.y = 60, 60

        # Output
        out = self.graph.add_node(IngeTrazoOutputNode())
        out.x, out.y = 380, 60
        out.inputs[1].default_value = "RoofFromFace"

        # Connections
        self.graph.connect(ref.outputs[0], roof.inputs[0])   # Surface
        self.graph.connect(s_angle.outputs[0], roof.inputs[2])  # Angle
        self.graph.connect(s_style.outputs[0], roof.inputs[3])  # Style
        self.graph.connect(s_over.outputs[0], roof.inputs[4])   # Overhang
        self.graph.connect(s_thick.outputs[0], roof.inputs[5])  # Thickness
        self.graph.connect(roof.outputs[0], out.inputs[0])      # Mesh -> Output

        self.scene.sync_from_graph()
        self.run_evaluation()
