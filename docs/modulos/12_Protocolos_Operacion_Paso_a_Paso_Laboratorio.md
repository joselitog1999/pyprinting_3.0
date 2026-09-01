# 📋 Módulo 12: Procedimientos Operativos Estandarizados (SOP) y Protocolos Paso a Paso

**Suite PyPrinting 3.0 — Laboratorio de Nanofotónica (INS-UNSAM / CONICET)**  
*Documento de Referencia Técnica y Protocolo Operativo N° 12*  
*Autor: José Luis González Peñafiel (Becario Doctoral CONICET)*  
*Ubicación*: `docs/modulos/12_Protocolos_Operacion_Paso_a_Paso_Laboratorio.md`

---

## 📖 Índice de Protocolos
1. [Fase 1: Pre-Vuelo y Encendido del Hardware](#1-fase-1-pre-vuelo-y-encendido-del-hardware)
2. [Fase 2: Preparación de la Muestra Coloidal y Celda Microfluídica](#2-fase-2-preparación-de-la-muestra-coloidal-y-celda-microfluídica)
3. [Fase 3: Montaje Óptico y Calibración Inicial en PyPrinting 3.0](#3-fase-3-montaje-óptico-y-calibración-inicial-en-pyprinting-30)
4. [Fase 4: Ejecución de Impresión Óptica (Optical Printing) Monomaterial](#4-fase-4-ejecución-de-impresión-óptica-optical-printing-monomaterial)
5. [Fase 5: Nanofabricación Secuencial Multi-Material con Partícula Ancla ($P_0$)](#5-fase-5-nanofabricación-secuencial-multi-material-con-partícula-ancla-p_0)
6. [Fase 6: Caracterización Espectral In-Situ con PySpectrum 3.0](#6-fase-6-caracterización-espectral-in-situ-con-pyspectrum-30)
7. [Fase 7: Apagado Seguro y Mantenimiento del Sistema](#7-fase-7-apagado-seguro-y-mantenimiento-del-sistema)
8. [Árbol Rápido de Diagnóstico y Recuperación de Fallos (Quick Troubleshooting)](#8-árbol-rápido-de-diagnóstico-y-recuperación-de-fallos-quick-troubleshooting)

---

## 1. Fase 1: Pre-Vuelo y Encendido del Hardware

```
[Mesa Antivibratoria] ──► [Encendido Láseres] ──► [Chasis NI-DAQmx] ──► [Controlador PI E-517] ──► [PyPrinting 3.0]
     Presión 4-6 bar       Calentamiento 20 min      Dispositivo Dev1       Canales X/Y/Z Online       Lanzador Principal
```

### Protocolo Paso a Paso:
1. **Mesa Óptica Antivibratoria**:
   - Verificar que el compresor de aire mantenga los pistones neumáticos presurizados a $4 - 6\ \text{bar}$ y que la mesa esté flotando libremente sin tocar los topes mecánicos.
2. **Fuentes Láser**:
   - **Láser Verde $532\ \text{nm}$ (Impresión Óptica)**: Encender la fuente de alimentación y permitir un período de estabilización térmica de **$20\ \text{minutos}$** para evitar fluctuaciones de potencia y ruido de modo longitudinal (*pointing stability* $< 5\ \mu\text{rad}$).
   - **Láser Infrarrojo $808\ \text{nm} / 1064\ \text{nm}$ (Pinzas Ópticas IR)**: Encender y ajustar corriente base.
   - **Láser Rojo $637\ \text{nm}$ / Amarillo $592\ \text{nm}$**: Encender si se realizarán mediciones confocales multiespectrales.
3. **Electrónica y Adquisición de Datos**:
   - Encender el chasis **National Instruments NI-DAQmx** (`PCIe-6323` o `USB-6343`, identificado como `Dev1`).
   - Encender la controladora de platina piezoeléctrica **Physik Instrumente (PI E-517 / E-736)**. Comprobar que los tres canales piezoeléctricos $(1: X, 2: Y, 3: Z)$ se encuentren en la posición central de reposo ($50.0\ \mu\text{m}, 50.0\ \mu\text{m}, 10.0\ \mu\text{m}$).
4. **Cámara Réflex Canon EOS 500D**:
   - Colocar el dial de la cámara en modo **Manual (M)**.
   - Conectar el cable USB de alta velocidad al ordenador.
   - Encender la cámara (*Power ON*).
5. **Inicio del Entorno de Software**:
   - Abrir una terminal o acceso directo y ejecutar el lanzador principal:
     ```bash
     python main.py
     ```
   - Verificar en la barra superior que el selector esté en **`Modo Laboratorio Real`** (`PYPRINTING_SAFE=0`) y que la tarjeta de estado muestre `PI: Online`, `NI-DAQ: Online`, `Cámara: Online`.

---

## 2. Fase 2: Preparación de la Muestra Coloidal y Celda Microfluídica

```
┌────────────────────────────────────────────────────────┐
│             ESTRUCTURA DE LA CÁMARA FLUIDICA           │
│                                                        │
│   Portaobjetos de Vidrio Superior (Grasa Sellado)     │
│   ══════════════════════════════════════════════════   │
│   ░░░░ Canal de Fluido con Coloides AuNPs ░░░░░░░░░░   │  Espaciador 100 µm
│   ──────────────────────────────────────────────────   │
│   Cubreobjetos #1.5 Funcionalizado con APTES (-NH3+)   │
│   ══════════════════════════════════════════════════   │
│                      ▲                                 │
│                      │ Aceite Inmersión n=1.518        │
│                 [OBJETIVO 100x]                        │
└────────────────────────────────────────────────────────┘
```

### Protocolo de Preparación:
1. **Limpieza de Cubreobjetos de Vidrio (#1.5, $170\ \mu\text{m}$ de espesor)**:
   - Lavar con solución Piranha ($\text{H}_2\text{SO}_4:\text{H}_2\text{O}_2 = 3:1$) durante $30\ \text{minutos}$ o baño ultrasónico secuencial en Acetona $\to$ Isopropanol $\to$ Agua Milli-Q ($10\ \text{minutos}$ cada uno).
   - Secar con flujo laminar de gas nitrógeno puro ($\text{N}_2$).
2. **Silanización con APTES (Carga Positiva para Fijar AuNPs-Citrato)**:
   - Sumergir el cubreobjetos en una solución al $1\%\ \text{v/v}$ de **3-Aminopropiltrietoxisilano (APTES)** en etanol absoluto durante $15\ \text{minutos}$.
   - Enjuagar profusamente con etanol absoluto y agua Milli-Q para remover monómeros no enlazados.
   - Curar en estufa a $100\ ^\circ\text{C}$ durante $15\ \text{minutos}$ para consolidar los enlaces covalentes $\text{Si-O-Si}$.
3. **Ensamblado de la Celda de Fluido**:
   - Colocar dos tiras de Parafilm o cinta doble faz de $100\ \mu\text{m}$ como espaciadores sobre el portaobjetos soporte.
   - Colocar el cubreobjetos funcionalizado encima, formando un microcanal de $\sim 20 - 50\ \mu\text{L}$.
4. **Inyección de la Solución Coloidal**:
   - Diluir la solución stock de AuNPs ($60\ \text{nm}$, citrato) en agua Milli-Q hasta una concentración de trabajo de $C \approx 10^9 - 10^{10}\ \text{partículas}/\text{mL}$ (Absorbancia $\text{DO} \sim 0.01 - 0.05$ a $535\ \text{nm}$).
   - Inyectar $30\ \mu\text{L}$ de la suspensión por capilaridad en el canal.
   - Sellar ambos extremos con grasa de alto vacío para evitar corrientes de evaporación convectiva.

---

## 3. Fase 3: Montaje Óptico y Calibración Inicial en PyPrinting 3.0

1. **Colocación de Aceite de Inmersión**:
   - Depositar una única gota limpia y sin burbujas de **aceite de inmersión ($n=1.518$)** en la lente frontal del objetivo $100\times / \text{NA}=1.40$.
   - Fijar la muestra sobre el soporte de la platina piezoeléctrica PI con las pinzas magnéticas.
2. **Detección de la Interfaz Vidrio-Agua**:
   - En `app.py`, ir al dock **`Focus z`**.
   - Hacer clic en `Scan Z Interfaz` ($10\ \text{Hz}$, rango $5\ \mu\text{m}$).
   - Identificar el pico máximo de reflexión Fresnel de la interfaz vidrio-agua ($R \approx 0.4\%$). Fijar el punto cero de referencia axial ($Z_0 = 0.0\ \mu\text{m}$).
3. **Caracterización de PSF y Alineación Óptica**:
   - Abrir **`psf_analyzer.py`** desde el menú `Tools -> PSF Analyzer` (`Ctrl+P`).
   - Realizar un escaneo confocal $2\ \mu\text{m} \times 2\ \mu\text{m}$ sobre una nanopartícula fijada aislada.
   - Ajustar el modelo Gaussiano 2D. Verificar que la cintura focal cumpla:
     $$w_0 \le \frac{0.61 \lambda}{\text{NA}} \approx \frac{0.61 \times 532\ \text{nm}}{1.40} \approx 231\ \text{nm}$$
   - Comprobar que la elipticidad sea $< 1.15$ y que no existan aberraciones comáticas ni astigmáticas apreciables.

---

## 4. Fase 4: Ejecución de Impresión Óptica Monomaterial

```
[Diseñador 2D] ──► [Exportar .txt] ──► [Measurements] ──► [Fijar P0] ──► [Impresión Auto] ──► [Grilla Lista]
 grid_generator     Recipe.txt          Load Grid (.txt)    Imprime Nodo 0     Deriva & ETA        34 Partículas
```

### Protocolo de Impresión:
1. **Generar la Grilla**:
   - Abrir el **Diseñador de Redes 2D** (`grid_generator.py`).
   - Diseñar la geometría deseada (e.g. *Hexagonal $a=3.0\ \mu\text{m}$ contenida en Hexágono de apotema $a_p=6.0\ \mu\text{m}$*).
   - Fijar `Distancia Mínima d_min = 0.5 µm` para asegurar exclusión física.
   - Exportar con **`💾 Exportar .txt Unificado`** como `Hex_ap6um_a3um.txt`.
2. **Cargar en la Suite de Impresión**:
   - En `app.py`, abrir la ventana de mediciones (`Ctrl+M` o menú `Measurements -> Printing`).
   - Hacer clic en el botón **`Load grid`** y seleccionar el archivo `Hex_ap6um_a3um.txt`.
3. **Configurar Parámetros de Impresión**:
   - **Potencia Láser 532 nm**: Ajustar en el dock `Laser 532` a $V_{\text{AO2}} = 0.80\ \text{V}$ ($P_{\text{sample}} \approx 3.5\ \text{mW}$).
   - **Criterio de Parada**: Seleccionar **`Modo 0 (Threshold Clásico)`** o **`Modo 1 (Salto Diferencial de Derivada)`** con umbral $\Delta V = 0.15\ \text{V}$.
   - **Tiempo de Exposición de Seguridad ($T_{\text{max}}$)**: Fijar en $10.0\ \text{s}$.
4. **Lanzar la Secuencia Automatizada**:
   - Presionar **`▶ Start Printing`**.
   - El sistema moverá la platina PI secuencialmente en patrón de Serpiente nodo por nodo.
   - El obturador láser se abrirá en cada nodo; al impactar e inmovilizarse la nanopartícula, el salto de fotodiodo cerrará el obturador en $< 2\ \text{ms}$, avanzando inmediatamente al siguiente nodo.
   - Monitorear el tiempo restante estimado (**ETA**) y la velocidad de deriva calculada en vivo en la barra de estado.

---

## 5. Fase 5: Nanofabricación Secuencial Multi-Material con Partícula Ancla ($P_0$)

Para imprimir redes complejas compuestas por dos o tres materiales distintos (e.g., dímeros Au-Ag, redes de Nitruro de Boro h-BN con sitios B de oro y N de plata):

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 PROTOCOLO MULTI-MATERIAL CON PARTÍCULA ANCLA                │
│                                                                             │
│  [PASE 1: Au 60nm]                                                          │
│  1. Imprime Partícula Ancla P0 ⭐ en (-6.5, -6.5 µm).                       │
│  2. Imprime todos los sitios de Material 1 (Au 60nm).                       │
│  3. Lava el microcanal con Agua Milli-Q (Remueve Au libre).                 │
│                                                                             │
│  [PASE 2: Ag 40nm]                                                          │
│  4. Inyecta coloide de Material 2 (Ag 40nm).                                │
│  5. Re-cuadratura confocal en P0 ⭐ (Corrige deriva mecánica total).        │
│  6. Imprime todos los sitios de Material 2 (Ag 40nm).                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

1. **Exportar Paquete Multi-Paso**:
   - En `grid_generator.py`, configurar los materiales correspondientes para cada átomo de la celda en `⚛️ Base Atómica`.
   - Hacer clic en **`📦 Paquete Receta Multi-Paso (P0)`**. Se generarán `Pass1_Material_1_ref_P0.txt` y `Pass2_Material_2_ref_P0.txt`.
2. **Ejecutar Pase 1 (Material 1 — Au 60nm)**:
   - Cargar `Pass1_Material_1_ref_P0.txt` en `Measurements`.
   - Iniciar la impresión. El nodo 0 imprimirá la **Partícula Ancla $P_0$** y luego completará todos los sitios del Material 1.
3. **Lavado y Cambio de Coloide**:
   - Sin mover mecánicamente el cubreobjetos, hacer circular $100\ \mu\text{L}$ de agua Milli-Q por el canal para eliminar las AuNPs en suspensión.
   - Inyectar $30\ \mu\text{L}$ del coloide secundario (AgNPs $40\ \text{nm}$).
4. **Re-Cuadratura y Ejecución del Pase 2 (Material 2 — Ag 40nm)**:
   - Cargar `Pass2_Material_2_ref_P0.txt`.
   - Realizar un micro-escaneo confocal $1\ \mu\text{m} \times 1\ \mu\text{m}$ sobre las coordenadas de $P_0$. El software re-centrará automáticamente el origen de coordenadas sobre el centroide sub-nanométrico de $P_0$, anulando cualquier deriva acumulada durante el cambio de fluido.
   - Ejecutar la impresión del Pase 2.

---

## 6. Fase 6: Caracterización Espectral In-Situ con PySpectrum 3.0

Una vez finalizada la nanofabricación, caracterizar espectralmente cada nanopartícula o dímero plasmónico:

1. **Abrir PySpectrum 3.0**:
   - En `app.py`, presionar `Ctrl+S` o abrir desde el lanzador `main.py`.
2. **Calibración de Fondo y Lámpara Halógena**:
   - Encender la lámpara halógena de campo oscuro.
   - Bloquear el haz con el obturador y hacer clic en **`Capturar Espectro Oscuro (Dark Spectrum)`** para corregir la corriente oscura de la cámara CCD Andor.
   - Cargar el perfil de calibración de lámpara halógena (`lamparaIR_grade_2.txt`).
3. **Medición de Resonancia Plasmónica (LSPR)**:
   - Centrar confocalmente la platina PI sobre una partícula impresa.
   - Seleccionar el rango de longitudes de onda deseado ($450 - 850\ \text{nm}$) con el modo **Step & Glue**.
   - Presionar **`Adquirir Espectro Extinción/Dispersión`**.
   - Ajustar el pico LSPR mediante el modelo polinomial SPR integrado para determinar la longitud de onda de resonancia ($\lambda_{\text{max}}$) y el ancho a media altura ($\text{FWHM}$).

---

## 7. Fase 7: Apagado Seguro y Mantenimiento del Sistema

1. **Seguridad de Emisión Láser**:
   - Cerrar todos los obturadores mecánicos (`Close All Shutters`).
   - Reducir a $0.0\ \text{V}$ el voltaje de modulación analógica del láser 532 nm.
   - Apagar las llaves de emisión de todos los láseres.
2. **Retiro y Limpieza de la Muestra**:
   - Bajar la platina piezoeléctrica en Z ($Z = 0.0\ \mu\text{m}$) mediante el control macrométrico para separar el cubreobjetos del objetivo.
   - Retirar la celda de fluido.
   - **Limpieza del Objetivo**: Limpiar inmediatamente el aceite de inmersión de la lente frontal utilizando papel especial para ópticas (*Lens Paper*) humedecido con unas gotas de alcohol isopropílico o etanol anhidro de grado espectroscópico. *Nunca usar acetona ni papel tisú común.*
3. **Apagado de Instrumentos**:
   - Cerrar las sesiones de PySpectrum y PyPrinting.
   - Apagar la controladora PI E-517, el chasis NI-DAQmx y la cámara réflex Canon.

---

## 8. Árbol Rápido de Diagnóstico y Recuperación de Fallos

```
¿Qué problema ocurre?
├── [El obturador láser no abre]
│     ├── Verificar que SAFE_MODE esté en 0 (Modo Real).
│     ├── Comprobar cable BNC entre salida digital DO0/P0.0 de NI-DAQ y driver del obturador.
│     └── Revisar si el voltaje analógico AO2 está fijado en 0.0 V (abrir Laser532Window).
│
├── [La nanopartícula no se imprime tras > 10 segundos]
│     ├── Concentración coloidal demasiado baja (inocular muestra más concentrada).
│     ├── Superficie del vidrio sin carga positiva (repetir silanización con APTES).
│     └── Foco láser desfasado en Z (re-calibrar interfaz vidrio-agua en dock Focus z).
│
├── [Aparece una burbuja gigante que distorsiona la imagen]
│     ├── Potencia láser excesiva (sobrecalentamiento spinodal T > 280 °C).
│     └── Reducir inmediatamente el voltaje AO2 a < 1.0 V y limpiar el cubreobjetos.
│
└── [Deriva lateral durante la impresión de grillas grandes]
      ├── Verificar que la Partícula Ancla P0 esté activa con control adaptativo.
      └── Asegurar que la celda de fluido esté perfectamente sellada con grasa sin fugas.
```
