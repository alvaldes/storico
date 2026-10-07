---
title: Roles y permisos
description: Los dos roles de un espacio de trabajo, quién es su propietario y una tabla de quién puede hacer qué, operación por operación.
---

## Dos roles, y un propietario que no es un rol

Cada miembro de un espacio de trabajo tiene exactamente uno de dos roles: **administrador** o **miembro**. Esos son los únicos roles del sistema: no existe un administrador a nivel de sistema ni un rol de propietario. La propiedad es un campo del espacio de trabajo (el identificador de usuario del propietario), y el propietario puede tener cualquiera de los dos roles.

## Quién puede crear un espacio de trabajo

Cualquier usuario autenticado puede crear un espacio de trabajo. Quien lo crea se convierte automáticamente en su propietario y en miembro administrador. No interviene ningún otro permiso.

## Quién puede hacer qué

| Operación | Quién |
| --- | --- |
| Crear un espacio de trabajo | Cualquier usuario autenticado, que pasa a ser su propietario y administrador |
| Leer, actualizar o eliminar un espacio de trabajo | Propietario o administrador |
| Listar miembros, añadir un miembro, cambiar el rol de un miembro, quitar un miembro | Propietario o administrador |
| Transferir la propiedad a otro administrador | **Solo el propietario** |
| Leer la configuración de LLM, cambiarla, editar los prompts, gestionar los proveedores personalizados y consultar los modelos de un proveedor | Administrador |
| Probar una conexión de LLM con credenciales que aún no están guardadas | Administrador |
| Leer si el espacio de trabajo puede extraer y qué campos faltan | Cualquier miembro: es la única lectura de configuración que un miembro sin rol de administrador puede llamar |
| Iniciar una extracción | Propietario o administrador |
| Eliminar una historia | Propietario o administrador |
| Marcar una tarea como inválida o quitar una marca de invalidación | Propietario o administrador |
| Crear, listar, actualizar o eliminar proyectos | Cualquier miembro |
| Crear y editar historias de usuario; leer las historias, sus versiones y su historial de invalidaciones | Cualquier miembro |
| Importar historias desde un CSV | Cualquier miembro |
| Consultar el estado de una extracción en curso | Cualquier miembro |
| Exportar las tareas del espacio de trabajo | Cualquier miembro |
| Leer tareas y actualizarlas: su estado y sus etiquetas en cualquier versión, sus dependencias solo en la versión actual | Cualquier miembro |

Una nota al pie de esa tabla:

- **Iniciar una extracción crea una versión nueva de la historia**, así que queda reservado al propietario o a un administrador. Eliminar una historia de usuario lleva la misma regla, y también los extremos que mutan el historial de invalidaciones.

## Las protecciones alrededor de la membresía

- El rol del propietario no se puede cambiar: primero hay que transferir la propiedad.
- Al propietario no se le puede quitar del espacio de trabajo.
- Un administrador no puede quitarse a sí mismo mientras sea el último administrador del espacio de trabajo: la solicitud se rechaza con HTTP 400 y `LAST_ADMIN_ERROR`.
- Añadir un miembro asigna siempre el rol de **miembro**; llegar a administrador es un cambio de rol, no una opción de invitación.

## Operaciones que dependen de otro servicio

Algunas operaciones protegidas por permisos pueden fallar por un motivo que no tiene nada que ver con los permisos: eliminar una historia, y marcar o quitar una invalidación, deben actualizar el almacén vectorial. Cuando Qdrant está configurado pero no es accesible, se rechazan con HTTP 503 y `VECTOR_STORE_UNAVAILABLE`. Consulta [Contexto histórico](/es/docs/embeddings-rag).
