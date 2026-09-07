# 🔬 Reporte Estratégico: Análisis Profundo de Andor Solis vs. PySpectrum 3.0

**Evaluación Comparativa Honesta, Ángulos No Obvios y Hoja de Ruta para Potenciar la Espectroscopía en PyPrinting**  
*Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)*  
*Autor:* José Luis González Peñafiel (*Becario Doctoral CONICET*)  
*Fecha:* Septiembre 2026  

---

## 1. 🔍 Anatomía y Arquitectura de Andor Solis

**Andor Solis** es el software propietario de adquisición y análisis desarrollado por Oxford Instruments / Andor Technology para su línea de detectores científicos (iXon, Newton, iDus, iKon, Zyla) y espectrógrafos de la serie Shamrock (SR-163, SR-303i, SR-500i, Kymera).

### 1.1 ¿Cómo funciona Solis bajo el capó?
Solis es esencialmente una aplicación de escritorio Windows (construida sobre Win32 / MFC con arquitectura MDI clásica de ventanas flotantes) que actúa como envoltorio gráfico sobre dos bibliotecas dinámicas de enlace en C/C++:
1. **`atmcd64d.dll` (Andor SDK 2)**: Control de bajo nivel de cámaras CCD / EMCCD (relojes verticales/horizontales, amplificadores de salida, ganancia EM RealGain™, enfriamiento Peltier, lectura FVB y tiempos de exposición precisos).
2. **`ShamrockCIF.dll` (Shamrock SDK)**: Control de motores paso a paso de redes de difracción, husillos de longitud de onda, ranuras micrométricas bilaterales y espejos rebatibles.

Cualquier función que Solis ejecuta en su interfaz gráfica está implementada mediante llamadas a estas DLLs. Por consiguiente, **el 100% de las funciones físicas de Solis pueden ser invocadas y mejoradas desde Python**.

---

## 2. ⚖️ Comparación Honesta: Andor Solis vs. PySpectrum 3.0

| Dimensión / Módulo | Andor Solis (Propietario Oxford Instruments) | PySpectrum / PyPrinting 3.0 (Nativo Python) | Balance Crítico y Veredicto |
| :--- | :--- | :--- | :--- |
| **Arquitectura de Software** | Monolito cerrado C++ (Win32/MFC), dependiente de licencias dongle/software. | Modular, código abierto, desacoplado en GUI (PyQt6), drivers Ctypes y motores numéricos. | **Gana PySpectrum** en flexibilidad, extensibilidad y mantenimiento futuro. |
| **Sincronización con Nanoposicionamiento** | **Nula (Ciego a la Muestra)**: Solis no tiene interfaz para platinas piezoeléctricas (PI E-517), ni sabe dónde está la muestra. | **Total e Integrada**: Comparte el bus de hardware con PyPrinting. Mapeo hiperespectral confocal 3D $(X, Y, \lambda)$ en tiempo real. | **Victoria decisiva de PySpectrum**: La nanofotónica requiere correlacionar espectro con posición sub-nanométrica. |
| **Sinergia con Optical Printing** | **Inexistente**: No puede controlar obturadores láser NI-DAQmx ni sincronizarse con fotodiodos iSCAT. | **Nativa**: Puede medir fotoluminiscencia o Raman antes, durante y después de imprimir cada nanopartícula individual. | **Victoria decisiva de PySpectrum**: Cierra el ciclo "Impresión $\to$ Caracterización in-situ". |
| **Formatos y Flujo de Datos** | Archivos binarios propietarios `.sif` (requiere conversores externos o scripts como `sifreader`). | Contenedores científicos abiertos HDF5 (`.h5`), arrays NumPy (`.npy`), TIFF 16-bit, CSV y portapapeles. | **Gana PySpectrum**: Integración directa con `numpy`, `scipy`, `pandas` y herramientas de ML. |
| **Modo de Lectura CCD (FVB)** | **Hardware FVB Puro**: Agrupa electrones en el registro serie antes de digitalizar (mínimo ruido). | Actualmente toma frame 2D y promedia filas en software (`np.mean(frame, axis=0)`). | **Gana Solis**: El binning en software arrastra el ruido de lectura de las 1000 filas ($\sqrt{1000} \approx 31.6\times$). |
| **Procesamiento Espectral en Vivo** | Filtros fijos y rígidos. Despiking básico y sustracción de fondo estática. | Algoritmos quimiométricos avanzados en vivo: AsLS, AirPLS, ModPoly, PCA en tiempo real, termometría Stokes/Anti-Stokes. | **Gana PySpectrum**: La quimiometría y termometría en vivo en Python superan con creces las herramientas de Solis. |
| **Cosido de Espectros (Step & Glue)** | Algoritmo calibrado con corrección de eficiencia relativa (REC) y compensación angular de red. | Algoritmo propio `glue_steps` con solapamiento y calibración de lámpara halógena. | **Empate con ventaja de Solis en velocidad**: PySpectrum puede alcanzar la misma precisión mejorando el blending. |
| **Sincronización de Shutter** | Disparo por hardware TTL interno de la cámara (sincronización a nivel de microsegundo). | Shutter externo comandado por NI-DAQmx vía software (latencia USB/OS de ~10–20 ms). | **Gana Solis**: El shutter por hardware previene fotoblanqueo durante tiempos muertos de lectura. |
| **Automatización y Scripts** | "Andor Basic": lenguaje arcaico tipo Pascal/BASIC de los 90, sin soporte de librerías modernas. | Python puro: threads concurrentes, asyncio, librerías científicas, redes neuronales, etc. | **Victoria aplastante de PySpectrum**. |

---

## 3. 💡 Ángulos No Obvios que Revela la Comparación

### Ángulo 1: El "Full Vertical Binning" (FVB) a nivel de Hardware vs. Software
En espectroscopía de fotones débiles (como Raman de nanopartícula única o luminiscencia Anti-Stokes):
- En **Solis (FVB Hardware)**: La cámara transfiere verticalmente los paquetes de electrones de toda la columna del CCD hacia el registro serie de lectura *antes* de pasarlos por el preamplificador y el convertidor A/D. **El ruido de lectura ($e^-$ rms) se paga una sola vez por columna**, independientemente de la altura del chip.
- En **binning por software (Image Mode 2D $\to$ `axis=0`)**: Cada fila vertical se digitaliza independientemente. Si el sensor tiene $1002$ filas, se digitalizan $1002$ muestras por columna y se suman en RAM. La varianza de ruido se multiplica por $1002$, resultando en un ruido de lectura **$\approx 31.6$ veces mayor**, hundiendo la relación señal-ruido ($\text{SNR}$).
- *Oportunidad*: Implementar el modo FVB nativo de `atmcd64d.dll` (`SetReadMode(0)`) en PySpectrum para espectros 1D, reservando el modo imagen 2D (`SetReadMode(4)`) únicamente para alineación óptica de la ranura.

### Ángulo 2: El Sincronismo Shutter-Trigger por Hardware TTL
En Solis, la cámara iXon3 controla su propio obturador mediante un pulso eléctrico TTL emitido por su conector trasero (*Shutter Output*), el cual abre el obturador exactamente cuando la matriz inicia la integración y lo cierra cuando concluye, compensando los tiempos de apertura mecánica (20–30 ms).  
En PySpectrum, si el obturador lo abre la NI-DAQmx por comando USB antes de ordenar la captura a la cámara, la muestra sufre **fotocalentamiento o fotoblanqueo innecesario** durante la latencia del sistema operativo. Integrar el control del obturador a través del trigger de la cámara o coordinar los tiempos en hardware resuelve esta deriva.

### Ángulo 3: Calibración X-Axis Polinomial de Fábrica vs. Regresión Lineal
Solis no asume que la dispersión espectral sea lineal ($\Delta \lambda \neq \text{cte}$). La ecuación de la red Czerny-Turner proyecta longitudes de onda en un plano focal curvo, siguiendo un polinomio cúbico:
$$\lambda(\text{píxel}) = c_0 + c_1 \cdot \text{px} + c_2 \cdot \text{px}^2 + c_3 \cdot \text{px}^3$$
Solis lee estos coeficientes $c_0, c_1, c_2, c_3$ directamente de la memoria EEPROM del espectrógrafo mediante la función del SDK:
`ShamrockGetPixelCalibrationCoefficients(device, &A, &B, &C, &D)`  
Importar esta llamada directa en `shamrock_driver.py` proporciona la calibración micrométrica exacta garantizada por Andor para cualquier longitud de onda central y red sin necesidad de recalibrar manualmente.

### Ángulo 4: Despiking de Rayos Cósmicos (L.A.Cosmic vs. Filtro Solis)
El filtro de rayos cósmicos de Solis es un simple filtro de vecinos más cercanos o resta de cuadros consecutivos. En espectroscopía Raman de alta resolución, estos filtros suelen mutilar picos estrechos legítimos (como el fonón del Silicio a $520.7\text{ cm}^{-1}$). En Python podemos implementar el algoritmo **L.A.Cosmic** (*Laplacian Cosmic Ray Rejection*, van Dokkum), que discrimina rayos cósmicos por su gradiente laplaciano sub-pixel sin tocar los picos espectrales reales.

### Ángulo 5: Multi-Track y Espectroscopía Bicolor Simultánea
Solis permite definir varios "Tracks" o franjas horizontales en el CCD. Dado que el espectrógrafo Shamrock 500i es astigmáticamente corregido en el eje vertical:
- En la fila vertical $Y = 300$, se puede focalizar el haz reflejado por el divisor (referencia del láser).
- En la fila vertical $Y = 700$, se enfoca la emisión de la nanopartícula.
- Ambos espectros se pueden leer simultáneamente en el mismo ciclo del CCD, permitiendo **corrección de fluctuación de potencia láser en tiempo real espectro a espectro**.

---

## 4. 🚀 Funciones Concretas a Importar y Potenciar en PySpectrum / PyPrinting

```
                                      HOJA DE RUTA DE EVOLUCIÓN
                                                  │
                 ┌────────────────────────────────┼────────────────────────────────┐
                 ▼                                ▼                                ▼
         MODOS DE CÁMARA                  ÓPTICA & CALIBRACIÓN             SINERGIA EXPERIMENTAL
       (atmcd64d.dll SDK)                 (ShamrockCIF.dll)                (PyPrinting Core)
                 │                                │                                │
    • FVB Hardware (ultra-SNR)       • Coeficientes cúbicos EEPROM    • Loop Impresión -> Espectro
    • Imagen 2D (Modo Alineación)    • Apertura dinámica de Slit      • Mapeo Hiperespectral 3D
    • Shutter TTL sincronizado       • Step & Glue con Sigmoide       • Termometría Stokes/Anti-Stokes
```

### 1. Conmutación Rápida "Modo Alineación" vs. "Modo Espectro"
- **Modo Alineación (2D Image View)**: Abre la ranura a $2500\,\mu\text{m}$, coloca la red en orden cero (espejo) o longitud de onda central, y adquiere imágenes 2D rápidas a 20 FPS. Permite al usuario ver la mancha difractiva de la nanopartícula alineada exactamente en el centro de la rendija.
- **Modo Espectro (FVB)**: Con un solo clic, cierra la rendija a $50\,\mu\text{m}$, selecciona la red de $1200\text{ l/mm}$ o $150\text{ l/mm}$, activa el modo **Full Vertical Binning (FVB)** en hardware y adquiere con máxima relación señal-ruido.

### 2. Extracción de Coeficientes de Calibración de la EEPROM
Implementar en `shamrock_driver.py` la llamada a `ShamrockGetPixelCalibrationCoefficients`. Esto elimina cualquier discrepancia entre el eje de longitud de onda de PySpectrum y el de Andor Solis, garantizando concordancia absoluta al $100\%$.

### 3. Step & Glue Mejorado con Blending Sigmoideo
El cosido de Solis utiliza corrección de viñeteo en los bordes de la red. En `pyspectrum/calibration/halogen_lamp.py`, podemos reemplazar el corte abrupto por una función de ponderación sigmoidea suave (*cross-fade* ponderado):
$$w(x) = \frac{1}{1 + e^{-(x - x_{\text{mid}})/\sigma}}$$
Esto elimina escalones de intensidad en zonas de solapamiento donde la eficiencia de la red decae en las esquinas del CCD.

### 4. Automatización del Ciclo "Print & Probe" en PyPrinting
La mayor debilidad de Solis es que no sabe qué ocurre en el microscopio. PyPrinting puede incorporar una macro automática:
1. Imprimir nanopartícula o dímero plasmónico en $(x_i, y_i, z_i)$.
2. Conmutar el espejo rebatible (`down_flipper()`).
3. Disparar adquisición FVB de fotoluminiscencia o Raman.
4. Ajustar la resonancia plasmónica ($\lambda_{\max}$) en vivo mediante ajuste analítico.
5. Guardar el espectro y los parámetros del fit directamente en el contenedor HDF5 de la grilla.

---

*Documento técnico de análisis estratégico elaborado para el desarrollo de la Suite PyPrinting 3.0.*
