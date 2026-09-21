# CAT-100: Marco Unificado de Nanofabricación Óptica, Trampeo Láser y Termoplasmónica
## Cadena de Causalidad Física de la Impresión Fototérmica: Fuerzas de Radiación, Efectos Joule y Marangoni, Adhesión Coloidal DLVO y Control Metrológico en Lazo Cerrado

---

**Signatura Bibliotecaria:** `CAT-100`  
**Clasificación Temática:** `[FIS]` / `[PRT]` Tratado Rector de Nanofabricación Óptica y Control Optomecánico  
**Pilar:** Pilar I — Nanofabricación Óptica, Control de Posición y Termoplasmónica (NODO RECTOR)  
**Autoría:** José Luis González Peñafiel (*Becario Doctoral CONICET*), Comité Científico PyPrinting 3.0  
**Fecha de Publicación:** Septiembre 2026  
**Estado:** Producción / Consolidado  
**Módulos Asociados:** `app.py`, `gui/printing_routine.py`, `hardware/photodiode_monitor.py`, `motion/tilt_compensator.py`, `hardware/drift_tracker.py`, `core/nanopositioning.py`  
**Documentos Vinculados:**  
- [[CAT-101_Protocolo_Operativo_Impresion_Fototermica_Grillas_2D]] (Protocolo práctico de laboratorio)  
- [[CAT-103_Control_Lazo_Cerrado_Fototermico_y_Sintesis_Dimeros]] (Modos de parada y dímeros)  
- [[CAT-104_Compensacion_Inclinacion_Z_Confocal_y_Healing_Pass]] (Inclinación Z y pasada de completitud)  
- [[CAT-105_Compensacion_Deriva_Termomecanica_Particula_Ancla_P0]] (Compensación de deriva piezoeléctrica)  
- [[CAT-106_Control_Adaptativo_Frecuencia_Autofoco_Gradiente_Deriva]] (Lazo adaptativo de autofoco)  
- [[CAT-107_Cinetica_Captura_Fotodiodo_Time_Volt_Filtro_Nhold]] (Cinética de fotodiodo Time-Volt)  
- [[CAT-108_Teoria_Optica_Telescopio_Rele_4f_y_Canales_Confocales]] (Óptica de foco y telescopio relé)  
- [[CAT-109_Electrodinamica_Fuerzas_Opticas_y_Termoplasmonica_Printing]] (Fuerzas electrodinámicas y calentamiento)  
- [[CAT-110_Fisicoquimica_Coloides_DLVO_y_Funcionalizacion_Superficies]] (Potencial DLVO y silanización APTES)  
- [[CAT-111_Nanotermometria_DLS_y_Dinamica_Fluctuaciones_Brownianas]] (Nanotermometría DLS in-situ)  
- [[CAT-112_Teoria_Lente_Termica_Gradientes_Indice_y_Marangoni]] (Lente térmica y convección Marangoni)  
- [[CAT-113_Lazo_Cerrado_Metrologico_InSitu_y_Control_Predictivo]] (Control predictivo RLS a <4 nm)  
- [[CAT-114_Pinzas_Opticas_Contrapropagantes_y_Microscopia_iSCAT]] (Pinzas ópticas contrapropagantes e iSCAT)  

---

## 1. Resumen Ejecutivo

La nanolitografía óptica asistida por luz (**Light-Assisted Nanopatterning** o impresión fototérmica) es la tecnología medular de PyPrinting 3.0. Permite ensamblar nanopartículas metálicas coloidales individuales (Au/Ag de $40 - 100\ \text{nm}$) sobre sustratos de vidrio funcionalizado en coordenadas predeterminadas con precisión nanométrica, sin recurrir a salas limpias costosas ni a litografía por haz de electrones (EBL).

Sin embargo, el proceso de impresión no es una simple soldadura térmica puntual. Es una **cadena acoplada de fenómenos multifísicos** que operan en escalas temporales desde microsegundos hasta minutos: electrodinámica de haces enfocados, fuerzas de radiación óptica, absorción plasmónica resonante, calentamiento Joule local, gradientes termo-ópticos ($dn/dT$), flujos hidrodinámicos termocapilares (convección de Marangoni), termoforesis, cinética coloidal DLVO y quimisorción superficial irreversible.

Este reporte actúa como el **Nodo Rector y Nota Paraguas del Pilar I**. Establece la cadena de causalidad física completa de la impresión, unifica los modelos matemáticos dispersos en las notas analíticas `CAT-101` a `CAT-114` y documenta cómo los sistemas de control en tiempo real (seguimiento de deriva $P_0$, autofoco adaptativo y parada por fotodiodo a $10\ \text{kHz}$) aseguran la viabilidad del proceso.

---

## 2. La Cadena de Causalidad Física de la Impresión Fototérmica

```
                               CADENA DE CAUSALIDAD MULTIFÍSICA
                               
   [1. ÓPTICA]           Láser focalizado (lambda=532 nm, w_0 ~ 300 nm)
                             │
                             ▼
   [2. ELECTROMAG.]      Fuerzas Ópticas de Radiación:
                           • Gradiente atractiva: F_grad ~ Re(alpha) grad |E|^2
                           • Dispersión desestabilizadora: F_scat ~ k Im(alpha) |E|^2
                             │
                             ▼
   [3. TERMOPLASMÓNICA]  Absorción resonante LSPR -> Calentamiento Joule:
                           • P_abs = (1/2) sigma_abs I_0
                           • Delta T_local ~ 40 - 100 K
                             │
                             ▼
   [4. HIDRODINÁMICA]    Gradientes térmicos locales:
                           • Lente térmica negativa (dn/dT < 0 en agua)
                           • Convección de Marangoni: tau_M = -beta_T grad_|| T
                           • Termoforesis coloidal: v_T = -D_T grad T
                             │
                             ▼
   [5. FISICOQUÍMICA]    Aproximación coloide-sustrato:
                           • Barrera electrostática DLVO superada por F_grad + F_Marangoni
                           • Quimisorción irreversible en monocapa de APTES (-NH_3^+)
                             │
                             ▼
   [6. METROLOGÍA]       Detección y parada en lazo cerrado:
                           • Salto en fotodiodo (10 kHz) -> Cierre de obturador en <5 ms
                           • Corrección de deriva termomecánica con partícula P_0
```

---

## 3. Matriz de Fenómenos y Modelos Físicos Fundamentales

| Fenómeno Físico | Ecuación de Gobierno | Consecuencia en el Experimento | Documento Rector |
| :--- | :--- | :--- | :--- |
| **Fuerzas Ópticas** | $\mathbf{F} = \frac{1}{4}\varepsilon_0\varepsilon_m\text{Re}(\alpha)\nabla|\mathbf{E}|^2 + \frac{n_m\sigma_{\text{scat}}}{c}\mathbf{S}$ | Atrae al coloide hacia el centro del foco láser. | [[CAT-109_Electrodinamica_Fuerzas_Opticas_y_Termoplasmonica_Printing]] |
| **Calentamiento Joule** | $\Delta T(r) = \frac{\sigma_{\text{abs}} I_0}{4\pi \kappa_m r}$ | Aumenta la temperatura local $T_{\text{nano}}$ en decenas de grados. | [[CAT-111_Nanotermometria_DLS_y_Dinamica_Fluctuaciones_Brownianas]] |
| **Convección Marangoni** | $\tau_M = -\beta_T \nabla_\parallel T$ | Flujo hidrodinámico toroidal que arrastra coloides hacia el sustrato. | [[CAT-112_Teoria_Lente_Termica_Gradientes_Indice_y_Marangoni]] |
| **Potencial DLVO** | $V_{\text{tot}}(h) = -\frac{A_H R}{6h} + 2\pi\varepsilon R \psi_1\psi_2 e^{-\kappa h}$ | Determina si la partícula colisiona o se repele del vidrio. | [[CAT-110_Fisicoquimica_Coloides_DLVO_y_Funcionalizacion_Superficies]] |
| **Cinética Fotodiodo** | $V(t) = V_{\text{base}} + \frac{\Delta V}{1 + e^{-(t-t_0)/\tau}}$ | Detecta la inmovilización en microsegundos y comanda la parada. | [[CAT-107_Cinetica_Captura_Fotodiodo_Time_Volt_Filtro_Nhold]] |
| **Deriva Térmica** | $\vec{D}(t) = \mathbf{r}_{P0}(t) - \mathbf{r}_{P0}(0)$ | Sustracción piezoeléctrica activa de la deriva ambiental ($\sim 1\ \text{nm/min}$). | [[CAT-105_Compensacion_Deriva_Termomecanica_Particula_Ancla_P0]] |

---

## 4. Mapa de Navegación del Pilar I

```
                                  MAPA DE NAVEGACIÓN — PILAR I
                                                
                                   CAT-100 (ESTE DOCUMENTO)
                                        [NODO RECTOR]
                                              │
         ┌───────────────────┬────────────────┴───────────────────┬───────────────────┐
         ▼                   ▼                                    ▼                   ▼
    [PROTOCOLO Y LAZO]  [DERIVA Y ESTABILIDAD]               [TERMOPLASMÓNICA]   [COLOIDES Y FUERZAS]
      CAT-101 (Protocolo) CAT-104 (Inclinación Z)              CAT-107 (Time-Volt) CAT-109 (Fuerzas)
      CAT-103 (Parada)    CAT-105 (Ancla P0)                   CAT-111 (DLS / VFT) CAT-110 (DLVO / APTES)
      CAT-113 (Predictivo)CAT-106 (Autofoco Adaptativo)        CAT-112 (Marangoni) CAT-114 (Contrapropagante)
```

---

## 5. Referencias Bibliográficas Primarias

1. **Gargiulo, J., Cerrocchi, M., Cortés, E., Violi, I. L., & Stefani, F. D.** (2016). *Connecting Metallic Nanoparticles by Optical Printing*. Nano Letters, 16(2), 1224–1229. [DOI: 10.1021/acs.nanolett.5b04542](https://doi.org/10.1021/acs.nanolett.5b04542)
2. **Baffou, G., & Quidant, R.** (2013). *Thermo-plasmonics: using metallic nanostructures as nano-sources of heat*. Laser & Photonics Reviews, 7(2), 171–187. [DOI: 10.1002/lpor.201200003](https://doi.org/10.1002/lpor.201200003)
3. **Derjaguin, B., & Landau, L.** (1941). *Theory of the stability of strongly charged lyophobic sols*. Acta Physicochim. URSS, 14, 633–662.
4. **Verwey, E. J. W., & Overbeek, J. T. G.** (1948). *Theory of the Stability of Lyophobic Colloids*. Elsevier, Amsterdam.
