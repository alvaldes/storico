---
title: Importación de historias desde CSV
description: Las dos formas de CSV que Storico acepta, los límites que aplica, los duplicados que omite y cada motivo por el que rechaza un archivo.
---

Importar es una forma de **crear historias de usuario** desde un archivo en lugar de escribirlas una por una. No es extracción: crea las historias, y cada una todavía debe extraerse por su cuenta después. El punto de entrada es **Importar CSV** en la página de historias, que pide un proyecto y un archivo; la importación añade las historias a ese proyecto.

Vale repetir un límite, porque los nombres se parecen: esto es **creación de historias**, no `POST /batch`. Storico no tiene endpoint de extracción por lotes y cada extracción es una historia.

## La solicitud

`POST /api/v1/workspaces/{workspace_id}/stories/import`, enviada como `multipart/form-data` con dos campos: `project_id` y `file`. Una importación exitosa responde **HTTP 201** con:

| Campo | Significado |
| --- | --- |
| `created` | Cuántas historias se escribieron |
| `skipped` | Cuántas filas se omitieron por ser duplicados |
| `total_rows` | Cuántas filas de datos no vacías tenía el archivo |
| `duplicates` | Una entrada por fila omitida: su línea, el motivo y la historia con la que coincidió |
| `story_ids` | Los identificadores de las historias creadas |

El proyecto debe pertenecer al espacio de trabajo de la ruta; un proyecto de otro espacio de trabajo se rechaza con HTTP 403 y `PROJECT_NOT_IN_WORKSPACE`, y uno desconocido con HTTP 404 y `ENTITY_NOT_FOUND`.

## El archivo

| Regla | Valor |
| --- | --- |
| Codificación | UTF-8; se tolera una marca de orden de bytes al inicio, cualquier otra cosa es `invalid_encoding` |
| Delimitador | Lo decide la primera línea: coma, punto y coma o tabulador. Si no tiene ninguno de los tres, el archivo se lee como **una sola columna** y cada línea se conserva entera |
| Encabezado | Obligatorio: la primera línea nombra las columnas. Se compara sin distinguir mayúsculas y sin los espacios de los extremos |
| Tamaño | Como máximo 2 MB |
| Filas | Como máximo 1000 filas de datos; las filas vacías se omiten y no cuentan |
| Columnas extra | Permitidas e ignoradas |

Como un archivo sin delimitador en su primera línea se lee como una sola columna, el texto canónico de la historia —que contiene comas por construcción— sobrevive entero en lugar de cortarse en su primera coma.

## Las dos formas aceptadas

### Una columna de historias

El encabezado nombra una sola columna y cada fila es una historia completa:

```csv
story
"As a user, I want to reset my password, so that I can regain access to my account."
```

Los nombres de encabezado aceptados son `story`, `input` y `raw_text`. Cada fila se analiza en su actor, su funcionalidad y su beneficio, así que se guarda igual que una historia escrita en el formulario.

### Tres columnas de partes

El encabezado nombra las tres partes y cada fila las lleva por separado:

```csv
actor,feature,benefit
user,reset my password,regain access to my account
```

Las tres son obligatorias: un encabezado con solo una o dos de ellas se rechaza como `header_unrecognized`. El texto que ve el modelo se construye entonces a partir de las partes con una plantilla fija:

```text
As a(n) {actor}, I want {feature}, so that {benefit}
```

Puedes añadir una cuarta columna, `raw_text`, para aportar ese texto tú mismo en su lugar: cuando la celda está presente y no está vacía se usa tal cual, con sus saltos de línea internos incluidos, y la plantilla no se usa en esa fila.

## Límites de los campos

| Campo | Máximo |
| --- | --- |
| `actor` | 100 caracteres |
| `feature` | 300 caracteres |
| `benefit` | 300 caracteres |
| `raw_text` | 2000 caracteres |

En la forma de una columna, el texto original se limita a 2000 caracteres y cada parte en la que se analiza se verifica contra su propio límite.

## Una fila mala rechaza el archivo entero

Una importación es **todo o nada**. Si alguna fila tiene un problema, no se escribe nada y la respuesta es HTTP 422 con el código de error `IMPORT_VALIDATION_FAILED`. El diálogo enumera las líneas problemáticas para que el archivo se pueda corregir y subir de nuevo.

| Motivo | Qué significa |
| --- | --- |
| `field_count_mismatch` | La fila tiene un número de valores distinto del que declara el encabezado. Esta verificación corre primero, porque cuando los conteos no coinciden el mapeo de columnas no es fiable y cualquier queja por campo en esa fila sería ruido |
| `parts_look_like_a_full_story` | Bajo un encabezado de tres columnas, las celdas unidas se leen como una sola historia canónica completa: la señal de una historia entera pegada en las columnas de sus partes. Un `actor` que ya empieza con "As a…" se rechaza por el mismo motivo, porque la app lo renderiza como `As a(n) {actor}` y la corrección es escribir solo el actor |
| `missing_field` | Una celda obligatoria no existe en la fila |
| `empty_field` | Una celda obligatoria existe pero está vacía |
| `too_long` | Un valor supera el límite de la tabla anterior; la respuesta nombra el campo, su longitud y el máximo |
| `unparsable_story` | Una fila de una columna no coincide con el formato de historia aceptado |

Las filas se verifican en ese orden y una fila reporta como máximo un motivo.

Un archivo también puede rechazarse antes de examinar ninguna fila; la respuesta es entonces HTTP 422 con `IMPORT_FILE_REJECTED`:

| Motivo | Qué significa |
| --- | --- |
| `empty_file` | El archivo no tiene contenido, o solo espacios |
| `invalid_encoding` | Los bytes no son UTF-8 válido |
| `header_unrecognized` | La primera línea no nombra ni una columna de historia completa ni las tres columnas de partes |
| `too_many_rows` | Más de 1000 filas de datos |
| `malformed_csv` | El archivo no se pudo analizar como CSV |

Y un archivo de más de 2 MB se rechaza con HTTP 413 y `IMPORT_FILE_TOO_LARGE` antes de leerlo.

## Los duplicados se omiten, no se rechazan

Dos filas cuentan como la misma historia cuando sus `(actor, feature, benefit)` recortados son **exactamente** iguales: sin unificar mayúsculas ni normalizar espacios. Un duplicado no es un error: se omite y se reporta en `duplicates`.

- `duplicate`: la historia ya existe en el proyecto, y la entrada lleva el identificador de la historia existente.
- `duplicate_in_file`: una fila anterior de la misma carga ya la reclamó, y la entrada lleva el número de línea de esa fila.

Por eso volver a subir el mismo archivo es inofensivo: responde HTTP 201 con `created` en 0 y todas las filas reportadas como omitidas.

## Una aclaración más

Importar crea historias; no extrae tareas. Nada en esta ruta ejecuta un modelo, y la validación automática descrita en la página de [Proveedores de LLM](/es/docs/llm-providers) tampoco se ejecuta en las extracciones que inicies después desde la app.
