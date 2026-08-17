# Matriz de mapeo — NIST AI RMF ↔ ecosistema Bitronic

**Componente 3 de AVS ([D-03]) · v0.1 — borrador de trabajo.**

NIST AI RMF 1.0 organiza la gestión de riesgo en 4 funciones: **GOVERN,
MAP, MEASURE, MANAGE**. Esta matriz ubica cada categoría relevante contra
un artefacto **existente en disco** — el criterio de hecho del componente:
un auditor externo verifica cada control apuntando a un archivo real. Donde
no hay artefacto, se declara `gap` (honestidad antes que cosmética: la
regla de la casa).

| ID | Función NIST | Qué pide | Artefacto en el ecosistema | Estado |
|:--|:--|:--|:--|:--|
| GV-1 | GOVERN | Política y accountable por la IA | `MagnusAgent/constitution/magnus_constitution.md` (7 reglas no negociables) + roles en cada `COLABORACION.md` | ✅ |
| GV-2 | GOVERN | Roles y responsabilidades definidos | Protocolo de `COLABORACION.md` (implementador/revisor/humano-árbitro, reglas de conflicto y checkpoint) | ✅ |
| GV-3 | GOVERN | Procesos de decisión documentados y trazables | Logs append-only con decisiones numeradas [D-nn] (EMS y AVS) + `MagnusAgent/CAMINO.md` | ✅ |
| GV-4 | GOVERN | Diversidad de opinión / revisión crítica | Circuito ZCode↔ChatGPT con árbitro humano; alternativas [ALT-nn] obligatorias en revisión | ✅ |
| MP-1 | MAP | Contexto y propósito del sistema documentado | `README.md` de cada proyecto + `MagnusAgent/docs/00-VISION-Y-ARQUITECTURA.md` | ✅ |
| MP-2 | MAP | Riesgos específicos identificados y priorizados | Sección de riesgos de `EMS/docs/04-PLAN-MEJORAS.md` (7+) + riesgos de revisión T-01 EMS | ✅ |
| MP-3 | MAP | Límites del sistema declarados | "Lo que honestamente no se puede": modo extractivo, sin verdad absoluta (READMEs de Magnus/AVS) | ✅ |
| MP-4 | MAP | Datos: fuentes y procedencia | Tiers T0–T4 con `fuente_original` por página wiki; chunk-hash + snapshot_id en citas Magnus | ✅ |
| MS-1 | MEASURE | Métricas de desempeño del sistema | RAG recall@8 = 94.7%, routing 100% (26 goldens) en `MagnusAgent/evaluation/` | ✅ |
| MS-2 | MEASURE | Evaluación de salida (factibilidad/citas) | `CitationEvaluator` estructural + `LLMJudgeEvaluator` opcional en Magnus | ✅ |
| MS-3 | MEASURE | Integridad y trazabilidad verificable | **AVS El Auditor**: recomputación de cadena de custodia EMS (E1–E7), exit-code para CI | ✅ |
| MS-4 | MEASURE | Vigilancia continua / regresiones | Suites pytest (282+178+13) offline | ⚠️ parcial: falta gate de CI automático ([P-03]) |
| MN-1 | MANAGE | Mitigación de riesgos implementada | Anti-eco EMS (contradicción antes que match); degradación extractiva Magnus; egress denegado | ✅ |
| MN-2 | MANAGE | Respuesta a incidentes / corrección de errores | Sucesión no destructiva (`supersedes`), bugs reales documentados y corregidos (EMS Fase B) | ✅ |
| MN-3 | MANAGE | Retiro/control de datos (derecho al olvido) | Purga G2 de EMS: **decidida, sin implementar** | ❌ gap |
| MN-4 | MANAGE | Cambios gestionados y versionados | `schema_version` + migraciones EMS; snapshots de wiki; tags v0.x | ✅ |

**Barras de estado: 12 ✅ · 1 ⚠️ parcial · 1 ❌ gap.**

## Lectura del resultado

1. El ecosistema ya cubre GOVERN y MAP casi por accidente — la disciplina
   de logs append-only y constitución *es* gestión de riesgo formalizada.
2. El ⚠️ (MS-4) es justo el componente 1 de AVS: harness como gate de CI.
3. El ❌ (MN-3, right-to-be-forgotten) ya era Fase G de EMS — la matriz
   NIST independiente llega a la misma conclusión que el roadmap propio:
   convergencia que valida ambas listas.

*Este documento declara mapeos verificables contra artefactos que existen
en la fecha de su escritura; si un artefacto cambia, el mapeo se
supersede, no se edita (regla de la casa).*
