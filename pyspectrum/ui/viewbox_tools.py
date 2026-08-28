# -*- coding: utf-8 -*-
"""
viewbox_tools.py — Herramientas de visualización y overlays para PyQt6 & PyQtGraph
PySpectrum 3.0 — UNSAM Nanofotónica
"""
from __future__ import annotations
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg


class LinePlotWidget(QtWidgets.QWidget):
    """Widget de trazado genérico para perfiles espectrales o temporales."""

    def __init__(self, title: str = "Perfil", x_label: str = "X", y_label: str = "Y", parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.graphics_layout = pg.GraphicsLayoutWidget()
        self.plot_item = self.graphics_layout.addPlot(row=0, col=0, title=title)
        self.plot_item.setLabels(bottom=x_label, left=y_label)
        self.plot_item.showGrid(x=True, y=True, alpha=0.3)
        self.curve = self.plot_item.plot(pen=pg.mkPen("#89B4FA", width=1.8))

        layout.addWidget(self.graphics_layout)

    def set_data(self, x: np.ndarray, y: np.ndarray, pen_color: str = "#89B4FA"):
        self.curve.setData(x, y, pen=pg.mkPen(pen_color, width=1.8))


class GridOverlay:
    """Retícula y círculos concéntricos para centrado de haz en el ViewBox."""

    def __init__(self, view_box, shape=(1002, 1002)):
        self.showed = False
        self.vb = view_box
        self.shape = shape

        pen_dot = pg.mkPen(color=(249, 226, 175), width=1.2, style=QtCore.Qt.PenStyle.DotLine)
        pen_solid = pg.mkPen(color=(249, 226, 175), width=1.0, style=QtCore.Qt.PenStyle.SolidLine)

        self.y_line = pg.InfiniteLine(pen=pen_solid)
        self.x_line = pg.InfiniteLine(pen=pen_solid, angle=0)
        self.rect0 = QtWidgets.QGraphicsRectItem()
        self.rect0.setPen(pen_dot)
        self.rect1 = QtWidgets.QGraphicsRectItem()
        self.rect1.setPen(pen_dot)
        self.circle = QtWidgets.QGraphicsEllipseItem()
        self.circle.setPen(pen_dot)

        self.update(self.shape)

    def update(self, shape):
        cx, cy = 0.5 * shape[0], 0.5 * shape[1]
        self.y_line.setPos(cx)
        self.x_line.setPos(cy)
        self.rect0.setRect(cx - 41, cy - 41, 82, 82)
        self.rect1.setRect(cx - 64, cy - 64, 128, 128)
        self.circle.setRect(cx - 100, cy - 100, 200, 200)

    def toggle(self):
        if self.showed:
            self.hide()
        else:
            self.show()

    def show(self):
        self.vb.addItem(self.x_line)
        self.vb.addItem(self.y_line)
        self.vb.addItem(self.rect0)
        self.vb.addItem(self.rect1)
        self.vb.addItem(self.circle)
        self.showed = True

    def hide(self):
        self.vb.removeItem(self.x_line)
        self.vb.removeItem(self.y_line)
        self.vb.removeItem(self.rect0)
        self.vb.removeItem(self.rect1)
        self.vb.removeItem(self.circle)
        self.showed = False
