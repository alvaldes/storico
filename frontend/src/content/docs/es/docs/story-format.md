---
title: Formato de historia de usuario
description: La forma que Storico espera, las dos maneras en que el formulario recibe una historia, los límites y dónde se aplica realmente el formato.
---

## La forma

Una historia es una sola oración en la forma ágil canónica:

```text
As a(n) [role], I want [feature], so that [benefit]
```

> "As a user, I want to reset my password, so that I can regain access to my account."

Las tres partes son campos separados en la base de datos, y la oración completa se guarda como el **texto original** de la historia. Ese texto original es la cadena que el modelo realmente lee: es la historia de usuario del prompt y también lo que guarda el contexto histórico, así que es la parte que conviene cuidar.

## Las dos maneras en que el formulario recibe una historia

**Modo por partes** son tres campos: el rol, la funcionalidad y el beneficio. Las palabras de enlace no se escriben nunca. El formulario compone el texto original con una plantilla fija en inglés:

```text
As a(n) {actor}, I want {feature}, so that {benefit}
```

Esas palabras están fijas, no traducidas. Cambiar la interfaz a español cambia las etiquetas alrededor de los campos, nunca el texto que llega al modelo, que es justamente el punto.

**Modo de texto completo** recibe la oración entera en una sola caja. El formulario comprueba que lleve las tres palabras clave —una apertura `As a`/`As an`/`As a(n)`, `I want` y `so that`— y después la divide en el rol, la funcionalidad y el beneficio. Un texto que tiene las palabras clave pero no se puede dividir se rechaza, y a un texto que no las tiene se le responde con un mensaje que indica el formato esperado.

## Límites

| Campo | Límite |
| --- | --- |
| Rol (`actor`) | 100 caracteres, obligatorio |
| Funcionalidad (`feature`) | 300 caracteres, obligatoria |
| Beneficio (`benefit`) | 300 caracteres, obligatorio |
| Texto original | 2000 caracteres |

En el modo de texto completo, las partes se **recortan** a sus límites en lugar de rechazarse, mientras que el texto original conserva hasta sus 2000 caracteres. Una historia muy larga se extrae igual, con las partes recortadas para mostrarlas y la oración completa preservada para el prompt.

## Las historias se esperan en inglés

La interfaz es bilingüe; las historias no. Los modelos que esta herramienta apunta fueron entrenados predominantemente en inglés y su salida para descomponer tareas se mide en inglés. El modo por partes impone los conectores en inglés por construcción, porque siempre los compone así.

## Dónde se aplica el formato y dónde no

- **El formulario** lo aplica: la comprobación de palabras clave y la división corren antes de enviar nada.
- La **[importación desde CSV](/es/docs/story-import)** lo aplica en la forma de una columna: una fila que no coincide con el formato se rechaza con el motivo `unparsable_story`.
- **La API no lo aplica.** Guarda cuatro campos —rol, funcionalidad, beneficio y texto original— y aplica sus límites de longitud. No vuelve a comprobar que el texto original se lea como una historia canónica, así que una historia creada directamente contra la API con un texto raro se acepta y luego se extrae tal cual.
