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
- **API keys de LLM** — Almacenadas en DB (campo `api_key` en `workspace_llm_configs`), nunca expuestas al frontend

### Frontend

- **API keys nunca en localStorage** — `settingsStore` persiste solo `settings.export`
- **Content-Type** forzado a `application/json`
- **No secrets en código** — Variables de entorno via `import.meta.env`

### Producción (pendiente)

- [ ] Rate limiting (Vercel WAF o slowapi)
- [ ] Error monitoring (Sentry)
- [ ] Auditoría de variables de entorno en Vercel
- [ ] Dominio personalizado + renovar SSL
- [ ] Restringir CORS a dominios específicos

## Referencias

- ADR-003: Autenticación y Permisos (ver [architecture.md](architecture.md))
- `prod.todo.md` — Items de seguridad pendientes para producción
