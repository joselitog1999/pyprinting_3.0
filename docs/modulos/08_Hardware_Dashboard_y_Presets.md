# 🔬 Módulo 08: Tablero de Seguridad de Hardware y Asistente de Presets

**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Archivos Fuente**: [`modules/hardware_dashboard.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/modules/hardware_dashboard.py) / [`modules/preset_wizard.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/modules/preset_wizard.py) / [`core/preset_manager.py`](file:///c:/Users/josel/Documents/Obsidian_Vault/printing3/core/preset_manager.py)  
**Lanzador Rápido**: Atajo `Ctrl+H` o botón `🧙 Lanzar Asistente` desde la ventana de Impresión

---

## 1. 🏷️ Resumen y Rol en el Sistema

Este subsistema combina dos herramientas críticas para la confiabilidad y reproducibilidad experimental de **PyPrinting 3.0**:

1. **Tablero de Seguridad de Hardware (`hardware_dashboard.py`)**:
   - Monitoreo en vivo del estado de los 5 dispositivos físicos: Platina PI E-517/E-736, Placa NI-DAQmx PCIe-6323/USB-6343 (`Dev1`), Cámara Canon EOS 500D (EDSDK), Relés de Obturadores TTL y Flipper Motorizado.
   - **Aislamiento por Software (*Soft Isolation*)**: Permite desconectar o simular individualmente cualquier subsistema sin reiniciar la aplicación ni afectar a los demás dispositivos.
   - **Re-escaneo en Caliente (*Hot Re-scan*)**: Restablece la comunicación USB/PCIe tras reconectar un cable o encender un controlador.
2. **Asistente Guiado de Presets Experimentales (`preset_wizard.py`)**:
   - Cuadro de diálogo multipaso (`QWizard`) que guía al investigador a través de 5 etapas para configurar, validar y guardar recetas experimentales en formato de texto plano `.txt`.

---

## 2. 🖼️ Maqueta de la Interfaz Visual (ASCII Layout)

### A. Tablero de Seguridad de Hardware
```
┌────────────────────────────────────────────────────────────────────────┐
│  PyPrinting 3.0 — Tablero de Conexiones y Seguridad de Hardware-  □  × │
├────────────────────────────────────────────────────────────────────────┤
│  ESTADO DE CONECTIVIDAD Y TELEMETRÍA EN VIVO                           │
│                                                                        │
│  [🟢 ONLINE]  Platina Piezoeléctrica PI E-517 / E-736                  │
│               Puerto: COM3 / USB  |  Pos: (+25.400, +30.120, +15.000) µm│
│               [ 🔌 Desconectar (Soft) ]  [ 🔄 Re-conectar ]            │
│                                                                        │
│  [🟢 ONLINE]  Tarjeta NI-DAQmx PCIe-6323 / USB-6343 (Dev1)             │
│               Canales AI: 0,1,2,3  |  AO: 0,1,2  |  DO: port0/line0:7  │
│               [ 🔌 Desconectar (Soft) ]  [ 🔄 Re-conectar ]            │
│                                                                        │
│  [🟢 ONLINE]  Cámara Réflex Canon EOS 500D (EDSDK 64-bit)              │
│               Sensor: APS-C 15.1 MP  |  Batería: 85%  |  Live View: 28fps│
│               [ 🔌 Desconectar (Soft) ]  [ 🔄 Re-conectar ]            │
│                                                                        │
│  [🟢 ONLINE]  Obturadores Láser TTL y Flipper Motorizado               │
│               Relés activos: 532 nm Cerrado, 637 nm Cerrado, Fl: ABAJO  │
│                                                                        │
│  [ 🔄 RE-ESCANEAR TODO EL HARDWARE ]       [ 🧪 MODO SEGURO GLOBAL ]   │
└────────────────────────────────────────────────────────────────────────┘
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
| `Soft Disconnect` | `QPushButton` | Suspende las llamadas a la DLL/controlador y conmuta a mock/simulación sin cerrar la aplicación. |
| `Re-conectar` | `QPushButton` | Inicializa nuevamente la conexión USB/PCIe del dispositivo específico. |
| `Re-escanear Todo` | `QPushButton` | Ejecuta un ciclo completo de descubrimiento de periféricos físicos. |
| `Modo Seguro Global`| `QPushButton` | Fuerza a toda la aplicación a operar en modo simulado para desarrollo o docencia. |
| `Wizard Siguiente` | `QPushButton` | Avanza a la siguiente etapa del asistente validando tipos numéricos y rangos físicos. |
| `Wizard Finalizar` | `QPushButton` | Escribe el archivo `.txt` en la carpeta `presets/` y lo selecciona en la GUI. |

---

## 4. 📥 Archivos de Entrada que Solicita

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
