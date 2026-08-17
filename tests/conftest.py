"""Caminos de test: el paquete local `avs` y, si existe, el hermano EMS.

La dependencia de EMS es SOLO de tests: generan memorias reales contra las
que auditar. El código de AVS jamás importa EMS ([D-04] — el auditor no
depende de lo auditado).
"""
from __future__ import annotations

import sys
from pathlib import Path

_RAIZ_AVS = Path(__file__).resolve().parents[1]
if str(_RAIZ_AVS) not in sys.path:
    sys.path.insert(0, str(_RAIZ_AVS))

_RAIZ_EMS = _RAIZ_AVS.parent / "EMS-Evidenced-Memory-System"
if (_RAIZ_EMS / "memory" / "sqlite_store.py").is_file():
    sys.path.insert(0, str(_RAIZ_EMS))
