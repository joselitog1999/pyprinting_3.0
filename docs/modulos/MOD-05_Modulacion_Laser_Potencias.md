# MOD-05: Modulación y Control de Láseres de Excitación 💡

**PyPrinting 3.0 — Suite de Nanofotónica y Control Instrumental**  
**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Manual de Usuario Canónico** | **Código:** `MOD-05` | **Nivel de Usuario:** Básico / Operador  
**Archivos Fuente Asociados:**
- [`modules/camera.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/modules/camera.py) (`Laser532Window`, `Laser532Backend`)
- [`core/shutters.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/core/shutters.py) (Control serie RS-232, obturadores y modulación analógica DAC ao2)

---

## 🔗 Matriz de Referencias Cruzadas

* **Reportes de Sistema Conexos:**
  * `[[SYS-203_Control_Comunicaciones_Laseres_RS232_SCPI]]`
  * `[[SYS-201_Seguridad_Optica_Watchdog_y_Obturadores]]`
  * `[[SYS-102_Senales_Slots_PyQt6_y_Temporizacion_DAQmx]]`
* **Fundamentos Científicos Asociados:**
  * `[[CAT-101_Protocolo_Operativo_Impresion_Fototermica_Grillas_2D]]`
  * `[[CAT-107_Cinetica_Captura_Fotodiodo_Time_Volt_Filtro_Nhold]]`
  * `[[CAT-109_Electrodinamica_Fuerzas_Opticas_y_Termoplasmonica_Printing]]`
* **Manuales de Usuario Conexos:**
  * `[[MOD-01_Microscopio_Derecho_App]]`
  * `[[MOD-02_Measurements_Printing_y_Dimeros]]`
  * `[[MOD-13_Hardware_Dashboard_y_Presets]]`

---

## 1. Resumen y Rol en el Sistema


El módulo **Modulación Láser 532 nm** proporciona el control analógico y digital sobre la fuente láser principal de bombeo óptico y termometría fototérmica ($\lambda = 532\ \text{nm}$, verde). 

> [!NOTE]
> **Desacoplamiento de Interfaz**: A fin de mantener una arquitectura limpia y evitar controles redundantes, el control analógico de tensión ($V_{\text{AO2}}$) reside exclusivamente en esta ventana flotante dedicada (`Laser532Window`). El dock `Shutters / Flipper` en la ventana principal de PyPrinting se enfoca exclusivamente en la conmutación digital rápida por relés TTL y en las políticas de seguridad del Watchdog.

Funciones principales:
- **Control Analógico de Potencia (AO2 NI-DAQmx)**: Ajuste fino de la tensión de modulación en el canal `Dev1/ao2` en el rango de $0.00\ \text{V}$ a $5.00\ \text{V}$.
- **Control de Obturador Rápido TTL**: Disparo del relé digital de obturación con tiempos de respuesta menores a $1\ \text{ms}$.
- **Calibración Potencia BFP vs Voltaje ($P_{\text{BFP}} \leftrightarrow V_{\text{AO2}}$)**: Interpolación de curvas de calibración para trabajar directamente en unidades de potencia óptica real ($\text{mW}$) en el Plano Focal Posterior (*Back Focal Plane*, BFP).

---

## 2. 🖼️ Maqueta de la Interfaz Visual (ASCII Layout)

```
┌────────────────────────────────────────────────────────────────────────┐
│  PyPrinting 3.0 — Control y Modulación Láser 532 nm          -  □  ×    │
├────────────────────────────────────────────────────────────────────────┤
│  CONTROL DE POTENCIA Y OBTURACIÓN                                      │
│                                                                        │
│   Obturador Láser 532 nm:   [ 🟢 SHUTTER ABIERTO (ON) ]               │
│                                                                        │
│   Voltaje de Modulación (AO2):                                         │
│   [ 2.500 ] V    [◄ -0.05V]  [───●───────────] 50.0%  [+0.05V ►]       │
│                                                                        │
│   Potencia Estimada en BFP:                                            │
│   [ 12.45 ] mW   (Curva de Calibración: Polinómica Grado 2)            │
├────────────────────────────────────────────────────────────────────────┤
│  CALIBRACIÓN POTENCIA VS VOLTAJE                                       │
│  [ 📂 Cargar Calibración ]  [ 💾 Guardar Calibración ]  [ 📊 Ver Curva ]│
│  Archivo Activo: Calibration_Power_532nm.txt                           │
├────────────────────────────────────────────────────────────────────────┤
│  🟢 DAQ Dev1/ao2 activo | Salida: 2.500 V | Estado Shutter: ABIERTO    │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 🎛️ Catálogo de Botones y Controles

| Control / Botón | Tipo de Widget | Rango / Valores | Descripción Técnica |
|---|---|---|---|
| `Shutter 532 Button` | `QPushButton` | `ABIERTO / CERRADO` | Conmuta la línea digital TTL del obturador del láser verde. |
| `Voltaje Slider` | `QSlider` | $0.00 - 5.00\ \text{V}$ | Modifica el nivel analógico de forma continua mediante `nidaqmx.Task.write`. |
| `Voltaje SpinBox` | `QDoubleSpinBox` | $0.000 - 5.000\ \text{V}$ | Entrada numérica precisa de voltaje con resolución de $1\ \text{mV}$. |
| `Potencia Edit` | `QLineEdit` | $0.0 - 100.0\ \text{mW}$ | Permite fijar directamente la potencia en mW y calcula el voltaje requerido. |
| `Cargar Calibración` | `QPushButton` | Archivo `.txt` | Importa una tabla de pares $(V_i, P_i)$ medida con sensor de potencia térmico. |

---

## 4. 📥 Archivos de Entrada que Solicita

1. **Archivo de Calibración de Potencia (`Calibration_Power_532nm.txt`)**:
   - *Formato*: Archivo de texto delimitado por tabuladores o comas con pares $[V_{\text{AO2}}, P_{\text{mW}}]$.
   - *Ejemplo*:
     ```
     # Calibracion Laser 532 nm BFP - PM100D Thorlabs
     # Voltaje(V)    Potencia(mW)
     0.000           0.00
     1.000           2.45
     2.000           8.12
     3.000           18.40
     4.000           32.10
     5.000           48.50
     ```

---

## 5. 📤 Archivos de Salida que Genera

1. **Archivo de Calibración Actualizado (`Calibration_Power_532nm.txt`)**:
   - Guarda la nueva curva calibrada con fecha y coeficiente de ajuste $R^2$.

---

## 6. ⚙️ Formulación de Calibración e Interpolación

La conversión entre el voltaje de comando $V$ y la potencia óptica $P$ en el BFP se realiza mediante ajuste polinomial de segundo orden:

$$P(V) = c_2 V^2 + c_1 V + c_0$$

Y la función inversa para fijar una potencia deseada $P_{\text{target}}$:
$$V(P_{\text{target}}) = \frac{-c_1 + \sqrt{c_1^2 - 4c_2(c_0 - P_{\text{target}})}}{2c_2}$$

---

## 7. ⚠️ Límites de Validez y Modos de Falla

| Condición de Borde (Fallo de Controlador / Láser) | Firma Experimental (Potenciómetro / Telemetría) | Acción Correctiva Física (Procedimiento en Laboratorio) |
| :--- | :--- | :--- |
| **Sobrevoltaje Analógico AO2 en Tarjeta NI-DAQmx** ($V_{\text{AO2}} > 5.00\ \text{V}$). | El controlador del láser entra en modo de protección contra sobrevoltaje o satura la emisión óptica a niveles peligrosos. | La GUI satura por software el comando a un límite rígido de $5.00\ \text{V}$ (o $4.50\ \text{V}$); verificar con voltímetro en bornes del BNC `ao2`. |
| **Inestabilidad Térmica del Láser DPSS Ventus 532 nm** (Tiempo de calentamiento $< 20\ \text{min}$). | Fluctuaciones de potencia óptica a alta frecuencia ($RMS > 5\%$) y saltos de modo longitudinal en las trazas fototérmicas basales. | Esperar al menos $20\ \text{minutos}$ tras encender la fuente láser para permitir el equilibrio térmico del diodo de bombeo y cristal no lineal (LBO). |
| **Descalibración de la Curva Potencia-Voltaje** por envejecimiento óptico o desalineación. | La potencia física real medida en el objetivo difiere en más de un $15\%$ del valor nominal mostrado en pantalla en mW. | Colocar el cabezal del medidor de potencia óptico (Thorlabs PM100D) en la platina y ejecutar la rutina de calibración multipunto ($0$ a $5\ \text{V}$). |

---

## 8. 🔗 Referencias Cruzadas
- [[MOD-01_Microscopio_Derecho_App]] — Control del escáner confocal y conmutación rápida de shutters.
- [[MOD-02_Measurements_Printing_y_Dimeros]] — Modulación de potencia en rutinas de impresión y dímeros.
- [[SYS-203_Control_Comunicaciones_Laseres_RS232_SCPI]] — Protocolos de comunicación serie RS-232 y comandos SCPI.
- [[SYS-201_Seguridad_Optica_Watchdog_y_Obturadores]] — Sistema de watchdog y seguridad de obturadores ópticos.
- [[CAT-109_Electrodinamica_Fuerzas_Opticas_y_Termoplasmonica_Printing]] — Electrodinámica y cálculo de absorción fototérmica.

