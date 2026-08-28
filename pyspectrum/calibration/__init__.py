# -*- coding: utf-8 -*-
"""
Módulos de Calibración Espectral, Normalización de Lámpara Halógena y Ajustes Analíticos
"""
from .halogen_lamp import HalogenLampCalibration, glue_steps
from .fit_raman_water import fit_signal_raman
from .fit_polynomial import fit_signal_polynomial
