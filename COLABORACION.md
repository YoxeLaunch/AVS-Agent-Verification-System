# COLABORACION.md — Log compartido de trabajo conjunto

Sistema de colaboración sobre el proyecto AVS — Agent Verification System
(la capa de verificación y certificación del ecosistema: EMS, MagnusAgent
y la wiki LLM-WIKI/IMPERNO).

| Rol | Participante | Responsabilidad principal |
|---|---|---|
| Implementador | **ZCode** (agente local, tiene acceso al disco y al código) | Escribir código, ejecutar tests, auditar el estado real del repo |
| Revisor | **ChatGPT** (contraparte de diseño, sin acceso directo al disco) | Revisión crítica de diseño, alternativas, contrapunto |
| Árbitro + transporte | **El humano (JoseO)** | Decide conflictos, mueve bloques de handoff entre sesiones |

## Protocolo

1. **Append-only.** Las entradas se añaden al final, nunca se editan ni se
   borran (misma filosofía que la sucesión de claims de EMS). Si una decisión
   cambia, se escribe una entrada nueva que la supersede citándola.
2. **Formato de entrada:**
   ```
   ### YYYY-MM-DD HH:MM — De: <ZCode|ChatGPT|Humano> — <asunto>
   <contenido: decisiones [D-nn], respuestas [P-nn], alternativas [ALT-nn],
   hallazgos, preguntas>
   ```
3. **Numeración global:** decisiones `[D-nn]`, preguntas `[P-nn]`,
   alternativas `[ALT-nn]`, tareas `T-nn`. Nunca se reutilizan números.
4. **Regla de tokens:** nadie re-deriva contexto que ya está aquí o en los
   docs referenciados. Se cita `archivo:linea` en lugar de pegar código.
   Los bloques de handoff son autocontenidos y acotados.
5. **Regla de conflicto:** si ZCode y ChatGPT discrepan, gana el argumento,
   no el autor; si persiste, decide el humano y queda registrado como [D-nn].
6. **Estado de tareas:** la tabla de abajo es la única fuente de verdad de
   quién hace qué. Nadie trabaja una tarea asignada al otro sin entrada
   previa en el log.
7. **Regla de arranque:** al iniciar cualquier sesión, lo primero es leer el
   Tablero de Estado y las entradas nuevas desde la última visita — antes de
   trabajar. Nadie toma una tarea sin refrescar estado.
8. **Regla de checkpoint:** antes de cerrar la sesión, actualizar el Tablero
   de Estado y dejar una entrada breve: qué se hizo, qué queda a medias
   (y dónde quedó exactamente: archivo:linea), y qué se espera del otro.

## Estado de tareas

| ID | Tarea | Dueño | Estado | Notas |
|---|---|---|---|---|
| T-01 | Vertical slice del Auditor: dada una DB de EMS, recomputar la cadena de custodia (events → claims) y verificar FK, legalidad de transiciones de tier y bidireccionalidad de sucesión | ZCode | **completada** | 13/13 tests; [P-01] resuelta de facto: lectura cruda (ver entrada de cierre) |

## Tablero de estado

> **Excepción mutable:** esta sección es la única parte editable del archivo
> (el registro de abajo sigue siendo append-only). Es el tablero kanban:
> qué hace cada uno AHORA, qué espera, qué está libre. Se actualiza en cada
> checkpoint (regla 8).

| Participante | Trabajando ahora | Esperando de | Libre para tomar |
|---|---|---|---|
| ZCode | — (sesión cerrada: T-01/El Auditor completo) | Humano: decidir siguiente componente | Componente 1 (harness CI — depende de [P-02]/[P-03]), componente 3 (matriz NIST — documental) |
| ChatGPT | — | — | Revisión del alcance fundacional + del Auditor ya construido (bloque de handoff abajo) |
| Humano | — | — | Responder [P-02]..[P-04]; pegar handoff a ChatGPT |

_Última actualización: 2026-08-16 por ZCode (T-01 completa: AuditorEMS + CLI, 13/13)._

## Registro

### 2026-08-16 — De: ZCode — Entrada fundacional: contexto, decisiones y preguntas abiertas

**Contexto (mínimo; el detalle está en el README):**

- El ecosistema tiene tres órganos maduros: MagnusAgent (runtime multiagente,
  282/282 tests), EMS (memoria evidenciada, 178/178 tests) y LLM-WIKI
  (corpus curado). Ninguno puede *probar* que funciona ni que su evidencia
  es íntegra — la verificación que existe es interna a cada repo.
- El análisis de la pieza faltante (sesión con el humano, 2026-08-16)
  concluyó que el cuarto órgano es la capa de verificación, con el matiz
  clave: a nivel comercial no se certifica la verdad, se certifica la
  **verificabilidad** (rastreabilidad, integridad, reproducibilidad, proceso
  accountable — el patrón de la revisión por pares).
- Este repo nace para construirla. Nada de código aún; estas decisiones
  gobiernan la Fase 0.

**Decisiones:**

- **[D-01] Mandato.** AVS existe para comprobar que el ecosistema funciona
  y es verídico a nivel de estandarización comercial — certificando
  verificabilidad, no verdad absoluta. El contenido se evalúa
  probabilísticamente; la curación humana sigue siendo el gate final.
- **[D-02] Nombre.** AVS — Agent Verification System, par simétrico de
  EMS-Evidenced Memory System (*memoria evidenciada / agente verificado*).
  Elección del humano (entrada siguiente). **Certus queda reservado** para
  un sistema futuro.
- **[D-03] Alcance inicial: tres componentes.**
  (1) Harness de evaluación continua: goldens por dominio y métricas de
  faithfulness/citation-integrity como gates de CI.
  (2) El Auditor: CLI que recomputa — cadena de custodia de EMS (events),
  provenance de citas de Magnus (chunk-hash + snapshot del wiki), legalidad
  de transiciones de tier.
  (3) Matriz de mapeo a estándares: NIST AI RMF / ISO 42001 control por
  control contra artefactos existentes.
- **[D-04] Independencia del auditor.** AVS lee y reporta; nunca corrige lo
  que audita. La separación es la garantía. La verificación es siempre por
  recomputación desde artefactos crudos, no por consulta al sistema auditado.
- **[D-05] Principios heredados del ecosistema.** Local-first,
  offline-determinista, stdlib + PyYAML, append-only, y la documentación
  nunca se adelanta al código.
- **[D-06] Escalera de estandarización como mapa.** Niveles 1–3 (eval
  funcional, verificación estructural, gobernanza NIST/ISO 42001) son
  técnicos y construibles ya. Niveles 4–5 (ISO 27001/SOC 2, regulatorio)
  solo tienen sentido con producto y datos de terceros; se declaran, no se
  emprenden.

**Preguntas abiertas (para revisión y/o decisión humana):**

- **[P-01] Superficie de lectura del Auditor.** ¿Consume las API públicas
  de EMS/Magnus, o lee artefactos crudos (SQLite, JSONL, Markdown)
  directamente? API pública = menos fricción y estabilidad de contrato;
  lectura cruda = independencia máxima (una API bugueada no puede ocultar
  su propio desorden), pero acopla AVS a formatos internos versionados.
  Nota: [D-04] empuja hacia lectura cruda; la cadena de events de EMS ya
  es contrato público de facto.
- **[P-02] Dónde viven los goldens.** Magnus ya tiene goldens de RAG y
  routing en su repo. ¿AVS centraliza la evaluación de los tres hermanos
  (goldens propios), o apunta a los suites existentes y solo agrega las
  métricas que faltan (faithfulness, citation-integrity)?
- **[P-03] Relación con la Fase G de EMS (CI).** EMS tiene una fase G de CI
  decidida y sin implementar. ¿AVS la absorbe como su componente 1, la
  complementa, o se coordinan?
- **[P-04] El examinador (idea "Magister").** Certificar dominio por
  exámenes (agentes y humano, con resultados decayendo en EMS) — ¿rama
  futura de AVS o quinto órgano independiente? No bloquea la Fase 0, pero
  conviene decidirlo antes de que el harness de evaluación crezca.

— fin de la entrada —

### 2026-08-16 — De: Humano (transcrito por ZCode) — Elección del nombre

> "Yo elegiría AVS — Agent-Verification-System (el par natural de EMS:
> memoria evidenciada / agente verificado). Lo de Certus lo dejaré para
> otro sistema por ahí."

Registrada como [D-02].

— fin de la entrada —

### 2026-08-16 — De: ZCode — Checkpoint de cierre: T-01 completa, El Auditor v0.1.0 (13/13)

**Qué se construyó** (`avs/auditor.py`, `avs/cli.py`, pyproject, tests):

1. **`AuditorEMS`**: abre la DB de EMS en modo SOLO LECTURA
   (`file:...?mode=ro`) y RECOMPUTA la cadena de custodia. **[P-01]
   resuelta de facto por [D-04]**: lectura cruda de SQLite, cero imports de
   EMS — los contratos (esquema v2, `TIPOS_EVENTO`) se re-declaran
   localmente con su fuente de verdad citada. La especificación de la
   cadena re-derivada es `tests/test_custodia_pipeline.py` de EMS (leído
   antes de escribir una sola regla: ninguna regla vive en AVS sin estar
   documentada allá).
2. **Siete verificaciones** (E1–E7): esquema conocido; tipos de evento
   cerrados; eventos sin huérfanos; origen auditable (todo claim nace de
   `extraction`); transiciones legales re-derivadas evento a evento
   (extracción crea en T1 con contador 1; refuerzo T1/T2 suma exactamente
   1 — cruza T1→T2 al pasar el umbral; promoción solo T2→T3 y con
   evaluador y motivo; sucesión deja `superseded`; expiración solo desde
   `active` y con umbral superado); sucesión bidireccional en fila; y
   estado final derivable (fila == cadena en tier/estado/contador).
3. **Severidades**: `violacion` rompe integridad; `advertencia` =
   `estado_no_derivable` — escritura sin custodia (legítima: `store.add`
   sin evento existe en EMS) o adulteración directa. El auditor reporta,
   no adivina.
4. **CLI** `avs audit-ems <db> [--json]` con contrato de CI: 0 íntegro /
   1 violaciones / 2 uso. pyproject con console_script `avs`, v0.1.0.

**Tests (13/13, ~3 s, offline):** dependencia de EMS SOLO en tests (vía
`tests/conftest.py`): integración contra memorias REALES producidas por el
pipeline de EMS — ciclo de vida completo (promoción + expiración +
sucesión canónica de docs/01) audita íntegro con CERO hallazgos, la
auditoría es solo lectura (hash del archivo invariante) y determinista.
Detección de las 7 adulteraciones crudas: claim borrado, tier adulterado
en fila, tipo de evento falsificado, promoción con salto de tier, sucesión
no recíproca, origen eliminado, payload mutilado. CLI por función y como
proceso (`python -m avs.cli`).

**Demo ejecutada en vivo:** memoria canónica → `✅ ÍNTEGRO` (exit 0);
tras adulterarla por fuera de EMS (downgrade T3→T1, DELETE del claim
sucesor, evento `'promoton'` inyectado) → 4 violaciones + 1 advertencia
con la evidencia exacta por claim y seq (exit 1). Artefactos en `demo/`.

**Pendiente / esperando:** [P-02]..[P-04] siguen abiertas (dónde viven los
goldens, relación con Fase G de EMS, destino del examinador). Siguientes
naturales: componente 1 (harness de evaluación como gates de CI — depende
de [P-02]/[P-03]) o componente 3 (matriz NIST AI RMF — documental, sin
dependencias, se puede avanzar ya).

— fin de la entrada —

### 2026-08-16 — De: ZCode — Checkpoint relámpago: componente 3 (matriz NIST) en borrador

`docs/01-MATRIZ-NIST-AI-RMF.md`: 16 categorías de las 4 funciones (GV/MP/
MS/MN) mapeadas contra artefactos reales en disco. Resultado: **12 ✅ ·
1 ⚠️ (MS-4 vigilancia continua — es el componente 1 de AVS) · 1 ❌ (MN-3
right-to-be-forgotten — es la Fase G de EMS)**. Hallazgo registrado: la
matriz NIST, construida de forma independiente, converge con el roadmap
propio del ecosistema en exactamente sus dos gaps conocidos — validación
cruzada de ambas listas. Pendiente: [P-02]..[P-04]; el componente 1 es el
único bloque restante de [D-03].

— fin de la entrada —

## Bloque de handoff → ChatGPT v1 (copiar/pegar tal cual + adjuntar README.md)

> Estás entrando como revisor en el cuarto proyecto de un ecosistema
> personal de IA. Contexto:
>
> **El ecosistema (en disco):**
> - **MagnusAgent**: runtime multiagente local-first. RAG híbrido (94.7%
>   recall@8), egreso denegado por defecto, servidor MCP, agentes YAML,
>   CitationEvaluator anti-alucinación. 282/282 tests.
> - **EMS — Evidenced Memory System**: memoria nivelada T0→T3 con cadena de
>   custodia transaccional (events append-only en SQLite), consentimiento
>   obligatorio, sucesión no destructiva. 178/178 tests.
> - **LLM-WIKI (IMPERNO)**: corpus Obsidian curado por humano, nivel T4.
>
> **AVS — Agent Verification System (este repo, recién fundado):** la capa
> de verificación y certificación. Mandato [D-01]: a nivel comercial no se
> certifica la verdad, se certifica verificabilidad — que toda afirmación es
> rastreable a evidencia y que nada se adulteró en el camino. Tres
> componentes decididos [D-03]: harness de evaluación continua, el Auditor
> (CLI que recomputa), matriz NIST AI RMF / ISO 42001. Principio clave
> [D-04]: independencia — AVS lee y reporta, nunca corrige lo que audita.
> Nada implementado aún; el README declara decisiones, no capacidades.
>
> **Cómo trabajamos:** ZCode implementa (acceso a disco); tú revisas diseño;
> el humano transporta entradas vía este log append-only ([D-nn]/[P-nn]/
> [ALT-nn]/T-nn, tablero kanban, reglas de arranque y checkpoint — ver
> Protocolo arriba).
>
> **Tu tarea:** revisar la fundación:
> 1. Responder [P-01]..[P-04] (arriba), cada una con decisión y
>    justificación breve.
> 2. Proponer [ALT-nn] donde veas un camino mejor para la Fase 0.
> 3. Riesgos no cubiertos (pista: ¿qué puede hacer que un verificador dé
>    verde a algo roto — falso positivo de auditoría — y cómo se detecta?).
> 4. Si tienes margen: diseñar el criterio de hecho del vertical slice T-01
>    (Auditor sobre cadena de custodia de EMS).
>
> **ENTREGA:** UNA sola entrada formateada para el log, lista para pegar:
> `### <fecha> — De: ChatGPT — Revisión fundacional de AVS` seguida de tus
> respuestas. Nada más que esa entrada.
