# SPDX-License-Identifier: GPL-3.0-or-later
"""Node Property Inspector side panel for viewing, renaming, and controlling selected nodes."""
from __future__ import annotations

import math
from typing import Optional, Any, List
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QDoubleSpinBox, QSpinBox, QSlider, QCheckBox, QPlainTextEdit,
    QScrollArea, QFrame, QSizePolicy
)

from ..engine import NodeBase, Port, PortType
from ..nodes_library import VARIABLE_NAMES


class NodeInspectorPanel(QWidget):
    """
    Side property panel that appears when a node is selected on the canvas.
    Controls:
    - Node nickname / custom title
    - Input & Output port renaming
    - Dynamic input port addition & removal (e.g. ExpressionNode)
    - Expression formula editing with syntax hints
    - Slider parameters: Min, Max, Decimals, Value
    - Real-time synchronization with canvas node widgets and graph solver
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_node: Optional[NodeBase] = None
        self.current_node_item: Optional[Any] = None
        self.current_scene: Optional[Any] = None
        self._syncing = False
        self.is_pinned = False

        self.setMinimumWidth(280)
        self.setMaximumWidth(340)

        self.setup_ui()
        self.setup_styling()

    def setup_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Header bar
        header_bar = QWidget()
        header_bar.setObjectName("inspector_header")
        header_layout = QHBoxLayout(header_bar)
        header_layout.setContentsMargins(12, 8, 8, 8)
        header_layout.setSpacing(6)

        lbl_title = QLabel("📋 Node Properties")
        lbl_title.setObjectName("inspector_title")
        font = QFont("Segoe UI", 10, QFont.Bold)
        lbl_title.setFont(font)
        header_layout.addWidget(lbl_title, 1)

        self.btn_pin = QPushButton("📌")
        self.btn_pin.setObjectName("inspector_pin")
        self.btn_pin.setCheckable(True)
        self.btn_pin.setChecked(False)
        self.btn_pin.setToolTip("Pin side panel (keep open when unselected)")
        self.btn_pin.setFixedSize(22, 22)
        self.btn_pin.clicked.connect(self.toggle_pin)
        header_layout.addWidget(self.btn_pin, 0)

        btn_close = QPushButton("✕")
        btn_close.setObjectName("inspector_close")
        btn_close.setToolTip("Close properties panel")
        btn_close.setFixedSize(22, 22)
        btn_close.clicked.connect(self.close_panel)
        header_layout.addWidget(btn_close, 0)

        outer_layout.addWidget(header_bar)

        # Scroll area for dynamic content
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(12, 10, 12, 12)
        self.content_layout.setSpacing(12)

        self.scroll.setWidget(self.content_widget)
        outer_layout.addWidget(self.scroll, 1)

    def setup_styling(self) -> None:
        self.setStyleSheet("""
            QWidget {
                background: #1e222b;
                color: #eceff4;
                font-family: 'Segoe UI', system-ui, sans-serif;
                font-size: 11px;
            }
            #inspector_header {
                background: #21252b;
                border-bottom: 1px solid #282c34;
            }
            #inspector_title {
                color: #88c0d0;
                font-size: 12px;
                font-weight: bold;
            }
            #inspector_pin {
                background: transparent;
                color: #d8dee9;
                border: 1px solid transparent;
                border-radius: 4px;
                font-size: 11px;
                padding: 0px;
            }
            #inspector_pin:hover {
                background: #3b4252;
                color: #ffffff;
            }
            #inspector_pin:checked {
                background: #88c0d0;
                color: #1e222b;
                border: 1px solid #88c0d0;
                font-weight: bold;
            }
            #inspector_close {
                background: transparent;
                color: #d8dee9;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }
            #inspector_close:hover {
                background: #bf616a;
                color: #ffffff;
            }
            .section_title {
                color: #81a1c1;
                font-size: 11px;
                font-weight: bold;
                margin-top: 4px;
            }
            QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {
                background: #181a20;
                color: #eceff4;
                border: 1px solid #3b4252;
                border-radius: 4px;
                padding: 4px 6px;
                font-size: 11px;
            }
            QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border: 1px solid #88c0d0;
                background: #1e222b;
            }
            QPushButton {
                background: #282c34;
                color: #eceff4;
                border: 1px solid #3b4252;
                border-radius: 4px;
                padding: 4px 8px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: #3b4252;
                color: #ffffff;
            }
            QPushButton:pressed {
                background: #4c566a;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #282c34;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #4fc1ff;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #eceff4;
                border: 1px solid #3b4252;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::handle:horizontal:hover {
                background: #ffffff;
                border: 1px solid #4fc1ff;
            }
            QScrollBar:vertical {
                background: #181a20;
                width: 8px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #3b4252;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #4c566a;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

    def toggle_pin(self) -> None:
        """Toggle pinning of the side inspector panel."""
        self.is_pinned = self.btn_pin.isChecked()
        self.btn_pin.setToolTip(
            "Unpin side panel (auto-hide when unselected)"
            if self.is_pinned
            else "Pin side panel (keep open when unselected)"
        )

    def close_panel(self) -> None:
        self.is_pinned = False
        if hasattr(self, "btn_pin"):
            self.btn_pin.setChecked(False)
            self.btn_pin.setToolTip("Pin side panel (keep open when unselected)")
        self.hide()
        try:
            if self.current_scene:
                self.current_scene.clearSelection()
        except RuntimeError:
            pass

    def populate(self, node: NodeBase, node_item: Any, scene: Any) -> None:
        """Populate the inspector panel with the selected node's properties."""
        self.current_node = node
        self.current_node_item = node_item
        self.current_scene = scene

        # Clear existing content
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        self._param_spin_min = None
        self._param_spin_max = None
        self._param_spin_dec = None
        self._param_spin_val = None
        self._param_slider = None

        if not node:
            return

        self._syncing = True

        # --- Section 1: Identity & Nickname ---
        self._build_identity_section(node)

        # --- Section 2: Parameters & Widgets ---
        self._build_parameters_section(node)

        # --- Section 3: Inputs ---
        self._build_inputs_section(node)

        # --- Section 4: Outputs ---
        self._build_outputs_section(node)

        self.content_layout.addStretch(1)
        self._syncing = False

    def _build_identity_section(self, node: NodeBase) -> None:
        sec_box = QWidget()
        lay = QVBoxLayout(sec_box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        # Type badge
        lbl_type = QLabel(f"<b>Type:</b> {node.__class__.__name__} <span style='color: #88c0d0;'>({node.category})</span>")
        lbl_type.setTextFormat(Qt.RichText)
        lay.addWidget(lbl_type)

        # Nickname / Instance Name
        lay_name = QHBoxLayout()
        lay_name.setSpacing(6)
        lbl_nick = QLabel("Nickname:")
        lbl_nick.setFixedWidth(56)
        le_name = QLineEdit(node.name)
        le_name.setPlaceholderText("Custom nickname...")

        def on_name_changed(txt):
            if not self._syncing:
                node.name = txt.strip() if txt.strip() else node.__class__.name
                node.dirty = True
                if self.current_node_item:
                    self.current_node_item.update()
                if self.current_scene:
                    self.current_scene.notify_graph_changed()

        le_name.textChanged.connect(on_name_changed)
        lay_name.addWidget(lbl_nick)
        lay_name.addWidget(le_name, 1)
        lay.addLayout(lay_name)

        # Description
        if node.description:
            lbl_desc = QLabel(node.description)
            lbl_desc.setWordWrap(True)
            lbl_desc.setStyleSheet("color: #7f8c98; font-size: 10px; line-height: 120%;")
            lay.addWidget(lbl_desc)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #2c313a;")
        lay.addWidget(sep)

        self.content_layout.addWidget(sec_box)

    def _build_parameters_section(self, node: NodeBase) -> None:
        t_name = node.__class__.__name__
        has_params = (t_name in (
            "NumberSliderNode", "IntegerSliderNode", "ExpressionNode",
            "ToggleNode", "StringNode", "PanelNode", "ReferenceFaceNode",
            "ImageFileNode", "ImagePreviewNode", "ImageSamplerNode"
        ))

        if not has_params:
            return

        sec_box = QWidget()
        lay = QVBoxLayout(sec_box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        lbl_sec = QLabel("⚙️ Parameters")
        lbl_sec.setProperty("class", "section_title")
        lbl_sec.setStyleSheet("color: #81a1c1; font-weight: bold;")
        lay.addWidget(lbl_sec)

        if t_name in ("NumberSliderNode", "IntegerSliderNode"):
            is_int = (t_name == "IntegerSliderNode")
            min_val = float(node.widget_values.get("min", 0.0))
            max_val = float(node.widget_values.get("max", 50.0 if not is_int else 100.0))
            cur_val = float(node.widget_values.get("value", 5.0 if not is_int else 10))
            decimals = int(node.widget_values.get("decimals", 2 if not is_int else 0))

            grid = QGridLayout()
            grid.setSpacing(6)

            # Min
            grid.addWidget(QLabel("Min:"), 0, 0)
            spin_min = QDoubleSpinBox() if not is_int else QSpinBox()
            spin_min.setRange(-1000000, 1000000)
            spin_min.setValue(min_val if not is_int else int(round(min_val)))
            spin_min.setKeyboardTracking(False)
            if hasattr(spin_min, "lineEdit") and spin_min.lineEdit():
                spin_min.lineEdit().returnPressed.connect(spin_min.clearFocus)
            if not is_int:
                spin_min.setDecimals(decimals)
            grid.addWidget(spin_min, 0, 1)

            # Max
            grid.addWidget(QLabel("Max:"), 1, 0)
            spin_max = QDoubleSpinBox() if not is_int else QSpinBox()
            spin_max.setRange(-1000000, 1000000)
            spin_max.setValue(max_val if not is_int else int(round(max_val)))
            spin_max.setKeyboardTracking(False)
            if hasattr(spin_max, "lineEdit") and spin_max.lineEdit():
                spin_max.lineEdit().returnPressed.connect(spin_max.clearFocus)
            if not is_int:
                spin_max.setDecimals(decimals)
            grid.addWidget(spin_max, 1, 1)

            # Decimals (for float)
            spin_dec = None
            if not is_int:
                grid.addWidget(QLabel("Decimals:"), 2, 0)
                spin_dec = QSpinBox()
                spin_dec.setRange(0, 6)
                spin_dec.setValue(decimals)
                spin_dec.setKeyboardTracking(False)
                if hasattr(spin_dec, "lineEdit") and spin_dec.lineEdit():
                    spin_dec.lineEdit().returnPressed.connect(spin_dec.clearFocus)
                grid.addWidget(spin_dec, 2, 1)

            # Value
            row_idx = 3 if not is_int else 2
            grid.addWidget(QLabel("Value:"), row_idx, 0)
            spin_val = QDoubleSpinBox() if not is_int else QSpinBox()
            spin_val.setRange(min_val, max_val)
            spin_val.setValue(cur_val if not is_int else int(round(cur_val)))
            spin_val.setKeyboardTracking(False)
            if hasattr(spin_val, "lineEdit") and spin_val.lineEdit():
                spin_val.lineEdit().returnPressed.connect(spin_val.clearFocus)
            if not is_int:
                spin_val.setDecimals(decimals)
            grid.addWidget(spin_val, row_idx, 1)

            # Live slider
            slider = QSlider(Qt.Horizontal)
            slider.setMinimum(0)
            steps = int(round(max_val - min_val)) if is_int else 1000
            slider.setMaximum(max(1, steps))
            if is_int:
                tick = int(round(cur_val - min_val))
            else:
                ratio = (cur_val - min_val) / (max_val - min_val) if max_val > min_val else 0.0
                tick = int(round(ratio * 1000))
            slider.setValue(max(0, min(steps, tick)))

            grid.addWidget(slider, row_idx + 1, 0, 1, 2)
            lay.addLayout(grid)

            self._param_spin_min = spin_min
            self._param_spin_max = spin_max
            self._param_spin_dec = spin_dec
            self._param_spin_val = spin_val
            self._param_slider = slider

            def update_slider_model():
                if self._syncing:
                    return
                mn = spin_min.value()
                mx = spin_max.value()
                if mx <= mn:
                    mx = mn + 1.0
                    spin_max.blockSignals(True)
                    spin_max.setValue(mx)
                    spin_max.blockSignals(False)

                node.widget_values["min"] = mn
                node.widget_values["max"] = mx
                if not is_int and spin_dec is not None:
                    dec = spin_dec.value()
                    node.widget_values["decimals"] = dec
                    spin_min.setDecimals(dec)
                    spin_max.setDecimals(dec)
                    spin_val.setDecimals(dec)

                cur_v = min(mx, max(mn, spin_val.value()))
                node.widget_values["value"] = int(round(cur_v)) if is_int else float(cur_v)

                spin_val.blockSignals(True)
                spin_val.setRange(mn, mx)
                spin_val.setValue(cur_v)
                spin_val.blockSignals(False)

                steps_now = int(round(mx - mn)) if is_int else 1000
                slider.blockSignals(True)
                slider.setMaximum(max(1, steps_now))
                if is_int:
                    tick = int(round(cur_v - mn))
                else:
                    ratio = (cur_v - mn) / (mx - mn) if mx > mn else 0.0
                    tick = int(round(ratio * 1000))
                slider.setValue(max(0, min(steps_now, tick)))
                slider.blockSignals(False)

                node.dirty = True

                if self.current_node_item and hasattr(self.current_node_item, "update_slider_range"):
                    self.current_node_item.update_slider_range()

                if self.current_scene:
                    self.current_scene.notify_graph_changed()

            def on_panel_slider(val):
                if self._syncing:
                    return
                mn = spin_min.value()
                mx = spin_max.value()
                if is_int:
                    num = int(round(mn + val))
                else:
                    max_ticks = float(slider.maximum()) or 1000.0
                    ratio = val / max_ticks
                    num = mn + ratio * (mx - mn)

                spin_val.blockSignals(True)
                spin_val.setValue(num)
                spin_val.blockSignals(False)

                node.widget_values["value"] = int(num) if is_int else float(num)
                node.dirty = True

                if self.current_node_item and hasattr(self.current_node_item, "update_slider_range"):
                    self.current_node_item.update_slider_range()

                if self.current_scene:
                    self.current_scene.notify_graph_changed()

            def on_spin_val(v):
                if self._syncing:
                    return
                mn = spin_min.value()
                mx = spin_max.value()
                v = min(mx, max(mn, v))
                steps_now = int(round(mx - mn)) if is_int else 1000
                slider.blockSignals(True)
                slider.setMaximum(max(1, steps_now))
                if is_int:
                    tick = int(round(v - mn))
                else:
                    ratio = (v - mn) / (mx - mn) if mx > mn else 0.0
                    tick = int(round(ratio * 1000))
                slider.setValue(max(0, min(steps_now, tick)))
                slider.blockSignals(False)

                node.widget_values["value"] = int(v) if is_int else float(v)
                node.dirty = True

                if self.current_node_item and hasattr(self.current_node_item, "update_slider_range"):
                    self.current_node_item.update_slider_range()

                if self.current_scene:
                    self.current_scene.notify_graph_changed()

            spin_min.valueChanged.connect(update_slider_model)
            spin_max.valueChanged.connect(update_slider_model)
            if not is_int and spin_dec is not None:
                spin_dec.valueChanged.connect(update_slider_model)
            spin_val.valueChanged.connect(on_spin_val)
            slider.valueChanged.connect(on_panel_slider)

        elif t_name == "ExpressionNode":
            lay.addWidget(QLabel("Formula / Expression:"))
            cur_expr = str(node.widget_values.get("expr", "x + y"))
            te_expr = QPlainTextEdit(cur_expr)
            te_expr.setMaximumHeight(70)
            te_expr.setStyleSheet("""
                QPlainTextEdit {
                    background: #181a20;
                    color: #56b6c2;
                    border: 1px solid #434c5e;
                    border-radius: 4px;
                    padding: 4px 6px;
                    font-family: Consolas, 'Courier New', monospace;
                    font-size: 11px;
                    font-weight: bold;
                }
                QPlainTextEdit:focus {
                    border: 1px solid #88c0d0;
                    background: #1e222b;
                }
            """)

            def on_expr_text():
                if self._syncing:
                    return
                txt = te_expr.toPlainText().strip()
                node.widget_values["expr"] = txt
                node.dirty = True
                if hasattr(node, "sync_dynamic_ports"):
                    if node.sync_dynamic_ports():
                        if self.current_node_item and hasattr(self.current_node_item, "rebuild_ports"):
                            self.current_node_item.rebuild_ports()
                        self.populate(self.current_node, self.current_node_item, self.current_scene)
                if self.current_node_item and hasattr(self.current_node_item, "update_expression_text"):
                    self.current_node_item.update_expression_text(txt)
                if self.current_scene:
                    self.current_scene.notify_graph_changed()

            te_expr.textChanged.connect(on_expr_text)
            lay.addWidget(te_expr)

            lbl_hint = QLabel("Math: sin, cos, tan, ln, log, sqrt, abs, pi, e, deg, rad")
            lbl_hint.setStyleSheet("color: #7f8c98; font-size: 9px;")
            lay.addWidget(lbl_hint)

        elif t_name == "ToggleNode":
            cb = QCheckBox("Active / True")
            cb.setChecked(bool(node.widget_values.get("value", True)))

            def on_cb(chk):
                node.widget_values["value"] = chk
                node.dirty = True
                if self.current_scene:
                    self.current_scene.notify_graph_changed()

            cb.toggled.connect(on_cb)
            lay.addWidget(cb)

        elif t_name == "StringNode":
            le_str = QLineEdit(str(node.widget_values.get("value", "")))

            def on_str(txt):
                node.widget_values["value"] = txt
                node.dirty = True
                if self.current_scene:
                    self.current_scene.notify_graph_changed()

            le_str.textChanged.connect(on_str)
            lay.addWidget(le_str)

        elif t_name == "PanelNode":
            pte_panel = QPlainTextEdit(str(node.widget_values.get("display") or node.widget_values.get("text") or ""))
            pte_panel.setMaximumHeight(90)
            conn = node.inputs[0].has_connection if node.inputs else False
            pte_panel.setReadOnly(conn)

            def on_pte():
                if self._syncing:
                    return
                txt = pte_panel.toPlainText()
                node.widget_values["text"] = txt
                node.widget_values["display"] = txt
                node.dirty = True
                if self.current_node_item and hasattr(self.current_node_item, "update_panel_content"):
                    self.current_node_item.update_panel_content(txt)
                if self.current_scene:
                    self.current_scene.notify_graph_changed()

            pte_panel.textChanged.connect(on_pte)
            lay.addWidget(pte_panel)

        elif t_name == "ReferenceFaceNode":
            p_box = QWidget()
            p_lay = QVBoxLayout(p_box)
            p_lay.setContentsMargins(8, 6, 8, 6)
            p_lay.setSpacing(8)
            p_box.setStyleSheet("background: #252830; border-radius: 6px;")

            saved_ref = node.widget_values.get("referenced_face")
            status_txt = f"Referenced: {saved_ref.get('summary', '')}" if saved_ref else "No face stored (Click 'Set Selected Face')"
            lbl_info = QLabel(status_txt)
            lbl_info.setWordWrap(True)
            lbl_info.setStyleSheet("color: #a3be8c; font-size: 11px; font-weight: bold;" if saved_ref else "color: #d8dee9; font-size: 11px; font-style: italic;")

            btn_set = QPushButton("📌 Set Selected Face")
            btn_set.setCursor(Qt.PointingHandCursor)
            btn_set.setStyleSheet("""
                QPushButton {
                    background: #434c5e; color: #eceff4; border: 1px solid #4c566a;
                    border-radius: 4px; padding: 6px 10px; font-weight: bold;
                }
                QPushButton:hover { background: #4c566a; color: #88c0d0; border-color: #88c0d0; }
            """)

            btn_clear = QPushButton("✕ Clear Stored Face")
            btn_clear.setCursor(Qt.PointingHandCursor)
            btn_clear.setStyleSheet("""
                QPushButton {
                    background: #2e3440; color: #bf616a; border: 1px solid #bf616a;
                    border-radius: 4px; padding: 4px 8px;
                }
                QPushButton:hover { background: #bf616a; color: #eceff4; }
            """)

            def on_inspector_set():
                app = getattr(self.current_scene, "app", None)
                if not app:
                    from PySide6.QtWidgets import QApplication
                    app = getattr(QApplication.instance(), "_extension_app_handle", None)
                msg, ok = node.reference_from_selection(app)
                lbl_info.setText(msg)
                if ok:
                    lbl_info.setStyleSheet("color: #a3be8c; font-size: 11px; font-weight: bold;")
                else:
                    lbl_info.setStyleSheet("color: #ebcb8b; font-size: 11px;")
                node.dirty = True
                if self.current_scene:
                    self.current_scene.notify_graph_changed()
                if self.current_node_item and hasattr(self.current_node_item, "update"):
                    self.current_node_item.update()

            def on_inspector_clear():
                node.clear_reference()
                lbl_info.setText("Face cleared (using live selection or demo)")
                lbl_info.setStyleSheet("color: #d8dee9; font-size: 11px; font-style: italic;")
                node.dirty = True
                if self.current_scene:
                    self.current_scene.notify_graph_changed()
                if self.current_node_item and hasattr(self.current_node_item, "update"):
                    self.current_node_item.update()

            btn_set.clicked.connect(on_inspector_set)
            btn_clear.clicked.connect(on_inspector_clear)

            p_lay.addWidget(lbl_info)
            p_lay.addWidget(btn_set)
            p_lay.addWidget(btn_clear)
            lay.addWidget(p_box)

        elif t_name in ("ImageFileNode", "ImagePreviewNode", "ImageSamplerNode"):
            p_box = QWidget()
            p_lay = QVBoxLayout(p_box)
            p_lay.setContentsMargins(0, 0, 0, 0)
            p_lay.setSpacing(6)

            # Image Path Field
            p_lay.addWidget(QLabel("Image File:"))
            row_f = QHBoxLayout()
            row_f.setSpacing(4)
            le_path = QLineEdit(str(node.widget_values.get("image_path", "")))
            le_path.setPlaceholderText("Select image file...")

            btn_browse = QPushButton("Browse...")
            btn_browse.setCursor(Qt.PointingHandCursor)

            row_f.addWidget(le_path, 1)
            row_f.addWidget(btn_browse, 0)
            p_lay.addLayout(row_f)

            # Thumbnail preview box
            lbl_preview = QLabel()
            lbl_preview.setFixedSize(200, 120)
            lbl_preview.setAlignment(Qt.AlignCenter)
            lbl_preview.setStyleSheet("background: #181a20; border: 1px solid #3b4252; border-radius: 4px; color: #4c566a; font-size: 11px;")

            def refresh_insp_preview():
                import os
                from PySide6.QtGui import QImage, QPixmap
                qimg = node.widget_values.get("_cached_qimage")
                p = node.widget_values.get("image_path", "")
                if not qimg and p and os.path.exists(p):
                    qimg = QImage(p)
                if qimg and not qimg.isNull():
                    pix = QPixmap.fromImage(qimg).scaled(lbl_preview.width() - 4, lbl_preview.height() - 4, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    lbl_preview.setPixmap(pix)
                    lbl_preview.setText("")
                else:
                    lbl_preview.setPixmap(QPixmap())
                    lbl_preview.setText("No Image Loaded")

            refresh_insp_preview()

            def on_browse_click():
                from PySide6.QtWidgets import QFileDialog
                path, _ = QFileDialog.getOpenFileName(
                    None, "Select Image", "",
                    "Images (*.png *.jpg *.jpeg *.bmp *.webp *.tif);;All Files (*.*)"
                )
                if path:
                    le_path.setText(path)
                    node.widget_values["image_path"] = path
                    refresh_insp_preview()
                    node.dirty = True
                    if self.current_scene:
                        self.current_scene.notify_graph_changed()
                    if self.current_node_item and hasattr(self.current_node_item, "update"):
                        self.current_node_item.update()

            def on_path_text_change(txt):
                if not self._syncing:
                    node.widget_values["image_path"] = txt.strip()
                    refresh_insp_preview()
                    node.dirty = True
                    if self.current_scene:
                        self.current_scene.notify_graph_changed()

            btn_browse.clicked.connect(on_browse_click)
            le_path.textChanged.connect(on_path_text_change)

            # Specific controls for ImageSamplerNode
            if t_name == "ImageSamplerNode":
                chk_inv = QCheckBox("Invert Brightness / Heights")
                chk_inv.setChecked(bool(node.widget_values.get("invert", False)))

                def on_inv_toggled(chk):
                    node.widget_values["invert"] = chk
                    node.dirty = True
                    if self.current_scene:
                        self.current_scene.notify_graph_changed()
                    if self.current_node_item and hasattr(self.current_node_item, "update"):
                        self.current_node_item.update()

                chk_inv.toggled.connect(on_inv_toggled)
                p_lay.addWidget(chk_inv)

                # Channel selection
                p_lay.addWidget(QLabel("Color Channel:"))
                cb_chan = QComboBox()
                cb_chan.addItems(["Grayscale", "Red", "Green", "Blue", "Alpha"])
                cur_ch = node.widget_values.get("channel", "Grayscale")
                idx_ch = cb_chan.findText(cur_ch)
                if idx_ch >= 0:
                    cb_chan.setCurrentIndex(idx_ch)

                def on_ch_changed(idx):
                    node.widget_values["channel"] = cb_chan.currentText()
                    node.dirty = True
                    if self.current_scene:
                        self.current_scene.notify_graph_changed()

                cb_chan.currentIndexChanged.connect(on_ch_changed)
                p_lay.addWidget(cb_chan)

                # Sampling filter
                p_lay.addWidget(QLabel("Filter Mode:"))
                cb_flt = QComboBox()
                cb_flt.addItems(["Bilinear", "Nearest"])
                cur_flt = node.widget_values.get("filter", "Bilinear")
                idx_flt = cb_flt.findText(cur_flt)
                if idx_flt >= 0:
                    cb_flt.setCurrentIndex(idx_flt)

                def on_flt_changed(idx):
                    node.widget_values["filter"] = cb_flt.currentText()
                    node.dirty = True
                    if self.current_scene:
                        self.current_scene.notify_graph_changed()

                cb_flt.currentIndexChanged.connect(on_flt_changed)
                p_lay.addWidget(cb_flt)

            p_lay.addWidget(QLabel("Preview:"))
            p_lay.addWidget(lbl_preview)
            lay.addWidget(p_box)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #2c313a;")
        lay.addWidget(sep)

        self.content_layout.addWidget(sec_box)

    def _build_inputs_section(self, node: NodeBase) -> None:
        sec_box = QWidget()
        lay = QVBoxLayout(sec_box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(6)
        lbl_sec = QLabel(f"📥 Inputs ({len(node.inputs)})")
        lbl_sec.setProperty("class", "section_title")
        lbl_sec.setStyleSheet("color: #81a1c1; font-weight: bold;")
        hdr_row.addWidget(lbl_sec, 1)

        # If node supports dynamic ports (like ExpressionNode)
        is_dynamic = hasattr(node, "sync_dynamic_ports") or (node.__class__.__name__ == "ExpressionNode")
        if is_dynamic:
            btn_add_input = QPushButton("➕ Add Input")
            btn_add_input.setToolTip("Add a new input variable port")
            btn_add_input.setFixedHeight(22)
            btn_add_input.clicked.connect(self._add_dynamic_input)
            hdr_row.addWidget(btn_add_input, 0)

        lay.addLayout(hdr_row)

        # Port list
        for port in list(node.inputs):
            row = QWidget()
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(4, 2, 4, 2)
            row_lay.setSpacing(6)
            row.setStyleSheet("background: #252830; border-radius: 4px;")

            # Pin dot
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {port.get_color()}; font-size: 10px;")
            row_lay.addWidget(dot, 0)

            # Editable name
            le_pname = QLineEdit(port.name)
            le_pname.setFixedHeight(22)
            le_pname.setToolTip(f"Port name: {port.name} ({port.port_type.value})")

            def make_renamer(p=port, le=le_pname):
                def rename_port(new_txt):
                    if not self._syncing and new_txt.strip():
                        p.name = new_txt.strip()
                        node.dirty = True
                        if self.current_node_item:
                            self.current_node_item.update()
                        if self.current_scene:
                            self.current_scene.notify_graph_changed()
                return rename_port

            le_pname.textChanged.connect(make_renamer(port, le_pname))
            row_lay.addWidget(le_pname, 1)

            # Type badge
            type_tag = QLabel(port.port_type.value)
            type_tag.setStyleSheet("color: #7f8c98; font-size: 9px; padding: 1px 4px; background: #1e222b; border-radius: 2px;")
            row_lay.addWidget(type_tag, 0)

            # Wire count badge
            n_wires = len(port.connections)
            if n_wires > 0:
                conn_badge = QLabel(f"● {n_wires}")
                conn_badge.setStyleSheet("color: #4fc1ff; font-weight: bold; font-size: 10px;")
            else:
                conn_badge = QLabel("○ unwired")
                conn_badge.setStyleSheet("color: #5c6370; font-size: 9px;")
            row_lay.addWidget(conn_badge, 0)

            # If ExpressionNode and variable port, show delete button
            if is_dynamic and port.name != "Expr":
                btn_del = QPushButton("✖")
                btn_del.setToolTip(f"Remove port {port.name}")
                btn_del.setFixedSize(18, 18)
                btn_del.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        color: #7f8c98;
                        border: none;
                        font-size: 10px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        color: #bf616a;
                    }
                """)

                def make_remover(p=port):
                    def remove_port():
                        self._remove_input_port(p)
                    return remove_port

                btn_del.clicked.connect(make_remover(port))
                row_lay.addWidget(btn_del, 0)

            lay.addWidget(row)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #2c313a;")
        lay.addWidget(sep)

        self.content_layout.addWidget(sec_box)

    def _build_outputs_section(self, node: NodeBase) -> None:
        sec_box = QWidget()
        lay = QVBoxLayout(sec_box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        lbl_sec = QLabel(f"📤 Outputs ({len(node.outputs)})")
        lbl_sec.setProperty("class", "section_title")
        lbl_sec.setStyleSheet("color: #81a1c1; font-weight: bold;")
        lay.addWidget(lbl_sec)

        self._output_labels = {}
        for port in list(node.outputs):
            row = QWidget()
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(4, 2, 4, 2)
            row_lay.setSpacing(6)
            row.setStyleSheet("background: #252830; border-radius: 4px;")

            dot = QLabel("●")
            dot.setStyleSheet(f"color: {port.get_color()}; font-size: 10px;")
            row_lay.addWidget(dot, 0)

            le_pname = QLineEdit(port.name)
            le_pname.setFixedHeight(22)

            def make_out_renamer(p=port):
                def rename_out(new_txt):
                    if not self._syncing and new_txt.strip():
                        p.name = new_txt.strip()
                        node.dirty = True
                        if self.current_node_item:
                            self.current_node_item.update()
                        if self.current_scene:
                            self.current_scene.notify_graph_changed()
                return rename_out

            le_pname.textChanged.connect(make_out_renamer(port))
            row_lay.addWidget(le_pname, 1)

            # Type badge
            type_tag = QLabel(port.port_type.value)
            type_tag.setStyleSheet("color: #7f8c98; font-size: 9px; padding: 1px 4px; background: #1e222b; border-radius: 2px;")
            row_lay.addWidget(type_tag, 0)

            # Output value preview
            preview_str = self._format_value_preview(port.value)
            lbl_val = QLabel(preview_str)
            lbl_val.setStyleSheet("color: #98c379; font-family: Consolas, monospace; font-size: 10px;")
            row_lay.addWidget(lbl_val, 0)
            self._output_labels[port] = lbl_val

            lay.addWidget(row)

        self.content_layout.addWidget(sec_box)

    def refresh_values(self) -> None:
        """Lightweight update of output preview values and parameter controls after an evaluation."""
        if not self.current_node:
            return

        # 1. Update outputs preview
        if hasattr(self, "_output_labels") and self._output_labels:
            for port, lbl in self._output_labels.items():
                lbl.setText(self._format_value_preview(port.value))

        # 2. Update parameter controls in-place if node is slider
        if (hasattr(self, "_param_spin_val") and self._param_spin_val is not None
                and hasattr(self, "_param_slider") and self._param_slider is not None):
            val = float(self.current_node.widget_values.get("value", 0.0))
            mn = float(self.current_node.widget_values.get("min", 0.0))
            mx = float(self.current_node.widget_values.get("max", 50.0))
            is_int = (self.current_node.__class__.__name__ == "IntegerSliderNode")

            self._param_spin_val.blockSignals(True)
            self._param_spin_val.setRange(mn, mx)
            self._param_spin_val.setValue(val if not is_int else int(round(val)))
            self._param_spin_val.blockSignals(False)

            steps_now = int(round(mx - mn)) if is_int else 1000
            self._param_slider.blockSignals(True)
            self._param_slider.setMaximum(max(1, steps_now))
            if is_int:
                tick = int(round(val - mn))
            else:
                ratio = (val - mn) / (mx - mn) if mx > mn else 0.0
                tick = int(round(ratio * 1000))
            self._param_slider.setValue(max(0, min(steps_now, tick)))
            self._param_slider.blockSignals(False)

    def _format_value_preview(self, val: Any) -> str:
        if val is None:
            return "None"
        if isinstance(val, (int, float)):
            if isinstance(val, float):
                return f"{val:.4g}"
            return str(val)
        if isinstance(val, (list, tuple)):
            n = len(val)
            if n == 0:
                return "[]"
            if n == 1:
                return f"[{self._format_value_preview(val[0])}]"
            return f"[{n} items]"
        cls_name = val.__class__.__name__
        if cls_name == "Point3D":
            return f"Pt({val.x:.2g}, {val.y:.2g}, {val.z:.2g})"
        if cls_name == "MeshData":
            return f"Mesh(V:{len(getattr(val, 'vertices', []))})"
        if cls_name == "PolylineData":
            return f"Poly({len(getattr(val, 'points', []))}pts)"
        return str(cls_name)

    def _add_dynamic_input(self) -> None:
        if not self.current_node:
            return
        node = self.current_node
        var_ports = [p for p in node.inputs if p.name != "Expr"]
        existing_names = {p.name for p in var_ports}
        next_name = None
        for name in VARIABLE_NAMES:
            if name not in existing_names:
                next_name = name
                break
        if not next_name:
            next_name = f"v{len(var_ports)}"

        new_p = Port(node, next_name, PortType.ANY, is_input=True, default_value=0.0, description=f"Input variable {next_name}")
        expr_idx = next((i for i, port in enumerate(node.inputs) if port.name == "Expr"), len(node.inputs))
        node.inputs.insert(expr_idx, new_p)

        if self.current_node_item and hasattr(self.current_node_item, "rebuild_ports"):
            self.current_node_item.rebuild_ports()

        if self.current_scene:
            self.current_scene.notify_graph_changed()

        self.populate(self.current_node, self.current_node_item, self.current_scene)

    def _remove_input_port(self, port: Port) -> None:
        if not self.current_node or not self.current_scene:
            return
        node = self.current_node

        # Disconnect any wires attached to this port
        for conn in list(port.connections):
            self.current_scene.graph.disconnect(conn.source, conn.target)
            for wire_id, wire in list(self.current_scene.wire_items.items()):
                if wire.connection == conn:
                    if wire in self.current_scene.items():
                        self.current_scene.removeItem(wire)
                    if wire_id in self.current_scene.wire_items:
                        del self.current_scene.wire_items[wire_id]

        if port in node.inputs:
            node.inputs.remove(port)

        if self.current_node_item and hasattr(self.current_node_item, "rebuild_ports"):
            self.current_node_item.rebuild_ports()

        node.dirty = True
        self.current_scene.notify_graph_changed()
        self.populate(self.current_node, self.current_node_item, self.current_scene)
