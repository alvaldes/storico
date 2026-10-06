---
title: Contexto histórico
description: De dónde salen los ejemplos del prompt de extracción, los tres ajustes por espacio de trabajo y qué pasa cuando el almacén vectorial no está disponible.
---

## De dónde salen los ejemplos

Cuando una ejecución termina, el servidor la escribe en una base de datos vectorial (Qdrant) como un punto que empareja un embedding de la historia de usuario con un resumen de las tareas que produjo esa ejecución. Cuando extraes una historia, el servidor calcula el embedding del texto y busca entre los puntos del mismo espacio de trabajo las extracciones pasadas más parecidas. Las mejores coincidencias se inyectan en el prompt como **ejemplos few-shot**: casos completos del pasado de "esta historia de usuario produjo estas tareas".

Toda búsqueda está acotada al espacio de trabajo y lleva tres reglas incondicionales: nunca lee los puntos de otro espacio de trabajo, nunca devuelve una extracción pasada cuyas tareas incluyan alguna marcada como inválida, y nunca devuelve las ejecuciones anteriores de la propia historia como ejemplos para ella misma.

## Los tres ajustes

La recuperación few-shot se configura por espacio de trabajo y está **activada por defecto**:

| Ajuste | Valor por defecto | Qué controla |
| --- | --- | --- |
| Few-shot activado | activado | Si la recuperación se ejecuta o no |
| Límite de few-shot | 3 | Cuántos ejemplos puede devolver la búsqueda |
| Umbral de few-shot | 0.85 | La puntuación mínima de similitud para que un punto cuente |

El umbral lo aplica el propio almacén vectorial: un punto solo regresa si su similitud con la historia que se está extrayendo es de al menos 0.85 (o el valor que haya fijado el espacio de trabajo). Un ejemplo en el prompt es el texto de la historia de usuario de una extracción pasada seguido de sus tareas; cuando la ejecución tiene una puntuación del juez, se muestra junto al ejemplo.

## Dónde viven los puntos

Cada entorno usa su propia colección, porque los vectores de modelos de embedding distintos no son comparables. El nombre de la colección viene del ajuste `STORICO_QDRANT_COLLECTION` y por defecto es `storico_extractions`; el valor que usa cada despliegue forma parte de la configuración de ese entorno. Además del vector, un punto guardado lleva el texto de la historia, el resumen de tareas, el modelo usado, el número de versión de la ejecución, los identificadores del espacio de trabajo, del proyecto y de la historia, una marca de validez, la puntuación opcional del juez y la fecha de creación.

## Cuando el almacén vectorial no está disponible

La recuperación y el almacenamiento son ambos de mejor esfuerzo, y ninguno puede hacer fallar una extracción:

- Si el servicio de embeddings no responde, el embedding vuelve vacío, la búsqueda no devuelve nada y la extracción continúa sin ejemplos.
- Si Qdrant no responde, la búsqueda no devuelve nada y la extracción continúa sin ejemplos.
- Guardar el punto de una ejecución terminada también puede fallar en silencio: el fallo queda registrado en el log y la extracción —ya guardada en la base de datos— sigue siendo exitosa.

Dicho de otro modo: una extracción igual termina con éxito sin ejemplos cuando el almacén vectorial no está disponible. El único coste es el contexto: el prompt se genera sin la sección de ejemplos few-shot hasta que el almacén vuelva.

## Lo que esta función no hace

La aplicación web nunca pide la validación automática de una extracción: no se ejecuta ningún paso de LLM-as-a-Judge y no se produce ninguna puntuación de confianza para las ejecuciones iniciadas desde la app.
