# Reporte Científico Canónico: Mapeo Hiperespectral SERS Confocal Automatizado y Reconstrucción Tensorial 🌈🔬

**Biblioteca Científica Canónica — Pilar II: Super-Resolución Óptica, Espectrometría y Curación de Datos**  
**Signatura Canónica**: `CAT-205` | **Clúster**: `[FIS]` (Física)  
**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Autor Principal**: José Luis González Peñafiel (*Físico EPN, Becario Doctoral CONICET, INS-UNSAM*)  
**Fecha de Publicación**: Septiembre 2026 | **Estado**: Vigente y Certificado por QA  
**Módulos del Sistema Asociados**: `pyspectrum.py`, `analysis/raman_analyzer.py`, `sif_analyzer.py`, `modules/measurements.py`  
**Referencias Cruzadas**: `[[CAT-101_Protocolo_Operativo_Impresion_Fototermica_Grillas_2D]]`, `[[CAT-108_Teoria_Optica_Telescopio_Rele_4f_y_Canales_Confocales]]`, `[[CAT-109_Electrodinamica_Fuerzas_Opticas_y_Termoplasmonica_Printing]]`, `[[CAT-401_Estandar_Serializacion_Jerarquica_Contenedor_HDF5]]`, `[[SYS-301_Sistema_Espectrometro_Shamrock500i_iXon3]]`, `[[SYS-305_Arquitectura_Optomecanica_Microscopio_Derecho_y_Ruteo_Espectral]]`, `[[SYS-306_Arquitectura_Motor_Raman_y_Quimiometria_Multiespectral]]`

---

## 1. Resumen Ejecutivo

La nanolitografía óptica fototérmica en PyPrinting 3.0 permite fabricar arreglos bidimensionales periódicos de nanopartículas de oro y dímeros plasmónicos con separaciones inter-partícula manométricas sub-10 nm (`[[CAT-101_Protocolo_Operativo_Impresion_Fototermica_Grillas_2D]]`). La caracterización espectral tradicional punto por punto mediante posicionamiento manual resulta inviable en redes que contienen cientos o miles de nodos.

Este reporte formaliza la integración metrológica y algorítmica del **Mapeo Hiperespectral SERS Confocal Automatizado**: la derivación electrodinámica del factor de realce de campo cercano ($EF_{\text{SERS}} \propto |E_{\text{loc}}/E_0|^4$), el acoplamiento cinemático entre el registro de impresión (`printing_results.txt` / contenedor HDF5) y la platina piezoeléctrica Physik Instrumente (PI), el protocolo de sincronización de obturadores y cámara EMCCD Andor iXon3 (`[[SYS-301_Sistema_Espectrometro_Shamrock500i_iXon3]]`), y la **reconstrucción tensorial del hipercubo de datos $I(x, y, \lambda)$** mediante análisis multivariado de curvas (MCR-ALS) y descomposición en valores singulares (SVD) para espectroscopía Raman ultra-sensible a nivel de molécula individual.

---

## 2. Electrodinámica del Factor de Realce SERS en Puntos Calientes (*Hotspots*)

La dispersión Raman espontánea es un proceso inelástico de sección eficaz extremadamente débil ($\sigma_{\text{Raman}} \sim 10^{-30} - 10^{-28}\ \text{cm}^2/\text{molécula}$). En la vecindad de una nanoestructura plasmónica de oro o plata, la resonancia plasmónica localizada (LSPR) amplifica tanto el campo eléctrico incidente excitador $\mathbf{E}_0(\omega_L)$ como el campo dispersado inelástico emitido por la molécula $\mathbf{E}_{\text{dip}}(\omega_R)$:

$$\mathbf{E}_{\text{loc}}(\mathbf{r}, \omega_L) = \mathbf{M}(\mathbf{r}, \omega_L) \cdot \mathbf{E}_0(\omega_L)$$

$$\mathbf{E}_{\text{rad}}(\mathbf{r}, \omega_R) = \mathbf{M}(\mathbf{r}, \omega_R) \cdot \mathbf{E}_{\text{dip}}(\omega_R)$$

```
                               PUNTOS CALIENTES PLASMÓNICOS (HOTSPOTS)
                 
                   Au Nanopartícula 1             Au Nanopartícula 2
                     ╭─────────────╮     Gap      ╭─────────────╮
                     │             │   d < 5 nm   │             │
                   ──┼─►           ├───► ||| ◄────┤           ◄─┼── Haz Láser 785 nm
                     │    LSPR     │    HOTSPOT   │    LSPR     │
                     ╰─────────────╯   EF > 10^8  ╰─────────────╯
                                       Molécula
                                       Analito
```

### 2.1 La Ley del Cuarto de Potencia del Campo Eléctrico ($|E|^4$)
Bajo la aproximación de dispersión inelástica con desplazamiento de Stokes moderado ($\omega_L \approx \omega_R$), los tensores de realce de campo local coinciden: $\mathbf{M}(\mathbf{r}, \omega_L) \approx \mathbf{M}(\mathbf{r}, \omega_R) \equiv g(\mathbf{r})$. El **Factor de Realce Electromagnético SERS ($EF_{\text{SERS}}$)** se formula rigurosamente como:

$$EF_{\text{SERS}}(\mathbf{r}) = \left| \frac{\mathbf{E}_{\text{loc}}(\mathbf{r}, \omega_L)}{\mathbf{E}_0(\omega_L)} \right|^2 \cdot \left| \frac{\mathbf{E}_{\text{loc}}(\mathbf{r}, \omega_R)}{\mathbf{E}_0(\omega_R)} \right|^2 \approx \left| \frac{\mathbf{E}_{\text{loc}}(\mathbf{r})}{\mathbf{E}_0} \right|^4$$

| Geometría Plasmónica | Espaciamiento $d$ | Factor de Realce Típico $EF_{\text{SERS}}$ | Régimen de Detección |
|---|:---:|:---:|:---:|
| Monómero AuNP esférico ($80\ \text{nm}$) | — | $10^3 - 10^4$ | Detección de ensamble micromolar |
| Dímero AuNP plasmónico | $5.0\ \text{nm}$ | $10^6 - 10^7$ | Trazas nanomolares |
| Nanodímero de ultra-alta proximidad | $\mathbf{1.5\ \text{nm}}$ | $\mathbf{5 \times 10^8 - 10^9}$ | **Nivel de Molécula Individual (Single-Molecule SERS)** |
| Red 2D periódica (Modo SLR acoplado) | $a = 500\ \text{nm}$ | $10^5 - 10^6$ (delocalizado) | Mapeo macroscópico homogéneo |

---

## 3. Acoplamiento Cinemático y Protocolo Automatizado de Adquisición

El software vincula bidireccionalmente el registro de salida del proceso de nanofabricación con el subsistema de espectroscopía confocal:

```
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                    PIPELINE CINEMÁTICO DE MAPEO SERS                     │
  ├─────────────────────────────────────────────────────────────────────────┤
  │ 1. Ingesta de Coordenadas: Lectura de N nodos impresos (X_i, Y_i).      │
  │ 2. Ordenamiento Topológico TSP: Minimización de tiempo de traslación.   │
  │ 3. Bucle por Nodo i:                                                    │
  │    a. Mover platina piezoeléctrica PI E-709 a (X_i, Y_i).               │
  │    b. Esperar tiempo de asentamiento mecánico (t_settle = 35 ms).       │
  │    c. Abrir obturador de excitación Raman (785 nm / 532 nm).            │
  │    d. Adquirir espectro con Andor iXon3 EMCCD (t_int = 50 - 500 ms).    │
  │    e. Cerrar obturador de excitación (Watchdog activo SYS-201).         │
  │    f. Almacenar espectro calibrado en longitud de onda S_i(lambda).     │
  │ 4. Ensamblado del Hipercubo 3D H(x, y, lambda) en contenedor HDF5.     │
  └─────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Optimización de Trayectoria (Problema del Viajante / TSP Meandro)
Para una red 2D de $M \times N$ nodos, el ordenamiento en zigzag o serpentina (*meander scan*) reduce el tiempo total de traslación frente al barrido estándar con retorno de carro:

$$T_{\text{meander}} = \sum_{k=1}^{MN-1} \frac{\|\mathbf{r}_{k+1} - \mathbf{r}_k\|}{v_{\text{piezo}}} \approx (MN) \frac{a}{v_{\text{piezo}}}$$

donde $a$ es la constante de red y $v_{\text{piezo}} \approx 200\ \mu\text{m/s}$ la velocidad máxima de la platina flexural sin excitar resonancias mecánicas.

---

## 4. Reconstrucción Tensorial del Hipercubo de Datos $\mathbf{\mathcal{H}}(X, Y, \lambda)$

Los datos adquiridos sobre una grilla espacial discretizada se estructuran formalmente como un **tensor de orden 3**:

$$\mathbf{\mathcal{H}} \in \mathbb{R}^{N_x \times N_y \times N_\lambda}$$

donde $N_x, N_y$ son las dimensiones espaciales y $N_\lambda = 1024$ (canales espectrales del sensor EMCCD).

```
                      ESTRUCTURA DEL HIPERCUBO ESPECTRAL 3D
                               
                               Longitud de Onda lambda
                                   /
                                  /
                                 ┌────────────────────────┐
                                /                        /│
                               ┌────────────────────────┐ │
                              /                        /│ │
                             ┌────────────────────────┐ │ │
                             │                        │ │ │
                   Eje Y     │    Canal Confocal      │ │ │
                    ▲        │    Raman / SERS        │ │/
                    │        │    I(x, y, lambda)     │ /
                    │        └────────────────────────┘/
                    └────────────────► Eje X
```

### 4.1 Descomposición Multivariada de Curvas (MCR-ALS)
El hipercubo desplegado en una matriz bidimensional $\mathbf{D} \in \mathbb{R}^{(N_x N_y) \times N_\lambda}$ se descompone según la ley bilineal de Beer-Lambert generalizada:

$$\mathbf{D} = \mathbf{C} \mathbf{S}^T + \mathbf{E}$$

donde:
* $\mathbf{C} \in \mathbb{R}^{(N_x N_y) \times K}$ representa los perfiles de concentración espacial de los $K$ componentes químicos o modos plasmónicos presentes.
* $\mathbf{S} \in \mathbb{R}^{N_\lambda \times K}$ contiene los espectros puros de cada analito libre de fondo de fluorescencia.
* $\mathbf{E}$ es la matriz de residuos no correlacionados, optimizada mediante mínimos cuadrados alternados bajo restricciones de no negatividad ($\mathbf{C} \ge 0, \mathbf{S} \ge 0$).

---

## 5. Implementación Computacional en Python

```python
"""
CAT-205: Mapeo Hiperespectral SERS Confocal Automatizado y Reconstrucción Tensorial.
Generación de trayectorias, adquisición simulada y ensamblado de hipercubos 3D.
"""
from typing import Tuple, List, Dict
import numpy as np

class SERSHyperspectralMapper:
    def __init__(
        self,
        wavelengths_nm: np.ndarray,
        laser_wavelength_nm: float = 785.0
    ):
        self.wavelengths = wavelengths_nm
        self.laser_wl = laser_wavelength_nm
        # Convertir a desplazamiento Raman en cm^-1
        self.raman_shifts = (1e7 / self.laser_wl) - (1e7 / self.wavelengths)

    def optimize_meander_trajectory(self, grid_coords: np.ndarray) -> np.ndarray:
        """
        Ordena las coordenadas (N, 2) en trayectoria meandro (serpentina)
        para minimizar el tiempo de desplazamiento de la platina piezoeléctrica.
        """
        # Agrupar por filas (orden ascendente en Y con tolerancia)
        y_vals = np.round(grid_coords[:, 1], decimals=3)
        unique_y = np.unique(y_vals)
        ordered_indices = []

        for row_idx, y_val in enumerate(unique_y):
            row_mask = np.isclose(y_vals, y_val)
            row_indices = np.where(row_mask)[0]
            # Ordenar según X: alternar izquierda->derecha y derecha->izquierda
            x_sorted = row_indices[np.argsort(grid_coords[row_indices, 0])]
            if row_idx % 2 == 1:
                x_sorted = x_sorted[::-1]
            ordered_indices.extend(x_sorted.tolist())

        return grid_coords[ordered_indices]

    def build_hyperspectral_cube(
        self,
        grid_coords: np.ndarray,
        spectra_matrix: np.ndarray,
        grid_shape: Tuple[int, int]
    ) -> np.ndarray:
        """
        Construye el hipercubo tensorial H(Ny, Nx, N_lambda) a partir de coordenadas y espectros.
        spectra_matrix: shape (N_puntos, N_lambda)
        """
        ny, nx = grid_shape
        n_lambda = len(self.wavelengths)
        hypercube = np.zeros((ny, nx, n_lambda), dtype=np.float32)

        for idx, spec in enumerate(spectra_matrix):
            row = idx // nx
            col = idx % nx
            # Invertir fila si es serpentina
            if row % 2 == 1:
                col = (nx - 1) - col
            hypercube[row, col, :] = spec

        return hypercube

    def compute_band_integrated_map(
        self,
        hypercube: np.ndarray,
        peak_center_cm1: float,
        band_width_cm1: float = 20.0
    ) -> np.ndarray:
        """Extrae un mapa 2D de intensidad integrando sobre una banda Raman específica."""
        band_mask = np.abs(self.raman_shifts - peak_center_cm1) <= (band_width_cm1 / 2.0)
        return np.sum(hypercube[:, :, band_mask], axis=2)
```

---

## 6. Conclusiones y Conexión Instrumental

1. El mapeo automatizado por coordenadas discretas reduce el tiempo de caracterización espectral de grillas completas de varias horas a **pocos minutos**, protegiendo a las moléculas adsorbidas contra el fotoblanqueamiento.
2. Al acoplarse con la serialización HDF5 canónica (`[[CAT-401_Estandar_Serializacion_Jerarquica_Contenedor_HDF5]]`), los hipercubos adquiridos quedan indexados de forma permanente junto a las imágenes confocales y los vectores de deriva.
