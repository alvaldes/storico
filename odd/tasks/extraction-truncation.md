# Feature: extraction truncation is never silent

A run whose answer was cut by the output budget must end as a classified failure that names the budget,
never as a `completed` run carrying fewer tasks than the model meant to write.

## Specs

**S1 — Ninguna corrida truncada se presenta como buena.**
Pedido del owner, literal: *"el único punto de todo esto que puede estar dándote menos tareas sin avisar"*.
Una respuesta cortada por el presupuesto de salida MUST end as `failed`, with **zero** tasks persisted for
that version. A `completed` run MAY legitimately carry few tasks; it MUST NOT carry a set the budget cut.

**S2 — El motivo nombra la causa y la salida.**
`error_info` MUST state that the output budget (`max_tokens`) cut the answer and that raising it is the fix.
No copy nueva de UI: el texto viaja por el canal que ya existe (`Extractions.error_info`) y se muestra en el
toast de fallo y en la card de versión fallida (`versionSelector.no_output_desc`). Texto técnico en inglés,
como el resto de ese campo.

**S3 — No se reintenta.**
Un corte por presupuesto es determinista: el mismo `max_tokens` corta igual. El error MUST travel the
deterministic path (`LLMError`/`ParseError` in `run_background_extraction`), which marks the run `failed`
without the retry loop. Retrying it MUST NOT happen.

**S4 — Cada proveedor mira su propia señal, y sólo la suya.**
- OpenAI-compatible: `finish_reason == "length"` on a **non-empty** content (today only the empty-content
  path inspects it: `infrastructure/llm/openai_adapter.py:46,257`).
- Ollama: `done_reason == "length"` when `stream: false` (`ollama_adapter.py:156`).
- Gemini: the candidate finish reason for `MAX_TOKENS`.
- Anthropic: `stop_reason == "max_tokens"`.
Each adapter MUST cite the exact attribute and verify it against the installed SDK, not from memory. The
default is **not** "clean": an adapter whose signal cannot be observed is recorded in the Log as out of
reach, never guessed.

**S5 — El registro lo dice sin abrir la caja.**
The version row ends `failed`, the extracted version has no tasks, and `error_info` carries S2's text. A
test at the run level proves it, and a test proves that a legitimately short (not truncated) answer still
ends `completed`.

## Tasks

| ID | Task | Spec | Route | Commit |
|----|------|------|-------|--------|
| T1 | Detection in every adapter, each against its own SDK signal | S4 | worker | `61c1cad` |
| T2 | Deterministic classification: `failed`, zero tasks, `error_info` naming the budget | S1, S2, S3 | worker | `61c1cad` |
| T3 | Tests: truncated-with-content per adapter, run-level failure, and a short-but-complete answer staying `completed` | S1, S3, S5 | worker | `61c1cad` |
| T4 | Confirm the reason surfaces in the existing UI; change copy only if it would not | S2, S5 | parent | `61c1cad` |

## Log

**L1** — Pedido del owner (2026-11-03), literal: *"ok hagamoslo y despues dime que cambia esto en la app y el
resutlado"*, sobre el punto que el padre describió como *"el único punto de todo esto que puede estar
dándote menos tareas sin avisar"*.

**L2** — Decisión previa que encuadra esta feature (commit `7164982`, registrada en `prod.todo.md`), literal
del owner: *"No le quiero poner tiempo a la extracción porque eso haría que se cortara una extracción y
podría quedarme con menos tareas de las que estaba pensado"*. Por eso esta feature NO agrega ningún plazo
por tiempo: arregla la única vía real de perder tareas, que es la truncación por presupuesto de salida.

**L3** — Medido por el padre antes de escribir esta especificación: `_parse` devuelve en cuanto encuentra
**una** tarea y sólo levanta `ParseError` si no parsea ninguna
(`backend/src/storico/infrastructure/llm/task_parser.py:75-83`), y el adapter de OpenAI mira
`finish_reason: length` únicamente cuando el contenido vino **vacío**
(`openai_adapter.py:46,257`). Consecuencia: hoy una respuesta cortada con 3 de 6 tareas se persiste como
corrida `completed`.

**L4** — Implementado y verificado el 2026-11-03 en `61c1cad`. Las señales de OpenAI, Anthropic y Gemini se
comprobaron contra los tipos del SDK instalado en el entorno `storico`; la de Ollama **no** se pudo observar
en esta máquina (no hay SDK y el servicio no responde), así que se implementó contra el contrato documentado
del cuerpo no-streaming, leída con `isinstance`/`.get` para que un cuerpo sin motivo nunca se clasifique como
truncación — falla abierto, no inventa. Ojo al leer la UI: una respuesta que se cortó justo en el borde de una
tarea también se clasifica como fallida, a propósito (S1).
