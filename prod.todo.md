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
| `STORICO_ENCRYPTION_KEY` configurada | ✅ | Configurada en el `.env` de la VM de producción y cargada en el contenedor (verificado el 2026-09-20, después del reinicio que la tomó). La revisión `0024` cifró la credencial que estaba en texto plano y el proceso la descifra, así que guardar y leer credenciales de workspace funcionan. Generar la clave con `cryptography.fernet.Fernet.generate_key()` y guardarla fuera del repositorio; **perderla deja ilegibles las credenciales ya guardadas**. En la VM quedó un respaldo del archivo como `.env.bak-20260920233204`. |
| Orden de las migraciones | ✅ | Aplicadas en el orden que pide cada revisión: `0022` y `0023` primero (la columna tiene que existir antes de que el código la escriba), después el reinicio del contenedor con la clave cargada, y recién `0024`, que reescribe valores existentes. El esquema quedó en `0024` (head) el 2026-09-20. |
| El deploy corre las migraciones | 🔲 | `.github/workflows/deploy-backend.yml` hace `git reset --hard` y `docker run`, y **cero `alembic`**. Ese es el mecanismo que produjo el incidente del 2026-09-20: el esquema quedó en `0021` contra un head `0024` y la extracción falló 56 veces con `column extractions.completed_at does not exist`. Se aplicaron a mano hasta `0024`, pero **la próxima revisión de esquema vuelve a caer en lo mismo**. El paso va después del `git reset` y antes de arrancar el contenedor nuevo. |
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
