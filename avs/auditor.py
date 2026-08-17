"""El Auditor — verificación por recomputación de la cadena de custodia de EMS.

Componente 2 de AVS ([D-03]), vertical slice T-01. Principio rector ([D-04],
independencia): AVS abre la DB de EMS en modo SOLO LECTURA y jamás importa
código de EMS — los contratos (esquema v2 y conjunto cerrado de tipos de
evento) se re-declaran aquí. Si EMS migra su esquema, este archivo es el que
debe actualizarse; la alternativa (importar EMS) convertiría al auditor en
dependencia de lo auditado. El auditor nunca le pregunta al sistema si está
bien: **recomputa**.

La especificación canónica de la cadena es `tests/test_custodia_pipeline.py`
de EMS (extracción → refuerzos → promoción → expiración; sucesión con dos
eventos). Ninguna regla vive aquí sin estar documentada allá.

Qué verifica (nivel 2 de la escalera de estandarización — integridad):

  E1  Esquema conocido (tablas presentes, user_version ≤ SCHEMA_VERSION).
  E2  Tipos de evento cerrados — un typo rompería la cadena en silencio.
  E3  Eventos sin huérfanos: cada claim_id resuelve a un claim existente.
  E4  Origen auditable: todo claim nace de un `extraction` (su primer evento).
  E5  Transiciones legales al re-derivar la cadena evento a evento:
      extracción crea en T1 con contador 1; refuerzo mantiene T1/T2 (cruza
      T1→T2 al pasar el umbral) e incrementa el contador exactamente en 1;
      promoción es solo T2→T3 y con evaluador y motivo; sucesión deja
      `superseded`; expiración solo desde `active` y bajo umbral.
  E6  Sucesión bidireccional (fila): supersedes ↔ superseded_by coinciden.
  E7  Estado final derivable: la fila del claim coincide con lo que la cadena
      deriva (tier, estado, contador). Un UPDATE directo a la tabla —
      adulteración — produce exactamente esta señal.

Severidades: `violacion` rompe la integridad de la cadena. `advertencia`
señala estado no derivable — puede ser una escritura legítima sin evento
(`store.add()` sin `event_type` existe en EMS) o una adulteración: el
auditor reporta, no adivina.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Contratos re-declarados, no importados ([D-04]). Fuente de verdad: EMS
#: `memory/sqlite_store.py` (SCHEMA_VERSION, TIPOS_EVENTO, esquema v2).
SCHEMA_VERSION = 2
TIPOS_EVENTO = frozenset({
    "extraction", "reinforcement", "promotion", "supersession",
    "expiration", "wiki_sync",
})

VIOLACION = "violacion"
ADVERTENCIA = "advertencia"

#: Claves que TODO evento de transición debe llevar para que la cadena
#: "explique" el cambio (requisito humano T-06 de EMS, `memory/events.py`).
_PAYLOAD_REQUERIDO = (
    "estado_anterior", "estado_nuevo",
    "tier_anterior", "tier_nuevo",
    "contador_anterior", "contador_nuevo",
)

#: Transiciones legales por tipo (E5). El refuerzo que cruza el umbral
#: documenta T1→T2; la promoción es exclusivamente T2→T3.
_TIERES_REFUERZO = {("T1", "T1"), ("T1", "T2"), ("T2", "T2")}
_ESTADOS_REFUERZO = {("active", "active"), ("expired", "active")}


class AuditorError(RuntimeError):
    """La DB no puede auditarse como memoria EMS (no existe, no es legible)."""


@dataclass(frozen=True)
class Hallazgo:
    codigo: str
    severidad: str
    detalle: str
    claim_id: str | None = None
    seq: int | None = None


@dataclass(frozen=True)
class Veredicto:
    db: str
    schema_version: int
    total_claims: int
    total_eventos: int
    hallazgos: tuple[Hallazgo, ...]

    @property
    def ok(self) -> bool:
        return not self.violaciones

    @property
    def violaciones(self) -> tuple[Hallazgo, ...]:
        return tuple(h for h in self.hallazgos if h.severidad == VIOLACION)

    @property
    def advertencias(self) -> tuple[Hallazgo, ...]:
        return tuple(h for h in self.hallazgos if h.severidad == ADVERTENCIA)


class AuditorEMS:
    """Audita la cadena de custodia de una memoria EMS leyendo SOLO SQLite."""

    def __init__(self, db: str | Path):
        ruta = Path(db)
        if not ruta.is_file():
            raise AuditorError(f"no existe una DB de EMS en {ruta}")
        self.db = str(ruta)

    def auditar(self) -> Veredicto:
        uri = Path(self.db).resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        try:
            return self._auditar(conn)
        finally:
            conn.close()

    # -- núcleo -----------------------------------------------------------------------
    def _auditar(self, conn: sqlite3.Connection) -> Veredicto:
        hallazgos: list[Hallazgo] = []

        tablas = {f[0] for f in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        faltan = {"claims", "events"} - tablas
        if faltan:
            raise AuditorError(
                f"la DB no tiene las tablas de EMS {sorted(faltan)} — "
                "¿es una memoria producida por SqliteClaimStore?")

        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            hallazgos.append(Hallazgo(
                "esquema_del_futuro", ADVERTENCIA,
                f"user_version={version} > {SCHEMA_VERSION} conocido por AVS; "
                "las reglas de este auditor pueden quedarse cortas"))

        filas = {f["id"]: f for f in conn.execute("SELECT * FROM claims")}
        eventos = list(conn.execute("SELECT * FROM events ORDER BY seq"))

        por_claim: dict[str, list[sqlite3.Row]] = {}
        for ev in eventos:
            self._validar_evento(ev, filas, por_claim, hallazgos)

        for claim_id, fila in filas.items():
            cadena = por_claim.get(claim_id, [])
            if not cadena or cadena[0]["tipo"] != "extraction":
                hallazgos.append(Hallazgo(
                    "origen_no_auditable", VIOLACION,
                    "el claim no nace de un evento extraction: su origen no "
                    "puede reconstruirse desde la cadena",
                    claim_id=claim_id))
            estado = self._rederivar(claim_id, cadena, filas, hallazgos)
            if estado is not None:
                self._comparar_con_fila(claim_id, estado, fila, hallazgos)

        self._sucesion_bidireccional(filas, hallazgos)

        return Veredicto(
            db=self.db, schema_version=version,
            total_claims=len(filas), total_eventos=len(eventos),
            hallazgos=tuple(hallazgos))

    @staticmethod
    def _validar_evento(ev: sqlite3.Row, filas: dict[str, sqlite3.Row],
                        por_claim: dict[str, list], hallazgos: list) -> None:
        if ev["tipo"] not in TIPOS_EVENTO:
            hallazgos.append(Hallazgo(
                "tipo_desconocido", VIOLACION,
                f"tipo {ev['tipo']!r} fuera del conjunto cerrado "
                f"{sorted(TIPOS_EVENTO)}",
                claim_id=ev["claim_id"], seq=ev["seq"]))
            return
        if ev["claim_id"] is None:
            if ev["tipo"] != "wiki_sync":  # wiki_sync puede ser global (Fase D)
                hallazgos.append(Hallazgo(
                    "evento_sin_claim", VIOLACION,
                    f"evento {ev['tipo']} sin claim_id: una transición sin "
                    "sujeto no es custodia", seq=ev["seq"]))
            return
        if ev["claim_id"] not in filas:
            hallazgos.append(Hallazgo(
                "evento_huerfano", VIOLACION,
                "el evento apunta a un claim ausente de la tabla (¿DELETE "
                "directo?): la cadena recuerda lo que la fila niega",
                claim_id=ev["claim_id"], seq=ev["seq"]))
            return
        por_claim.setdefault(ev["claim_id"], []).append(ev)

    def _rederivar(self, claim_id: str, cadena: list[sqlite3.Row],
                   filas: dict[str, sqlite3.Row],
                   hallazgos: list) -> dict[str, Any] | None:
        """Re-deriva {tier, estado, contador} desde el PRIMER evento.

        El payload es la autoridad de la transición; el estado previo del
        replay se usa para detectar incoherencia (el evento dice venir de un
        estado que la cadena no tiene). Tras cada evento se adopta el estado
        NUEVO del payload — un evento ilegal no cascada sobre los siguientes.
        """
        estado: dict[str, Any] | None = None

        def viola(codigo: str, detalle: str, seq: int, *,
                  severidad: str = VIOLACION) -> None:
            hallazgos.append(Hallazgo(codigo, severidad, detalle,
                                      claim_id=claim_id, seq=seq))

        for ev in cadena:
            tipo, seq = ev["tipo"], ev["seq"]
            if tipo == "wiki_sync":  # Fase D de EMS: sin semántica que auditar aún
                continue
            payload = json.loads(ev["payload"]) if ev["payload"] else None
            faltan = [k for k in _PAYLOAD_REQUERIDO
                      if payload is None or k not in payload]
            if faltan:
                viola("payload_incompleto",
                      f"faltan {faltan}: una secuencia que existe pero no "
                      "explica el cambio no es cadena de custodia", seq)
                continue
            p = payload
            nuevo = {"tier": p["tier_nuevo"], "estado": p["estado_nuevo"],
                     "contador": p["contador_nuevo"]}

            if tipo == "extraction":
                if estado is not None:
                    viola("extraccion_duplicada",
                          "extraction sobre un claim que ya tenía estado en "
                          "la cadena", seq)
                if p["estado_anterior"] is not None:
                    viola("extraccion_con_anterior",
                          f"estado_anterior={p['estado_anterior']!r}: una "
                          "extracción es una creación, no tiene antes", seq)
                if p["tier_nuevo"] != "T1":
                    viola("extraccion_tier_ilegal",
                          f"un claim nace en T1, no en {p['tier_nuevo']!r}", seq)
                if p["contador_nuevo"] != 1:
                    viola("extraccion_contador_ilegal",
                          f"un claim nace con contador 1, no "
                          f"{p['contador_nuevo']}", seq)
            elif estado is None:
                viola("transicion_sin_origen",
                      f"{tipo} antes de cualquier extraction: la cadena no "
                      "documenta el nacimiento del claim", seq)
            else:
                if p["tier_anterior"] != estado["tier"]:
                    viola("transicion_tier_incoherente",
                          f"el evento dice venir de tier {p['tier_anterior']!r} "
                          f"pero la cadena deriva {estado['tier']!r}", seq)
                if p["estado_anterior"] != estado["estado"]:
                    viola("transicion_estado_incoherente",
                          f"el evento dice venir de estado "
                          f"{p['estado_anterior']!r} pero la cadena deriva "
                          f"{estado['estado']!r}", seq)
                if p["contador_anterior"] != estado["contador"]:
                    viola("transicion_contador_incoherente",
                          f"el evento dice venir de contador "
                          f"{p['contador_anterior']} pero la cadena deriva "
                          f"{estado['contador']}", seq)

                if tipo == "reinforcement":
                    if (p["tier_anterior"], p["tier_nuevo"]) not in _TIERES_REFUERZO:
                        viola("salto_tier_ilegal",
                              f"refuerzo {p['tier_anterior']}→{p['tier_nuevo']}: "
                              "solo T1→T1, T1→T2 (umbral) o T2→T2", seq)
                    if (p["estado_anterior"], p["estado_nuevo"]) not in _ESTADOS_REFUERZO:
                        viola("estado_ilegal",
                              f"{p['estado_anterior']}→{p['estado_nuevo']}: un "
                              "refuerzo mantiene active o revive desde expired", seq)
                    if p["contador_nuevo"] != p["contador_anterior"] + 1:
                        viola("contador_incoherente",
                              f"contador {p['contador_anterior']}→"
                              f"{p['contador_nuevo']}: cada refuerzo suma "
                              "exactamente 1", seq)
                elif tipo == "promotion":
                    if (p["tier_anterior"], p["tier_nuevo"]) != ("T2", "T3"):
                        viola("salto_promocion_ilegal",
                              f"promoción {p['tier_anterior']}→"
                              f"{p['tier_nuevo']}: solo T2→T3", seq)
                    if (p["estado_anterior"], p["estado_nuevo"]) != ("active", "active"):
                        viola("estado_ilegal",
                              f"{p['estado_anterior']}→{p['estado_nuevo']}: "
                              "solo se promueve un claim activo", seq)
                    if not p.get("evaluador") or not p.get("motivo"):
                        viola("promocion_sin_autoridad",
                              "promoción sin evaluador/motivo: la autoridad "
                              "T3 queda sin responsable", seq)
                elif tipo == "supersession":
                    if p["estado_nuevo"] != "superseded":
                        viola("estado_ilegal",
                              f"una sucesión deja superseded, no "
                              f"{p['estado_nuevo']!r}", seq)
                    reemplazo = (p.get("sucesion") or {}).get("reemplazado_por")
                    if not reemplazo or reemplazo not in filas:
                        viola("sucesion_rota",
                              "el evento no nombra un reemplazo existente", seq)
                    elif filas[reemplazo]["supersedes"] != claim_id:
                        viola("sucesion_no_reciproca",
                              f"el reemplazo {reemplazo} no apunta de vuelta "
                              "con supersedes", seq)
                elif tipo == "expiration":
                    if (p["estado_anterior"], p["estado_nuevo"]) != ("active", "expired"):
                        viola("estado_ilegal",
                              f"{p['estado_anterior']}→{p['estado_nuevo']}: "
                              "solo expira un claim activo", seq)
                    if ("confianza_efectiva" in p and "umbral" in p
                            and not p["confianza_efectiva"] < p["umbral"]):
                        viola("umbral_incoherente",
                              f"expira con confianza_efectiva "
                              f"{p['confianza_efectiva']} ≥ umbral "
                              f"{p['umbral']}: la cadena no explica por qué "
                              "caducó", seq, severidad=ADVERTENCIA)

            estado = nuevo
        return estado

    @staticmethod
    def _comparar_con_fila(claim_id: str, estado: dict[str, Any],
                           fila: sqlite3.Row, hallazgos: list) -> None:
        diferencias = []
        if fila["tier"] != estado["tier"]:
            diferencias.append(f"tier fila={fila['tier']} cadena={estado['tier']}")
        if fila["status"] != estado["estado"]:
            diferencias.append(
                f"estado fila={fila['status']} cadena={estado['estado']}")
        if fila["reinforcement_count"] != estado["contador"]:
            diferencias.append(
                f"contador fila={fila['reinforcement_count']} "
                f"cadena={estado['contador']}")
        if diferencias:
            hallazgos.append(Hallazgo(
                "estado_no_derivable", ADVERTENCIA,
                "la fila no coincide con lo que la cadena deriva ("
                + "; ".join(diferencias) + ") — escritura sin custodia "
                "(store.add sin evento) o adulteración directa de la tabla",
                claim_id=claim_id))

    @staticmethod
    def _sucesion_bidireccional(filas: dict[str, sqlite3.Row],
                                hallazgos: list) -> None:
        for claim_id, fila in filas.items():
            if fila["supersedes"] is not None:
                otra = filas.get(fila["supersedes"])
                if otra is None:
                    hallazgos.append(Hallazgo(
                        "sucesion_rota", VIOLACION,
                        f"supersedes apunta a {fila['supersedes']}, ausente "
                        "de la tabla", claim_id=claim_id))
                elif otra["superseded_by"] != claim_id:
                    hallazgos.append(Hallazgo(
                        "sucesion_no_reciproca", VIOLACION,
                        f"supersedes→{fila['supersedes']} pero el reemplazado "
                        f"dice superseded_by={otra['superseded_by']!r}",
                        claim_id=claim_id))
            if fila["superseded_by"] is not None:
                otra = filas.get(fila["superseded_by"])
                if otra is None:
                    hallazgos.append(Hallazgo(
                        "sucesion_rota", VIOLACION,
                        f"superseded_by apunta a {fila['superseded_by']}, "
                        "ausente de la tabla", claim_id=claim_id))
                elif otra["supersedes"] != claim_id:
                    hallazgos.append(Hallazgo(
                        "sucesion_no_reciproca", VIOLACION,
                        f"superseded_by→{fila['superseded_by']} pero el "
                        f"reemplazo dice supersedes={otra['supersedes']!r}",
                        claim_id=claim_id))
