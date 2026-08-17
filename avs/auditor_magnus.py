"""El Auditor — verificación por recomputación de las citas RAG de Magnus.

Segunda mitad del Componente 2 de AVS ([D-03]): dada una traza JSONL de
consultas de MagnusAgent y la raíz de LLM-Wiki, recomputa de forma
independiente el hash de cada chunk citado y el snapshot_id de la wiki, y
reporta cualquier discrepancia. Mismo principio rector que `auditor.py`
([D-04], independencia): AVS nunca importa código de MagnusAgent — el
algoritmo de troceo, hash y snapshot se re-declara aquí. Fuente de verdad:
`MagnusAgent/kernel/rag/file_store.py` (`_sha`, `_index_document`,
`ingest`) y `MagnusAgent/orchestration/audit.py` (`build_entry`, forma de
las trazas). Si Magnus cambia ese algoritmo, este archivo es el que debe
actualizarse.

Qué verifica:

  M1  Cada línea de traza es JSON válido y trae `conocimiento.chunks` /
      `conocimiento.version`.
  M2  El snapshot_id declarado coincide con el recomputado desde la wiki
      actual — si no coincide, la wiki cambió desde que se emitió la cita
      (deriva legítima, no necesariamente manipulación).
  M3  Cada `chunk_id` citado tiene el formato `<fuente>#<idx>`.
  M4  La fuente citada existe como archivo `.md` en la wiki actual.
  M5  El `chunk_id` citado es producido por el troceo real de esa fuente.
  M6  El hash citado coincide con el hash recomputado del pasaje. Si el
      snapshot ya no coincidía (M2), un hash distinto es la consecuencia
      esperada de la deriva y se reporta como `advertencia`; si el
      snapshot sí coincidía pero el hash no, es `violacion` — el contenido
      dice ser el mismo pero el pasaje citado no calza.

Al igual que el auditor de EMS, esto es solo lectura: nunca se escribe en
la wiki ni en los archivos de traza.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from avs.auditor import ADVERTENCIA, VIOLACION, AuditorError

#: Reimplementación literal de `MagnusAgent/kernel/rag/file_store.py::_sha`.
def _sha(text: str, n: int = 16) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:n]


@dataclass(frozen=True)
class HallazgoCita:
    codigo: str
    severidad: str
    detalle: str
    chunk_id: str | None = None
    trace_file: str | None = None
    linea: int | None = None


@dataclass(frozen=True)
class VeredictoMagnus:
    trace_source: str
    wiki_root: str
    snapshot_actual: str
    total_entradas: int
    total_citas: int
    hallazgos: tuple[HallazgoCita, ...]

    @property
    def ok(self) -> bool:
        return not self.violaciones

    @property
    def violaciones(self) -> tuple[HallazgoCita, ...]:
        return tuple(h for h in self.hallazgos if h.severidad == VIOLACION)

    @property
    def advertencias(self) -> tuple[HallazgoCita, ...]:
        return tuple(h for h in self.hallazgos if h.severidad == ADVERTENCIA)


def recomputar_wiki(wiki_root: Path) -> tuple[str, dict[str, dict[str, str]], set[str]]:
    """Reimplementación literal de `FileWikiStore.ingest()` + `_index_document()`:
    mismo orden, misma lectura tolerante a errores, mismo troceo, mismo hash —
    para que una divergencia real de contenido sea la única causa de un
    mismatch, no una diferencia de algoritmo."""
    huellas: list[str] = []
    chunks_reales: dict[str, dict[str, str]] = {}
    archivos_existentes: set[str] = set()

    for md in sorted(wiki_root.rglob("*.md")):
        rel = md.relative_to(wiki_root)
        try:
            raw = md.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        source = str(rel).replace("\\", "/")
        archivos_existentes.add(source)
        huellas.append(f"{source}:{_sha(raw, 32)}")
        for chunk_id, texto in _trocear(raw, source):
            chunks_reales[chunk_id] = {"hash": _sha(texto), "source": source}

    snapshot_actual = _sha("\n".join(huellas)) if huellas else "vacio"
    return snapshot_actual, chunks_reales, archivos_existentes


def _trocear(raw: str, source: str) -> list[tuple[str, str]]:
    """Reimplementación literal de `_index_document`: quita front-matter,
    trocea por encabezados/líneas en blanco, descarta fragmentos < 40
    caracteres, trunca a 1200."""
    raw = re.sub(r"^---\n.*?\n---\n", "", raw, count=1, flags=re.S)
    buf: list[str] = []
    idx = 0
    salida: list[tuple[str, str]] = []

    def flush() -> None:
        nonlocal buf, idx
        texto = " ".join(buf).strip()
        buf = []
        if len(texto) < 40:
            return
        idx += 1
        salida.append((f"{source}#{idx}", texto[:1200]))

    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("#"):
            flush()
        elif not s:
            flush()
        else:
            buf.append(s)
    flush()
    return salida


class AuditorMagnus:
    """Audita citas RAG de Magnus recomputando hash y snapshot desde la wiki."""

    def __init__(self, trace: str | Path, wiki_root: str | Path):
        wiki = Path(wiki_root)
        if not wiki.is_dir():
            raise AuditorError(f"no existe una raíz de wiki en {wiki}")
        self.wiki_root = wiki

        ruta_trace = Path(trace)
        if ruta_trace.is_dir():
            archivos = sorted(ruta_trace.glob("magnus-*.jsonl"))
            if not archivos:
                raise AuditorError(
                    f"{ruta_trace} no contiene archivos magnus-*.jsonl — "
                    "¿MAGNUS_TRACE_DIR apunta aquí?")
            self.trace_files = archivos
        elif ruta_trace.is_file():
            self.trace_files = [ruta_trace]
        else:
            raise AuditorError(f"no existe traza en {ruta_trace}")
        self.trace_source = str(trace)

    def auditar(self) -> VeredictoMagnus:
        hallazgos: list[HallazgoCita] = []

        snapshot_actual, chunks_reales, archivos_existentes = recomputar_wiki(
            self.wiki_root)

        total_entradas = 0
        total_citas = 0
        for archivo in self.trace_files:
            with open(archivo, "r", encoding="utf-8") as f:
                for numero_linea, linea in enumerate(f, start=1):
                    linea = linea.strip()
                    if not linea:
                        continue
                    total_entradas += 1
                    n_citas = self._auditar_linea(
                        linea, archivo, numero_linea, snapshot_actual,
                        chunks_reales, archivos_existentes, hallazgos)
                    total_citas += n_citas

        return VeredictoMagnus(
            trace_source=self.trace_source, wiki_root=str(self.wiki_root),
            snapshot_actual=snapshot_actual, total_entradas=total_entradas,
            total_citas=total_citas, hallazgos=tuple(hallazgos))

    # -- auditoría de trazas ------------------------------------------------------------
    @staticmethod
    def _auditar_linea(linea: str, archivo: Path, numero_linea: int,
                       snapshot_actual: str, chunks_reales: dict[str, dict[str, str]],
                       archivos_existentes: set[str], hallazgos: list) -> int:

        def hallazgo(codigo: str, severidad: str, detalle: str,
                    chunk_id: str | None = None) -> None:
            hallazgos.append(HallazgoCita(
                codigo, severidad, detalle, chunk_id=chunk_id,
                trace_file=archivo.name, linea=numero_linea))

        try:
            entrada: Any = json.loads(linea)
        except json.JSONDecodeError as exc:
            hallazgo("linea_no_json", VIOLACION,
                     f"línea no es JSON válido: {exc}")
            return 0

        conocimiento = entrada.get("conocimiento") if isinstance(entrada, dict) else None
        if not isinstance(conocimiento, dict) or "chunks" not in conocimiento:
            hallazgo("entrada_malformada", VIOLACION,
                     "la entrada no trae conocimiento.chunks: no hay nada "
                     "que auditar en esta línea")
            return 0

        version = conocimiento.get("version")
        snapshot_coincide = version == f"wiki:{snapshot_actual}"
        if not snapshot_coincide:
            hallazgo("snapshot_no_coincide", ADVERTENCIA,
                     f"la traza declara {version!r} pero la wiki actual da "
                     f"wiki:{snapshot_actual} — la wiki cambió desde que se "
                     "emitió esta cita")

        citas = conocimiento.get("chunks")
        if not isinstance(citas, list):
            hallazgo("entrada_malformada", VIOLACION,
                     "conocimiento.chunks no es una lista")
            return 0

        for cita in citas:
            if not isinstance(cita, dict) or "id" not in cita or "hash" not in cita:
                hallazgo("cita_malformada", VIOLACION,
                         f"cita sin id/hash: {cita!r}")
                continue
            chunk_id = cita["id"]
            hash_citado = cita["hash"]

            if "#" not in chunk_id:
                hallazgo("chunk_id_formato_invalido", VIOLACION,
                         f"chunk_id {chunk_id!r} no tiene el formato "
                         "<fuente>#<idx>", chunk_id=chunk_id)
                continue

            source = chunk_id.rsplit("#", 1)[0]
            if source not in archivos_existentes:
                hallazgo("fuente_inexistente", VIOLACION,
                         f"la fuente {source!r} no existe en la wiki actual",
                         chunk_id=chunk_id)
                continue

            real = chunks_reales.get(chunk_id)
            if real is None:
                hallazgo("chunk_id_inexistente", VIOLACION,
                         f"el archivo existe pero el troceo actual no "
                         f"produce el chunk {chunk_id!r}", chunk_id=chunk_id)
                continue

            if real["hash"] != hash_citado:
                severidad = ADVERTENCIA if not snapshot_coincide else VIOLACION
                detalle = (
                    f"hash citado {hash_citado!r} no coincide con el "
                    f"recomputado {real['hash']!r}"
                    + (" — explicado por la deriva de snapshot ya reportada"
                       if severidad == ADVERTENCIA else
                       " pese a que el snapshot de la wiki coincide: el "
                       "pasaje citado no es el que existe hoy"))
                hallazgo("hash_no_coincide", severidad, detalle, chunk_id=chunk_id)

        return len(citas)
