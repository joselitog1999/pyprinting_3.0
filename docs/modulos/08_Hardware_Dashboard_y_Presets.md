# 🔬 Módulo 08: Tablero de Seguridad de Hardware y Asistente de Presets

**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Archivos Fuente**: [`modules/hardware_dashboard.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/modules/hardware_dashboard.py) / [`modules/preset_wizard.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/modules/preset_wizard.py) / [`core/preset_manager.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/core/preset_manager.py)  
**Lanzador Rápido**: Atajo `Ctrl+H` o botón `🧙 Lanzar Asistente` desde la ventana de Impresión

---

## 1. 🏷️ Resumen y Rol en el Sistema

Este subsistema combina dos herramientas críticas para la confiabilidad y reproducibilidad experimental de **PyPrinting 3.0**:

1. **Tablero de Seguridad y Conexiones de Hardware (`hardware_dashboard.py` / `core/hardware_manager.py`)**:
   - Monitoreo en vivo del estado de los dispositivos físicos: Platina PI E-517/E-727, Placa NI-DAQmx PCIe-6323/USB-6343 (`Dev1`), Cámara Canon EOS 500D (EDSDK), Espectrógrafo Andor Shamrock SR-303i, Cámara Andor CCD (Espectroscopía), Relés de Obturadores TTL y Flipper Motorizado.
   - **Perfiles de Inicialización por Defecto**: Aislamiento selectivo de hardware por aplicación para evitar sobrecarga de bus USB y bloqueos de puertos.
   - **Aislamiento por Software (*Soft Mock Isolation*)**: Permite aislar o simular individualmente cualquier subsistema sin reiniciar la aplicación ni afectar a los demás dispositivos.
   - **Detección Rigurosa de Hardware vs. Mocks**: Eliminación total de falsos positivos `Conectado` mediante re-inspección forzada en el bus y liberación de handles DLL colgados.
   - **Detección de Bloqueo Exclusivo de Puerto USB**: Advierte si la platina PI o la cámara están tomadas por otro proceso o ventana activa de PyPrinting.
2. **Asistente Guiado de Presets Experimentales (`preset_wizard.py`)**:
   - Cuadro de diálogo multipaso (`QWizard`) que guía al investigador a través de 5 etapas para configurar, validar y guardar recetas experimentales en formato de texto plano `.txt`.

---

## 2. 🖼️ Maqueta de la Interfaz Visual (ASCII Layout)

### A. Tablero de Seguridad de Hardware
```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  PyPrinting 3.0 — Tablero de Conexiones y Seguridad de Hardware              -  □  ×   │
├────────────────────────────────────────────────────────────────────────────────────────┤
│  [ Perfil: PyPrinting ▼]  │  [ 🟢 3 Conectados | 🟡 0 Simulados | 🔴 3 Desconectados ] │
├────────────────────────────────────────────────────────────────────────────────────────┤
│  ESTADO DE CONECTIVIDAD, TELEMETRÍA Y ACCIONES EN CALIENTE                             │
│                                                                                        │
│  [🟢 ONLINE]  Platina Piezoeléctrica PI E-517 (USB '0119048050')                      │
│               Posición: (+25.400, +30.120, +15.000) µm  |  [X] Aislar  [ 🔌 Desconectar]│
│                                                                                        │
│  [🟢 ONLINE]  Tarjeta NI-DAQmx PCIe-6323 / USB-6343 (Dev1)                             │
│               Canales AI: 0..3  |  AO: 0..2  |  DO: port0/line0:7  |  [X] Aislar       │
│                                                                                        │
│  [🔴 OFFLINE] Cámara Réflex Canon EOS 500D (EDSDK)                                     │
│               Detalle: Desconectado por perfil por defecto (Disponible bajo demanda)    │
│               [ 🔌 Conectar ]  [ ] Aislar                                              │
│                                                                                        │
│  [🔴 OFFLINE] Espectrógrafo Andor Shamrock SR-303i                                     │
│               Detalle: Desconectado por perfil por defecto (Disponible bajo demanda)    │
│               [ 🔌 Conectar ]  [ ] Aislar                                              │
│                                                                                        │
│  [🔴 OFFLINE] Cámara Andor CCD (Espectroscopía)                                        │
│               Detalle: Desconectado por perfil por defecto (Disponible bajo demanda)    │
│               [ 🔌 Conectar ]  [ ] Aislar                                              │
│                                                                                        │
│  [ 🔄 RE-ESCANEAR TODO ]      [ 🔌 RECONECTAR TODO ]      [ 🧪 MODO SEGURO GLOBAL ]    │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### B. Asistente Guiado de Presets (`QWizard`)
```
┌────────────────────────────────────────────────────────────────────────┐
│  Asistente de Configuración de Presets Experimentales (Paso 2 de 5)    │
├────────────────────────────────────────────────────────────────────────┤
│  PASO 2: SELECCIÓN DE CRITERIO DE PARADA Y SENSIBILIDAD                │
│                                                                        │
│  Seleccioná el criterio de parada adecuado para tu tipo de muestra:    │
│  ( ) Modo 0: Salto Relativo Legacy (Muestras de alto contraste)        │
│  (●) Modo 1: Salto Relativo + Umbral Absoluto (V) & Anti-Paso [Rec.]   │
│  ( ) Modo 2: Derivada Temporal Adaptativa dI/dt (Crecimiento suave)    │
│  ( ) Modo 3: Calibración Confocal Raw Reescalada                       │
│  ( ) Modo 4: Criterio Híbrido Tri-Factor All-In-One                    │
│                                                                        │
│  Parámetros:                                                           │
│  • Umbral Relativo:   [ 1.50 ]  (Salto del 50% sobre el fondo)         │
│  • Umbral Absoluto:   [ 2.50 ] V (Detección instantánea a t=0)         │
│  • Pasos Anti-Paso:   [ 5    ] muestras a 1 kHz (5 ms sostenidos)      │
│                                                                        │
│  [ ◄ Atrás ]                          [ Siguiente ► ]   [ Cancelar ]   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 🎛️ Catálogo de Botones y Controles

| Control / Botón | Tipo de Widget | Función Técnica |
|---|---|---|
| `Selector de Perfil` | `QComboBox` | Conmuta entre `PyPrinting`, `PySpectrum`, `Cámara` y `Completo (All)`, aplicando la política de aislamiento instantáneo. |
| `Soft Disconnect` | `QPushButton` | Suspende las llamadas a la DLL/controlador y conmuta a mock/simulación sin cerrar la aplicación. |
| `Re-conectar / Conectar` | `QPushButton` | Inicializa bajo demanda la conexión USB/PCIe del dispositivo específico en caliente. |
| `Aislar (Soft Mock)` | `QCheckBox` | Bloquea el acceso físico al driver y suministra telemetría virtual para pruebas sin apagar el equipo. |
| `Re-escanear Todo` | `QPushButton` | Ejecuta un ciclo completo de descubrimiento de periféricos físicos liberando handles colgados. |
| `Modo Seguro Global`| `QPushButton` | Fuerza a toda la aplicación a operar en modo simulado para desarrollo o docencia. |
| `Wizard Siguiente` | `QPushButton` | Avanza a la siguiente etapa del asistente validando tipos numéricos y rangos físicos. |
| `Wizard Finalizar` | `QPushButton` | Escribe el archivo `.txt` en la carpeta `presets/` y lo selecciona en la GUI. |

---

## 4. 🚀 Perfiles de Inicialización de Hardware por Defecto

Para evitar la contienda por puertos serie/USB compartidos y acelerar el tiempo de arranque de cada herramienta, el sistema define cuatro perfiles predeterminados en [`core/hardware_manager.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/core/hardware_manager.py):

| Perfil | Aplicación Destino | Dispositivos Conectados por Defecto | Dispositivos Desconectados (Bajo Demanda) |
|---|---|---|---|
| **`pyprinting`** | [`app.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/app.py) | • Tarjeta NI-DAQmx (Dev1)<br>• Platina PI Piezo (E-517)<br>• Láser 532 nm (AO2) | • Cámara Réflex Canon EOS (EDSDK)<br>• Espectrógrafo Andor Shamrock<br>• Cámara Andor CCD |
| **`camera`** | [`camera.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/camera.py) | • Cámara Réflex Canon EOS (EDSDK) | • Platina PI Piezo<br>• Tarjeta NI-DAQmx<br>• Espectrógrafo Shamrock<br>• Cámara Andor CCD |
| **`pyspectrum`**| [`pyspectrum.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/pyspectrum.py) | • Platina PI Piezo (E-517)<br>• Tarjeta NI-DAQmx (Dev1)<br>• Espectrógrafo Shamrock<br>• Cámara Andor CCD | • Cámara Réflex Canon EOS (EDSDK) |
| **`all`** | Diagnósticos / Laboratorio Completo | • **Todos los dispositivos físicos** | Ninguno (Inspección total) |

> [!NOTE]
> **Conexión en Caliente (*Hot-Plug*)**: Si el usuario está trabajando en `PyPrinting` y necesita encender la cámara Canon o adquirir un espectro con Shamrock, no requiere reiniciar la app ni cambiar de perfil: basta pulsar el botón **`🔌 Conectar`** correspondiente en el Tablero o el botón de inicio de cámara para inicializar la conexión en caliente inmediatamente.

---

## 5. 🛡️ Diagnóstico de Conectividad y Telemetría de la Platina PI

### 5.1 Modo Virtual Transparente en Nanoposicionamiento
Históricamente, al encender la aplicación con la platina apagada o con cable USB desconectado, el controlador pasaba a modo virtual silencioso. La interfaz seguía mostrando números cambiando al pulsar las flechas de desplazamiento (`x ►`), creando la falsa impresión de que la platina física respondía.

A partir de la versión 3.0:
1. **Badge en Tiempo Real en el Dock de Nanoposicionamiento**:
   - `🟢 PI Física (SN: 0119048050)`: La platina responde a comandos GCS y verifica comunicación continua mediante consulta `qIDN()`.
   - `🟡 Modo Virtual (Desconectada)`: Advierte explícitamente que no hay movimiento mecánico real.
2. **Botón `🔌 Reconectar` Integrado**:
   - Permite encender la controladora E-517 en la mesa óptica y pulsar **`Reconectar`** directamente desde el panel de nanoposicionamiento, sin recargar la aplicación ni perder la calibración de la muestra.
3. **Consola Explicativa**:
   - Todo intento de movimiento en modo virtual imprime: `[PI VIRTUAL] MOV {'1': 50.0} (Platina física desconectada)`.

### 5.2 Prevención de Colisión de Puertos USB
El driver FTDI de Physik Instrumente y el SDK de Canon requieren acceso exclusivo al bus USB. Si el usuario intenta abrir el Tablero de Hardware o una segunda herramienta mientras la platina está tomada por la ventana principal de `PyPrinting`, el sistema detecta el error de contienda y despliega un diagnóstico claro:
`🔴 Desconectada — Puerto USB ocupado por otra ventana activa de PyPrinting` en lugar de reportar genéricamente que el dispositivo no existe.

---

## 6. 📥 Archivos de Entrada que Solicita

1. **Archivos de Preset Existentes (`presets/*.txt`)**:
   - Permite editar o clonar recetas experimentales previas.

---

## 5. 📤 Archivos de Salida que Genera

1. **Archivo de Preset Experimental (`presets/Nombre_del_Preset.txt`)**:
   - *Estructura estándar*:
     ```ini
     name=Oro_80nm_532nm_AltaPotencia
     description=Impresión rápida de nanopartículas de oro de 80nm sobre vidrio silanizado
     stop_mode=1
     umbral_rel=1.80
     umbral_abs=3.20
     umbral_min=0.00
     umbral_down=0.50
     slope_flat=0.05
     tmax=15.0
     n_hold=6
     steps_before=10
     steps_after=10
     autofocus_every=5
     shift_x=2.0
     shift_y=2.0
     dx=3.0
     dy=3.0
     scan_preprint=True
     drift_correction=True
     ```
2. **Reporte de Diagnóstico de Hardware (`hardware_diagnostic_report.txt`)**:
   - Registro de versiones de firmware, voltajes y estado de comunicación.

---

## 6. ⚙️ Flujo del Asistente QWizard

```mermaid
flowchart LR
    P1[Paso 1: Identificación y Láser] --> P2[Paso 2: Criterio de Parada]
    P2 --> P3[Paso 3: Geometría de Grilla]
    P3 --> P4[Paso 4: Autofoco y Deriva P0]
    P4 --> P5[Paso 5: Resumen y Guardado .txt]
    P5 --> F[Guardar en presets/ y Cargar en GUI]
```

---

## 7. ⚠️ Límites de Validez y Modos de Falla

| Condición de Borde (Fallo de Hardware / Preset) | Firma Experimental (Dashboard / Logs / Errores) | Acción Correctiva Física (Procedimiento en Laboratorio) |
| :--- | :--- | :--- |
| **Conflicto de Recursos NI-DAQmx** (`DAQError -200088: Resource already reserved`). | El botón de adquisición o escaneo arroja error en consola; el hardware NI-DAQmx no responde porque una tarea previa quedó abierta en un hilo huérfano. | Presionar `Reset DAQ Tasks` en el Tablero de Hardware para forzar la liberación de canales (`task.stop()` y `task.close()`); desconectar y reconectar el cable USB de la tarjeta si el driver persiste bloqueado. |
| **Carga de Preset Corrupto con Parámetros Fuera de Rango**. | Excepción `KeyError` o `ValueError` al cargar un preset; valores de desplazamiento o coordenadas de grilla que superan el límite piezo de $100\ \mu\text{m}$. | El gestor `preset_manager.py` rechaza automáticamente valores fuera de cota y restaura la plantilla base `factory_defaults.json`. Editar manualmente el archivo `.txt` con valores válidos. |
| **Falsa Detección en Caliente (*Hot Re-scan*) por Cable USB Dañado**. | El indicador del dispositivo parpadea entre `ONLINE` y `ERROR`; caídas aleatorias durante mediciones prolongadas. | Reemplazar el cable USB 2.0/3.0 de grado industrial blindado, evitar el uso de concentradores (*USB Hubs*) pasivos y conectar directamente a los puertos traseros del motherboard de la PC. |

---

## 8. 🔗 Referencias Cruzadas
- [📘 Manual de Usuario — Sección 8: Diagnóstico y Seguridad de Hardware](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/MANUAL_USUARIO.md#8-diagnóstico-y-seguridad-de-hardware-hardware-dashboard)
- [📘 Manual de Usuario — Sección 5.4: Gestor de Presets](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/docs/MANUAL_USUARIO.md#54-gestor-de-presets-y-asistente-de-configuración)
- [📑 Reporte de Robustez de Hardware (`reportes/sistema/Matriz_de_Riesgos_y_Robustez_PyPrinting3.md`)](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/reportes/sistema/Matriz_de_Riesgos_y_Robustez_PyPrinting3.md)
