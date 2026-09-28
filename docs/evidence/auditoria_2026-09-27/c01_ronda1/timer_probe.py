import sys, time, numpy as np
from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal, QCoreApplication, Qt
app = QCoreApplication(sys.argv)
res = {}
class W(QObject):
    done = pyqtSignal()
    def run(self, interval, ttype, key, n=120):
        self.ts=[]; self.n=n; self.key=key
        self.t = QTimer(self); self.t.setTimerType(ttype)
        self.t.timeout.connect(self._tick); self.t.start(interval)
    def _tick(self):
        self.ts.append(time.perf_counter())
        if len(self.ts) >= self.n:
            self.t.stop(); d = np.diff(self.ts)*1e3
            res[self.key] = (np.mean(d), np.median(d), np.percentile(d,5), np.percentile(d,95), d.min(), d.max())
            self.done.emit()
class Go(QObject):
    sig = pyqtSignal(int, object, str)
th = QThread(); w = W(); w.moveToThread(th); th.start()
g = Go(); g.sig.connect(w.run)
plan = [(35, Qt.TimerType.CoarseTimer, "35ms Coarse (default)"), (35, Qt.TimerType.PreciseTimer, "35ms Precise"), (10, Qt.TimerType.CoarseTimer, "10ms Coarse (default)")]
it = iter(plan)
def nxt():
    try: iv, tt, k = next(it); g.sig.emit(iv, tt, k)
    except StopIteration: app.quit()
w.done.connect(nxt); nxt(); app.exec(); th.quit(); th.wait()
for k,v in res.items(): print(f"{k:24s} mean={v[0]:.2f} med={v[1]:.2f} p5={v[2]:.2f} p95={v[3]:.2f} min={v[4]:.2f} max={v[5]:.2f} ms")
