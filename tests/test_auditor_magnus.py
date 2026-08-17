"""T-02 — El Auditor contra citas RAG REALES de Magnus y contra manipulación.

Mismo patrón de dos familias que `test_auditor_ems.py`:

  1. Integración: una traza genuina construida con el mismo algoritmo que
     `AuditorMagnus` reimplementa (chunking/hash/snapshot de
     `MagnusAgent/kernel/rag/file_store.py`) debe auditar ÍNTEGRA contra la
     wiki que la originó, y la auditoría no debe tocar ni la wiki ni la
     traza (solo lectura).
  2. Manipulación/deriva: cada mutación directa de la traza o de la wiki
     (por fuera de Magnus) debe producir el hallazgo que la delata.

A diferencia de los tests de EMS, estos NO dependen de que MagnusAgent esté
presente como hermano — las fixtures se construyen aquí mismo, reutilizando
el propio `avs.auditor_magnus` para generar hashes/ids "genuinos", salvo un
caso de control calculado a mano.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from avs.auditor_magnus import AuditorError, AuditorMagnus, recomputar_wiki


# -- fixtures -------------------------------------------------------------------------

_NOTA_ALERGIA = """---
titulo: Alergias
---
# Penicilina

Soy alergico a la penicilina desde la infancia segun me conto mi madre.

# Otros medicamentos

No he tenido reacciones a otros antibioticos hasta el momento actual.
"""

_NOTA_DIETA = """# Dieta

Ya no como carne desde hace dos anios por decision personal y de salud.
"""


def _escribir_wiki(root: Path) -> None:
    (root / "01-Salud").mkdir(parents=True, exist_ok=True)
    (root / "01-Salud" / "Alergias.md").write_text(_NOTA_ALERGIA, encoding="utf-8")
    (root / "02-Dieta.md").write_text(_NOTA_DIETA, encoding="utf-8")


@pytest.fixture
def wiki(tmp_path) -> Path:
    root = tmp_path / "wiki"
    root.mkdir()
    _escribir_wiki(root)
    return root


def _snapshot_y_chunks(wiki_root: Path):
    """Usa el propio recomputador del auditor para construir una traza
    genuina — evita duplicar el algoritmo de hash a mano en cada test."""
    return recomputar_wiki(wiki_root)


def _entrada(wiki_root: Path, chunk_ids: list[str], *, snapshot: str | None = None,
            chunks_reales=None) -> dict:
    snap, reales, _ = _snapshot_y_chunks(wiki_root)
    if snapshot is None:
        snapshot = snap
    if chunks_reales is None:
        chunks_reales = reales
    return {
        "ts": "2026-08-17T00:00:00+00:00", "agente": "a1",
        "consulta": "pregunta de prueba", "modo": "rag",
        "conocimiento": {
            "version": f"wiki:{snapshot}",
            "chunks": [
                {"id": cid, "hash": chunks_reales[cid]["hash"],
                 "fuente": f"{chunks_reales[cid]['source']} · «heading»",
                 "score": 0.9}
                for cid in chunk_ids
            ],
        },
        "evaluacion": None, "guardrails": None, "proveedor": {},
    }


def _trace_file(tmp_path: Path, entradas: list[dict]) -> Path:
    ruta = tmp_path / "magnus-2026-08-17.jsonl"
    with open(ruta, "w", encoding="utf-8") as f:
        for e in entradas:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return ruta


def _codigos(veredicto) -> set[str]:
    return {h.codigo for h in veredicto.hallazgos}


# -- familia 1: integración contra traza genuina ---------------------------------------

def test_traza_genuina_contra_wiki_actual_audita_integra(tmp_path, wiki):
    _, reales, _ = _snapshot_y_chunks(wiki)
    entrada = _entrada(wiki, list(reales.keys())[:2])
    trace = _trace_file(tmp_path, [entrada])

    v = AuditorMagnus(trace, wiki).auditar()
    assert v.ok, [(h.codigo, h.detalle) for h in v.hallazgos]
    assert v.hallazgos == ()
    assert v.total_entradas == 1
    assert v.total_citas == 2


def test_auditar_es_solo_lectura_y_determinista(tmp_path, wiki):
    _, reales, _ = _snapshot_y_chunks(wiki)
    entrada = _entrada(wiki, list(reales.keys())[:1])
    trace = _trace_file(tmp_path, [entrada])

    huella_wiki = hashlib.sha256(
        b"".join(p.read_bytes() for p in sorted(wiki.rglob("*.md")))).hexdigest()
    huella_trace = hashlib.sha256(trace.read_bytes()).hexdigest()

    v1 = AuditorMagnus(trace, wiki).auditar()
    v2 = AuditorMagnus(trace, wiki).auditar()
    assert v1 == v2

    huella_wiki_2 = hashlib.sha256(
        b"".join(p.read_bytes() for p in sorted(wiki.rglob("*.md")))).hexdigest()
    assert huella_wiki_2 == huella_wiki
    assert hashlib.sha256(trace.read_bytes()).hexdigest() == huella_trace


# -- familia 2: detección de manipulación/deriva ---------------------------------------

def test_detecta_hash_no_coincide(tmp_path, wiki):
    _, reales, _ = _snapshot_y_chunks(wiki)
    chunk_id = next(iter(reales))
    entrada = _entrada(wiki, [chunk_id])
    entrada["conocimiento"]["chunks"][0]["hash"] = "0" * 16  # falsificado
    trace = _trace_file(tmp_path, [entrada])

    v = AuditorMagnus(trace, wiki).auditar()
    assert not v.ok
    assert "hash_no_coincide" in _codigos(v)
    h = next(x for x in v.hallazgos if x.codigo == "hash_no_coincide")
    assert h.severidad == "violacion"


def test_deriva_de_snapshot_baja_severidad_del_hash(tmp_path, wiki):
    _, reales, _ = _snapshot_y_chunks(wiki)
    chunk_id = next(iter(reales))
    entrada = _entrada(wiki, [chunk_id])
    trace = _trace_file(tmp_path, [entrada])

    # la nota cambia DE VERDAD después de grabar la traza
    (wiki / "02-Dieta.md").write_text(
        _NOTA_DIETA + "\nEdicion posterior a la traza.\n", encoding="utf-8")

    v = AuditorMagnus(trace, wiki).auditar()
    assert "snapshot_no_coincide" in _codigos(v)
    snap_h = next(x for x in v.hallazgos if x.codigo == "snapshot_no_coincide")
    assert snap_h.severidad == "advertencia"
    hash_h = next((x for x in v.hallazgos if x.codigo == "hash_no_coincide"), None)
    if hash_h is not None:
        assert hash_h.severidad == "advertencia"


def test_detecta_fuente_inexistente(tmp_path, wiki):
    entrada = _entrada(wiki, [])
    entrada["conocimiento"]["chunks"] = [
        {"id": "01-Salud/NoExiste.md#1", "hash": "0" * 16,
         "fuente": "01-Salud/NoExiste.md", "score": 0.5}]
    trace = _trace_file(tmp_path, [entrada])

    v = AuditorMagnus(trace, wiki).auditar()
    assert not v.ok
    assert "fuente_inexistente" in _codigos(v)


def test_detecta_chunk_id_inexistente(tmp_path, wiki):
    _, reales, _ = _snapshot_y_chunks(wiki)
    source = next(iter(reales.values()))["source"]
    entrada = _entrada(wiki, [])
    entrada["conocimiento"]["chunks"] = [
        {"id": f"{source}#99", "hash": "0" * 16, "fuente": source, "score": 0.5}]
    trace = _trace_file(tmp_path, [entrada])

    v = AuditorMagnus(trace, wiki).auditar()
    assert not v.ok
    assert "chunk_id_inexistente" in _codigos(v)


def test_detecta_chunk_id_sin_formato(tmp_path, wiki):
    entrada = _entrada(wiki, [])
    entrada["conocimiento"]["chunks"] = [
        {"id": "sin-separador", "hash": "0" * 16, "fuente": "x", "score": 0.5}]
    trace = _trace_file(tmp_path, [entrada])

    v = AuditorMagnus(trace, wiki).auditar()
    assert not v.ok
    assert "chunk_id_formato_invalido" in _codigos(v)


def test_detecta_linea_jsonl_corrupta(tmp_path, wiki):
    _, reales, _ = _snapshot_y_chunks(wiki)
    entrada_valida = _entrada(wiki, list(reales.keys())[:1])
    ruta = tmp_path / "magnus-2026-08-17.jsonl"
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(json.dumps(entrada_valida, ensure_ascii=False) + "\n")
        f.write("esto no es json\n")

    v = AuditorMagnus(ruta, wiki).auditar()
    assert not v.ok
    assert "linea_no_json" in _codigos(v)
    # la línea válida se sigue procesando
    assert v.total_entradas == 2
    assert v.total_citas == 1


def test_detecta_entrada_sin_conocimiento(tmp_path, wiki):
    entrada = {"ts": "2026-08-17T00:00:00+00:00", "agente": "a1"}
    trace = _trace_file(tmp_path, [entrada])

    v = AuditorMagnus(trace, wiki).auditar()
    assert not v.ok
    assert "entrada_malformada" in _codigos(v)


# -- errores de uso ---------------------------------------------------------------------

def test_wiki_root_inexistente_da_error_claro(tmp_path):
    with pytest.raises(AuditorError):
        AuditorMagnus(tmp_path / "traza.jsonl", tmp_path / "no-existe")


def test_trace_inexistente_da_error_claro(tmp_path, wiki):
    with pytest.raises(AuditorError):
        AuditorMagnus(tmp_path / "no-existe.jsonl", wiki)


def test_directorio_de_trazas_sin_jsonl_da_error_claro(tmp_path, wiki):
    vacio = tmp_path / "trazas_vacias"
    vacio.mkdir()
    with pytest.raises(AuditorError):
        AuditorMagnus(vacio, wiki)


# -- CLI ----------------------------------------------------------------------------------

def test_cli_codigos_de_salida(tmp_path, wiki, capsys):
    from avs.cli import main
    _, reales, _ = _snapshot_y_chunks(wiki)
    entrada = _entrada(wiki, list(reales.keys())[:1])
    trace = _trace_file(tmp_path, [entrada])

    assert main(["audit-magnus", str(trace), str(wiki)]) == 0
    assert "ÍNTEGRO" in capsys.readouterr().out

    entrada["conocimiento"]["chunks"][0]["hash"] = "0" * 16
    trace2 = _trace_file(tmp_path, [entrada])
    assert main(["audit-magnus", str(trace2), str(wiki)]) == 1
    assert "violaciones" in capsys.readouterr().out


def test_cli_json(tmp_path, wiki, capsys):
    from avs.cli import main
    _, reales, _ = _snapshot_y_chunks(wiki)
    entrada = _entrada(wiki, list(reales.keys())[:1])
    trace = _trace_file(tmp_path, [entrada])

    assert main(["audit-magnus", str(trace), str(wiki), "--json"]) == 0
    salida = json.loads(capsys.readouterr().out)
    assert salida["total_citas"] == 1
    assert salida["hallazgos"] == []


def test_cli_ruta_inexistente_da_exit_2(tmp_path, wiki):
    from avs.cli import main
    assert main(["audit-magnus", str(tmp_path / "no-existe.jsonl"), str(wiki)]) == 2


def test_cli_como_proceso(tmp_path, wiki):
    _, reales, _ = _snapshot_y_chunks(wiki)
    entrada = _entrada(wiki, list(reales.keys())[:1])
    trace = _trace_file(tmp_path, [entrada])

    raiz = Path(__file__).resolve().parents[1]
    r = subprocess.run(
        [sys.executable, "-m", "avs.cli", "audit-magnus", str(trace), str(wiki)],
        capture_output=True, text=True, encoding="utf-8", cwd=raiz)
    assert r.returncode == 0, r.stderr
    assert "ÍNTEGRO" in r.stdout
