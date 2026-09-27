# Gold Exemplar: Presupuesto de Incertidumbre ISO/GUM Cerrado y Verificado

Referenciado por `metrology.md`. Este es el caso real del laboratorio, destilado de
`CAT-203` — no un ejemplo sintético. Cuando se pida un presupuesto de incertidumbre, igualar
esta estructura: **clasificar, cuantificar, combinar, verificar que cierra, e identificar el
término dominante.** Un presupuesto que no hace el último paso es una tabla, no una herramienta.

## Caso: localización lateral $x_0$ de una nanopartícula, Olympus 60× W

Condiciones: agua ($n=1.333$), $\text{NA}=1.00$, $M_{\text{eff}} = 83.33\times$ en el canal
confocal de 532 nm, $\Delta x = 15.0\ \text{nm/px}$, escaneo de 2 minutos compensado por
partícula ancla $P_0$ y autofoco.

## 1. Ecuación de medición y modelo de combinación

Las cinco fuentes son independientes, así que se combinan en cuadratura (`CAT-203` §3):

$$u_c(x_0) = \sqrt{u_{\text{piezo}}^2 + u_{\text{pix}}^2 + u_{\text{fit}}^2 + u_{\text{drift}}^2 + u_{\text{ph}}^2}$$

La independencia es una **afirmación física, no una conveniencia algebraica**: si el autofoco
acoplara deriva con desalineación de pinhole habría un término de covarianza $2\,c_i c_j\,u(x_i,x_j)$
y esta forma sería inválida. Declararlo explícitamente es parte del presupuesto.

## 2. Cuantificación por fuente, con su tipo de evaluación

| Fuente | Tipo | Distribución | Derivación | $u_i$ [nm] |
| :--- | :--- | :--- | :--- | ---: |
| Piezo PI E-517 ($u_{\text{piezo}}$) | B | — | Ruido estocástico del sensor capacitivo en lazo cerrado | $1.50$ |
| Cuantización de píxel ($u_{\text{pix}}$) | B | Uniforme en $[-\Delta x/2, \Delta x/2]$ | $\Delta x/\sqrt{12} = 15.0/3.4641$ | $4.33$ |
| Desalineación de pinhole ($u_{\text{ph}}$) | B | Uniforme, $\delta x_{\text{ph}} = \pm 1.0\ \mu\text{m}$ | $1000/(83.33 \cdot \sqrt{12})$ | $3.46$ |
| Deriva térmica residual ($u_{\text{drift}}$) | A | — | $v_{\text{drift}} \approx 15\text{–}25$ nm/min, compensada | $3.10$ |
| Ajuste gaussiano ($u_{\text{fit}}$) | A | — | Matriz de covarianza, $\text{SNR}=40$, $N=10^4$ fotones | $0.55$ |

**Tipo A** = evaluada estadísticamente a partir de observaciones repetidas. **Tipo B** = de
especificación, geometría o juicio científico. La distinción no es burocrática: fija de dónde
salen los grados de libertad efectivos si hace falta Welch-Satterthwaite.

## 3. Combinación y verificación aritmética

El paso que más se omite. Un presupuesto debe **cerrar**:

$$u_c^2 = 1.50^2 + 4.33^2 + 3.46^2 + 3.10^2 + 0.55^2 = 2.250 + 18.749 + 11.972 + 9.610 + 0.303 = 42.88\ \text{nm}^2$$

$$u_c = \sqrt{42.88} = \mathbf{6.55\ \text{nm}} \qquad U = k \cdot u_c = 2 \times 6.55 = \mathbf{13.10\ \text{nm}}\quad (k=2,\ \approx 95\%)$$

**Verificación cruzada independiente** (Nikon 100× Oil, $\Delta x = 10.0$ nm/px,
$M_{\text{eff}} = 125\times$), para confirmar que el modelo es consistente y no un ajuste a un
solo punto:

$$u_{\text{pix}} = 10.0/\sqrt{12} = 2.89 \quad u_{\text{ph}} = 1000/(125 \cdot \sqrt{12}) = 2.31$$
$$u_c = \sqrt{1.50^2 + 2.89^2 + 2.31^2 + 2.50^2 + 0.40^2} = \sqrt{22.33} = \mathbf{4.73\ \text{nm}} \qquad U = \mathbf{9.46\ \text{nm}}$$

Ambos coinciden con la matriz de `CAT-203` §4. Si no cerraran, el presupuesto estaría mal —
no la tabla.

## 4. Declaración metrológica final

$$x_0 = (\bar{x}_0 \pm 13.10)\ \text{nm},\quad k=2,\ \text{nivel de confianza} \approx 95\%$$

Nunca reportar $u_c$ sin decir $k$, y nunca reportar $U$ sin decir a qué nivel de confianza
corresponde. Un número sin su factor de cobertura no es trazable.

## 5. Término dominante — de dónde sale el valor de ingeniería

| Fuente | Contribución a $u_c^2$ | Peso |
| :--- | ---: | ---: |
| $u_{\text{pix}}$ | $18.749$ | **44 %** |
| $u_{\text{ph}}$ | $11.972$ | 28 % |
| $u_{\text{drift}}$ | $9.610$ | 22 % |
| $u_{\text{piezo}}$ | $2.250$ | 5 % |
| $u_{\text{fit}}$ | $0.303$ | 0.7 % |

La cuantización de píxel domina, así que **la palanca real es $\Delta x$** (magnificación o
binning), no comprar un piezo mejor ni refinar el solver: bajar $u_{\text{fit}}$ a cero mejoraría
$u_c$ en un 0.3 %. Ése es el resultado accionable, y es la razón por la que `CAT-203` §5 traza la
curva de optimización de $\Delta x$ en lugar de quedarse en la tabla.

Cuidado con el límite: reducir $\Delta x$ sube $u_{\text{pix}}$ a la baja pero reparte los mismos
fotones en más píxeles, empeorando $u_{\text{fit}}$ vía SNR. El óptimo es un compromiso, y el
piso absoluto es la cota de Cramér-Rao (`CAT-202`) — una precisión reportada por debajo de la CRLB
para el conteo de fotones medido es un error de cálculo, no un logro.

## Checklist antes de aceptar un presupuesto

1. ¿Está declarada la independencia de las fuentes, o hay covarianzas ignoradas en silencio?
2. ¿Cada fuente dice si es Tipo A o B, y con qué distribución? (Uniforme $\Rightarrow \sqrt{12}$;
   triangular $\Rightarrow \sqrt{6}$; certificado a $k=2 \Rightarrow U/2$.)
3. ¿La suma en cuadratura **cierra numéricamente**? Recalcularla, no confiar en la tabla.
4. ¿Está declarado $k$ junto a $U$?
5. ¿Se identificó el término dominante y se dijo cuál es la palanca?
6. ¿La precisión reportada respeta la CRLB para el $N$ de fotones real?
