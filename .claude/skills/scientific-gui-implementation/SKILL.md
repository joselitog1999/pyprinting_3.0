---
name: scientific-gui-implementation
description: Procedural implementation standard for PyQt6/pyqtgraph scientific graphical user interfaces in PyPrinting 3.0. Governs sacred session state preservation, defensive signal blocking, direct plot manipulation, table micro-interactions, asynchronous worker threading, and Catppuccin styling.
---

# Scientific GUI Implementation & Ergonomics Standard Skill

This skill governs the concrete implementation, code architecture, and defensive auditing of scientific desktop interfaces in PyPrinting 3.0 (built with PyQt6 and pyqtgraph). It serves as the primary procedural instrument for the `scientific-gui-designer` and `qa-ux-auditor` subagents.

---

## 1. Foundational Tenet: Sacred Session State & Unitary Mutation Policy

In an experimental laboratory, an operator spends 20–40 minutes curating optical spots, tuning thresholds, and classifying defect clusters. **Accidentally wiping this session state is an unforgivable defect.**

### Mandatory Unitary Rules
1. **Never Invalidate Unrelated State**:
   Executing an action on an individual entity (e.g. running a multi-Gaussian fit on Cluster #3) must NEVER call global resetting routines like `_update_real_space_analysis()` without an explicit `preserve_clusters=True` flag.
2. **Stable Positional Identifiers**:
   Always assign persistent particle identifiers (`particle_id`) to raw localization tables. When local edits remove, add, or resolve particles, recalculate coordinate arrays while preserving the ID mappings of unaffected particles.
3. **Queue Reordering (Work Queue Pattern)**:
   When resolving an item from a table (e.g., resolving a cluster or dismissing a false positive):
   - Mark its status as `"Resuelto (Algoritmo)"` or `"Resuelto (Manual)"`.
   - Update its row styling to soft green (`#a6e3a1`).
   - Move the resolved item to the bottom of the table.
   - Automatically highlight and select the next pending item at the top.

---

## 2. Defensive Signal Blocking Protocol

Bidirectional data binding between interactive canvas items (ROIs, linear regions, boundary rulers) and numerical input widgets (`QSpinBox`, `QDoubleSpinBox`) creates immediate risk of infinite feedback loops and race conditions.

### The Immutable Signal Rule
Whenever programmatic code updates a GUI widget in response to a canvas event (or vice-versa), the target widget MUST be wrapped in `blockSignals(True)`:

```python
# CORRECT
def _on_roi_region_changed(self):
    val_nm = self.roi.value()
    self.spin_boundary_nm.blockSignals(True)
    try:
        self.spin_boundary_nm.setValue(val_nm)
    finally:
        self.spin_boundary_nm.blockSignals(False)
```

```python
# PROHIBITED (Triggers recursive signal loop)
def _on_roi_region_changed(self):
    self.spin_boundary_nm.setValue(self.roi.value())
```

---

## 3. Direct Plot Manipulation & Micro-Interactions

A scientific GUI must favor **direct manipulation on the plot** over indirect typing in distant panels:

### Point-in-Polygon Direct Selection
When the operator clicks on an image canvas, convert the scene coordinates to data coordinates and perform spatial containment tests:
```python
# Example: selecting a cluster by clicking inside its polygon
scene_pos = event.scenePos()
view_pos = self.plot_widget.plotItem.vb.mapSceneToView(scene_pos)
cx, cy = view_pos.x(), view_pos.y()

# Using OpenCV pointPolygonTest on contour_polygon_nm
dist = cv2.pointPolygonTest(contour_nm, (cx, cy), measureDist=False)
if dist >= 0:
    # Point is inside or on the contour -> select corresponding cluster row
    self._select_cluster_by_id(cluster_id)
```

### Table Ergonomics & Arrow Key Navigation
1. **Selection Sync**: Always connect both `cellClicked` and `currentCellChanged` / `itemSelectionChanged` so that moving with the keyboard arrow keys instantly updates overlays and inspection canvases.
2. **Table Dimensions**: Table height must accommodate at least 8–10 visible rows without cramping (e.g. `setFixedHeight(280)`).
3. **Custom Context Menus**:
   Always enable custom context menus on diagnostic tables:
   ```python
   self.table_clusters.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
   self.table_clusters.customContextMenuRequested.connect(self._on_table_clusters_context_menu)
   ```
   Provide fast actions: *Resolve (Multi-Gauss)*, *Merge to Center-of-Mass*, *Mark as Resolved*, *Discard*.

---

## 4. Asynchronous Concurrency with QThread

Never freeze the main GUI thread during heavy numerical operations (Monte Carlo ensembles, NUFFT calculations, Picasso MLE iterations).

### Strict QThread Rules
1. **Use `QThread` with Worker Pattern**:
   Do NOT subclass `QThread.run()` with complex business logic; instantiate a worker object inheriting `QObject`, move it to the thread via `worker.moveToThread(thread)`, and communicate exclusively via `pyqtSignal`.
2. **Defensive Signal Disconnection**:
   Before launching a new run on an existing worker thread, disconnect old callbacks or recreate the worker to prevent duplicate signal dispatches:
   ```python
   if self._worker is not None and self._worker.isRunning():
       self._worker.wait()
   ```
3. **GUI Updates on Main Thread Only**:
   Worker threads must NEVER modify PyQt6 widgets directly. Emit signals carrying plain NumPy arrays, dictionaries, or dataclasses.

---

## 5. Library Pitfalls & Coordinate Conventions

### PyQtGraph vs NumPy Axis Convention
* **NumPy arrays** are indexed as `array[row, col]` $	o$ `array[y, x]`.
* **PyQtGraph `ImageItem`** expects data transposed or indexed as `[x, y]` depending on `axisOrder`:
  - Always be explicit: `pg.setConfigOption('imageAxisOrder', 'col-major')` or transpose before passing: `image_item.setImage(data.T)`.
  - Contours and polygon coordinates must match physical space ($x$ horizontal in nm, $y$ vertical in nm).

### Picasso SR API Compatibility
* Always provide `return_info=False` explicitly when calling `picasso.localize.identify()` to maintain forward compatibility with Picasso v0.11+.

### Trackpy Inversion
* When detecting dark features on a bright background, invert the image array beforehand (`np.max(img) - img`) rather than relying on deprecated `invert=True` flags in `trackpy.locate()`.

---

## 6. Scientific Pedagogy & Contextual Help

Every scientific panel must include pedagogical affordances:
1. **Rich Tooltips**: Explain physical SI units, formulas, and typical experimental values (e.g., $\sigma_{	ext{psf}} pprox 139\ 	ext{nm}$ for 60x/1.2W objective at $\lambda = 532\ 	ext{nm}$).
2. **Deep-Linked Help**: Provide a `[📖 Help]` or `[❓ Ayuda]` button opening `analysis/scientific_wiki_browser.py` at the exact canonical monograph (`CAT-xxx`).

---

## 7. Catppuccin Mocha Color Reference

Maintain chromatic consistency across all PyPrinting 3.0 tools:

| Role | Color Name | Hex Code | Purpose |
| :--- | :--- | :--- | :--- |
| **Canvas Background** | `Crust` | `#11111b` | Main pyqtgraph viewport background |
| **Panel Background** | `Base` / `Mantle` | `#1e1e2e` / `#181825` | Side panels, group boxes, dialog surfaces |
| **Text Primary** | `Text` | `#cdd6f4` | Labels, axis titles, table values |
| **Accent / Action** | `Mauve` / `Sapphire` | `#cba6f7` / `#74c7ec` | Primary action buttons, selected highlights |
| **Success / Resolved** | `Green` | `#a6e3a1` | Resolved clusters, passing quality gates |
| **Warning / Suspicious**| `Yellow` / `Peach` | `#f9e2af` / `#fab387` | Suspicious spots, high disorder ($\sigma_{	ext{pos}} > 0.15 a$) |
| **Error / Defect** | `Red` | `#f38ba8` | Vacancies, fitting divergences, hardware interlocks |
| **Diffraction / Reciprocal** | `Teal` / `Sky` | `#94e2d5` / `#89dceb` | Reciprocal Bragg peaks, Fourier masks |
