# 🔬 Módulo 10: PyPrinting 2 Legacy (`PyPrinting_UNSAM.py`)

**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Archivo Fuente**: [`PyPrinting_UNSAM.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/PyPrinting_UNSAM.py)  
**Lanzador Rápido**: Botón 4 en [`main.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/main.py) o `python PyPrinting_UNSAM.py`

---

## 1. 🏷️ Resumen y Rol en el Sistema

El módulo **PyPrinting 2 Legacy** preserva el entorno histórico de adquisición monolítico utilizado durante las primeras generaciones de experimentos de nanofabricación fototérmica en el INS-UNSAM.

Se mantiene dentro del lanzador [`main.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/main.py) con fines de:
- **Compatibilidad Retrospectiva**: Reproducción exacta de protocolos experimentales y secuencias previas.
- **Validación Cruzada**: Verificación de algoritmos frente a la nueva arquitectura modular desacoplada de PyPrinting 3.0.
- **Docencia y Referencia**: Demostración de la evolución desde código monolítico PyQt4/PyQt5 hacia la arquitectura multihilo PyQt6.

---

## 2. 🖼️ Maqueta de la Interfaz Visual (ASCII Layout)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  PyPrinting 2 — Nanofabricación Óptica (Versión Legacy)                                               -  □  ×    │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│  File   Settings   Help                                                                                          │
├───────────────────────────────────────────────────────────────────────┬──────────────────────────────────────────┤
│  PANEL CONFOCAL Y TRAZA HISTÓRICO                                     │  PARÁMETROS DE DETECCIÓN LEGACY          │
│  ┌─────────────────────────────────────────────────────────────────┐ │  Láser: [ 532 nm ]  Potencia: [ 10 mW ]   │
│  │                                                                 │ │  Umbral Relativo:   [ 1.30 ]              │
│  │   [ Mapa de Barrido Confocal Clásico ]                          │ │  Umbral Down:       [ 0.50 ]              │
│  │                                                                 │ │  Tiempo Máximo (s): [ 30.0 ]              │
│  │                                                                 │ │  Autofoco cada:     [ 5 ] partículas      │
│  │                                                                 │ │  Steps Before (M2): [ 10 ]                │
│  │                                                                 │ │  Steps After (M):   [ 10 ]                │
│  │                                                                 │ │                                           │
│  │                                                                 │ │  [ Cargar Grilla ]                        │
│  │                                                                 │ │  [ Iniciar Impresión ]                    │
│  └─────────────────────────────────────────────────────────────────┘ │  [ Detener Todo ]                        │
├───────────────────────────────────────────────────────────────────────┴──────────────────────────────────────────┤
│  Platina PI: (X=10.000, Y=10.000, Z=5.000) µm | Estado: Esperando inicio de secuencia                            │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 🎛️ Catálogo de Botones y Parámetros

| Parámetro / Botón | Tipo | Descripción |
|---|---|---|
| `Umbral` | `QLineEdit` | Multiplicador de salto de señal ($I_{\text{new}} > I_{\text{old}} \cdot \text{umbral}$). |
| `Umbral Down` | `QLineEdit` | Límite inferior de caída para aborto por fotoblanqueamiento ($I_{\text{new}} < I_{\text{old}} \cdot \text{umbral\_down}$). |
| `Time Max` | `QLineEdit` | Tiempo límite en segundos para cerrar el obturador si no se detecta evento. |
| `Steps Before / After` | `QLineEdit` | Longitud de las ventanas móviles $M_2$ y $M$ para el cálculo de $I_{\text{old}}$ e $I_{\text{new}}$. |
| `Iniciar Impresión` | `QPushButton` | Lanza el bucle secuencial de impresión. |

---

## 4. 📥 Archivos de Entrada que Solicita

1. **Grillas de Coordenadas (`*.txt`)**:
   - Archivos de texto plano con posiciones discretas $[x, y]$.
2. **Última Posición (`Last_position.txt`)**:
   - Coordenadas de inicio de la platina piezoeléctrica.

---

## 5. 📤 Archivos de Salida que Genera

1. **Trazas Experimentales (`NP_00i.txt`)**:
   - Archivo con 4 columnas temporales de voltaje del fotodiodo.
2. **Escaneo Confocal (`NPscan_00i.tiff`)**:
   - Imagen en escala de grises de 16 bits.

---

## 6. ⚙️ Diferencias con PyPrinting 3.0

| Característica | PyPrinting 2 Legacy | PyPrinting 3.0 |
|---|---|---|
| **Arquitectura de Software** | Monolítica / Hilos combinados | Multihilo desacoplado (`Frontend / Backend` + `QThread`) |
| **Criterios de Parada** | 1 único modo (Salto relativo) | 5 modos configurables con protección anti-paso $N_{\text{hold}}$ |
| **Corrección de Deriva** | Sin compensación activa | Corrección nanométrica periódica sobre Partícula Ancla $P_0$ |
| **Presets de Impresión** | Manual por corrida | Gestor automático `.txt` con Asistente Guiado `QWizard` |
| **Visión de Cámara** | Live View básico | EDSDK 64-bit nativo, simulación EVF y SMLM (Trackpy + Picasso) |

---

## 7. 🔗 Referencias Cruzadas
- [📘 Manual de Usuario Principal](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/MANUAL_USUARIO.md)
- [📑 Reporte de Migración Arquitectónica (`reportes/sistema/PyPrinting_3_0_PyQt6_Migracion.md`)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/sistema/PyPrinting_3_0_PyQt6_Migracion.md)
