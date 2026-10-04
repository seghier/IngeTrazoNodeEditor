# SPDX-License-Identifier: GPL-3.0-or-later
"""Node graphics item and port sockets with embedded interactive widgets."""
from __future__ import annotations

from typing import List, Optional, Any
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
)
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsObject, QGraphicsProxyWidget,
    QSlider, QDoubleSpinBox, QCheckBox, QLineEdit, QPlainTextEdit, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton
)

from ..engine import NodeBase, Port, PortType


class PortItem(QGraphicsItem):
    """Circular socket for a single Port."""

    RADIUS = 6.0

    def __init__(self, port: Port, parent: NodeItem):
        super().__init__(parent)
        self.port = port
        self.node_item = parent
        self.setAcceptHoverEvents(True)
        self.is_hovered = False
        color_hex = port.get_color()
        self.brush = QBrush(QColor(color_hex))
        self.pen = QPen(QColor("#1e1e1e"), 1.5)

    def boundingRect(self) -> QRectF:
        r = self.RADIUS + 3.0
        return QRectF(-r, -r, 2 * r, 2 * r)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing)
        if self.is_hovered:
            painter.setBrush(QBrush(QColor("#ffffff")))
            painter.setPen(QPen(QColor(self.port.get_color()), 2.0))
        else:
            painter.setBrush(self.brush)
            painter.setPen(self.pen)

        painter.drawEllipse(QPointF(0, 0), self.RADIUS, self.RADIUS)

    def hoverEnterEvent(self, event) -> None:
        self.is_hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self.is_hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.scene().start_wire_drag(self)
            event.accept()
        else:
            super().mousePressEvent(event)


class NodeItem(QGraphicsObject):
    """Visual card for a NodeBase."""

    HEADER_HEIGHT = 28.0
    CORNER_RADIUS = 7.0
    ROW_HEIGHT = 22.0
    MIN_WIDTH = 150.0

    def __init__(self, node: NodeBase):
        super().__init__()
        self.node = node
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemIsSelectable |
            QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)

        self.input_ports: List[PortItem] = []
        self.output_ports: List[PortItem] = []
        self.widget_proxy: Optional[QGraphicsProxyWidget] = None
        self.slider_widget: Optional[QSlider] = None
        self.spin_widget: Optional[QDoubleSpinBox] = None
        self.expr_line_edit: Optional[QLineEdit] = None
        self.panel_pte: Optional[QPlainTextEdit] = None
        self.update_preview_pix: Optional[Any] = None
        self.width = self.MIN_WIDTH
        self.height = 80.0

        self.setPos(node.x, node.y)
        self.build_ui()

    def build_ui(self) -> None:
        # Determine height based on port count and widgets
        port_rows = max(len(self.node.inputs), len(self.node.outputs))
        content_height = max(30.0, port_rows * self.ROW_HEIGHT)

        # Check if node has embedded widget
        has_widget = self.has_custom_widget()
        if has_widget:
            t_name = self.node.__class__.__name__
            if t_name == "PanelNode":
                content_height += 124.0
                self.width = max(self.width, 220.0)
            elif t_name == "ReferenceFaceNode":
                content_height += 62.0
                self.width = max(self.width, 210.0)
            elif t_name == "ImageFileNode":
                content_height += 36.0
                self.width = max(self.width, 180.0)
            elif t_name == "ImagePreviewNode":
                content_height += 106.0
                self.width = max(self.width, 210.0)
            elif t_name == "ImageSamplerNode":
                content_height += 136.0
                self.width = max(self.width, 210.0)
            else:
                content_height += 44.0
                self.width = max(self.width, 220.0 if t_name == "ExpressionNode" else 210.0)

        self.height = self.HEADER_HEIGHT + content_height + 10.0

        # Create input port items (left side)
        y_cursor = self.HEADER_HEIGHT + 14.0
        for port in self.node.inputs:
            pi = PortItem(port, self)
            pi.setPos(0, y_cursor)
            self.input_ports.append(pi)
            y_cursor += self.ROW_HEIGHT

        # Create output port items (right side)
        y_cursor = self.HEADER_HEIGHT + 14.0
        for port in self.node.outputs:
            pi = PortItem(port, self)
            pi.setPos(self.width, y_cursor)
            self.output_ports.append(pi)
            y_cursor += self.ROW_HEIGHT

        # Add embedded interactive widget if applicable
        if has_widget:
            self.add_embedded_widget()

    def has_custom_widget(self) -> bool:
        t = self.node.__class__.__name__
        return t in (
            "NumberSliderNode", "IntegerSliderNode", "ToggleNode",
            "StringNode", "ExpressionNode", "PanelNode", "ReferenceFaceNode",
            "ImageFileNode", "ImagePreviewNode", "ImageSamplerNode"
        )

    def add_embedded_widget(self) -> None:
        t = self.node.__class__.__name__
        proxy = QGraphicsProxyWidget(self)

        container = QWidget()
        container.setStyleSheet("background: transparent;")

        if t in ("NumberSliderNode", "IntegerSliderNode"):
            is_int = (t == "IntegerSliderNode")
            min_val = float(self.node.widget_values.get("min", 0.0))
            max_val = float(self.node.widget_values.get("max", 50.0 if not is_int else 100.0))
            cur_val = float(self.node.widget_values.get("value", 5.0 if not is_int else 10))

            layout = QHBoxLayout(container)
            layout.setContentsMargins(10, 2, 10, 2)
            layout.setSpacing(6)

            slider = QSlider(Qt.Horizontal)
            slider.setMinimum(0)
            steps = int(round(max_val - min_val)) if is_int else 1000
            slider.setMaximum(max(1, steps))

            if is_int:
                initial_tick = int(round(cur_val - min_val))
            else:
                ratio = (cur_val - min_val) / (max_val - min_val) if max_val > min_val else 0.0
                initial_tick = int(round(ratio * 1000))
            slider.setValue(max(0, min(steps, initial_tick)))

            spin = QDoubleSpinBox()
            spin.setDecimals(0 if is_int else 2)
            spin.setRange(min_val, max_val)
            spin.setSingleStep(1.0 if is_int else 0.1)
            spin.setValue(cur_val)
            spin.setFixedWidth(56)

            slider.setStyleSheet("""
                QSlider::groove:horizontal {
                    height: 5px;
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
                    width: 14px;
                    height: 14px;
                    margin: -5px 0;
                    border-radius: 7px;
                }
                QSlider::handle:horizontal:hover {
                    background: #ffffff;
                    border: 1px solid #4fc1ff;
                }
            """)

            spin.setStyleSheet("""
                QDoubleSpinBox {
                    background: #252830;
                    color: #eceff4;
                    border: 1px solid #434c5e;
                    border-radius: 4px;
                    padding: 2px 2px 2px 4px;
                    font-size: 11px;
                }
                QDoubleSpinBox::up-button {
                    subcontrol-origin: border;
                    subcontrol-position: top right;
                    width: 15px;
                    background: #2e3440;
                    border-left: 1px solid #434c5e;
                    border-bottom: 1px solid #3b4252;
                }
                QDoubleSpinBox::down-button {
                    subcontrol-origin: border;
                    subcontrol-position: bottom right;
                    width: 15px;
                    background: #2e3440;
                    border-left: 1px solid #434c5e;
                }
                QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
                    background: #4c566a;
                }
                QDoubleSpinBox::up-arrow {
                    width: 0;
                    height: 0;
                    border-left: 3px solid transparent;
                    border-right: 3px solid transparent;
                    border-bottom: 4px solid #ffffff;
                }
                QDoubleSpinBox::down-arrow {
                    width: 0;
                    height: 0;
                    border-left: 3px solid transparent;
                    border-right: 3px solid transparent;
                    border-top: 4px solid #ffffff;
                }
            """)

            syncing = [False]

            def on_slider_moved(val):
                if syncing[0]:
                    return
                syncing[0] = True
                cur_min = float(self.node.widget_values.get("min", 0.0))
                cur_max = float(self.node.widget_values.get("max", 50.0 if not is_int else 100.0))
                if is_int:
                    num = int(round(cur_min + val))
                else:
                    max_ticks = float(slider.maximum()) or 1000.0
                    ratio = val / max_ticks
                    num = cur_min + ratio * (cur_max - cur_min)
                spin.setValue(num)
                self.node.widget_values["value"] = int(num) if is_int else float(num)
                self.node.dirty = True
                if self.scene():
                    self.scene().notify_graph_changed()
                syncing[0] = False

            def on_spin_changed(num):
                if syncing[0]:
                    return
                syncing[0] = True
                cur_min = float(self.node.widget_values.get("min", 0.0))
                cur_max = float(self.node.widget_values.get("max", 50.0 if not is_int else 100.0))
                steps_now = int(round(cur_max - cur_min)) if is_int else 1000
                slider.setMaximum(max(1, steps_now))
                if is_int:
                    tick = int(round(num - cur_min))
                else:
                    ratio = (num - cur_min) / (cur_max - cur_min) if cur_max > cur_min else 0.0
                    tick = int(round(ratio * 1000))
                slider.setValue(max(0, min(steps_now, tick)))
                self.node.widget_values["value"] = int(num) if is_int else float(num)
                self.node.dirty = True
                if self.scene():
                    self.scene().notify_graph_changed()
                syncing[0] = False

            slider.valueChanged.connect(on_slider_moved)
            spin.valueChanged.connect(on_spin_changed)

            self.slider_widget = slider
            self.spin_widget = spin

            layout.addWidget(slider, 1)
            layout.addWidget(spin, 0)

        elif t == "ToggleNode":
            layout = QHBoxLayout(container)
            layout.setContentsMargins(10, 0, 10, 0)
            layout.setSpacing(6)
            cb = QCheckBox("Active")
            cb.setChecked(bool(self.node.widget_values.get("value", True)))
            cb.setStyleSheet("color: #eceff4; font-size: 11px;")

            def on_toggle(checked):
                self.node.widget_values["value"] = checked
                self.node.dirty = True
                if self.scene():
                    self.scene().notify_graph_changed()

            cb.toggled.connect(on_toggle)
            layout.addWidget(cb)

        elif t == "StringNode":
            layout = QHBoxLayout(container)
            layout.setContentsMargins(10, 0, 10, 0)
            layout.setSpacing(6)
            le = QLineEdit(str(self.node.widget_values.get("value", "")))
            le.setStyleSheet("""
                QLineEdit {
                    background: #252830;
                    color: #eceff4;
                    border: 1px solid #434c5e;
                    border-radius: 4px;
                    padding: 2px 6px;
                    font-size: 11px;
                }
            """)

            def on_text(txt):
                self.node.widget_values["value"] = txt
                self.node.dirty = True
                if self.scene():
                    self.scene().notify_graph_changed()

            le.textChanged.connect(on_text)
            layout.addWidget(le)

        elif t == "ExpressionNode":
            layout = QHBoxLayout(container)
            layout.setContentsMargins(8, 0, 8, 0)
            layout.setSpacing(4)
            cur_expr = str(self.node.widget_values.get("expr", "x + y"))
            le = QLineEdit(cur_expr)
            le.setPlaceholderText("e.g. sin(x)*cos(y)")
            le.setStyleSheet("""
                QLineEdit {
                    background: #181a20;
                    color: #56b6c2;
                    border: 1px solid #434c5e;
                    border-radius: 4px;
                    padding: 2px 6px;
                    font-family: Consolas, 'Courier New', monospace;
                    font-size: 11px;
                    font-weight: bold;
                }
                QLineEdit:focus {
                    border: 1px solid #88c0d0;
                    background: #1e222b;
                }
            """)

            def on_expr_changed(txt):
                self.node.widget_values["expr"] = txt
                self.node.dirty = True
                if hasattr(self.node, "sync_dynamic_ports"):
                    if self.node.sync_dynamic_ports():
                        self.rebuild_ports()
                if self.scene():
                    self.scene().notify_graph_changed()

            self.expr_line_edit = le
            le.textChanged.connect(on_expr_changed)
            layout.addWidget(le)

        elif t == "PanelNode":
            layout = QVBoxLayout(container)
            layout.setContentsMargins(6, 0, 6, 4)
            layout.setSpacing(0)

            pte = QPlainTextEdit()
            pte.setPlaceholderText("// Double-click or type data...\n// or connect wire to view data")
            pte.setStyleSheet("""
                QPlainTextEdit {
                    background: #181a20;
                    color: #d8dee9;
                    border: 1px solid #3b4252;
                    border-radius: 4px;
                    padding: 4px 6px;
                    font-family: Consolas, 'Courier New', monospace;
                    font-size: 11px;
                    selection-background-color: #3b4252;
                    selection-color: #88c0d0;
                }
                QPlainTextEdit:focus {
                    border: 1px solid #88c0d0;
                }
                QScrollBar:vertical {
                    background: #181a20;
                    width: 10px;
                    margin: 0px;
                }
                QScrollBar::handle:vertical {
                    background: #3b4252;
                    min-height: 20px;
                    border-radius: 3px;
                }
                QScrollBar::handle:vertical:hover {
                    background: #4c566a;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
            """)

            # Load initial content
            init_val = self.node.widget_values.get("display") or self.node.widget_values.get("text") or ""
            pte.setPlainText(str(init_val))

            is_connected = self.node.inputs[0].has_connection if self.node.inputs else False
            pte.setReadOnly(is_connected)

            syncing = [False]

            def on_panel_text():
                if syncing[0]:
                    return
                if self.node.inputs and self.node.inputs[0].has_connection:
                    return
                syncing[0] = True
                txt = pte.toPlainText()
                self.node.widget_values["text"] = txt
                self.node.widget_values["display"] = txt
                self.node.dirty = True
                if self.scene():
                    self.scene().notify_graph_changed()
                syncing[0] = False

            def update_panel_ui(text_val: str):
                if syncing[0]:
                    return
                syncing[0] = True
                conn = self.node.inputs[0].has_connection if self.node.inputs else False
                pte.setReadOnly(conn)
                if pte.toPlainText() != text_val:
                    sb = pte.verticalScrollBar()
                    pos = sb.value() if sb else 0
                    pte.setPlainText(text_val)
                    if sb:
                        sb.setValue(pos)
                syncing[0] = False

            self.node.on_display_updated = update_panel_ui
            self.panel_pte = pte
            pte.textChanged.connect(on_panel_text)
            layout.addWidget(pte)

        elif t == "ReferenceFaceNode":
            layout = QVBoxLayout(container)
            layout.setContentsMargins(8, 0, 8, 4)
            layout.setSpacing(3)

            btn = QPushButton("📌 Set Selected Face")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: #3b4252;
                    color: #eceff4;
                    border: 1px solid #4c566a;
                    border-radius: 4px;
                    padding: 3px 6px;
                    font-size: 11px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #434c5e;
                    border: 1px solid #88c0d0;
                    color: #88c0d0;
                }
                QPushButton:pressed {
                    background: #2e3440;
                }
            """)

            saved_ref = self.node.widget_values.get("referenced_face")
            init_txt = f"Saved: {saved_ref.get('summary', '')}" if saved_ref else "No face stored (Click to set)"
            lbl_status = QLabel(init_txt)
            lbl_status.setAlignment(Qt.AlignCenter)
            lbl_status.setStyleSheet("color: #a3be8c; font-size: 10px; font-weight: bold;" if saved_ref else "color: #d8dee9; font-size: 10px; font-style: italic;")

            def on_pick():
                app = getattr(self.scene(), "app", None)
                if not app:
                    from PySide6.QtWidgets import QApplication
                    app = getattr(QApplication.instance(), "_extension_app_handle", None)
                msg, ok = self.node.reference_from_selection(app)
                lbl_status.setText(msg)
                if ok:
                    lbl_status.setStyleSheet("color: #a3be8c; font-size: 10px; font-weight: bold;")
                else:
                    lbl_status.setStyleSheet("color: #ebcb8b; font-size: 10px;")
                self.node.dirty = True
                if self.scene():
                    self.scene().notify_graph_changed()

            btn.clicked.connect(on_pick)
            layout.addWidget(btn)
            layout.addWidget(lbl_status)

        elif t == "ImageFileNode":
            layout = QVBoxLayout(container)
            layout.setContentsMargins(8, 0, 8, 4)
            layout.setSpacing(0)
            saved_p = self.node.widget_values.get("image_path", "")
            btn = QPushButton("📂 Change Image..." if saved_p else "📂 Open Image...")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: #434c5e; color: #eceff4; border: 1px solid #4c566a;
                    border-radius: 4px; padding: 4px 6px; font-size: 11px; font-weight: bold;
                }
                QPushButton:hover { background: #4c566a; border-color: #88c0d0; color: #88c0d0; }
                QPushButton:pressed { background: #2e3440; }
            """)

            def on_browse_file():
                from PySide6.QtWidgets import QFileDialog
                path, _ = QFileDialog.getOpenFileName(
                    None, "Select Image File", "",
                    "Images (*.png *.jpg *.jpeg *.bmp *.webp *.tif);;All Files (*.*)"
                )
                if path:
                    self.node.widget_values["image_path"] = path
                    btn.setText("📂 Change Image...")
                    self.node.dirty = True
                    if self.scene():
                        self.scene().notify_graph_changed()

            btn.clicked.connect(on_browse_file)
            layout.addWidget(btn)

        elif t in ("ImagePreviewNode", "ImageSamplerNode"):
            layout = QVBoxLayout(container)
            layout.setContentsMargins(8, 0, 8, 4)
            layout.setSpacing(3)
            if t == "ImageSamplerNode":
                row_btns = QHBoxLayout()
                row_btns.setSpacing(4)
                btn_open = QPushButton("📂 Open...")
                btn_open.setCursor(Qt.PointingHandCursor)
                btn_open.setStyleSheet("""
                    QPushButton {
                        background: #434c5e; color: #eceff4; border: 1px solid #4c566a;
                        border-radius: 4px; padding: 3px 6px; font-size: 10px; font-weight: bold;
                    }
                    QPushButton:hover { background: #4c566a; border-color: #88c0d0; color: #88c0d0; }
                """)
                btn_inv = QPushButton("⇅ Invert")
                btn_inv.setCursor(Qt.PointingHandCursor)
                btn_inv.setCheckable(True)
                btn_inv.setChecked(bool(self.node.widget_values.get("invert", False)))
                btn_inv.setStyleSheet("""
                    QPushButton {
                        background: #3b4252; color: #eceff4; border: 1px solid #4c566a;
                        border-radius: 4px; padding: 3px 6px; font-size: 10px;
                    }
                    QPushButton:checked { background: #88c0d0; color: #1e222b; font-weight: bold; }
                    QPushButton:hover { border-color: #88c0d0; }
                """)
                row_btns.addWidget(btn_open, 1)
                row_btns.addWidget(btn_inv, 1)
                layout.addLayout(row_btns)

            lbl_pix = QLabel()
            lbl_pix.setAlignment(Qt.AlignCenter)
            lbl_pix.setFixedSize(int(self.width - 24), 78)
            lbl_pix.setStyleSheet("background: #181a20; border: 1px solid #3b4252; border-radius: 4px; color: #4c566a; font-size: 10px;")

            def update_preview_pix():
                import os
                from PySide6.QtGui import QImage, QPixmap
                qimg = self.node.widget_values.get("_cached_qimage")
                if (qimg is None or (hasattr(qimg, "isNull") and qimg.isNull())) and hasattr(self.node, "get_input"):
                    inp = self.node.get_input("Image", None)
                    if hasattr(inp, "pixelColor") and not inp.isNull():
                        qimg = inp
                    elif isinstance(inp, str) and inp and os.path.exists(inp):
                        qimg = QImage(inp)
                if qimg is None or (hasattr(qimg, "isNull") and qimg.isNull()):
                    p = self.node.widget_values.get("image_path", "")
                    if p and os.path.exists(p):
                        qimg = QImage(p)

                if qimg and not qimg.isNull():
                    pix = QPixmap.fromImage(qimg).scaled(lbl_pix.width() - 4, lbl_pix.height() - 4, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    lbl_pix.setPixmap(pix)
                    lbl_pix.setText("")
                else:
                    lbl_pix.setPixmap(QPixmap())
                    lbl_pix.setText("No Image Loaded")

            self.update_preview_pix = update_preview_pix
            self.node.on_display_updated = update_preview_pix
            update_preview_pix()
            layout.addWidget(lbl_pix)

            if t == "ImageSamplerNode":
                def on_sampler_browse():
                    from PySide6.QtWidgets import QFileDialog
                    path, _ = QFileDialog.getOpenFileName(
                        None, "Select Image", "",
                        "Images (*.png *.jpg *.jpeg *.bmp *.webp *.tif);;All Files (*.*)"
                    )
                    if path:
                        self.node.widget_values["image_path"] = path
                        update_preview_pix()
                        self.node.dirty = True
                        if self.scene():
                            self.scene().notify_graph_changed()

                def on_sampler_inv():
                    self.node.widget_values["invert"] = btn_inv.isChecked()
                    self.node.dirty = True
                    if self.scene():
                        self.scene().notify_graph_changed()

                btn_open.clicked.connect(on_sampler_browse)
                btn_inv.clicked.connect(on_sampler_inv)

        self.widget_proxy = proxy
        proxy.setWidget(container)
        if t == "PanelNode":
            widget_y = self.HEADER_HEIGHT + self.ROW_HEIGHT + 6.0
            widget_h = self.height - widget_y - 8.0
            proxy.setPos(0, widget_y)
            proxy.resize(self.width, max(40.0, widget_h))
        elif t == "ReferenceFaceNode":
            widget_y = self.height - 58.0
            proxy.setPos(0, widget_y)
            proxy.resize(self.width, 52.0)
        elif t == "ImageFileNode":
            widget_y = self.height - 38.0
            proxy.setPos(0, widget_y)
            proxy.resize(self.width, 32.0)
        elif t == "ImagePreviewNode":
            widget_y = self.height - 98.0
            proxy.setPos(0, widget_y)
            proxy.resize(self.width, 90.0)
        elif t == "ImageSamplerNode":
            widget_y = self.height - 128.0
            proxy.setPos(0, widget_y)
            proxy.resize(self.width, 120.0)
        else:
            widget_y = self.height - 38.0
            proxy.setPos(0, widget_y)
            proxy.resize(self.width, 32.0)

    def rebuild_ports(self) -> None:
        """Dynamically rebuild port items when dynamic ports change (e.g. ExpressionNode)."""
        # Unparent and remove old port items
        for pi in self.input_ports:
            pi.setParentItem(None)
            if self.scene():
                self.scene().removeItem(pi)
        for pi in self.output_ports:
            pi.setParentItem(None)
            if self.scene():
                self.scene().removeItem(pi)
        self.input_ports.clear()
        self.output_ports.clear()

        # Recalculate dimensions
        port_rows = max(len(self.node.inputs), len(self.node.outputs))
        content_height = max(30.0, port_rows * self.ROW_HEIGHT)
        has_widget = self.has_custom_widget()
        if has_widget:
            t_name = self.node.__class__.__name__
            if t_name == "PanelNode":
                content_height += 124.0
                self.width = max(self.width, 220.0)
            else:
                content_height += 44.0
                self.width = max(self.width, 220.0 if t_name == "ExpressionNode" else 210.0)

        self.prepareGeometryChange()
        self.height = self.HEADER_HEIGHT + content_height + 10.0

        # Re-create input port items (left side)
        y_cursor = self.HEADER_HEIGHT + 14.0
        for port in self.node.inputs:
            pi = PortItem(port, self)
            pi.setPos(0, y_cursor)
            self.input_ports.append(pi)
            y_cursor += self.ROW_HEIGHT

        # Re-create output port items (right side)
        y_cursor = self.HEADER_HEIGHT + 14.0
        for port in self.node.outputs:
            pi = PortItem(port, self)
            pi.setPos(self.width, y_cursor)
            self.output_ports.append(pi)
            y_cursor += self.ROW_HEIGHT

        # Reposition embedded widget if present
        proxy = self.widget_proxy
        if proxy is None:
            for child in self.childItems():
                if isinstance(child, QGraphicsProxyWidget):
                    proxy = child
                    break

        if proxy is not None:
            t_name = self.node.__class__.__name__
            if t_name == "PanelNode":
                widget_y = self.HEADER_HEIGHT + self.ROW_HEIGHT + 6.0
                widget_h = self.height - widget_y - 8.0
                proxy.setPos(0, widget_y)
                proxy.resize(self.width, max(40.0, widget_h))
            else:
                widget_y = self.height - 38.0
                proxy.setPos(0, widget_y)
                proxy.resize(self.width, 32.0)

        # Update paths of connected wires
        if self.scene() and hasattr(self.scene(), "wire_items"):
            for wire in self.scene().wire_items.values():
                if wire.connection.source.node == self.node:
                    wire.source_item = self.scene().find_port_item(wire.connection.source)
                    wire.update_path()
                elif wire.connection.target.node == self.node:
                    wire.target_item = self.scene().find_port_item(wire.connection.target)
                    wire.update_path()

        self.update()

    def update_slider_range(self) -> None:
        """Called when min/max/decimals/value is edited from the inspector panel."""
        if hasattr(self, "spin_widget") and self.spin_widget and hasattr(self, "slider_widget") and self.slider_widget:
            t = self.node.__class__.__name__
            is_int = (t == "IntegerSliderNode")
            min_val = float(self.node.widget_values.get("min", 0.0))
            max_val = float(self.node.widget_values.get("max", 50.0 if not is_int else 100.0))
            cur_val = float(self.node.widget_values.get("value", 5.0 if not is_int else 10))
            decimals = int(self.node.widget_values.get("decimals", 2 if not is_int else 0))

            cur_val = min(max_val, max(min_val, cur_val))
            self.node.widget_values["value"] = int(round(cur_val)) if is_int else cur_val

            self.spin_widget.blockSignals(True)
            self.slider_widget.blockSignals(True)

            self.spin_widget.setDecimals(decimals)
            self.spin_widget.setRange(min_val, max_val)
            self.spin_widget.setValue(cur_val)

            steps = int(round(max_val - min_val)) if is_int else 1000
            self.slider_widget.setMaximum(max(1, steps))
            if is_int:
                tick = int(round(cur_val - min_val))
            else:
                ratio = (cur_val - min_val) / (max_val - min_val) if max_val > min_val else 0.0
                tick = int(round(ratio * 1000))
            self.slider_widget.setValue(max(0, min(steps, tick)))

            self.spin_widget.blockSignals(False)
            self.slider_widget.blockSignals(False)

    def update_expression_text(self, text: str) -> None:
        """Called when expression is edited from the inspector panel."""
        if hasattr(self, "expr_line_edit") and self.expr_line_edit:
            if self.expr_line_edit.text() != text:
                self.expr_line_edit.blockSignals(True)
                self.expr_line_edit.setText(text)
                self.expr_line_edit.blockSignals(False)

    def update_panel_content(self, text: str) -> None:
        """Called when panel content is edited from the inspector panel."""
        if hasattr(self, "panel_pte") and self.panel_pte:
            if self.panel_pte.toPlainText() != text:
                self.panel_pte.blockSignals(True)
                self.panel_pte.setPlainText(text)
                self.panel_pte.blockSignals(False)


    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.width, self.height)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing)

        # Background card
        rect = self.boundingRect()
        bg_path = QPainterPath()
        bg_path.addRoundedRect(rect, self.CORNER_RADIUS, self.CORNER_RADIUS)

        # Card shadow & fill
        card_color = QColor("#1e222b")
        if self.isSelected():
            painter.setPen(QPen(QColor("#88c0d0"), 2.0))
        elif self.node.error:
            painter.setPen(QPen(QColor("#bf616a"), 2.0))
            err_tip = f"❌ {self.node.error}"
            if self.toolTip() != err_tip:
                self.setToolTip(err_tip)
        else:
            painter.setPen(QPen(QColor("#333842"), 1.2))
            desc_tip = self.node.description or self.node.name
            if self.toolTip() != desc_tip:
                self.setToolTip(desc_tip)

        painter.setBrush(QBrush(card_color))
        painter.drawPath(bg_path)

        # Header bar
        header_rect = QRectF(0, 0, self.width, self.HEADER_HEIGHT)
        header_path = QPainterPath()
        header_path.addRoundedRect(rect, self.CORNER_RADIUS, self.CORNER_RADIUS)
        header_clip = QPainterPath()
        header_clip.addRect(header_rect)
        final_header = header_path.intersected(header_clip)

        header_brush = QBrush(QColor(self.node.header_color))
        painter.setPen(Qt.NoPen)
        painter.setBrush(header_brush)
        painter.drawPath(final_header)

        # Header Title
        painter.setPen(QPen(QColor("#ffffff")))
        font = QFont("Segoe UI", 9, QFont.Bold)
        painter.setFont(font)
        painter.drawText(QRectF(10, 0, self.width - 20, self.HEADER_HEIGHT), Qt.AlignVCenter | Qt.AlignLeft, self.node.name)

        # Port Labels
        port_font = QFont("Segoe UI", 8)
        painter.setFont(port_font)
        painter.setPen(QPen(QColor("#abb2bf")))

        # Input labels (left)
        y_cur = self.HEADER_HEIGHT + 7.0
        for port in self.node.inputs:
            painter.drawText(QRectF(12, y_cur, self.width * 0.5, self.ROW_HEIGHT), Qt.AlignVCenter | Qt.AlignLeft, port.name)
            y_cur += self.ROW_HEIGHT

        # Output labels (right)
        y_cur = self.HEADER_HEIGHT + 7.0
        for port in self.node.outputs:
            painter.drawText(QRectF(self.width * 0.5 - 12, y_cur, self.width * 0.5, self.ROW_HEIGHT), Qt.AlignVCenter | Qt.AlignRight, port.name)
            y_cur += self.ROW_HEIGHT

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            new_pos = value
            self.node.x = new_pos.x()
            self.node.y = new_pos.y()
            if hasattr(self.scene(), "update_connected_wires"):
                self.scene().update_connected_wires(self)
        return super().itemChange(change, value)
