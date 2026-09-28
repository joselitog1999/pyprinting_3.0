# C-01 Ronda 1 — Panelista experimental (notas incrementales)

Convención de páginas: "p. impresa" = número al pie; "p. PDF" = página del archivo.

## Fuentes leídas

### Pereyra 2025 (Lic., único trabajo hecho en el banco INS-UNSAM)
`docs/bibliografia/Tesis del grupo/Licenciatura/2025_Tesis Abril J. Pereyra.pdf`

- Banco: láser Excelsior-532-150-CDRH, objetivo Olympus LUMPLFLN60XW (agua, NA 1.0), sustrato PDDA/PSS
  (negativo), NPs Au citrato 100 nm (Nanopartz), concentración ~pM (p. impresa 29, 33; PDF 30, 34).
  Rojo e IR presentes pero no usados (p. impresa 29).
- Detección confocal: luz retro-reflejada/dispersada de la muestra → objetivo → BS → lente → pinhole en plano
  conjugado → fotodiodo; notch separa la luz elástica de cada láser a su propio fotodiodo. "Eventos de impresión
  ... se manifiestan como aumentos repentinos y distinguibles en la señal del fotodiodo" (p. impresa 31, PDF 32).
  Un fotodiodo calibrado detrás del BS monitorea potencia (p. impresa 30, PDF 31).
- Escalas de tiempo (p. impresa 17, PDF 18): llegada por difusión al volumen de captura "unos pocos segundos"
  (depende de concentración y potencia); movimiento dentro del volumen de captura "del orden de milisegundos".
- Principio de detección (p. impresa 36, PDF 37): I(t) ∝ |E_r + E_sca|² (interferencia reflexión del sustrato +
  campo dispersado por la NP); u = I(t0+τ)/I(t0) = Id/Ir; u > 1 constructiva, u < 1 destructiva.
  **"En la implementación práctica, este umbral se monitorea de forma activa como un cociente móvil,
  u(t) = I(t+dt)/I(t−dt), donde dt es un intervalo de tiempo corto, típicamente entre 10 y 100 ms, que se ajusta
  para cada experimento."**
  → VERIFICADO: la cifra 10-100 ms existe, pero está en la **p. impresa 36 (= p. PDF 37)**; el triage cita "p. 37"
  (número de PDF). Y **no es una "ventana de detección"**: es el semi-intervalo dt del cociente móvil
  (ventana "antes" vs "después"), es decir, la escala de promediado del criterio, no el tiempo del evento.
- Fig. 2.5 (p. impresa 37, tomada de la tesis de Martínez, ref. 49): NP Au 60 nm, 532 nm. Ir ≈ 0.175 u.a.,
  paso abrupto a Id ≈ 0.44 u.a. (u ≈ 2.5) en t ≈ 1.2 s; el paso ocurre en ≲ 1-2 puntos del gráfico; la traza
  termina ~20-40 ms después del salto (corte). Pequeños picos transitorios (≈ +0.03) a 0.2, 0.6, 1.0 s:
  NPs que cruzan cerca del foco sin adherirse.
- Fig. 2.4(d) (p. impresa 35): traza en la GUI legado PyPrinting, canal "532 nm", 0.144 V de base; caída
  transitoria a ≈ 0.11 V (u ≈ 0.76) de ~0.3 s a t ≈ 4.8-5.1 s y retorno a la base. Es un evento transitorio,
  no un escalón sostenido (NP que entra y sale, o se imprime y se va). Nivel de señal: ~0.1-0.2 V.
- Criterio de la rutina: "umbral de señal y un tiempo de espera máximo" (p. impresa 36). GUI de la Fig. 2.4(c):
  "Umbral 1.2", "Time max (s) 20".
- Dímeros < 300 nm: tiempo de espera mayor; < 250 nm falla aún con 20× el tiempo habitual (p. impresa 18-19).
- Pereyra NO da potencia de impresión ni tiempo típico por NP en el banco nuevo.

### Martínez (tesis doctoral) — fuente de la Fig. 2.5 de Pereyra
`docs/bibliografia/Tesis del grupo/Tesis Luciana Martinez.pdf` (p. impresa = p. PDF en los tramos citados)

- Etapas (p. 36): difusión browniana hasta el foco "unos pocos segundos" (depende de concentración y potencia);
  movimiento guiado ópticamente "orden de milisegundos" (cita Gargiulo); DLVO a ~8-10 nm.
- Tiempo de impresión de una NP "en el orden de segundos" (p. 38).
- iSCAT confocal (p. 57): Id = Ir + Isca + 2·Er·Esca·cos(φ); contraste C = (Id − Ir)/Ir. Con Au 80 nm: máximo a
  532 nm, **mínimo a 808 nm** (el signo depende de λ y del material). → El criterio de parada tiene que admitir
  escalón hacia arriba o hacia abajo según el láser.
- Detección automatizada (p. 68-69): mismo cociente móvil u(t) = I(t+dt)/I(t−dt), "dt del orden de 10 a 100 ms,
  ajustándose libremente para cada experimento". Fig. 3.9 = Fig. 2.5 de Pereyra. Traza guardada por nodo (p. 66).
- **Latencia del legado, medida por el propio grupo (p. 112):** "Después de la impresión, el láser sigue
  iluminando a la NP durante un tiempo de respuesta de la detección automatizada que varía entre **10 y 100 ms**
  antes de ser apagado." Vuelo hasta el sustrato: "unos pocos milisegundos".
- Térmica (p. 112): β = 55 K·µm²/mW (Au 60 nm en vidrio/agua, 532 nm); I_printing = 10 mW/µm² → T ~ 570 °C;
  sin daño "debido a que los tiempos de impresión son del orden de milisegundos". Conclusión (p. 113): las Au
  esféricas toleran la impresión "debido a su exposición breve, del orden de centenas de milisegundos"; Ag y
  core-shell pueden dañarse (sec. 2.6).
- Iluminación prolongada, NP ya impresa (p. 78-79, 112-113): 4 mW/µm² (~240 °C): 60 s sin cambios, **300 s
  halo** (se pierde la bicapa PDDA/PSS alrededor); 7 mW/µm² (~400 °C): la NP **se entierra desde los 60 s**;
  15 mW/µm² → ~850 °C. A la irradiancia de impresión (10 mW/µm², ~570 °C) no hay dato de dosis tolerable,
  pero por interpolación el daño del polielectrolito aparece en ≲ 60 s.
- Fotoestabilidad (p. 49): Au 60 nm hasta 645 K en resonancia; Au-S se rompe a 470 K; altas temperaturas
  "sólo durante unos pocos milisegundos"; Ag en resonancia a alta potencia → colores anómalos (¿fotooxidación?).

### Gargiulo et al., ACS Nano 2017, 11, 9678, DOI 10.1021/acsnano.7b04136 ("Accuracy and Mechanistic Details")
- Eventos detectados "como un aumento escalonado de la señal de dispersión" confocal del láser de impresión,
  analizada en línea (p. C, Fig. 2b).
- Tiempo de espera: mediana **4.7 s** (196 NP Au 60 nm, P = 1.17 mW, 532 nm; Fig. 2d). No es puramente
  sin memoria. Crece bruscamente al acercarse a P_th (Au 1.00 mW; Ag 0.55 mW a 405 nm). Máximo 2 min (p. E).
- Al subir la potencia crecen los NPs defectuosos (colores anómalos: pérdida de selectividad o cambio de forma
  por alta temperatura) (p. E).
- **Fuera de resonancia** (p. E-F): señal débil o **negativa** por interferencia con la reflexión agua-vidrio;
  se superpone un láser de detección en la LSPR (< 10 % de la fuerza). NPs **atrapadas momentáneamente** en el
  volumen confocal elevan la señal → **paso de confirmación**: se bloquean ambos haces 1 s y se interroga con el
  haz de detección solo; si la NP no quedó fija, se reabre y se repite. → falsos positivos por atrapamiento
  transitorio son un modo de falla conocido.
- Tiempo de vuelo (p. F, Fig. 6a): NP a 2 µm del sustrato en el eje, P = 1 mW, w0 = 265 nm → **10 ms**.
  τ_f (difundir un radio) = 6·10⁻⁵ s. Concentración 2·10⁹ NP/mL → 500 µm³ por NP ≫ V_C = 0.05 µm³ (p. G):
  el volumen de captura está casi siempre vacío al abrir el láser.
- Deriva mecánica típica < 10 nm/min (p. C).

### Gargiulo 2017 (tesis doctoral), `docs/bibliografia/Julian_Gargiulo_2017.pdf` (p. impresa = p. PDF − 1)
- Banco CIBION: PI P-545, láseres 405/532/640, obturador mecánico + ND en flipper por láser, **PCIe-6353**
  (p. impresa 48, 54). Detección confocal con fotodiodos amplificados tras pinhole (p. impresa 50).
- **Programa Timetrace (p. impresa 56):** parada por condición en vivo ("change in slope, incrementation above
  certain threshold"); "works smoothly for acquisition rates up to 1 kHz"; "Due to the slow communication speed
  between the computer and the DAQ, **the response time for automated stopping is about 10 ms**."
- p. impresa 64: "Upon the detection of a printing event, the beam is **immediately blocked**." Deriva ~5 nm/min.
- Fig. 5.2(e) (p. impresa 65): escalón 0.42 → 1.05 u.a. (u ≈ 2.5) en t ≈ 3.6 s, subida en ≲ 1-2 puntos; la
  traza sigue alta hasta ~4.0 s (≈ 0.3-0.4 s post-escalón, leído del gráfico ±50 ms): en ese ejemplo la latencia
  efectiva fue de cientos de ms (domina la ventana del criterio), no 10 ms.
- Histograma de espera (Fig. 5.2f): cola pesada, eventos hasta ~100 s; mediana 4.7 s.

### Nanoestrellas, Nano Lett. 2023, DOI 10.1021/acs.nanolett.2c05109 (p. 5)
- 532 nm, 9.2 mW/µm² (70 % de la irradiancia mínima de impresión) → AuNS se remodelan a esferas; "in some cases,
  the reshaping occurs during the first second"; si hay retardo, "once it starts it is completed within one
  second". β532 = 26 K·µm²/mW. → Para NPs no esféricas, 1 s ya es escala de daño.

### Challenges 2022 (Violi et al., J. Chem. Phys. 156, 034201, DOI 10.1063/5.0078454)
- Difusión hasta el foco "a few seconds"; guiado "on the order of milliseconds" (p. 3).
- Au 60 nm hasta 645 K en resonancia; Au-S rompe a 470 K; altas T "only reached during a short time of a few
  milliseconds or less" (p. 14). **Ojo:** eso supone corte inmediato. Una NP impresa queda en el centro del haz
  (error ~50 nm) a T plena durante toda la latencia de corte, que el propio grupo cifra en 10-100 ms
  (Martínez p. 112). Dosis térmica real = latencia.

### Documentos del repositorio contrastados
- **CAT-107**: (a) "NA ≥ 1.3": FALSO, objetivo LUMPLFLN60XW NA = 1.0 (Pereyra p. 29; Martínez p. 55; SYS-305
  l. 140). (b) "luz transmitida / dispersada": la señal es retro-reflejada + retro-dispersada (iSCAT epi), no
  transmitida (Martínez p. 57; Gargiulo p. 50). (c) "τ_tránsito ~ 5-20 ms (1 a 2 muestras del ADC a 10 kHz)":
  sin fuente e internamente inconsistente (a 10 kS/s son 50-200 muestras). Estimación propia: D(Au 60 nm) =
  kT/(6πηa) ≈ 7 µm²/s → cruzar ~0.3 µm lleva ~2-6 ms; cruce libre ~1-10 ms; atrapamiento transitorio fuera de
  resonancia puede ser mucho más largo (ACS Nano 2017 p. E). (d) Tabla N_hold con "dt ≈ 10 ms": el código corre
  a 35 ms/tick → N_hold = 5 son 175 ms, no 50 ms.
- **SYS-305** l. 140: "Pinhole de 50 µm maximiza la **caída** de señal al fijar la partícula" contradice Pereyra
  p. 31 / Gargiulo / Martínez (Au a 532 nm → **aumento** escalonado). Sin fuente.
- **SYS-305** diagrama l. 98/103 ("Amarillo ai2 / Rojo ai1") contradice §5.1 y `config.PD_CHANNELS`
  (592→ai1, 637→ai2). l. 169: obturadores = "servos de dos posiciones con driver propio (indicación del
  operador)" → el tiempo mecánico de cierre puede igualar o superar la latencia de software. NO verificado.
- Las Fig. 2.4(d) y 2.5 de Pereyra son **copias de Martínez** (Fig. 3.6b y 3.9, banco CIBION). **No hay en la
  bibliografía ninguna traza de impresión medida en el banco INS-UNSAM**; todas las escalas de detección vienen
  del banco anterior.

---

## Análisis

### 1. Señal de un evento de impresión
I_d = I_r + I_sca + 2·sqrt(I_r·I_sca)·cos(φ) (Martínez p. 57). I_r: reflexión vidrio-agua (R ≈ 0.44 %); I_sca:
retro-dispersión de la NP; φ depende de material, λ y altura z.
- **PD del láser de impresión (532, ai0; Au en resonancia):** escalón hacia ARRIBA, u ≈ 2.5 para Au 60 nm
  (Gargiulo Fig. 5.2e; Martínez Fig. 3.9). Para Au 100 nm (la de Pereyra) sin dato medido.
- **Otros λ / fuera de resonancia:** contraste chico o NEGATIVO (Au 80 nm: mínimo a 808 nm, Martínez p. 57;
  ACS Nano 2017 p. E) → escalón hacia ABAJO. El código actual cuenta toda caída (`umbral_down`) como
  "timeout" (`measurements.py:2408-2418`): una impresión real con contraste negativo sale mal clasificada.
- **Monitor BS (ai6):** no cambia con la impresión; sirve de referencia de modo común (normalizar I/I_BS cancela
  ruido de intensidad del láser) y de testigo de obturador.
- **PDs de láseres con obturador cerrado:** oscuro + offset; sin evento.

Escalas de tiempo:
| Fase | Escala | Fuente |
|---|---|---|
| Espera (difusión al volumen de captura) | segundos; mediana 4.7 s (Au 60 nm, 1.17 mW, 532); cola hasta ~100 s | ACS Nano 2017 Fig. 2d; Gargiulo Fig. 5.2f; Martínez p. 36, 38; Pereyra p. 17 |
| Vuelo guiado al sustrato | ~10 ms desde 2 µm (1 mW, w0 265 nm) | ACS Nano 2017 p. F |
| Subida de la señal (volumen confocal → contacto) | ≲ pocos ms; puede oscilar por la franja axial iSCAT (período λ/2n ≈ 200 nm) | inferencia desde lo anterior; no medida |
| Adhesión (barrera DLVO) | ≪ 1 ms | ACS Nano 2017 p. F (τ_f = 6e-5 s) |
| Meseta post-impresión | persistente mientras el láser siga | todas |
| Termalización NP | ns (a²/κ ≈ 6 ns); campo µm: µs | estimación |
| Falsos: NP de paso | ~1-10 ms (picos de 1 punto en Martínez Fig. 3.9); atrapamiento transitorio: hasta cientos de ms | Martínez; ACS Nano 2017 p. E-F |
| Caída transitoria ~0.3 s (u ≈ 0.76), Martínez Fig. 3.6b | origen sin documentar | pregunta |

**Verificación del "10-100 ms":** existe en Pereyra **p. impresa 36 (= p. PDF 37)**; el triage citó el número de
PDF. **No es una ventana de detección**: es el dt del cociente móvil u(t) = I(t+dt)/I(t−dt), "típicamente entre
10 y 100 ms, que se ajusta para cada experimento" (texto derivado de Martínez p. 69). El dato independiente y más
útil es Martínez p. 112: **latencia de corte del legado 10-100 ms**. Con el legado (M = 10 puntos de ~10 ms) la
ventana es ~100 ms, el borde superior de ese dt.

### 2. Cadencia y latencia del criterio de parada
Criterio actual (M = M2 = 10, umbral 1.2, escalón u): I_new/I_old = 1 + k(u−1)/10 → para cuando k > 2/(u−1):
u = 2.5 → k = 2; u = 2 → 3; u = 1.5 → 5; u = 1.3 → 7. Latencia de software ≈ (k + ½)·T_punto + procesamiento
+ obturador.
| T_punto | u = 2.5 | u = 2 | u = 1.3 | + N_hold = 5 |
|---|---|---|---|---|
| 10 ms (legado) | ~25 ms | ~35 ms | ~75 ms | +40 ms |
| 35 ms (finita, `7f5d10a`) | ~90 ms | ~120 ms | ~260 ms | +140 ms |
| continua rota (`main`) | nunca antes del desborde; corte por umbral_down ≈ 1.1 s o T_max = 20 s | | | |

Consecuencias del corte tardío. La NP ya impresa queda en el centro del haz a temperatura plena y la termalización
es de ns, así que toda la latencia cuenta como dosis. Tasa de llegadas ≈ ln2/4.7 s ≈ 0.15 s⁻¹; después de la
primera NP es menor por la repulsión termoforética.
| Latencia | Térmica / morfología | P(2.ª NP) | Juicio |
|---|---|---|---|
| 35-100 ms | régimen histórico: Au esférica a ~570 °C (β·I = 55 × 10, Martínez p. 112) sin daño; "centenas de ms" toleradas (p. 113) | ≈ 0.5-1.5 % | OK Au esférica; marginal Ag / nanoestrellas / core-shell |
| ~250-300 ms (35 ms, u chico o N_hold) | igual para Au esférica; nanoestrellas a 532 se acercan a la escala de remodelado (< 1 s) | ≈ 4 % | tolerable; es la sobreexposición C-01b |
| ~1 s | 10× la dosis histórica; nanoestrellas remodeladas (Nano Lett. 2023); Ag con posible cambio de color o fotooxidación (Martínez §2.6) | ≈ 14 %; sale desplazada ≥ 250-300 nm por termoforesis (Pereyra p. 18-19) → defecto tipo dímero | inaceptable como régimen |
| 20 s (T_max, umbral_down = 0) | entierro desde 60 s a 400 °C y halo PDDA/PSS a 300 s y 240 °C (Martínez p. 78-79, 112); sin dato a ~570 °C y 20 s, extrapolación: daño del polielectrolito posible | ≈ 95 % → dobletes o cúmulos | daño y defecto casi seguros |

**¿Ruido o latencia?** Para Au en resonancia manda la LATENCIA: escalón ΔI/I ≈ 150 % frente a un ruido de base
de ~1-2 % p-p (leído de Martínez Fig. 3.9). Un punto de 1 ms lo resuelve con SNR ≫ 10.
- El ruido de disparo es irrelevante (~1 µW en el PD, ~10¹² fot/s). Domina el ruido técnico: intensidad del láser,
  electrónica del PDA, 50 Hz y vibración axial, que el iSCAT convierte en fase.
- El ruido importa sólo con contraste bajo (u → 1, fuera de resonancia, 637/808). Aun así, la solución no es
  alargar la ventana (cuesta latencia) sino **promediar sin huecos**. La lectura finita usa 1 ms de cada 35 ms
  (ciclo útil ~3 %): con ruido blanco y a igual tasa de falsas alarmas, adquirir sin huecos baja σ por punto
  ~sqrt(35) ≈ 6× y el tiempo de detección ~35×.
- Conviene además promediar en múltiplos de 20 ms (rechaza 50 Hz) y normalizar por el BS.

**Requisito propuesto:**
- R-lat: de punta a punta (escalón físico → haz bloqueado), **mediana ≤ 50 ms y p95 ≤ 100 ms** para u ≥ 1.5.
  Es la envolvente del legado (Martínez p. 112; Gargiulo p. 56). Software (última muestra → orden al obturador)
  ≤ 50 ms p95; la carrera del obturador se mide aparte y se suma. Techo duro: 200 ms.
- R-fresh: cada decisión usa muestras de, como mucho, un período de antigüedad; el atraso no crece; se verifica
  en ejecución.
- R-gap: adquisición sin huecos, o huecos conocidos. Período de punto 10-20 ms. Ventanas I_old/I_new en ms
  (10-100 ms, el dt de la tesis), no en ticks.
- R-zero: una lectura fallida nunca es 0.0 V: va NaN, se cierran los obturadores y se aborta el nodo. Tiempo
  tomado del reloj de muestreo, no de `time.time()`.
- R-sign: el criterio acepta como "success" un escalón hacia abajo cuando el contraste es negativo.

### 3. Cómo reconoce el operador cada modo de falla
| Modo | Firma | Contraprueba |
|---|---|---|
| Datos atrasados (continua, primer ~1 s) | "cámara lenta": los primeros ~29 ms reales estirados sobre ~1 s; el flanco de apertura del obturador se ve ~35× más lento; una NP que se ve llegar en campo oscuro NO da escalón | tapar el haz a mano: la traza reacciona tarde o no reacciona |
| 0 V tras el desborde (~1.03 s) | caída a **0.000 V exacto, sin ruido, en todos los canales a la vez incluido el BS**; nodos de ~1.1 s (umbral_down 0.8) o 20 s (umbral_down 0), todos "timeout" | un PD a oscuras lee offset con ruido (mV), nunca 0.000; BS en 0 con el láser encendido es imposible |
| Huecos (finita por tick) | traza plausible pero gruesa; transitorios de 1-10 ms como puntos sueltos o ausentes; 50 Hz aliasado (con ~28.6 Hz de muestreo cae cerca de 7 Hz; con jitter parece ruido); Δt entre filas > 35 ms e irregular | inyectar un seno conocido |
| Mock silencioso (`6abbbfc`) | traza plana ~0.5 V con ruido, independiente del obturador | cerrar el obturador: nada cambia |
| NaN (`_UnavailableNITask`) | traza vacía, interlock activo | — |
| Huella en la muestra (T_max) | dobletes o NPs desplazadas; Ag con colores raros; halos; nanoestrellas esferizadas | comparar con una grilla hecha con el legado |

### 4. Ensayo de banco
**Fase A (segura, sin impresión):** LED de ~530 nm, o el 532 atenuado con el ND sobre vidrio limpio, al PDA de ai0.
La modulación viene de un generador o de una DO libre; la misma señal entra por un **AI libre como loopback**
(instante exacto del escalón en la misma base de tiempo). La línea del obturador va a otro AI o a un osciloscopio,
y un PD aguas abajo del obturador mide el bloqueo real.
- A1 latencia: 100 escalones con u = 2.5, 1.5, 1.3 y 0.76 hacia abajo, en instantes aleatorios entre 0.1 y 30 s,
  para cubrir el desborde de ~1 s. Se mide escalón → orden → haz bloqueado. Aceptación: R-lat.
- A2 frescura: senos de 1 y 7 Hz durante 60 s. El atraso frente al loopback tiene que ser constante y ≤ 1
  período. Falsa C-01 si crece como ~0.97·t o aparecen ceros exactos.
- A3 transitorios: pulsos de 2, 5, 10, 20, 50, 100 y 300 ms, para calibrar N_hold y las ventanas contra pulsos
  reales en lugar de los 5-20 ms sin fuente de CAT-107.
- A4 controles: obturador cerrado (offset con ruido, no 0.000); LED fijo durante T_max (sin paradas falsas);
  `SAFE_MODE`.

**Fase B (muestra real):** grilla de 5×5 con Au de 60 o 100 nm sobre PDDA/PSS a la potencia habitual, con video de
campo oscuro como verificación independiente. Por nodo se registran t_step, la orden de cierre y el bloqueo (BS).
- Controles: (i) colchón sin coloide: 0 paradas en T_max; (ii) una grilla con retardo artificial de 1 s tras la
  detección, para medir el exceso de dobletes y defectos; (iii) 637 u 808 nm si se usan (contraste negativo).
- Aceptación: ≥ 95 % "success" con una NP por nodo y ninguna traza con ceros exactos.

### 5. Preguntas (una línea cada una)
1. ¿Fecha y commit de la última impresión "buena", y sus nodos: "success" o "timeout"?
2. En un `NP_xxx.txt` de producción: ¿Δt típico entre filas y cuántas filas hay después del escalón?
3. Con Au de 60 o 100 nm a 532 en este banco: ¿el escalón sube o baja, y de cuánto es u?
4. ¿Qué umbral, steps_before/after, N_hold, umbral_down y T_max usan en la práctica, y con qué preset?
5. ¿Modelo de los obturadores (¿servo?) y tiempo de cierre medido?
6. ¿Modelo y ganancia de los PDA?
7. En las trazas de producción, ¿hay picos o caídas transitorias (como la de ~0.3 s de Martínez Fig. 3.6b) y
   cuánto duran?
8. ¿Aparecen dobletes, NPs desplazadas o halos en grillas impresas después del 19-09?
9. ¿Potencia en el plano de la muestra, concentración del coloide y espera típica por NP?
10. ¿Se imprime con 592, 637 u 808 nm o sólo con 532?
11. ¿Hay un AI libre y un LED o generador de funciones para el ensayo A?
12. ¿El campo oscuro queda grabando durante la impresión?

### Veredicto
MODIFICATION_REQUIRED. La tarea continua es buena idea (sin huecos y con reloj de hardware) sólo si se lee lo
acumulado sin dejar crecer el atraso. La lectura finita por tick de producción basta físicamente para Au en
resonancia (el escalón persiste), a costa de ~3 % de ciclo útil y ~90-120 ms de latencia.
