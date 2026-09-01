# 🔮 Perspectivas, Objetivos Logrados y Nuevas Fronteras — PyPrinting 3.0

**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Autor**: Equipo de Desarrolladores & Investigadores de Nanofotónica  
**Ubicación**: `docs/PERSPECTIVAS.md`  
**Última Actualización**: 1 de Septiembre de 2026  

---

## 📖 Estado del Desarrollo y Hoja de Ruta

En concordancia con el principio de evolución continua de la suite **PyPrinting 3.0**, este documento mantiene el registro de las funcionalidades completadas y proyecta las futuras metas de investigación en nanofotónica experimental, óptica cuántica y nanolitografía fototérmica.

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   HITOS LOGRADOS (100% COMPLETOS)                               │
├─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ [x] Suite PySpectrum 3.0 (Shamrock Andor, Step & Glue, calibración halógena y espectro oscuro). │
│ [x] Diseñador Universal de Redes 2D (15 familias, slider γ continuo, bases fraccionales y d_min).│
│ [x] Protocolo Multi-Paso de Cuadratura por Partícula Ancla (P0) y recetas empaquetadas.        │
│ [x] Estimador Predictivo de Tiempo Restante (ETA dinámico con promedio acumulativo de trazas). │
│ [x] Control Adaptativo de Frecuencia de Autofoco según velocidad de deriva instantánea v_drift.│
│ [x] Suite Integral de Pruebas Automatizadas Unitarias (36 / 36 tests superados en tests/).     │
│ [x] Compendio Físico Riguroso, Manual Maestro (21 Secciones) y Protocolos SOP Estandarizados.   │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🎯 1. Nuevas Metas y Fronteras Científicas

### 1.1 Mapeo Hiperespectral SERS Automatizado en Coordenadas de Grilla
- **Concepto**: Acoplar de manera directa la lista de coordenadas de la grilla impresa (`printing_results.txt`) con la rutina de escaneo confocal de `pyspectrum.py`.
- **Objetivo**: Posicionar secuencialmente la platina piezoeléctrica PI sobre cada nanopartícula o nanodímero impreso, adquirir automáticamente el espectro Raman / SERS con sustracción de fondo y reconstruir mapas hiperespectrales 3D $(X, Y, \lambda)$ de dispersión inelástica.

### 1.2 Pinzas Ópticas Holográficas mediante Modulador Espacial de Luz (SLM)
- **Concepto**: Integrar el control de un modulador espacial de luz basado en cristal líquido sobre silicio (LCoS-SLM) en el trayecto de iluminación.
- **Objetivo**: Generar haces con momento angular orbital (haces tipo vórtice / Laguerre-Gauss $LG_{pl}$ y haces Bessel no difractantes) para realizar atrapamiento y rotación óptica simultánea de múltiples nanopartículas plasmónicas y nanoestructuras quirales.

### 1.3 Clasificación en Tiempo Real de Trazas mediante Redes Neuronales Profundas (Edge AI)
- **Concepto**: Entrenar un modelo de inferencia ligero (e.g. 1D-CNN o Transformer temporal) sobre el flujo DMA a $10\ \text{kHz}$ del fotodiodo.
- **Objetivo**: Discriminar en $< 0.5\ \text{ms}$ entre eventos de adhesión de monómeros, dímeros indeseados o impurezas coloidales, adaptando dinámicamente la potencia de corte del láser para maximizar la pureza monodispersa de la grilla.

### 1.4 Nanofabricación Tridimensional Quiral Multi-Capa (3D Optical Printing)
- **Concepto**: Extender el compositor de redes 2D hacia la tercera dimensión axial $Z$.
- **Objetivo**: Fabricar hélices plasmónicas y meta-átomos quirales 3D mediante deposición óptica asistida por fotopolimerización o matrices multicapa de soporte sacrificial.

---

## 💡 2. Sugerencias Técnicas de Arquitectura e Ingeniería

- [ ] **2.1 Watchdog de Seguridad para Obturadores Láser (*Hardware Heartbeat*)**:
  - **Propósito**: Temporizador a nivel de hardware NI-DAQmx que fuerce el cierre incondicional de los obturadores si el software sufriera una congelación imprevista, protegiendo las muestras de fotodaño.

- [ ] **2.2 Contenedor Unificado HDF5 / JSON Estructurado para Lotes Experimentales**:
  - **Propósito**: Exportar al final de la jornada un archivo único `session_data.h5` que consolide trazas temporales completas, imágenes confocales 16-bit, curvas de autofoco y vectores de deriva para procesamiento masivo en Python/Jupyter.

- [ ] **2.3 Capa Vectorial de Deriva en Tiempo Real en el Visor de Grilla**:
  - **Propósito**: Representación gráfica con vectores de color sobre `InteractiveGridWidget` indicando la trayectoria de deriva corregida $(\Delta x, \Delta y)$ en cada nodo impreso.
