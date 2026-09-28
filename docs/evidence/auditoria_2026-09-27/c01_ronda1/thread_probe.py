import sys, threading
from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal, QCoreApplication
app = QCoreApplication(sys.argv)
main_ident = threading.get_ident()
class Trace(QObject):
    data_printingSignal = pyqtSignal(list)
    def tick(self):
        self.data_printingSignal.emit([threading.get_ident()])
class Container(QObject):          # como app.py:421 Backend, no movido
    def __init__(self):
        super().__init__()
        self.trace = Trace()
        self.trace.data_printingSignal.connect(self._dispatch_trace)   # como app.py:473
        self.hits = []
    def _dispatch_trace(self, data):  # método Python sin @pyqtSlot
        self.hits.append((data[0], threading.get_ident()))
c = Container()
th = QThread(); c.trace.moveToThread(th); th.start()
QTimer.singleShot(0, lambda: None)
# disparar el tick DESDE el hilo del worker
from PyQt6.QtCore import QMetaObject, Qt
QMetaObject.invokeMethod(c.trace, "tick", Qt.ConnectionType.QueuedConnection) if False else None
t2 = QTimer(); t2.moveToThread(th)
def fire():
    c.trace.tick()
QTimer.singleShot(50, lambda: None)
import time
# usar un QTimer que vive en el hilo worker
class Starter(QObject):
    go = pyqtSignal()
s = Starter(); s.go.connect(c.trace.tick)  # trace en th -> tick corre en th
s.go.emit()
QTimer.singleShot(300, app.quit)
app.exec()
th.quit(); th.wait()
emit_tid, slot_tid = c.hits[0]
print("main:", main_ident, "emit (worker):", emit_tid, "slot _dispatch_trace:", slot_tid)
print("slot corre en hilo principal:", slot_tid == main_ident, "| emit en worker:", emit_tid != main_ident)
