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


def main(argv: list[str] | None = None) -> int:
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
    args = parser.parse_args(argv)

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


if __name__ == "__main__":
    sys.exit(main())
