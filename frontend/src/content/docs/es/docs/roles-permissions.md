---
title: Roles y permisos
description: Los dos roles de un espacio de trabajo, quién es su propietario y qué puede hacer cada uno.
---

## Dos roles, y un propietario que no es un rol

Cada miembro de un espacio de trabajo tiene exactamente uno de dos roles: **administrador** o **miembro**. Esos son los únicos roles del sistema: no existe un administrador a nivel de sistema ni un rol de propietario. La propiedad es un campo del espacio de trabajo (el identificador de usuario del propietario), y el propietario puede tener cualquiera de los dos roles.

## Quién puede crear un espacio de trabajo

Cualquier usuario autenticado puede crear un espacio de trabajo. Quien lo crea se convierte automáticamente en su propietario y en miembro administrador. No interviene ningún otro permiso.

## Lo que pueden hacer los administradores

Solo los administradores pueden:

- actualizar o eliminar el espacio de trabajo;
- gestionar sus miembros: listarlos, añadir a un usuario por correo, cambiar el rol de un miembro y quitar a un miembro;
- leer y cambiar la configuración de LLM, los proveedores personalizados y los prompts del espacio de trabajo, y consultar qué modelos ofrece un proveedor.

Dos protecciones se superponen a la gestión de miembros: el rol del propietario no se puede cambiar (primero hay que transferir la propiedad) y al propietario no se le puede quitar del espacio de trabajo.

## Lo que solo puede hacer el propietario

Transferir la propiedad del espacio de trabajo a otro administrador es la única operación reservada al propietario.

## Lo que requiere el propietario o un administrador

Iniciar una extracción crea una nueva versión de la historia, así que queda reservado al propietario del espacio de trabajo o a un administrador. La misma regla se aplica a eliminar una historia de usuario, y a marcar una tarea como inválida o quitar una marca de invalidación: los extremos que mutan el historial de invalidaciones.

## Lo que puede hacer cualquier miembro

Los miembros sin rol de administrador pueden trabajar con el contenido del espacio de trabajo:

- crear, listar, actualizar y eliminar proyectos;
- crear y editar historias de usuario, y leer las historias, sus versiones y su historial de invalidaciones;
- consultar el estado de una extracción en curso;
- exportar las tareas del espacio de trabajo;
- leer tareas y actualizarlas (su estado y sus etiquetas; las dependencias solo en la versión actual).

Eliminar una historia es la excepción: requiere al propietario o a un administrador, igual que iniciar una extracción.
