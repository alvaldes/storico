---
title: Proveedores de LLM
description: Los backends con los que Storico puede extraer, los campos que necesita cada uno, los proveedores personalizados y cómo se obtienen las listas de modelos.
---

Storico tiene **cuatro proveedores de primera clase** —Ollama, OpenAI, Anthropic y Gemini— y **proveedores personalizados**: cualquier otro nombre que un espacio de trabajo registre para un endpoint que hable el dialecto de OpenAI. El enrutamiento es por nombre exacto, así que un nombre fuera de los cuatro es, por definición, un proveedor personalizado, y quien lo llama es el adaptador compatible con OpenAI.

| Proveedor | API key | Los modelos se listan desde | Endpoint usado cuando Base URL está vacío |
| --- | --- | --- | --- |
| Ollama | no se usa | `/api/tags` | `http://localhost:11434` (el ajuste `STORICO_OLLAMA_HOST`) |
| OpenAI | obligatoria | `/models` | `https://api.openai.com/v1` |
| Anthropic | obligatoria | `/v1/models` | `https://api.anthropic.com` |
| Gemini | obligatoria | `/models`, conservando solo los modelos que anuncian `generateContent` | `https://generativelanguage.googleapis.com/v1beta` |
| Personalizado | opcional | `/models` y, si la primera queda vacía, `/v1/models` | ninguno: un proveedor personalizado necesita su Base URL |

## Los campos de configuración

Un espacio de trabajo guarda una única configuración de LLM. Estos son sus campos, con las longitudes que aplica la API:

| Campo | Tipo | Valor por defecto | Notas |
| --- | --- | --- | --- |
| `provider` | texto, hasta 50 caracteres | `ollama` | Texto libre; los cuatro nombres enrutan a sus adaptadores y cualquier otro enruta al compatible con OpenAI |
| `model` | texto, hasta 100 caracteres | sin definir | Obligatorio en todos los proveedores |
| `api_key` | texto, hasta 500 caracteres | sin definir | Obligatoria en OpenAI, Anthropic y Gemini; opcional en Ollama y en los personalizados |
| `base_url` | texto, hasta 500 caracteres | sin definir (el host de Ollama cuando el proveedor es Ollama) | Opcional en los proveedores en la nube, donde reemplaza al endpoint por defecto; obligatoria en un proveedor personalizado |
| `temperature` | número | `0.1` | El formulario de configuración la limita a 0–2 en pasos de 0.1; la API por sí sola acepta cualquier número |
| `max_tokens` | entero | `2048` | El formulario de configuración lo limita a 256–8192 en pasos de 256; la API por sí sola acepta cualquier entero |

Guardar es una **fusión parcial**: el endpoint de configuración actualiza solo los campos presentes en la solicitud, y un valor en blanco se guarda como no definido, no como una cadena vacía.

## Los campos obligatorios

Aquello sin lo cual un proveedor no se puede llamar:

| Proveedor | Obligatorio |
| --- | --- |
| Ollama | `model` |
| OpenAI, Anthropic, Gemini | `model`, `api_key` |
| Personalizado | `model`, `base_url`; la API key sigue siendo opcional, porque una pasarela autoalojada suele aceptar solicitudes sin autenticación |

Un valor compuesto solo por espacios cuenta como **no definido**, así que un formulario guardado con campos vacíos deja los mismos huecos que uno nunca llenado. Cuando falta un campo, la extracción se rechaza con HTTP 400 y el código de error `LLM_CONFIG_INCOMPLETE`, que nombra los campos que faltan; la página de la historia muestra cuáles están sin definir en lugar de iniciar una ejecución.

`GET /api/v1/workspaces/{workspace_id}/settings/llm/status` responde la misma pregunta para cualquier miembro del espacio de trabajo: un booleano, el proveedor efectivo y la lista de nombres de campos que faltan. Es la única ruta de configuración que un miembro sin rol de administrador puede leer, y nunca lleva la clave ni el endpoint que esos campos contienen.

## Proveedores personalizados

Un proveedor personalizado es un **nombre registrado por espacio de trabajo**, para un endpoint que hable el dialecto de OpenAI: una pasarela autoalojada, un proxy o un proveedor que los cuatro integrados no cubren.

- **El nombre** es texto libre de 1 a 50 caracteres una vez recortado, guardado exactamente como se escribe: los espacios alrededor se ignoran y las mayúsculas se conservan. La unicidad distingue mayúsculas de minúsculas, así que `Groq` y `groq` pueden convivir.
- **Nombres rechazados.** Un nombre integrado en cualquier combinación de mayúsculas se responde con HTTP 409 y `PROVIDER_NAME_BUILTIN`; el valor de control del selector de proveedores (`__add_custom_provider__`) se responde con HTTP 409 y `PROVIDER_NAME_RESERVED`; un nombre ya registrado en el espacio de trabajo se responde con HTTP 409 y `PROVIDER_DUPLICATE_NAME`.
- **Qué guarda la fila de un proveedor personalizado.** Solo su nombre. La Base URL, la API key y el modelo pertenecen a la configuración de LLM del espacio de trabajo, así que registrar un proveedor lo hace seleccionable pero todavía no llamable: hasta que la configuración tenga un modelo y una Base URL, la extracción queda bloqueada por la misma regla de completitud que cualquier otro proveedor.
- **Operaciones.** Un espacio de trabajo puede listar sus proveedores, crear uno (HTTP 201) y renombrarlo. Renombrar un proveedor al que apunta la configuración guardada también reapunta la configuración, para que la selección no se rompa. No hay endpoint para eliminarlo.

| Operación | Endpoint |
| --- | --- |
| Listar | `GET /api/v1/workspaces/{workspace_id}/settings/providers` |
| Crear | `POST /api/v1/workspaces/{workspace_id}/settings/providers` |
| Renombrar | `PATCH /api/v1/workspaces/{workspace_id}/settings/providers/{provider_id}` |

## Encontrar los modelos de un proveedor

`POST /api/v1/workspaces/{workspace_id}/settings/llm/models` hace de proxy hacia la lista de modelos del propio proveedor y responde con un arreglo de `{id, name}`. El cuerpo es opcional y describe la selección que se tiene a mano —proveedor, Base URL y API key—, de modo que la respuesta describe al proveedor recién elegido y no al que ya estaba guardado; una consulta nunca toma prestada la credencial guardada para un proveedor distinto. Sin cuerpo, se consulta la configuración guardada.

La respuesta es una **lista vacía**, no un error, cuando no hay con qué consultar:

- un proveedor en la nube sin API key en el cuerpo;
- un proveedor personalizado sin Base URL;
- nada guardado todavía y ningún proveedor en el cuerpo.

Cuando el proveedor en sí no se puede alcanzar, la ruta responde HTTP 502 y `PROVIDER_MODELS_UNREACHABLE`.

`POST /api/v1/llm/test` es la ruta hermana que prueba una conexión en lugar de listar modelos: envía un prompt mínimo (`Hello`) por el mismo adaptador que usa la extracción y reporta el resultado, incluido el mensaje de error de conexión cuando lo hay. Ambas rutas llevan las credenciales pendientes en el cuerpo y no en la cadena de consulta, para que una API key nunca termine en un registro de acceso.

## Dónde vive la API key

Una API key se cifra antes de guardarse. Leer la configuración del espacio de trabajo requiere el rol de administrador, y esa respuesta devuelve la clave tal como se configuró; el endpoint de estado que puede leer cualquier miembro es deliberadamente estrecho y nunca la incluye. Una clave que no se puede descifrar se reporta como tal en lugar de tratarse en silencio como ausente.

## La validación automática no se ejecuta

Una aclaración que vale para todos los proveedores: al extraer desde la aplicación web, esta nunca pide la validación automática de la extracción —no se ejecuta ningún paso de LLM-as-a-Judge y no se produce ninguna puntuación de confianza—. La capacidad existe en el motor; la app simplemente no la solicita.

## Códigos de error

| Código | HTTP | Significado |
| --- | --- | --- |
| `LLM_CONFIG_INCOMPLETE` | 400 | Al espacio de trabajo le falta un campo obligatorio para su proveedor |
| `CUSTOM_PROVIDER_NOT_FOUND` | 404 | El identificador del proveedor no existe |
| `PROVIDER_NOT_IN_WORKSPACE` | 403 | El identificador del proveedor pertenece a otro espacio de trabajo |
| `PROVIDER_DUPLICATE_NAME` | 409 | Ya existe un proveedor personalizado con ese nombre en el espacio de trabajo |
| `PROVIDER_NAME_BUILTIN` | 409 | El nombre es uno de los cuatro proveedores integrados |
| `PROVIDER_NAME_RESERVED` | 409 | El nombre está reservado por el selector de proveedores |
| `PROVIDER_MODELS_UNREACHABLE` | 502 | No se pudo alcanzar al proveedor para listar sus modelos |
| `REQUEST_VALIDATION_FAILED` | 422 | Un campo incumple su tipo o longitud declarados |
