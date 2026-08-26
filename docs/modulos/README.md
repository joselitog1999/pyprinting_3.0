# 📑 Índice General de Documentación Modular — PyPrinting 3.0

**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Autor Principal**: José Luis González Peñafiel (*Becario Doctoral CONICET*)  
**Ubicación**: `docs/modulos/README.md`

---

## 📖 Visión General

La carpeta `docs/modulos/` contiene la **documentación técnica, operativa y metrológica individualizada** para cada uno de los programas, herramientas y submódulos que integran la plataforma **PyPrinting 3.0**.

Cada documento incluye de forma estandarizada:
1. **🖼️ Maqueta visual de la interfaz de usuario (ASCII Layout)**.
2. **🎛️ Catálogo completo de botones, controles, atajos y parámetros**.
3. **📥 Archivos de entrada que solicita** (formatos, extensiones y estructuras internas).
4. **📤 Archivos de salida que genera** (especificación de columnas, unidades físicas y fragmentos de ejemplo).
5. **⚙️ Funcionalidades, formulación matemática y arquitectura de hilos**.
6. **🔗 Referencias cruzadas directas** al [Manual de Usuario Principal (`docs/MANUAL_USUARIO.md`)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/MANUAL_USUARIO.md) y a los reportes técnicos en `reportes/`.

---

## 🗂️ Matriz de Módulos del Sistema

| N° | Módulo / Archivo Fuente | Rol Principal y Descripción | Estado | Enlace a Documentación |
|:---:|---|---|:---:|:---:|
| **01** | **Microscopio Derecho (`app.py`)** | Suite principal multihilo: Mapeo Confocal 2D/3D, Trazas $10\ \text{kHz}$, Autofoco Axial Z y Nanoposicionamiento PI. | 🟢 Operativo | [01_Microscopio_Derecho_App.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/modulos/01_Microscopio_Derecho_App.md) |
| **02** | **Rutinas de Impresión y Dímeros (`modules/measurements.py`)** | Motor de nanofabricación fototérmica: Grillas $N \times M$, 5 Criterios de Parada, Corrección de Deriva P0 y Presets. | 🟢 Operativo | [02_Measurements_Printing_y_Dimers.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/modulos/02_Measurements_Printing_y_Dimers.md) |
| **03** | **Microscopio Contrapropagante (`contrapropagante.py`)** | Excitación dual síncrona TOP/BOT (60x Agua NA=1.0), ajuste Gauss/Donut y cálculo de desalineación $\mathbf{r}_{\text{TOP}} - \mathbf{r}_{\text{BOT}}$. | 🟢 Operativo | [03_Microscopio_Contrapropagante.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/modulos/03_Microscopio_Contrapropagante.md) |
| **04** | **Cámara Live View (`modules/camera.py`)** | Visión réflex Canon EOS 500D nativa EDSDK 64-bit (25 FPS, 15.1 MP), simulación EVF, PiP, reglas $\mu\text{m}$ y Trackpy/Picasso. | 🟢 Operativo | [04_Camara_Live_View_EDSDK.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/modulos/04_Camara_Live_View_EDSDK.md) |
| **05** | **PSF Analyzer (`analysis/psf_analyzer.py`)** | Ajuste analítico no lineal 2D (Gaussiana 7 parámetros y Donut $LG_{01}$), perfiles 1D y residuales de alineación óptica. | 🟢 Operativo | [05_PSF_Analyzer.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/modulos/05_PSF_Analyzer.md) |
| **06** | **Analizador de Imágenes (`analysis/image_analyzer.py`)** | Procesamiento de fotos TIFF/JPG, Deconvolución Richardson-Lucy en tiempo real (FFT), calibración $\mu\text{m}/\text{px}$ y SMLM. | 🟢 Operativo | [06_Image_Analyzer.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/modulos/06_Image_Analyzer.md) |
| **07** | **Modulación Láser 532 nm (`Laser532Window`)** | Control de potencia por voltaje analógico AO2 NI-DAQmx ($0-5\ \text{V}$) y disparo de obturador TTL. | 🟢 Operativo | [07_Modulacion_Laser_532.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/modulos/07_Modulacion_Laser_532.md) |
| **08** | **Tablero de Seguridad y Presets (`hardware_dashboard.py` / `preset_wizard.py`)** | Matriz de LEDs de telemetría, aislamiento por software (*Soft Isolation*), re-scan USB y Asistente QWizard de presets `.txt`. | 🟢 Operativo | [08_Hardware_Dashboard_y_Presets.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/modulos/08_Hardware_Dashboard_y_Presets.md) |
| **09** | **PySpectrum (`PySpectrum`)** | Suite de espectrometría, termometría fototérmica y espectroscopía de dispersión/scattering. | 🟡 En construcción | [09_PySpectrum_Roadmap.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/modulos/09_PySpectrum_Roadmap.md) |
| **10** | **PyPrinting 2 Legacy (`PyPrinting_UNSAM.py`)** | Suite histórica para compatibilidad con secuencias previas. | 🔵 Legacy | [10_PyPrinting2_Legacy.md](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/modulos/10_PyPrinting2_Legacy.md) |

---

## 🌐 Enlaces Centrales del Repositorio
- [📘 Manual de Usuario Exhaustivo (`docs/MANUAL_USUARIO.md`)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/MANUAL_USUARIO.md)
- [📝 Registro de Cambios y Validaciones (`docs/WALKTHROUGH.md`)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/WALKTHROUGH.md)
- [🔮 Perspectivas y Sugerencias Futuras (`docs/PERSPECTIVAS.md`)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/PERSPECTIVAS.md)
- [📑 Índice de Reportes Científicos y de Sistema (`reportes/README.md`)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/README.md)
