# Manual de Usuario Exhaustivo: PyPrinting 3.0 🔬
**Suite de Control, Espectroscopía Confocal, Caracterización de PSF y Nanofabricación Óptica**
*Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM)*
*Autor Principal: José Luis González Peñafiel (Becario Doctoral CONICET)*

---

## 📖 Índice General

1. [Panel de Inicio Principal (`main.py` — "Bienvenidos al printing")](#1-panel-de-inicio-principal-mainpy--bienvenidos-al-printing)
   - [1.1 Visión General, Filosofía de Diseño y Arquitectura Multihilo](#11-visión-general-filosofía-de-diseño-y-arquitectura-multihilo)
   - [1.2 Selección Global de Modo Seguro (`SAFE_MODE`) vs. Modo Laboratorio Real](#12-selección-global-de-modo-seguro-safe_mode-vs-modo-laboratorio-real)
   - [1.3 Navegación e Índice de Módulos en Grilla Simétrica $3 \times 3$](#13-navegación-e-índice-de-módulos-en-grilla-simétrica-3-times-3)
2. [Fundamentos Físicos, Formulación Matemática & Mapeo de Hardware](#2-fundamentos-físicos-formulación-matemática--mapeo-de-hardware)
   - [2.1 Impresión Óptica Fototérmica de Nanopartículas Coloidales](#21-impresión-óptica-fototérmica-de-nanopartículas-coloidales)
   - [2.2 Ensamblado Guiado de Nanodímeros Plasmónicos y Campo Cercano](#22-ensamblado-guiado-de-nanodímeros-plasmónicos-y-campo-cercano)
   - [2.3 Modelo Analítico Gaussiano 2D Anisotrópico de 7 Parámetros](#23-modelo-analítico-gaussiano-2d-anisotrópico-de-7-parámetros)
   - [2.4 Modelo Analítico Haz Vortex / Donut (Laguerre-Gauss $LG_{01}$)](#24-modelo-analítico-haz-vortex--donut-laguerre-gauss-lg_01)
   - [2.5 Métricas Analíticas y Alineación Sub-nanométrica de PSF](#25-métricas-analíticas-y-alineación-sub-nanométrica-de-psf)
   - [2.6 Operación de Umbralización No Lineal de Ruido ($P\%$)](#26-operación-de-umbralización-no-lineal-de-ruido-p)
   - [2.7 Algoritmo de Estabilización Z Axial por Autocorrelación de Pearson](#27-algoritmo-de-estabilización-z-axial-por-autocorrelación-de-pearson)
   - [2.8 Mapeo Físico de Coordenadas y Calibración de Platina Piezoeléctrica PI](#28-mapeo-físico-de-coordenadas-y-calibración-de-platina-piezoeléctrica-pi)
3. [Módulo 1: Microscopio Derecho (`app.py` — PyPrinting 3.0 Suite Completa)](#3-módulo-1-microscopio-derecho-apppy--pyprinting-30-suite-completa)
   - [3.1 Menú Principal (`Files`, `Tools`, `Measurements`, `Help`)](#31-menú-principal-files-tools-measurements-help)
   - [3.2 Dock: Confocal (Mapeo 2D/3D & Algoritmos de Centrado)](#32-dock-confocal-mapeo-2d3d--algoritmos-de-centrado)
   - [3.3 Dock: Trace (Trazas Temporales & Calibración Power BS)](#33-dock-trace-trazas-temporales--calibración-power-bs)
   - [3.4 Dock: Focus z (Autofoco Axial Dinámico)](#34-dock-focus-z-autofoco-axial-dinámico)
   - [3.5 Dock: Shutters / Flipper / Láser 532](#35-dock-shutters--flipper--láser-532)
   - [3.6 Dock: Nanopositioning (Platina Piezoeléctrica PI)](#36-dock-nanopositioning-platina-piezoeléctrica-pi)
   - [3.7 Ventana de Mediciones (Printing Automatizado & 5 Modos de Criterio de Parada)](#37-ventana-de-mediciones-printing-automatizado--5-modos-de-criterio-de-parada)
4. [Módulo 2: PySpectrum *(En Desarrollo: Espectrometría, Termometría & Scattering)*](#4-módulo-2-pyspectrum-en-desarrollo-espectrometría-termometría--scattering)
5. [Módulo 3: Microscopio Contrapropagante (`contrapropagante.py`)](#5-módulo-3-microscopio-contrapropagante-contrapropagantepy)
6. [Módulo 4: PyPrinting 2 (Legacy — `PyPrinting_UNSAM.py`)](#6-módulo-4-pyprinting-2-legacy--pyprinting_unsampy)
7. [Módulo 5: Cámara Live View (`camera.py` — Suite Canon EDSDK & Microfotónica)](#7-módulo-5-cámara-live-view-camerapy--suite-canon-edsdk--microfotónica)
8. [Módulo 6: Modulación Láser 532 nm (`Laser532Window`)](#8-módulo-6-modulación-láser-532-nm-laser532window)
9. [Módulo 7: PSF Analyzer (`psf_analyzer.py`)](#9-módulo-7-psf-analyzer-psf_analyzerpy)
10. [Módulo 8: Analizador de Imágenes Estáticas (`image_analyzer.py`)](#10-módulo-8-analizador-de-imágenes-estáticas-image_analyzerpy)
11. [Módulo 9: Documentación y Créditos del Autor](#11-módulo-9-documentación-y-créditos-del-autor)
12. [Tabla Completa de Parámetros Globales (`config.py`)](#12-tabla-completa-de-parámetros-globales-configpy)
13. [Flujos de Trabajo Experimentales (Protocolos Paso a Paso)](#13-flujos-de-trabajo-experimentales-protocolos-paso-a-paso)
14. [Modelo Metrológico de Incertidumbre y Criterios Sub-píxel (Norma ISO/GUM)](#14-modelo-metrológico-de-incertidumbre-y-criterios-sub-píxel-norma-isogum)
15. [Protección de Exclusión Mutua en Hardware Real (Modo Laboratorio)](#15-protección-de-exclusión-mutua-en-hardware-real-modo-laboratorio)
16. [Tabla de Atajos de Teclado (Shortcuts)](#16-tabla-de-atajos-de-teclado-shortcuts)
17. [Guía de Resolución de Problemas y Diagnóstico (Troubleshooting)](#17-guía-de-resolución-de-problemas-y-diagnóstico-troubleshooting)
18. [Preguntas Frecuentes (FAQ)](#18-preguntas-frecuentes-faq)

---

## 3. Módulo 1: Microscopio Derecho (`app.py` — PyPrinting 3.0 Suite Completa)

### 3.7 Ventana de Mediciones (Printing Automatizado & 5 Modos de Criterio de Parada)
La pestaña **`Printing`** y **`Dimers`** incorporan el desplegable de **5 Modos de Criterio de Parada** con visibilidad dinámica de casilleros en la interfaz:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ Criterio Parada: [ Modo 4: Criterio Híbrido Tri-Factor (All-In-One)                  ▼ ]│
└────────────────────────────────────────────────────────────────────────────────────────┘
```

1. **Modo 0: Legacy (Salto Relativo Estándar)**:
   - Evalúa $I_{\text{new}} / I_{\text{old}} > \text{Umbral}$. Habilita `Umbral rel`, `Steps before`, `Steps after` y `T max`.
2. **Modo 1: Salto Relativo + Umbral Absoluto (V) & Anti-Paso**:
   - Evalúa $I_{\text{new}} / I_{\text{old}} > \text{Umbral}$ **o** $I_{\text{new}} > \text{Umbral Abs (V)}$. Exige $N_{\text{hold}}$ pasos consecutivos para ignorar partículas de paso. Habilita `Umbral Abs (V)` y `N hold steps`.
3. **Modo 2: Derivada Temporal Adaptativa & Aplanamiento ($dI/dt$)**:
   - Evalúa la tasa de cambio $|dI/dt| < \text{Slope Flat}$ (aplanamiento asíntota) y $I_{\text{new}} > I_{\text{abs\_V}}$. Habilita `Slope Min`, `Slope Flat`, `Umbral Abs (V)` y `N hold steps`.
4. **Modo 3: Calibración Confocal Raw & Umbral Absoluto Reescalado**:
   - Calcula automáticamente el umbral absoluto en Volts $V_{\text{umbral}}$ a partir del mapa confocal previo y la relación de potencia $K_{\text{scale}} = P_{\text{print}} / P_{\text{scan}}$. Habilita `Ratio K (P/S)`, `Umbral (%)` y `N hold steps`. Guarda la matriz confocal reescalada en archivos `.txt` y `.tiff`.
5. **Modo 4: Criterio Híbrido Tri-Factor (All-In-One)**:
   - Combina simultáneamente los Modos 1, 2 y 3 con verificación anti-partículas de paso ($N_{\text{hold}}$ steps). Habilita todos los casilleros de la interfaz.

> [!NOTE]
> Para consultar la formulación matemática detallada y el diagrama de flujo multihilo, consulte el reporte técnico dedicado:
> [Reporte Técnico: Algoritmo de Impresión Óptica y Ensamblado de Nanodímeros (reportes/Algoritmo_Printing_y_Dimers_PyPrinting3.md)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/Algoritmo_Printing_y_Dimers_PyPrinting3.md)

---

*Manual de Usuario Exhaustivo de PyPrinting 3.0 — Laboratorio de Nanofotónica, Instituto de Nanosistemas (INS-UNSAM).*
*Autor Principal: José Luis González Peñafiel (Becario Doctoral CONICET).*
