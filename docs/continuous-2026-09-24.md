# Adjudicaciones continuas: 24/09/2026

## Fuentes y controles

- Maestros: `260924_lis_mae.pdf`, SHA256 `f9dd6262946245c33638320685ec5414663a40c1cd505afd959d367dffb0caff`.
- Secundaria: `260924_lis_sec.pdf`, SHA256 `5f523e1e98ecccade21ef8a83bd58cba11997bd01c1cf7e72bb509d420d742bc`.
- Archivos aportados por el responsable. URLs oficiales bajo `https://ceice.gva.es/documents/162909733/414354213/`.
- 159 adjudicaciones de Maestros y 150 de Secundaria y otros cuerpos: 309 puestos unicos, sin duplicados entre bolsas/cuerpos.
- Todas las adjudicaciones verificadas por nombre, especialidad, centro, fecha, jornada, tipo, ingles, itinerancia y observaciones; 63 conservan observaciones de la oferta.
- 399 puestos ofertados anteriores menos 309 cubiertos: se mantienen 90 sin cubrir.
- 303 cortes del dia contrastados (154 de Maestros y 149 de Secundaria); para Maestros se conserva ademas la posicion por especialidad.
- Sin cambios en los cortes de inicio, posiciones iniciales ni datos de centros. Se conservan las 203 adjudicaciones de dificil cobertura verificadas anteriormente.
- Lectura independiente de los PDF completos: 162 bloques Adjudicat en 830 paginas de Maestros y 217 en 1539 paginas de Secundaria, antes de eliminar repeticiones.
- 153 pruebas de regresion y validacion completa de los JSON. Comprobados los lectores de la web y Android con las fichas de dificil cobertura y homonimos anteriores.
- Detector real de Android: nuevo evento continuous_results, sin eventos nuevos de puestos ofertados ni de inicio de curso.

## Caso confirmado por el responsable

Marina Cruselles Seser, puesto 767331, centro 46017651 (FPA de Mislata), aparece adjudicada al programa 295 FPA Comunicacion (Valenciano/Ingles) bajo las bolsas 211 y 411. El responsable confirma **211 Ingles de Secundaria, posicion 96**. La bolsa 411 queda como no adjudicada.

Se conservan jornada completa, sustitucion determinada, requisito ingles, programa 295 en castellano y valenciano y la observacion ING-C1 de la oferta. La decision queda registrada en `data/program_assignment_reviews.json` para el SHA256 concreto del PDF, con controles de nombre, centro, puesto, programa y estado adjudicado en la bolsa elegida.

## Motivo de la detencion automatica

Las ejecuciones #1679 (36000919398) y #1680 (36001184443) usaron cc97702. En #1680 consta la descarga y lectura de ambos listados; la publicacion se detuvo ante las dos bolsas posibles de Marina. La proteccion incorporada el 22/09 evito una publicacion parcial y mantuvo los datos anteriores.

No se modifica el calendario ni se elige automaticamente una bolsa en casos dudosos. Con la confirmacion guardada, el extractor puede procesar este documento y las siguientes ejecuciones reconoceran ambos PDF como ya publicados.
