---
title: Inicio rápido
description: Instala Storico, crea el esquema, levanta las dos mitades y configura un modelo antes de tu primera extracción.
---

## Lo que necesitas

- **Python 3.12** para el backend;
- **Node.js 20+ y pnpm 10** para el frontend: pnpm es el único gestor de paquetes que usa este repositorio;
- **PostgreSQL**, donde viven todas las historias, tareas y espacios de trabajo;
- **Un modelo con el que extraer**: un Ollama local, o una API key de OpenAI, Anthropic o Gemini.

Qdrant es opcional en el sentido de que una extracción sigue teniendo éxito sin él: solo aporta los ejemplos few-shot que se describen en [Contexto histórico](/es/docs/embeddings-rag).

## 1. Instala el backend

El repositorio no impone un gestor de entornos; necesita uno con el extra `dev` instalado, igual que CI lo instala. La elección canónica del proyecto es un entorno de conda llamado `storico`:

```bash
cd backend
python -m pip install -e ".[dev]"
```

## 2. Configura el entorno

Copia `.env.example` a `.env`. Los ajustes que importan antes que cualquier otra cosa:

| Variable | Valor por defecto | Qué hace |
| --- | --- | --- |
| `STORICO_DATABASE_URL` | `postgresql+asyncpg://storico:storico@localhost:5432/storico` | Dónde viven los datos relacionales |
| `STORICO_ENCRYPTION_KEY` | ninguno | **Obligatoria para guardar credenciales de espacio de trabajo.** Sin ella, guardar una API key falla |
| `STORICO_QDRANT_URL` | `http://localhost:6333` | El almacén vectorial, para el contexto histórico |
| `STORICO_QDRANT_COLLECTION` | `storico_extractions` | La colección que guarda los vectores de extracción. Una colección pertenece al modelo de embedding que la llena, así que cada entorno define su propio valor |
| `STORICO_OLLAMA_HOST` | `http://localhost:11434` | El host de Ollama que llama el proveedor por defecto |
| `STORICO_AUTH_JWT_SECRET` | un marcador de desarrollo | Verifica los JWT que emite el proxy del frontend. Reemplázalo fuera de desarrollo |
| `STORICO_AUTH_ALLOWED_ORIGINS` | `http://localhost:4321` | Orígenes CORS separados por comas |

Los ajustes de embedding (`STORICO_EMBEDDING_PROVIDER`, `STORICO_EMBEDDING_MODEL`, `STORICO_EMBEDDING_DIMENSIONS`, y los modelos y API keys por proveedor) determinan los vectores. Las dimensiones deben coincidir con el modelo de embedding y con la colección, porque los vectores de modelos distintos no son comparables.

## 3. Crea el esquema

Ningún lanzador de este repositorio aplica las migraciones por ti. Desde `backend/`, con el entorno activo y `STORICO_DATABASE_URL` apuntando a tu base de datos:

```bash
alembic upgrade head
```

## 4. Levanta la API

```bash
python -m uvicorn storico.api.app:create_app --factory --port 8000
```

El flag `--factory` no es opcional. Sin él, uvicorn toma `create_app` mismo como la aplicación ASGI y arranca un servidor roto en lugar de fallar; con él, un fallo dentro de la fábrica corta el proceso con el error real.

`GET /api/v1/health` debería responder `ok`. La página interactiva de OpenAPI está en `/docs` de la API, y todos los endpoints aparecen también en la [Referencia de la API](/es/docs/api-reference).

## 5. Levanta el frontend

```bash
cd frontend
pnpm install
pnpm run dev
```

La aplicación está en **http://localhost:4321**. La documentación que estás leyendo la sirve el mismo proyecto, en `/en/docs` y `/es/docs`.

## 6. Configura un modelo antes de extraer

Este es el paso que bloquea la primera extracción, así que conviene hacerlo antes que nada:

1. **Inicia sesión.** La autenticación es solo OAuth: Google o GitHub. No hay contraseñas.
2. **Crea un espacio de trabajo** si no tienes uno. Cualquier usuario autenticado puede, y quien lo crea queda como su propietario y como administrador.
3. **Abre Configuración y guarda la configuración de LLM**: un proveedor y un modelo, más una API key en los proveedores en la nube. Para Ollama, descarga un modelo primero (`ollama pull llama3.2`) y comprueba que el host de `STORICO_OLLAMA_HOST` sea accesible. Consulta [Proveedores de LLM](/es/docs/llm-providers) para el detalle campo por campo.

:::caution
La extracción necesita un modelo y una configuración del proveedor guardados. Hasta que un espacio de
trabajo los tenga, **la extracción no puede comenzar**: la API la rechaza con `LLM_CONFIG_INCOMPLETE` y
la página de la historia indica qué falta por definir en lugar de generar tareas. Un espacio de trabajo
sin configurar se resuelve a Ollama, así que el campo que falta suele ser el modelo.
:::

## 7. Extrae tu primera historia

Crea un proyecto, añade una historia en el [formato estándar](/es/docs/story-format) y comienza la extracción. Se ejecuta de forma asíncrona: la solicitud responde de inmediato y la página de la historia informa el progreso. Las tareas que produce empiezan en **Pendiente** en el [tablero Kanban](/es/docs/kanban).

Si tienes varias historias, [impórtalas desde un CSV](/es/docs/story-import) en lugar de escribirlas una por una.

## Cuando algo no funciona

| Síntoma | Causa probable |
| --- | --- |
| `LLM_CONFIG_INCOMPLETE` | El espacio de trabajo no tiene modelo, o un proveedor en la nube no tiene API key |
| `LLM_CONNECTION_ERROR`, `LLM_RESPONSE_ERROR` | El host del proveedor no es accesible o rechazó la solicitud. Una API key incorrecta o vacía se ve así |
| La extracción termina con menos ejemplos, o sin ninguno | Qdrant o el servicio de embeddings no es accesible. Esto nunca hace fallar una extracción |
| La extracción agota el tiempo | El modelo tardó demasiado en responder. Un modelo más pequeño suele ser la solución |

## Ejecutar todo con Docker Compose

El repositorio también incluye un archivo Compose con cuatro servicios: la API, Ollama, PostgreSQL y Qdrant. `make build` construye las imágenes y `make up` las levanta, con la API en el puerto 8000.

El stack de Compose **no aplica migraciones**, así que el esquema hay que crearlo una vez antes de la primera solicitud:

```bash
cd backend
alembic upgrade head
```

Y como la base de datos de ese stack es el contenedor de Compose, el mismo valor tiene que llegar hasta ella: el archivo Compose define `STORICO_DATABASE_URL` para el contenedor de la API, pero tu shell necesita el suyo.
