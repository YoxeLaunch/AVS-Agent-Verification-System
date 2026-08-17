"""T-01 — El Auditor contra memorias REALES de EMS y contra adulteraciones.

Dos familias:

  1. Integración: una memoria producida por el pipeline real de EMS
     (extracción → refuerzos → promoción → expiración + sucesión canónica
     de docs/01) debe auditar ÍNTEGRA — cero hallazgos, y la auditoría no
     toca el archivo (solo lectura).
  2. Adulteración: cada mutación cruda de la DB (DELETE/UPDATE/INSERT
     directo por fuera de EMS) debe producir el hallazgo que la delata.
     El auditor no puede escribir; su única arma es detectar.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from avs.auditor import ADVERTENCIA, AuditorEMS, AuditorError

try:
    from memory.capture import Consent, ConversationRecord, Turn
    from memory.decay import expire_stale_claims
    from memory.extraction import extract_candidates
    from memory.promotion import promote_to_t3
    from memory.reinforcement import reinforce_or_create
    from memory.sqlite_store import SqliteClaimStore
    EMS_DISPONIBLE = True
except ImportError:  # EMS ausente: solo corren los tests que no lo necesitan
    EMS_DISPONIBLE = False

requires_ems = pytest.mark.skipif(
    not EMS_DISPONIBLE, reason="EMS no está en el directorio hermano")

_TS = datetime.now(timezone.utc).isoformat(timespec="seconds")


def _procesar(store, texto: str, conv_id: str):
    """El bucle de un llamante real: registrar fuente y correr el pipeline.
    Nada de eventos manuales — si aparecen, los emitió EMS."""
    record = ConversationRecord(
        id=conv_id, agent_id="a1", user_id="user-1", started_at=_TS,
        turns=(Turn("user", texto, _TS),),
        consent=Consent(True, "raw_conversation", "user-1", _TS))
    store.record_conversation_source(
        conv_id, agent_id="a1", user_id="user-1", started_at=_TS)
    resultado = None
    for candidato in extract_candidates(record):
        resultado = reinforce_or_create(candidato, store)
    return resultado


def _memoria_canonica(db: Path) -> dict[str, str]:
    """El ciclo de vida completo de EMS en una DB real: promoción con
    expiración, más la sucesión canónica ('ya no como carne')."""
    store = SqliteClaimStore(db)
    alergia = None
    for i in range(1, 4):
        alergia = _procesar(store, "soy alergico a la penicilina", f"conv-{i}")
    assert promote_to_t3(alergia, store).approved

    original = _procesar(store, "como carne todos los dias", "conv-10")
    nuevo = _procesar(store, "ya no como carne", "conv-11")

    claim = store.get(alergia.id)
    claim.last_reinforced_at = (datetime.now(timezone.utc) - timedelta(
        days=claim.decay_half_life_days * 10)).isoformat(timespec="seconds")
    store.add(claim)  # envejecer sin evento (escritura legítima sin custodia)
    assert expire_stale_claims(store)
    store.close()
    return {"alergia": alergia.id, "original": original.id, "nuevo": nuevo.id}


def _adulterar(db: Path, sql: str, params=()) -> None:
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(sql, params)
    conn.commit()
    conn.close()


def _codigos(veredicto) -> set[str]:
    return {h.codigo for h in veredicto.hallazgos}


@pytest.fixture
def memoria(tmp_path):
    db = tmp_path / "ems.db"
    return db, _memoria_canonica(db)


# -- familia 1: integración contra memoria real -----------------------------------

@requires_ems
def test_memoria_real_de_ems_audita_integra(memoria):
    db, ids = memoria
    v = AuditorEMS(db).auditar()
    assert v.ok, [(h.codigo, h.detalle) for h in v.hallazgos]
    assert v.hallazgos == ()
    assert v.total_claims == 3
    assert v.total_eventos == 8
    assert v.schema_version == 2


@requires_ems
def test_auditar_es_solo_lectura_y_determinista(memoria):
    db, _ = memoria
    huella = hashlib.sha256(db.read_bytes()).hexdigest()
    v1 = AuditorEMS(db).auditar()
    v2 = AuditorEMS(db).auditar()
    assert v1 == v2
    assert hashlib.sha256(db.read_bytes()).hexdigest() == huella, \
        "el auditor no puede escribir lo que audita ([D-04])"


# -- familia 2: detección de adulteración ------------------------------------------

@requires_ems
def test_detecta_claim_borrado(memoria):
    db, ids = memoria
    _adulterar(db, "DELETE FROM claims WHERE id = ?", (ids["alergia"],))
    v = AuditorEMS(db).auditar()
    assert not v.ok
    assert "evento_huerfano" in _codigos(v)


@requires_ems
def test_detecta_tier_adulterado_en_fila(memoria):
    db, ids = memoria
    _adulterar(db, "UPDATE claims SET tier = 'T1' WHERE id = ?",
               (ids["alergia"],))
    v = AuditorEMS(db).auditar()
    assert "estado_no_derivable" in _codigos(v)
    hallazgo = next(h for h in v.hallazgos if h.codigo == "estado_no_derivable")
    assert hallazgo.severidad == ADVERTENCIA


@requires_ems
def test_detecta_tipo_de_evento_desconocido(memoria):
    db, _ = memoria
    _adulterar(db, "INSERT INTO events (ts, tipo, claim_id, payload) VALUES "
                   "('2026-08-16T00:00:00+00:00', 'promoton', NULL, NULL)")
    v = AuditorEMS(db).auditar()
    assert "tipo_desconocido" in _codigos(v)
    assert not v.ok


@requires_ems
def test_detecta_promocion_con_salto_de_tier(memoria):
    db, ids = memoria
    payload = json.dumps({
        "estado_anterior": "active", "estado_nuevo": "active",
        "tier_anterior": "T1", "tier_nuevo": "T3",
        "contador_anterior": 1, "contador_nuevo": 1,
        "evaluador": "Falsificado", "motivo": "adulteración"})
    _adulterar(db, "INSERT INTO events (ts, tipo, claim_id, payload) VALUES "
                   "('2026-08-16T00:00:00+00:00', 'promotion', ?, ?)",
               (ids["nuevo"], payload))
    v = AuditorEMS(db).auditar()
    assert "salto_promocion_ilegal" in _codigos(v)
    assert not v.ok


@requires_ems
def test_detecta_sucesion_rota(memoria):
    db, ids = memoria
    _adulterar(db, "UPDATE claims SET superseded_by = NULL WHERE id = ?",
               (ids["original"],))
    v = AuditorEMS(db).auditar()
    assert "sucesion_no_reciproca" in _codigos(v)
    assert not v.ok


@requires_ems
def test_detecta_origen_eliminado(memoria):
    db, ids = memoria
    _adulterar(db, "DELETE FROM events WHERE tipo = 'extraction' "
                   "AND claim_id = ?", (ids["original"],))
    v = AuditorEMS(db).auditar()
    assert "origen_no_auditable" in _codigos(v)
    assert not v.ok


@requires_ems
def test_detecta_payload_mutilado(memoria):
    db, ids = memoria
    seq = sqlite3.connect(db).execute(
        "SELECT seq FROM events WHERE tipo = 'reinforcement' AND claim_id = ?"
        " ORDER BY seq LIMIT 1", (ids["alergia"],)).fetchone()[0]
    _adulterar(db, "UPDATE events SET payload = NULL WHERE seq = ?", (seq,))
    v = AuditorEMS(db).auditar()
    assert "payload_incompleto" in _codigos(v)
    assert not v.ok


def test_db_inexistente_da_error_claro(tmp_path):
    with pytest.raises(AuditorError):
        AuditorEMS(tmp_path / "no-existe.db").auditar()


# -- CLI ----------------------------------------------------------------------------

@requires_ems
def test_cli_codigos_de_salida(memoria, capsys):
    from avs.cli import main
    db, ids = memoria
    assert main(["audit-ems", str(db)]) == 0
    assert "ÍNTEGRO" in capsys.readouterr().out

    _adulterar(db, "DELETE FROM claims WHERE id = ?", (ids["nuevo"],))
    assert main(["audit-ems", str(db)]) == 1
    assert "violaciones" in capsys.readouterr().out


@requires_ems
def test_cli_json(memoria, capsys):
    from avs.cli import main
    db, _ = memoria
    assert main(["audit-ems", str(db), "--json"]) == 0
    salida = json.loads(capsys.readouterr().out)
    assert salida["total_claims"] == 3
    assert salida["hallazgos"] == []


@requires_ems
def test_cli_como_proceso(memoria):
    db, _ = memoria
    raiz = Path(__file__).resolve().parents[1]
    r = subprocess.run(
        [sys.executable, "-m", "avs.cli", "audit-ems", str(db)],
        capture_output=True, text=True, cwd=raiz)
    assert r.returncode == 0, r.stderr
    assert "ÍNTEGRO" in r.stdout
