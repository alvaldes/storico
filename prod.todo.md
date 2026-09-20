# Checklist de producción

Lo que falta antes y después de poner Storico en producción. **Este archivo es la lista única**: los
pendientes de despliegue estaban en `docs/deployment.md` y los de seguridad en `docs/security.md`, y
las dos listas se superponían en cuatro ítems (rate limiting, monitoreo de errores, auditoría de
variables de entorno y dominio propio). Cada ítem dice dónde está el detalle cuando lo hay.

Estado: 🔲 pendiente · 🟡 parcial · ✅ hecho

## Antes de desplegar

Prerrequisitos que, si faltan, rompen algo en silencio o fallan recién en producción.

| Ítem | Estado | Detalle |
|------|--------|---------|
| `STORICO_ENCRYPTION_KEY` configurada | 🔲 | Sin ella el backend **se niega a guardar** una credencial de workspace (falla cerrada) y la revisión `0024` falla a propósito. Generarla con `cryptography.fernet.Fernet.generate_key()` y guardarla fuera del repositorio; perderla deja las credenciales guardadas ilegibles. |
| Orden de las migraciones | 🔲 | `0024` (cifrar credenciales) se corre **después** de desplegar el código que cifra y descifra: el release anterior le entregaría el ciphertext al proveedor como si fuera una API key. `0023` va al revés — la columna tiene que existir antes. Cada revisión lo dice en su propio docstring. |
| Suite de integración contra Postgres real | 🟡 | El test de integración se saltea sin Docker. Correrlo al menos una vez antes de desplegar: es lo que cubre las restricciones que SQLite no aplica (tipos, largo de columnas, claves foráneas). |

## Seguridad

| Ítem | Estado | Detalle |
|------|--------|---------|
| Cifrado en reposo de las API keys | ✅ | Fernet con clave maestra en el entorno; revisión `0024`. Ver `docs/security.md`. |
| Rate limiting | 🔲 | Vercel WAF o `slowapi`. |
| Restringir CORS a dominios específicos | 🔲 | Hoy toma `STORICO_AUTH_ALLOWED_ORIGINS`; revisar que en producción no incluya orígenes de desarrollo. |
| Auditoría de variables de entorno en Vercel | 🔲 | Que ninguna clave de desarrollo quede en el proyecto de producción. |
| Rota­ción de la clave maestra | 🔲 | El prefijo `v1:` del ciphertext existe para permitirla; la herramienta no está escrita. |
| `POST /api/v1/llm/test` ecoa el error de transporte | 🔲 | Sus cinco ramas devuelven `{e}`; admin-only, pero es la misma forma que se corrigió en el probe de modelos. Ver `odd/tasks/llm-probe-credential-leak.md`. |

## Observabilidad

| Ítem | Estado | Detalle |
|------|--------|---------|
| Monitoreo de errores (Sentry) | 🔲 | |
| Campos estructurados en los logs | ✅ | 28 llamadas a `logger.*` pasan `extra=`, así que un fallo llega con sus datos y no solo con un texto. |
| Correlation IDs para trazabilidad | 🔲 | **No existen.** `AGENTS.md` los anunciaba en su tabla de features y se corrigió ahí; un request no lleva identificador que lo siga de punta a punta. |

## Infraestructura y costos

| Ítem | Estado | Detalle |
|------|--------|---------|
| Qdrant Cloud + adaptador de embeddings | 🔲 | El RAG degrada con gracia si falta; en producción conviene decidir si se usa. |
| Dominio propio + SSL | 🔲 | |
| CI que construya el frontend | 🔲 | `.github/workflows/ci.yml` corre `tsc` y `vitest`, no `astro build`. Un build roto y un artefacto viejo pasan los dos sin que nadie se entere; ver `docs/deployment.md`. |

## Producto (después de la evaluación)

| Ítem | Estado | Detalle |
|------|--------|---------|
| Conector Trello | 🔲 | |
| Conectores Jira / GitHub Projects / Azure DevOps | 🔲 | V2/V3. |
| Adaptador de OpenAI con tests de construcción positiva | ✅ | El adaptador existe y la extracción lo construye por dos ramas: `openai` y proveedor personalizado (`backend/src/storico/infrastructure/tasks/extraction_task.py`). El test de construcción es `backend/tests/test_unit/test_llm_port_selection.py::TestKnownCloudProviders::test_openai_with_key_forwards_base_url`, que verifica el tipo del adaptador y que el `base_url` configurado llega a él. |

## Tesis

| Ítem | Estado | Detalle |
|------|--------|---------|
| Juicio de expertos (n=6) | 🔲 | Scrum Masters y Product Owners; métricas TCR/TAS/IFI. |
| Comparativa manual vs automática | 🔲 | |

---

Este archivo lo mantiene quien despliega. Si un ítem se cierra, se marca acá y se deja el detalle en
el documento que le corresponda — no se abre una segunda lista.
