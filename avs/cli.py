"""CLI de AVS — `avs audit-ems <db>`.

Códigos de salida (contrato para CI, componente 1): 0 veredicto íntegro,
1 violaciones de integridad, 2 error de uso o DB ilegible.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from avs.auditor import ADVERTENCIA, VIOLACION, AuditorEMS, AuditorError
from avs.auditor_magnus import AuditorMagnus


def _forzar_utf8_en_stdio() -> None:
    """En Windows, stdout/stderr de un subproceso caen en el codepage de la
    consola (cp1252), que no puede codificar los símbolos del veredicto
    (⚖ ✅ ❌ ⚠️). `reconfigure` existe en streams TextIOWrapper reales desde
    Python 3.7; se guarda en try/except porque un stream ya redirigido a algo
    que no es TextIOWrapper (p. ej. bajo algunos capturadores de CI) puede no
    tenerlo."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def _texto(veredicto) -> str:
    lineas = [
        "⚖  AVS — Auditor de cadena de custodia EMS",
        f"DB: {veredicto.db}",
        f"Esquema v{veredicto.schema_version} · "
        f"{veredicto.total_claims} claims · {veredicto.total_eventos} eventos",
    ]
    if veredicto.ok and not veredicto.advertencias:
        lineas.append("Veredicto: ✅ ÍNTEGRO — 0 violaciones, 0 advertencias")
    elif veredicto.ok:
        lineas.append(f"Veredicto: ✅ ÍNTEGRO — 0 violaciones, "
                      f"{len(veredicto.advertencias)} advertencias")
    else:
        lineas.append(f"Veredicto: ❌ {len(veredicto.violaciones)} "
                      f"violaciones, {len(veredicto.advertencias)} "
                      "advertencias")
    for h in sorted(veredicto.hallazgos,
                    key=lambda h: (h.severidad != VIOLACION,
                                   h.seq if h.seq is not None else 0,
                                   h.codigo)):
        icono = "❌" if h.severidad == VIOLACION else "⚠️ "
        donde = f" (seq {h.seq})" if h.seq is not None else ""
        quien = f" claim {h.claim_id[:12]}…" if h.claim_id else ""
        lineas.append(f"  {icono} [{h.codigo}]{quien}{donde}: {h.detalle}")
    lineas.append("")
    lineas.append("AVS no demuestra verdad; demuestra que nada se "
                  "adulteró en el camino.")
    return "\n".join(lineas)


def _texto_magnus(veredicto) -> str:
    lineas = [
        "⚖  AVS — Auditor de citas RAG de Magnus",
        f"Trazas: {veredicto.trace_source}",
        f"Wiki: {veredicto.wiki_root}",
        f"Snapshot actual: wiki:{veredicto.snapshot_actual} · "
        f"{veredicto.total_entradas} entradas · "
        f"{veredicto.total_citas} citas",
    ]
    if veredicto.ok and not veredicto.advertencias:
        lineas.append("Veredicto: ✅ ÍNTEGRO — 0 violaciones, 0 advertencias")
    elif veredicto.ok:
        lineas.append(f"Veredicto: ✅ ÍNTEGRO — 0 violaciones, "
                      f"{len(veredicto.advertencias)} advertencias")
    else:
        lineas.append(f"Veredicto: ❌ {len(veredicto.violaciones)} "
                      f"violaciones, {len(veredicto.advertencias)} "
                      "advertencias")
    for h in sorted(veredicto.hallazgos,
                    key=lambda h: (h.severidad != VIOLACION, h.codigo)):
        icono = "❌" if h.severidad == VIOLACION else "⚠️ "
        donde = f" ({h.trace_file}:{h.linea})" if h.trace_file else ""
        quien = f" cita {h.chunk_id}" if h.chunk_id else ""
        lineas.append(f"  {icono} [{h.codigo}]{quien}{donde}: {h.detalle}")
    lineas.append("")
    lineas.append("AVS no demuestra verdad; demuestra que nada se "
                  "adulteró en el camino.")
    return "\n".join(lineas)


def main(argv: list[str] | None = None) -> int:
    _forzar_utf8_en_stdio()
    parser = argparse.ArgumentParser(
        prog="avs",
        description="AVS — Agent Verification System: la capa de "
                    "verificación del ecosistema")
    sub = parser.add_subparsers(dest="comando", required=True)
    audit = sub.add_parser(
        "audit-ems",
        help="verifica por recomputación la cadena de custodia de una DB "
             "de EMS (solo lectura)")
    audit.add_argument("db", help="ruta de la DB SQLite de EMS")
    audit.add_argument("--json", action="store_true",
                       help="emitir el veredicto como JSON")

    audit_m = sub.add_parser(
        "audit-magnus",
        help="verifica por recomputación las citas RAG de Magnus contra la "
             "wiki actual (chunk-hash + snapshot_id, solo lectura)")
    audit_m.add_argument("trace",
                         help="archivo .jsonl de trazas de Magnus, o "
                              "directorio con varios magnus-*.jsonl")
    audit_m.add_argument("wiki_root", help="ruta a la raíz de LLM-Wiki/wiki")
    audit_m.add_argument("--json", action="store_true",
                         help="emitir el veredicto como JSON")

    args = parser.parse_args(argv)

    if args.comando == "audit-ems":
        return _ejecutar_audit_ems(args)
    return _ejecutar_audit_magnus(args)


def _ejecutar_audit_ems(args) -> int:
    try:
        veredicto = AuditorEMS(args.db).auditar()
    except AuditorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(asdict(veredicto), ensure_ascii=False, indent=2))
    else:
        print(_texto(veredicto))
    return 0 if veredicto.ok else 1


def _ejecutar_audit_magnus(args) -> int:
    try:
        veredicto = AuditorMagnus(args.trace, args.wiki_root).auditar()
    except AuditorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(asdict(veredicto), ensure_ascii=False, indent=2))
    else:
        print(_texto_magnus(veredicto))
    return 0 if veredicto.ok else 1


if __name__ == "__main__":
    sys.exit(main())
