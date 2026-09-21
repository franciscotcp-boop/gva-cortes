# Puestos publicados el 21/09/2026 para la adjudicacion del 22/09/2026

- Documento: `260922_pue_prov.pdf`, 83 paginas.
- Fuente verificada: https://ceice.gva.es/documents/162909733/414354213/260922_pue_prov.pdf
- SHA256: `cb80d01f497fb680679ecec5ed40375fade66c4c7a38ca4867abfd20e8086839`.
- Fecha impresa de publicacion: 21/09/2026. Se conserva el contrato existente del conjunto ordinario: `publication_date` y `snapshot_date` identifican la convocatoria (22/09/2026), no la fecha de lectura. No impide mostrar ni notificar los puestos el dia anterior.
- 528 puestos: 250 de Maestros y 278 de otros cuerpos, en 82 especialidades.
- 100 vacantes, 343 sustituciones indeterminadas, 85 determinadas.
- 38 puestos con requisito ingles, 31 itinerantes, 110 con observaciones.
- Sin centros desconocidos, duplicados ni fechas incompletas en observaciones.
- El nuevo listado sustituye los ordinarios anteriores. No se conservan puestos de dificil cobertura caducados.
- Cortes, posiciones y contexto de adjudicaciones permanecen intactos.

## Correccion del extractor

La ejecucion local del extractor anterior se detenía en el puesto 912650 (IES de Rafelbunyol, especialidad 256) porque interpretaba `FRA-B2` como horas. El puesto 769157 (FPA Profesor Alberto Barrios, 295) presentaba el mismo problema con `ING-C1`.

Se separan los requisitos linguisticos de las horas. `FRA-B2` se conserva junto a `VAL + FRANC.` en observaciones, sin activar requisito ingles. `ING-C1` activa requisito ingles y conserva explicitamente el nivel C1 en observaciones. Se mantienen los errores de validacion para valores no reconocidos.

## Comprobaciones

- 137 pruebas de regresion correctas, incluidas tres nuevas pruebas de requisitos linguisticos.
- Inventario independiente mediante pypdf: mismos 528 identificadores de puesto que el extractor por columnas, y numeracion completa 1-528.
- Validacion estructural del conjunto completo y revision visual de los dos requisitos singulares.
- GitHub, al consultar el historial el 21/09/2026 a las 15:xx Europe/Madrid, no mostraba ninguna ejecucion principal de ese dia. La ultima era #1669 del 19/09, correcta. El ultimo vigilante (#930, 21/09 03:23) termino sin actuar por estar fuera de horario. Ambos workflows estaban activos. No se atribuye a un fallo remoto no observado; el defecto del extractor se ha reproducido con el PDF adjunto y corregido.
