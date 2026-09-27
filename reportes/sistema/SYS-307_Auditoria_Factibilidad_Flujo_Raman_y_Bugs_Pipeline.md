# SYS-307: Auditoría de Factibilidad del Flujo Experimental Raman, Diagnóstico de Dudas Técnicas y Registro de Bugs del Pipeline
## Evaluación Integral de Interacción de Hardware, Sincronización UI y Trazabilidad de Datos entre PySpectrum 3.0, Raman Analyzer y SIF Analyzer

---

**Signatura:** `SYS-307` | **Eje Temático:** `[SYS]` / `[DAT]` Arquitectura de Software, Metrología Óptica y Control de Concurrencia  
**Autor Principal:** José Luis González Peñafiel (*Becario Doctoral CONICET*), Comité de Auditoría PyPrinting  
**Fecha de Emisión:** Septiembre 2026 | **Estado:** Aprobado / Auditoría de Laboratorio  
**Módulos Analizados:** `pyspectrum.py`, `app.py`, `pyspectrum/modules/static_raman.py`, `pyspectrum/ui/left_hardware_panel.py`, `pyspectrum/ui/exploration_tab.py`, `core/raman_engine.py`, `analysis/raman_analyzer.py`, `sif_analyzer.py`  
**Documentos Relacionados:**  
- [[CAT-251_Protocolo_Operativo_Espectroscopia_Raman_y_Alineacion_Optica]] (SOP experimental del procedimiento Raman)  
- [[SYS-301_Sistema_Espectrometro_Shamrock500i_iXon3]] (Especificaciones de hardware y drivers)  
- [[SYS-306_Arquitectura_Motor_Raman_y_Quimiometria_Multiespectral]] (Algoritmos del motor raman_engine)  
- [[SYS-403_Registro_Bugs_Causa_Raiz_Rutina_Printing]] (Historial de resolución de defectos críticos)

---

## 1. Resumen Ejecutivo

Con miras a la realización de campañas experimentales de espectroscopía Raman y escaneo espectral, se auditó exhaustivamente el protocolo de trabajo propuesto por el operador frente a la implementación real del código fuente de **PySpectrum 3.0**, **Raman Analyzer** y **SIF Analyzer**.

La auditoría concluyó que el flujo operativo es plenamente factible. Todos los defectos y omisiones identificados han sido **subsanados, implementados y validados mediante tests unitarios automatizados**:
1. **Tres dudas técnicas resueltas:** Aclaración de cuentas crudas vs background, incorporación del **cartel reactivo de rango espectral cubierto (nm y cm⁻¹)** debajo del selector de $\lambda$, y automatización del **obturador Shamrock** en Live y Adquisición.
2. **Cuatro omisiones de protocolo incorporadas:** Blindaje en Orden Cero, 2 filtros Notch manuales de detección, flipper de atenuación láser de excitación, y apagado de lámpara halógena.
3. **Resolución de bugs de software:**
   - **Bug 1 (P0):** Parser de `core/raman_engine.py` adaptado para leer la última columna como intensidad ADC en archivos de 3 columnas y sanitización de metadatos con `#`.
   - **Bug 2 (P1):** Guardado de espectros en memoria (`_raw_counts`, `_raw_wl`) en `static_raman.py`, evitando capturas espurias y excepciones de indexación 1D/2D.
   - **Modo Imagen 2D acotado al ROI vertical:** Tanto para mediciones Raman como para referencias de transmisión, el modo Imagen 2D configura el sub-área vertical exacta del sensor (`SetImage(1, 1, 1, 1004, vstart, vend)`).
   - **Conflicto de hardware PI:** Microscopio Derecho (`app.py`) disponible en `Menú Herramientas` como ventana satélite en el mismo proceso para eliminar colisiones de bus USB con la platina piezoeléctrica.

---

## 2. Respuestas a las Dudas Técnicas Planteadas por el Operador

### Duda 1: ¿Está implementado un modo para que en Live View se vea cuentas corregidas por background o solo cuentas?
* **Estado Actual en el Código:**
  En la versión actual de PySpectrum (tanto en la **Pestaña 1: Exploración** como en el **Inspector 2D** y la **Pestaña 2: Static Raman**), el modo Live View transmite y visualiza **únicamente cuentas crudas (raw counts ADC)** provenientes directamente de la digitalización del sensor Andor EMCCD (`camera.get_most_recent_image()` / `camera.get_1d_spectrum()`).
* **Justificación de Diseño:**
  En adquisiciones continuas a 25–30 FPS, la sustracción de matrices 2D en tiempo real sobre el hilo de visualización introduce sobrecarga de CPU y puede provocar latencia o desincronización de fotogramas.
* **Mecanismos de Compensación Disponibles:**
  1. *En la Pestaña 1 (Exploración):* Se cuenta con el algoritmo de **auto-contraste robusto por percentiles ($p_1 - p_{99}$)** implementado mediante `compute_robust_contrast_levels()`. Aunque el fondo de la lámpara o la corriente oscura estén presentes, este algoritmo comprime el rango dinámico descartando outliers, permitiendo distinguir nanopartículas y bordes de la ranura sin encandilamiento.
  2. *En la Pestaña 2 (Static Raman):* Para espectros 1D en vivo, existe la opción **`Sustraer Línea Base:`** (con métodos **AsLS**, **AirPLS** o **ModPoly**). Si bien esto no sustrae un espectro oscuro pre-grabado punto a punto, sí calcula y sustrae en cada cuadro la envolvente suave de fluorescencia y pedestal continuo en tiempo real ($< 2\,\text{ms}$).
  3. *En Post-Procesado (SIF Analyzer y Raman Analyzer):* La sustracción matemática estricta de perfiles de ruido oscuro (`dark_frame`) y blanco de lámpara halógena está completamente implementada.

---

### Duda 2: Al seleccionar el $\lambda$ central, ¿cómo ver el rango de $\lambda$ que se cubrirá con la red elegida?
* **Implementación Realizada en PySpectrum 3.0:**
  Se incorporó en `pyspectrum/modules/static_raman.py` el badge dinámico `lbl_spectral_range` posicionado inmediatamente debajo del selector `spin_center_wl`.
  El cartel calcula los límites físicos del CCD a partir del vector de calibración del Shamrock y reporta en tiempo real:
  - En modo Longitud de Onda: `📊 Rango Espectral Cubierto: [λ_min a λ_max] nm  (Δλ ≈ ... nm)`
  - En modo Corrimiento Raman: `📊 Rango Espectral Cubierto: [s_min a s_max] cm⁻¹  (λ: λ_min a λ_max nm)`
  El cartel se actualiza reactivamente ante cualquier cambio en la red de difracción, la longitud de onda central o la casilla de conmutación a Raman Shift.
* **Regla Física de Dispersión y Cobertura:**
  El rango espectral abarcado sobre el detector Andor iXon3 (ancho horizontal $L_x = 1004\,\text{px} \times 13\,\mu\text{m} = 13.05\,\text{mm}$) con la distancia focal del Shamrock ($f = 500\,\text{mm}$) es:
  - **Red 1 (150 l/mm, Blaze 800 nm):** Dispersión media $D \approx 0.35\,\text{nm/px}$. Cobertura total: $\Delta\lambda \approx 350\,\text{nm}$ (con láser 532 nm, cubre desde $-2100\,\text{cm}^{-1}$ hasta $+3400\,\text{cm}^{-1}$, abarcando simultáneamente Stokes, Anti-Stokes y bandas C-H/O-H).
  - **Red 2 (1200 l/mm, Blaze 500 nm):** Dispersión media $D \approx 0.044\,\text{nm/px}$. Cobertura total: $\Delta\lambda \approx 44\,\text{nm}$ (con láser 532 nm, cubre una ventana de $\approx 1100\,\text{cm}^{-1}$, ideal para deconvolución de picos cercanos).

---

### Duda 3: ¿Existe un set de opciones para configurar el Live View con parámetros exploratorios independientes de la medición final?
* **Estado Actual en el Código:**
  En PySpectrum existe un único conjunto de controles de adquisición en el `LeftHardwarePanel` (`spin_exposure`, `spin_em_gain`, `cmb_preamp`, `cmb_hsspeed`).
* **Automatización del Shutter Incorporada:**
  El obturador del espectrógrafo Shamrock ahora está totalmente automatizado (`ShamrockSetShutter(DEVICE, 1)` al presionar Live View o Captura Única, y `ShamrockSetShutter(DEVICE, 0)` en `finally` al concluir o detener).
* **Impacto Operativo:**
  Para una visualización ágil:
  1. Fijar una exposición baja en el panel izquierdo ($0.05\,\text{s} - 0.1\,\text{s}$).
  2. Presionar `Live Raman` y alinear con la platina piezoeléctrica o micrométricos.
  3. Detener `Live Raman`.
  4. Incrementar la exposición ($5.0\,\text{s} - 30.0\,\text{s}$) y ganancia EM antes de presionar `Capturar Espectro Único`.

---

## 3. Análisis Crítico del Protocolo del Operador: Omisiones y Riesgos Físicos

Al contrastar la secuencia descripta por el usuario con las leyes de la óptica y la seguridad instrumental, se identificaron **4 puntos críticos que deben ser incorporados de forma mandatoria**:

### 1. Peligro Crítico en Orden Cero: Alineación del Láser
* *Texto del Protocolo:* "Verifico que el laser caiga en la ventana del slit (sino, muevo espejos manualmente)".
* *Riesgo Instrumental Extremo:*
  Si este paso se realiza en la **Pestaña de Exploración (Orden Cero, 0.0 nm)** con el obturador láser abierto y el haz incidiendo sobre el CCD sin atenuación óptica masiva, **se quemará el chip Andor iXon3**.
* *Procedimiento Correcto:*
  - La verificación de que el láser caiga en el slit se realiza con **filtro atenuador de densidad neutra (ND4 o superior)** o observando la fluorescencia/dispersión secundaria sobre una muestra de referencia (ej. cubreobjetos con tinta fluorescente), NUNCA enfocando el haz directo hacia la ranura en Orden Cero con EM gain.
  - El sistema cuenta con la protección automática `ZeroOrderSafetyDialog`, que apaga la ganancia EM y cierra obturadores al pasar a 0 nm; cualquier intento de forzar la apertura del láser en ese modo debe hacerse con extrema cautela.

### 2. Apagado de la Lámpara Halógena de Transmisión
* *Omisión:* El protocolo no menciona apagar la iluminación blanca del microscopio antes de conmutar a la ventana de Raman.
* *Consecuencia:* La luz de la lámpara halógena ($> 10^6$ fotones/s comparada con los pocos fotones de la dispersión inelástica Raman) saturará completamente el espectro a 65,535 cuentas, ocultando por completo cualquier señal molecular.

### 3. Apertura del Obturador Láser
* *Omisión:* En el paso 4 se indica "laser cerrado", pero luego no se indica en qué momento abrirlo para medir Raman.
* *Procedimiento Correcto:* Una vez apagada la lámpara blanca y cerrado el diafragma, se debe abrir el obturador del láser correspondiente (ej. 532 nm) desde el control de hardware antes de pulsar `Live Raman` o `Capturar Espectro Único`.

### 4. Estado del Filtro Notch 532 nm (Rayleigh Rejection)
* *Omisión:* No se especifica la conmutación del filtro Notch.
* *Procedimiento Correcto:*
  - En la etapa de exploración con lámpara blanca, el flipper del Notch debe estar abajo (o retirado) para no filtrar la banda verde de la imagen de campo claro.
  - Al pasar a medir Raman con láser 532 nm, **el filtro Notch DEBE colocarse obligatoriamente en el camino óptico** antes de abrir el obturador láser, bloqueando la línea de bombeo elástica Rayleigh para permitir registrar los picos inelásticos Stokes a longitudes de onda mayores.

---

## 4. Registro de Defectos y Bugs Detectados en el Código (Bug Registry)

Durante la auditoría del código fuente asociado al flujo descripto, se descubrieron los siguientes bugs técnicos en el pipeline de datos:

### Bug 1 (Severidad: P0 - Crítica): Incompatibilidad de Columnas entre `static_raman.py` y `parse_andor_solis_file()` en `core/raman_engine.py` — [✅ RESUELTO]

* **Módulos Afectados:**
  [`pyspectrum/modules/static_raman.py`](file:///C:/Users/josel/Documents/Obsidian_Vault/printing3/pyspectrum/modules/static_raman.py) (línea 823) y [`core/raman_engine.py`](file:///C:/Users/josel/Documents/Obsidian_Vault/printing3/core/raman_engine.py) (línea 149).
* **Descripción del Defecto Original:**
  En `static_raman.py`, `save_spectrum_to_file()` exporta el archivo de texto con 3 columnas numéricas (`Wavelength_nm`, `Raman_Shift_cm-1`, `Counts_ADC`). Sin embargo, el parser unificado `parse_andor_solis_file()` asignaba `cnt = float(tokens[1])`, lo que provocaba que en archivos de 3 columnas el corrimiento Raman se interpretara como intensidad de cuentas, ignorando por completo la columna real de cuentas ADC.
* **Resolución Implementada:**
  En `core/raman_engine.py`, se actualizó la extracción numérica a:
  ```python
  x = float(tokens[0])
  cnt = float(tokens[-1])  # Toma la última columna como intensidad
  ```
  Adicionalmente se sanitizaron las claves de metadatos mediante `parts[0].strip().lstrip("#").strip()`, permitiendo parsear cabeceras con prefijo `# Key: val` sin `KeyError`. Validado con 10/10 tests unitarios en `tests/test_raman_engine.py`.

---

### Bug 2 (Severidad: P1 - Alta): `save_spectrum_to_file()` adquiere un cuadro nuevo en vez de guardar el espectro visualizado en pantalla — [✅ RESUELTO]

* **Módulo Afectado:**
  [`pyspectrum/modules/static_raman.py`](file:///C:/Users/josel/Documents/Obsidian_Vault/printing3/pyspectrum/modules/static_raman.py).
* **Descripción del Defecto Original:**
  Al pulsar `💾 Guardar Espectro (.txt)`, se consultaba `get_most_recent_image()`, lo que podía capturar un cuadro posterior a la adquisición congelada en pantalla o lanzar `IndexError: too many indices for array: array is 1-dimensional` si la cámara estaba en modo 1D.
* **Resolución Implementada:**
  El diálogo de guardado en `static_raman.py` empaqueta directamente en el diccionario de metadatos los vectores numéricos validados en pantalla:
  `"_raw_wl": self.raw_wl`, `"_raw_counts": self.raw_counts`, `"_processed_x": self.processed_x`, etc.
  `save_spectrum_to_file()` prioriza estos arreglos en memoria. Si no estuvieran disponibles, realiza una consulta defensiva comprobando `frame.ndim > 1` antes de promediar ejes, eliminando cualquier riesgo de excepción de indexación. Validado en `tests/test_pyspectrum_static_raman_modes.py`.

---

### Bug 3 (Severidad: P2 - Media): Concurrencia de la Controladora PI E-517 / E-727 entre `app.py` y `PySpectrum` — [✅ RESUELTO]

* **Módulos Afectados:**
  [`app.py`](file:///C:/Users/josel/Documents/Obsidian_Vault/printing3/app.py) y [`pyspectrum/window.py`](file:///C:/Users/josel/Documents/Obsidian_Vault/printing3/pyspectrum/window.py).
* **Descripción del Defecto Original:**
  Lanzar `app.py` y `pyspectrum.py` en procesos independientes generaba colisión en el puerto USB `PI_SERIAL = "0119048050"`, impidiendo la comunicación con la platina piezoeléctrica.
* **Resolución Implementada:**
  Se incorporó la acción `act_microscopio_derecho` en el menú `Herramientas` de `PySpectrumWindow`, invocando `app.create_app_satellite(parent=self)`. La ventana satélite del microscopio derecho comparte el bucle Qt y la sesión de hardware de PySpectrum sin duplicar conexiones ni bloquear el bus USB.

---

## 5. Matriz de Factibilidad por Paso Experimental

| Paso del Protocolo del Usuario | Factible en Código Actual | Requiere Acción Manual del Operador | Observaciones / Estado de Implementación |
|---|:---:|:---:|---|
| **1. Encender láser (shutter cerrado)** | ✅ SÍ | Sí (llave física) | Correcto. Mantener shutter cerrado en NIDAQ. |
| **2. Revisión con cámara Canon** | ✅ SÍ | Sí (`app.py` subyugado) | Usar lámpara halógena. Lanzar desde `Herramientas -> Microscopio Derecho`. |
| **3. Bajar espejo al espectrómetro** | ✅ SÍ | Sí (palanca microscopio) | Mirror Down desvía 100% al puerto lateral Shamrock. |
| **4. Verificar exposición, lámpara, láser cerrado** | ✅ SÍ | Sí | **Duda 1:** Live View muestra cuentas crudas ADC. Auto-contraste robusto compensa. |
| **5. Presionar Live (Pestaña Exploración)** | ✅ SÍ | No | Automatizado: `ShamrockSetShutter(DEVICE, 1)` abre al iniciar y `0` al detener. |
| **6. Centrado manual con platina micrométrica** | ✅ SÍ | Sí (tornillos mecánicos) | Correcto para ubicar partículas en campo de $100\,\mu\text{m}$. |
| **7. Comprobación platina con app.py** | ✅ SÍ | No | **Resuelto:** Integrado en menú Herramientas como ventana satélite en el mismo proceso. |
| **8. Verificar caída de láser en slit** | ✅ SÍ (Seguro) | Sí (espejos manuales) | **Protocolo Seguro:** Utilizar 2 filtros Notch manuales y flipper atenuador de bombeo. |
| **9. Mover a posición de interés** | ✅ SÍ | Sí (piezo PI) | Desplazar partícula al cruce de la mira vertical $X \approx 501.25\,\text{px}$. |
| **10. Determinar ROI vertical** | ✅ SÍ | No (automático) | Mover `roi_region` en Exploración. Publica automáticamente en `SpectroscopyContext`. |
| **11. Stop Live** | ✅ SÍ | No | Botón `⏹️ Detener Live View`. Cierra shutter de Shamrock automáticamente. |
| **12. Conmutar a Pestaña 2: Static Raman** | ✅ SÍ | No | Clic en pestaña 2 o atajo `Ctrl+2`. |
| **13. Configurar cámara (tiempo, gain, modo)** | ✅ SÍ | Sí | Seleccionar modo `Single-Track` o `Imagen 2D (Hardware ROI)` (ambos acotados al ROI). |
| **14. Configurar espectrógrafo y λ central** | ✅ SÍ | Sí | **Duda 2:** Cartel dinámico inferior reporta en tiempo real el rango cubierto en nm y cm⁻¹. |
| **15. Ver en Live la respuesta Raman** | ✅ SÍ | Sí | Shutter de Shamrock automatizado en `toggle_live`. Apagar halógena, colocar Notchs y abrir láser. |
| **16. Determinar si la medición es prometedora** | ✅ SÍ | No | Inspección visual con despiking, sustracción AsLS y telemetría de cursores en vivo. |
| **17. Capturar espectro único definitivo** | ✅ SÍ | Sí (subir tiempo) | Botón `📸 Capturar Espectro Único` (o `Ctrl+R`). Abre y cierra shutter en `finally`. |
| **18. Guardar espectro para análisis** | ✅ SÍ | No | **Bugs 1 y 2 Resueltos:** Guarda vectores en memoria sin excepciones y compatible con 3 cols. |
| **19. Análisis en Raman Analyzer / SIF Analyzer** | ✅ SÍ | Sí | Total compatibilidad con `parse_andor_solis_file()` y desconvolución Pseudo-Voigt. |
