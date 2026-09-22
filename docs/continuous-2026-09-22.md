# Adjudicaciones continuas: 22/09/2026

## Fuentes y validacion

- Maestros: `260922_lis_mae.pdf`, SHA256 `0da8ee5a06dcdcd54124db32540c99c65892058234e0e1df706d62dc88cce4c2`.
- Secundaria: `260922_lis_sec.pdf`, SHA256 `9605c0da31a326fdfee1dca174e1989f1da833bd7814a426ed721fd4e5510b08`.
- Archivos aportados por el responsable; URLs oficiales bajo `https://ceice.gva.es/documents/162909733/414354213/`.
- 239 adjudicaciones de Maestros y 223 de Secundaria y otros cuerpos: 462 puestos unicos, sin repetir los publicados en otras bolsas/cuerpos.
- Todas las adjudicaciones conciliadas con nombre, especialidad de origen, centro, fecha, tipo, horas, ingles, itinerancia y observaciones. 99 conservan observaciones de la oferta.
- 528 puestos ofertados anteriores menos 462 cubiertos: permanecen 66 sin cubrir.
- 441 filas de cortes del dia comprobadas (227 de Maestros y 214 de Secundaria); cada corte es el ultimo adjudicado por centro y especialidad.
- Sin cambios en los cortes de inicio, posiciones iniciales ni datos de los centros. Se conservan las 203 adjudicaciones de dificil cobertura ya verificadas.
- Lectura independiente de todos los PDF: 247 bloques Adjudicat en 856 paginas de Maestros y 319 en 1596 paginas de Secundaria, antes de eliminar repeticiones.
- 153 pruebas de regresion, validacion de los JSON y comprobaciones con los lectores reales de CodePen y Android.
- Detector real de Android: nuevo evento continuous_results, tanto desde la version anterior al dia como desde la actualizacion parcial. Sin nuevo evento de ofertas ni de inicio de curso.

## Especialidades confirmadas por el responsable

Las decisiones se guardan en `data/program_assignment_reviews.json`, limitadas al SHA256 del PDF de Secundaria y comprobando puesto, nombre, centro, programa y registro adjudicado en la bolsa elegida.

| Puesto | Docente | Bolsa | Posicion | Programa en observaciones |
| --- | --- | --- | --- | --- |
| 907991 | GARCIA VILLENA, MIGUEL | 204 Lengua Castellana y Literatura | 466 | 277 Ambito Sociolinguistico |
| 767275 | BOU GARCIA, BORJA | 256 Lengua y Literatura Valenciana | 164 | 297 FPA Comunicacion (Valenciano) |
| 924524 | APARICI GALDON, NURIA LLEDO | 207 Fisica y Quimica | 46 | 276 Ambito Cientifico |

Las notas de los datos conservan sus acentos y denominaciones en castellano y valenciano.

El programa 295 FPA Comunicacion (Valenciano/Ingles) se incorpora a los programas reconocidos. Para HERNANDEZ BERTO, ANA, puesto 769157, el unico encabezado adjudicado es 211 Ingles, posicion 57; se conservan el programa 295 y el requisito ingles.

## Incidencia de automatizacion

La ejecucion #1673 (run 35728298141, commit 75e1078) termino en verde, pero publico solo Maestros. La extraccion de Secundaria se detuvo ante las bolsas ambiguas del puesto 907991; run_mode capturaba la excepcion como aviso y continuaba publicando el otro PDF.

Ahora run_mode recoge las fuentes pendientes y falla antes de aplicar resultados, fichas o retirada de puestos si cualquier PDF nuevo no se puede procesar. Las condiciones existentes del workflow impiden publicar tras ese fallo y lo comunican al vigilante. El error enumera todos los puestos ambiguos para revisarlos conjuntamente, sin escoger bolsas automaticamente.

La publicacion de hoy se reconstruye con ambos documentos desde c1c937a, la ultima version completa anterior a los resultados de hoy, conservando las revisiones de dificil cobertura. No se revierte la web publica durante la preparacion.
