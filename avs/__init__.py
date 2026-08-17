"""AVS — Agent Verification System.

La capa de verificación y certificación del ecosistema ([D-01..D-06] en
COLABORACION.md). Este paquete contiene **El Auditor** (T-01): verificación
por recomputación de la cadena de custodia de EMS, en modo solo lectura —
AVS lee y reporta, nunca corrige lo que audita ([D-04]).
"""
from avs.auditor import (ADVERTENCIA, VIOLACION, AuditorEMS, AuditorError,
                         Hallazgo, Veredicto)

__version__ = "0.1.0"
__all__ = ["ADVERTENCIA", "VIOLACION", "AuditorEMS", "AuditorError",
           "Hallazgo", "Veredicto", "__version__"]
