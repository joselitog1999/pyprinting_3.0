# -*- coding: utf-8 -*-
"""
test_nanopositioning_regimes.py — Pruebas Unitarias de Cinemática y Regímenes de Coordenadas
PyPrinting 3.0 — UNSAM Nanofotónica

Verifica:
  1. Mapeo cinemático exacto en los 3 regímenes: Legacy, Laser Ref y Sample Ref.
  2. Despacho de señales de movimiento relativo por botones de interfaz y atajos de teclado.
  3. Comportamiento de salvaguarda de foco cuando se editan campos de texto (QLineEdit).
  4. Sincronización global en tiempo real entre múltiples instancias y el Tablero de Hardware.
"""
import sys
import unittest
from pathlib import Path

# Configurar entorno headless
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["PYPRINTING_SAFE"] = "1"

from PyQt6.QtWidgets import QApplication, QLineEdit
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QKeyEvent

app = QApplication.instance() or QApplication(sys.argv)

from config import (REGIME_LEGACY, REGIME_LASER_REF, REGIME_SAMPLE_REF)
from core.nanopositioning import Frontend, Backend, set_global_coordinate_regime, _ACTIVE_FRONTENDS
from modules.hardware_dashboard import HardwareDashboardWidget


class TestNanopositioningRegimes(unittest.TestCase):

    def setUp(self):
        self.frontend = Frontend()
        self.backend = Backend()
        self.frontend.make_connection(self.backend)
        self.emitted_moves = []
        self.frontend.move_signal.connect(lambda ax, dist: self.emitted_moves.append((ax, dist)))

    def tearDown(self):
        if self.frontend in _ACTIVE_FRONTENDS:
            _ACTIVE_FRONTENDS.remove(self.frontend)

    def test_legacy_regime_mapping(self):
        """Verifica que el régimen Legacy mantenga los ejes históricos: x=Eje1, y=Eje2."""
        self.frontend.set_regime(REGIME_LEGACY)
        self.frontend.StepEdit.setText("2.5")

        # 1. Derecha -> Eje 1 (x) +
        self.frontend.xUp()
        self.assertEqual(self.emitted_moves[-1], ('x', 2.5))

        # 2. Izquierda -> Eje 1 (x) -
        self.frontend.xDown()
        self.assertEqual(self.emitted_moves[-1], ('x', -2.5))

        # 3. Arriba -> Eje 2 (y) +
        self.frontend.yUp()
        self.assertEqual(self.emitted_moves[-1], ('y', 2.5))

        # 4. Abajo -> Eje 2 (y) -
        self.frontend.yDown()
        self.assertEqual(self.emitted_moves[-1], ('y', -2.5))

        # 5. Paso rápido 10x
        self.frontend.xUp2()
        self.assertEqual(self.emitted_moves[-1], ('x', 25.0))

    def test_laser_ref_regime_mapping(self):
        """
        Verifica el régimen Laser Ref:
        - Derecha (laser spot a la derecha): Eje 2 (y) +
        - Izquierda (laser spot a la izquierda): Eje 2 (y) -
        - Arriba (laser spot hacia arriba): Eje 1 (x) -
        - Abajo (laser spot hacia abajo): Eje 1 (x) +
        """
        self.frontend.set_regime(REGIME_LASER_REF)
        self.frontend.StepEdit.setText("1.0")

        # 1. Derecha
        self.frontend.move_direction("right", 1.0)
        self.assertEqual(self.emitted_moves[-1], ('y', 1.0))

        # 2. Izquierda
        self.frontend.move_direction("left", 1.0)
        self.assertEqual(self.emitted_moves[-1], ('y', -1.0))

        # 3. Arriba (spot hacia arriba requiere eje 1 -)
        self.frontend.move_direction("up", 1.0)
        self.assertEqual(self.emitted_moves[-1], ('x', -1.0))

        # 4. Abajo (spot hacia abajo requiere eje 1 +)
        self.frontend.move_direction("down", 1.0)
        self.assertEqual(self.emitted_moves[-1], ('x', 1.0))

        # 5. Botones de UI sincronizados
        self.frontend.xUp()
        self.assertEqual(self.emitted_moves[-1], ('y', 1.0))
        self.frontend.yUp()
        self.assertEqual(self.emitted_moves[-1], ('x', -1.0))

    def test_sample_ref_regime_mapping(self):
        """
        Verifica el régimen Sample Ref (opuesto a Laser Ref):
        - Derecha (muestra a la derecha): Eje 2 (y) -
        - Izquierda (muestra a la izquierda): Eje 2 (y) +
        - Arriba (muestra hacia arriba): Eje 1 (x) +
        - Abajo (muestra hacia abajo): Eje 1 (x) -
        """
        self.frontend.set_regime(REGIME_SAMPLE_REF)
        self.frontend.StepEdit.setText("1.5")

        # 1. Derecha
        self.frontend.move_direction("right", 1.0)
        self.assertEqual(self.emitted_moves[-1], ('y', -1.5))

        # 2. Izquierda
        self.frontend.move_direction("left", 1.0)
        self.assertEqual(self.emitted_moves[-1], ('y', 1.5))

        # 3. Arriba (muestra hacia arriba requiere eje 1 +)
        self.frontend.move_direction("up", 1.0)
        self.assertEqual(self.emitted_moves[-1], ('x', 1.5))

        # 4. Abajo (muestra hacia abajo requiere eje 1 -)
        self.frontend.move_direction("down", 1.0)
        self.assertEqual(self.emitted_moves[-1], ('x', -1.5))

    def test_keyboard_arrow_keys_navigation(self):
        """Verifica que las flechas del teclado desplacen exactamente 1 paso."""
        self.frontend.set_regime(REGIME_LASER_REF)
        self.frontend.StepEdit.setText("1.0")

        # Simular Key_Right -> Laser Derecha -> ('y', 1.0)
        ev_right = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
        self.frontend.keyPressEvent(ev_right)
        self.assertEqual(self.emitted_moves[-1], ('y', 1.0))

        # Simular Key_Up -> Laser Arriba -> ('x', -1.0)
        ev_up = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier)
        self.frontend.keyPressEvent(ev_up)
        self.assertEqual(self.emitted_moves[-1], ('x', -1.0))

        # Simular Shift + Key_Left -> Laser Izquierda 10x -> ('y', -10.0)
        ev_shift_left = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.ShiftModifier)
        self.frontend.keyPressEvent(ev_shift_left)
        self.assertEqual(self.emitted_moves[-1], ('y', -10.0))

    def test_focus_safeguard_when_editing_text(self):
        """Verifica que si un QLineEdit tiene foco, las flechas no muevan la platina."""
        self.frontend.set_regime(REGIME_LASER_REF)
        self.frontend.StepEdit.setFocus()
        self.emitted_moves.clear()

        ev_right = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
        self.frontend.keyPressEvent(ev_right)

        # No debe haberse emitido ningún movimiento porque StepEdit tiene el foco
        self.assertEqual(len(self.emitted_moves), 0)

    def test_global_synchronization_across_instances_and_dashboard(self):
        """Verifica que al cambiar el régimen en una instancia o en el Dashboard se sincronice globalmente."""
        fe2 = Frontend()
        try:
            # Inicialmente ambos en el mismo régimen
            self.frontend.set_regime(REGIME_LEGACY)
            self.assertEqual(fe2.current_regime, REGIME_LEGACY)

            # Cambiar a Laser Ref desde frontend
            self.frontend.cmb_regime.setCurrentIndex(1)  # Laser Ref
            self.assertEqual(self.frontend.current_regime, REGIME_LASER_REF)
            self.assertEqual(fe2.current_regime, REGIME_LASER_REF)

            # Cambiar a Sample Ref mediante función global (ej. desde Dashboard)
            set_global_coordinate_regime(REGIME_SAMPLE_REF)
            self.assertEqual(self.frontend.current_regime, REGIME_SAMPLE_REF)
            self.assertEqual(fe2.current_regime, REGIME_SAMPLE_REF)
            self.assertIn("Sample", self.frontend.xUpButton.text())
            self.assertIn("Sample", fe2.xUpButton.text())

            # Verificar widget de Hardware Dashboard
            hw_dash = HardwareDashboardWidget()
            hw_dash.combo_kin_regime.setCurrentIndex(1)  # Laser Ref
            self.assertEqual(self.frontend.current_regime, REGIME_LASER_REF)
            self.assertEqual(fe2.current_regime, REGIME_LASER_REF)
        finally:
            if fe2 in _ACTIVE_FRONTENDS:
                _ACTIVE_FRONTENDS.remove(fe2)


if __name__ == "__main__":
    unittest.main()
