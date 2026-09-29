# -*- coding: utf-8 -*-
"""
offset_write_dialog.py — Diálogo de escritura de un offset de red (paso 10, Ronda 3 §1.7, DEC-040)

Conduce la máquina de estados de `OffsetWriteTransaction` y **no decide nada por su cuenta**: cada botón es
una transición y el diálogo sólo muestra el estado que devuelve la transacción.

Páginas:
- **Leer:** automática al abrir.
- **Diferencias:** 1.ª confirmación.
- **Respaldo:** automática.
- **Escribir:** 2.ª confirmación tecleando el número de líneas de la red, y 3.ª si |Δ| > 50 pasos.
- **Resultado.**

Es un modal permitido (acción rara, con costo: Solis y el legado ven el valor, y puede girar la torreta).
Lleva su propio botón E-STOP (H-01) y ningún botón por defecto (H-23). No hay campo para teclear un offset
arbitrario: el valor viene de una propuesta o del respaldo (R4-B-1). Con NO COINCIDE, DESCONOCIDO o
ESCRITURA FALLIDA la única salida es "Volver al valor del respaldo", una transacción nueva (R4-D-3).
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from PyQt6 import QtCore, QtWidgets

from pyspectrum.calibration.offset_transaction import OffsetWriteTransaction, TxState

_GREEN, _RED, _YELLOW, _TEXT = "#a6e3a1", "#f38ba8", "#f9e2af", "#a6adc8"
_PAGES = ("read", "diff", "write", "result")
_HW_LABEL = {
    TxState.CONFIRMED: ("CONFIRMADO", _GREEN),
    TxState.MISMATCH: ("NO COINCIDE", _RED),
    TxState.READBACK_FAILED: ("DESCONOCIDO", _RED),
    TxState.WRITE_FAILED: ("ESCRITURA FALLIDA", _RED),
}


class OffsetWriteDialog(QtWidgets.QDialog):
    def __init__(self, transaction_factory: Callable[[], OffsetWriteTransaction], *,
                 estop_callback: Optional[Callable[[], None]] = None,
                 clock: Callable[[], float] = time.monotonic, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Escribir offset en el Shamrock")
        self.setModal(True)
        self.setMinimumSize(560, 420)
        self._estop = estop_callback
        self._clock = clock
        self._page_since = clock()
        self.transaction: OffsetWriteTransaction = transaction_factory()
        self._build_ui()
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._read()

    # ── UI ──
    def _button(self, text: str) -> QtWidgets.QPushButton:
        b = QtWidgets.QPushButton(text)
        b.setAutoDefault(False)
        b.setDefault(False)
        return b

    def _build_ui(self):
        lo = QtWidgets.QVBoxLayout(self)
        top = QtWidgets.QHBoxLayout()
        self.lbl_steps = QtWidgets.QLabel("")
        top.addWidget(self.lbl_steps, 1)
        self.btn_estop = self._button("🚨 E-STOP")
        self.btn_estop.setStyleSheet("background-color: #f38ba8; color: #11111b; font-weight: bold;")
        self.btn_estop.setToolTip("Parada de emergencia: cierra obturadores, aborta la cámara y pone la ganancia EM en 0.")
        self.btn_estop.clicked.connect(self._on_estop)
        top.addWidget(self.btn_estop)
        lo.addLayout(top)

        self.stack = QtWidgets.QStackedWidget()
        lo.addWidget(self.stack, 1)

        # Página "read": falla de lectura
        p_read = QtWidgets.QWidget()
        pl = QtWidgets.QVBoxLayout(p_read)
        self.lbl_read = QtWidgets.QLabel("")
        self.lbl_read.setWordWrap(True)
        pl.addWidget(self.lbl_read)
        pl.addStretch()
        self.stack.addWidget(p_read)

        # Página "diff"
        p_diff = QtWidgets.QWidget()
        dl = QtWidgets.QVBoxLayout(p_diff)
        self.lbl_diff = QtWidgets.QLabel("")
        self.lbl_diff.setWordWrap(True)
        self.lbl_diff.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        dl.addWidget(self.lbl_diff)
        dl.addStretch()
        row = QtWidgets.QHBoxLayout()
        row.addStretch()
        self.btn_cancel = self._button("Cancelar")
        self.btn_cancel.clicked.connect(self._on_cancel)
        row.addWidget(self.btn_cancel)
        self.btn_confirm_diff = self._button("Confirmo estas diferencias →")
        self.btn_confirm_diff.clicked.connect(self._on_confirm_diff)
        row.addWidget(self.btn_confirm_diff)
        dl.addLayout(row)
        self.stack.addWidget(p_diff)

        # Página "write"
        p_write = QtWidgets.QWidget()
        wl = QtWidgets.QVBoxLayout(p_write)
        self.lbl_backup = QtWidgets.QLabel("")
        self.lbl_backup.setWordWrap(True)
        wl.addWidget(self.lbl_backup)
        self.lbl_lines_prompt = QtWidgets.QLabel("")
        wl.addWidget(self.lbl_lines_prompt)
        self.edit_lines = QtWidgets.QLineEdit()
        self.edit_lines.setPlaceholderText("número de líneas de la red")
        self.edit_lines.textChanged.connect(self._update_write_enabled)
        wl.addWidget(self.edit_lines)
        self.chk_third = QtWidgets.QCheckBox("")
        self.chk_third.toggled.connect(self._update_write_enabled)
        self.chk_third.hide()
        wl.addWidget(self.chk_third)
        self.lbl_countdown = QtWidgets.QLabel("")
        wl.addWidget(self.lbl_countdown)
        wl.addStretch()
        row = QtWidgets.QHBoxLayout()
        row.addStretch()
        self.btn_cancel_write = self._button("Cancelar")
        self.btn_cancel_write.clicked.connect(self._on_cancel)
        row.addWidget(self.btn_cancel_write)
        self.btn_write = self._button("Escribir en el equipo")
        self.btn_write.setEnabled(False)
        self.btn_write.clicked.connect(self._on_write)
        row.addWidget(self.btn_write)
        wl.addLayout(row)
        self.stack.addWidget(p_write)

        # Página "result"
        p_res = QtWidgets.QWidget()
        rl = QtWidgets.QVBoxLayout(p_res)
        self.lbl_result = QtWidgets.QLabel("")
        self.lbl_result.setWordWrap(True)
        rl.addWidget(self.lbl_result)
        rl.addStretch()
        row = QtWidgets.QHBoxLayout()
        self.btn_backup_return = self._button("")
        self.btn_backup_return.clicked.connect(self._on_backup_return)
        self.btn_backup_return.hide()
        row.addWidget(self.btn_backup_return)
        self.btn_reread = self._button("Volver a leer")
        self.btn_reread.clicked.connect(self._reread)
        self.btn_reread.hide()
        row.addWidget(self.btn_reread)
        row.addStretch()
        self.btn_close = self._button("Cerrar")
        self.btn_close.clicked.connect(self.accept)
        row.addWidget(self.btn_close)
        rl.addLayout(row)
        self.stack.addWidget(p_res)

    def current_page(self) -> str:
        return _PAGES[self.stack.currentIndex()]

    def _show(self, page: str):
        self.stack.setCurrentIndex(_PAGES.index(page))
        self._page_since = self._clock()
        names = ["1 Leer", "2 Diferencias", "3 Respaldo", "4 Escribir", "5 Resultado"]
        current = {"read": 0, "diff": 1, "write": 3, "result": 4}[page]
        self.lbl_steps.setText("   ".join(("● " if i == current else "") + n for i, n in enumerate(names)))

    # ── Transiciones ──
    def _read(self):
        tx = self.transaction
        diff = tx.prepare()
        if diff is None:
            self.lbl_read.setText(tx.detail)
            self.lbl_read.setStyleSheet(f"color: {_RED};")
            self._show("read")
            return
        k = diff.key
        change_nm = (f"≈ {diff.estimated_nm:+.3f} nm" if diff.estimated_nm is not None
                     else "sin estimación en nm: sin S medida (BANCO-40)")
        lines = [
            f"Red {k.grating_index} · {k.lines_per_mm:.0f} l/mm · puertos entrada {k.entrance_port} / salida {k.exit_port}"
            f" · serie {k.serial}",
            "",
            f"Offset de red   leído ahora: {diff.offset_read} pasos   propuesto: {diff.requested} pasos   "
            f"cambio: {diff.delta:+d} pasos ({change_nm})",
            f"Origen: registro {tx.source_record_id or '—'}",
            "",
            "Efecto: Solis y el PySpectrum legado también verán este valor. Escribir puede girar la torreta: "
            "antes se cierran los obturadores y se confirma la ganancia EM en 0.",
        ]
        if not diff.serial_matches_file:
            lines.append("⛔ El archivo de calibraciones es de otro espectrógrafo: no se puede seguir.")
        self.lbl_diff.setText("\n".join(lines))
        self.btn_confirm_diff.setEnabled(diff.serial_matches_file)
        self._show("diff")

    def _reread(self):
        self.transaction = self.transaction.clone()
        self.btn_reread.hide()
        self.btn_backup_return.hide()
        self._read()

    def _on_confirm_diff(self):
        self.btn_confirm_diff.setEnabled(False)            # un doble clic no emite dos veces
        tx = self.transaction
        state = tx.confirm_diff(tx.diff_token())
        if state != TxState.BACKED_UP:
            self._show_result_text(tx.detail, _RED, reread=state in (TxState.TOKEN_EXPIRED,))
            return
        diff = tx.diff
        self.lbl_backup.setText(f"Respaldo guardado: {diff.offset_read} pasos (entrada {tx.pre_write_record_id[:8]}…).")
        self.lbl_lines_prompt.setText(f"Para escribir, tecleá el número de líneas de la red ({diff.key.lines_per_mm:.0f}):")
        self.edit_lines.clear()
        if diff.needs_third_confirmation:
            nm = (f" (≈ {diff.estimated_nm:+.2f} nm)" if diff.estimated_nm is not None else "")
            self.chk_third.setText(f"Entiendo que el cambio es de {diff.delta:+d} pasos{nm}.")
            self.chk_third.setChecked(False)
            self.chk_third.show()
        else:
            self.chk_third.hide()
        self._update_write_enabled()
        self._show("write")

    def _write_token(self):
        return self.transaction.write_token(typed_lines=self.edit_lines.text(),
                                            third_confirmed=self.chk_third.isChecked())

    def _update_write_enabled(self, *_):
        self.btn_write.setEnabled(self.transaction.state == TxState.BACKED_UP and self._write_token() is not None)

    def _on_write(self):
        self.btn_write.setEnabled(False)
        tx = self.transaction
        res = tx.confirm_write(self._write_token())
        label = _HW_LABEL.get(res.state)
        if label:
            text, color = label
            self._show_result_text(f"{text}: {res.detail}", color)
            back = tx.backup_return()
            if back is not None:
                self.btn_backup_return.setText(f"Volver al valor del respaldo ({back.requested_offset} pasos)…")
                self.btn_backup_return.show()
        else:
            self._show_result_text(res.detail, _RED if res.state != TxState.STALE_TOKEN else _YELLOW,
                                   reread=res.state in (TxState.STALE_TOKEN, TxState.TOKEN_EXPIRED,
                                                        TxState.PRECONDITION_FAILED))

    def _show_result_text(self, text: str, color: str, reread: bool = False):
        self.lbl_result.setText(text)
        self.lbl_result.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.btn_reread.setVisible(reread)
        self._show("result")

    def build_backup_return_dialog(self) -> Optional["OffsetWriteDialog"]:
        back = self.transaction.backup_return()
        if back is None:
            return None
        return OffsetWriteDialog(lambda: back, estop_callback=self._estop, clock=self._clock, parent=self.parent())

    def _on_backup_return(self):
        child = self.build_backup_return_dialog()
        if child is not None:
            self.accept()
            child.exec()

    def _on_cancel(self):
        self.transaction.cancel()
        self.reject()

    def _on_estop(self):
        if self._estop is not None:
            self._estop()

    # ── Vencimiento del token (60 s) ──
    def _tick(self):
        if self.current_page() not in ("diff", "write"):
            self.lbl_countdown.setText("")
            return
        left = self.transaction.token_ttl_s - (self._clock() - self._page_since)
        if left <= 0:
            self.transaction.cancel()
            self._reread()
            return
        self.lbl_countdown.setText(f"esta confirmación vence en {left:.0f} s" if left <= 20 else "")

    def keyPressEvent(self, event):
        # Enter nunca confirma (H-23); Esc cancela sólo antes de escribir
        if event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
            event.ignore()
            return
        super().keyPressEvent(event)
