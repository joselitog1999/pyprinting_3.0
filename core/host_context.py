# -*- coding: utf-8 -*-
"""Contexto de un programa abierto como satélite huésped (paso 13 del bloque A, DEC-040; R2-arq §3.1).

El anfitrión (PySpectrum 3.0) es el dueño de la platina, de las tareas DAQ y del espejo de detección. El
huésped (PyPrinting, el contrapropagante) usa esos recursos y nunca los crea, reconfigura ni destruye:
no conecta la platina (su `connect()` hace home y libera el interlock) ni cambia el perfil de hardware.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class HostContext:
    name: str
