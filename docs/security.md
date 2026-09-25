# Security

> Modelo de autenticación, autorización y seguridad en Storico.
> Última actualización: 2026-07-15

## Autenticación

### Proveedores

- **Google OAuth** — Auth.js provider
- **GitHub OAuth** — Auth.js provider
- **Sin email+password** — No hay registro por contraseña, no hay recovery

### Stack

Auth.js (anteriormente NextAuth.js) integrado con Astro via `auth-astro`.

```javascript
// astro.config.mjs
integrations: [react(), auth()]
```

### Sesiones

- JWT-based (o database sessions — configurable)
- Sin cookies de sesión del lado servidor
- El token se inyecta en headers de llamadas API

## Autorización

### Modelo de permisos

```
Admin → Workspace → Miembros (admin / member)
```

| Rol | Crear workspace | Gestionar miembros | CRUD proyectos | Extraer tareas |
|-----|----------------|--------------------|---------------|----------------|
| Admin | ✅ | ✅ | ✅ | ✅ |
| Member | ❌ | ❌ | ✅ | ✅ |

### Reglas

- Solo admins pueden crear workspaces y asignar usuarios a equipos
- Cualquier usuario logueado puede usar la app dentro de un workspace
- Roles: `admin` | `member` (en `workspace_members.role`)

### Excepciones de dominio

Definidas en `storico.domain.entities.exceptions`:

| Excepción | Descripción |
|-----------|-------------|
| `NotWorkspaceMember` | Usuario no es miembro del workspace |
| `InsufficientRole` | Usuario no tiene rol suficiente |
| `OwnerTransferError` | Error al transferir ownership |
| `LastAdminError` | No se puede remover el último admin |
| `CannotRemoveOwnerError` | No se puede remover al owner del workspace |

## Frontend

### Protección de rutas

Middleware de Astro protege rutas sensibles:

```typescript
protectedPaths = ['/dashboard', '/stories', '/kanban', '/export', '/account']
// Redirect a /login si no hay sesión
```

### Páginas públicas (sin auth)

`/`, `/login`, `/about`, `/privacy`, `/terms`, `/docs`, `/api`, `/status`

### Tokens

- Auth.js maneja sesiones vía JWT
- `AUTH_SECRET` — mismo valor en frontend y backend, distinto en dev y prod
- `STORICO_AUTH_INTERNAL_TOKEN` — token interno para comunicación frontend-backend

## Buenas prácticas

### Backend

- **CORS** — Configurable vía `STORICO_CORS_ORIGINS`. Default `"*"` en desarrollo.
- **Extra fields rechazados** — Schemas Pydantic usan `extra="forbid"`
- **SQL Injection** — SQLAlchemy con parametrización (no raw SQL)
- **API keys de LLM** — Almacenadas **cifradas en reposo** en la base de datos (campo `api_key` en `workspace_llm_configs`) con Fernet, usando el prefijo `v1:` como marca de formato. La clave maestra vive en la variable de entorno `STORICO_ENCRYPTION_KEY` del proceso; si no está configurada, guardar una credencial falla con `500` y el código `ENCRYPTION_KEY_MISSING` en lugar de escribirla en claro. La key sí se devuelve al **admin** del workspace: `GET /settings/llm` la incluye descifrada para que el formulario pueda mostrarla y probar el proveedor. El endpoint de estado (`GET /settings/llm/status`), legible por cualquier miembro, nunca devuelve valores — solo los nombres de los campos que faltan. **Qué NO protege**: el endpoint sigue entregando la key descifrada al admin del workspace (decisión ya documentada arriba); la clave maestra vive en el entorno del proceso; y el cifrado no protege frente a quien tenga a la vez la base de datos y la clave. **No existe configuración de LLM por usuario**: `GET`/`PUT /users/me/settings` transporta únicamente `export.defaultFormat`, un `PUT` con un bloque `llm` responde `422`, y la revisión `0022` removió del almacenamiento el bloque que versiones anteriores guardaban ahí.

### Frontend

- **API keys nunca en localStorage** — `settingsStore` persiste solo `settings.export`
- **Content-Type** forzado a `application/json`
- **No secrets en código** — Variables de entorno via `import.meta.env`

### Producción (pendiente)

- [ ] Rate limiting (`slowapi` en FastAPI o un límite de tasa en Caddy; el backend no está en Vercel, así que un WAF de Vercel no protege la API)
- [ ] Error monitoring (Sentry)
- [x] Auditoría de variables de entorno — hecha el 2026-09-24 sobre el `.env` de la VM **y** los dos proyectos de Vercel (el del frontend, que es el deploy en uso, y el que no está en uso), comparando por hash SHA-256 y sin imprimir ningún valor: las 11 de la VM y las 7 del front de producción están completas, y el `AUTH_SECRET` del front coincide con `STORICO_AUTH_JWT_SECRET` de la VM. Quedan anotadas dos observaciones **sin remediar por decisión del operador**: dev y prod comparten el secreto de firma y el cliente OAuth de Google, y el proyecto de Vercel en desuso conserva la `STORICO_DATABASE_URL` de producción en scope Preview. **Actualización 2026-09-25:** la segunda de esas observaciones quedó **remediada**: el proyecto en desuso se borró por consumo de Functions Storage (6.94 GB de los 10 GB del team), así que la credencial de la base de producción ya no vive en ningún scope Preview. La primera sigue abierta a propósito. Detalle en `prod.todo.md`.
- [x] Dominio personalizado — **no se usa**, decidido el 2026-09-23: producción ya sirve HTTPS con el certificado de Vercel en el front y el del host de la VM en la API, así que no se compra dominio ni se agrega un paso de renovación propio.
- [ ] Restringir CORS a dominios específicos

## Referencias

- ADR-003: Autenticación y Permisos (ver [architecture.md](architecture.md))
- `prod.todo.md` — Items de seguridad pendientes para producción
