# Puestos de dificil cobertura publicados el 24/09/2026

- Archivo: `260925_pue_prov.pdf`.
- Fuente: https://ceice.gva.es/documents/162909733/414892733/260925_pue_prov.pdf
- SHA256: `930d6ac72cb597a533be8447b0cffffa50078ea5dfcf85965a892f62b850f2a5`.
- La copia oficial descargada coincide exactamente con el archivo entregado.
- Fecha interna de publicacion: 24/09/2026; el nombre corresponde a la convocatoria del dia 25.
- El responsable solicita caducidad al cambiar de dia: ocultos desde el 25/09/2026, segun la regla existente. No se cambian aplicaciones ni calendarios.

## Resultado

- 12 paginas y 87 puestos, identificados por el extractor principal y por una segunda lectura independiente de todos los numeros de puesto.
- 15 puestos de Maestros y 72 de otros cuerpos, en 39 especialidades.
- 12 vacantes, 59 sustituciones indeterminadas y 16 determinadas.
- 6 puestos con requisito ingles y 8 itinerantes.
- Los 87 coinciden con ofertas ordinarias pendientes y prevalece dificil cobertura, sin duplicidades.
- Se conservan otros 3 puestos ordinarios: 90 puestos visibles hoy y 3 tras la caducidad.
- Sin centros desconocidos ni observaciones con fechas incompletas.
- Cortes, fichas personales, adjudicaciones de hoy y antecedentes de dificil cobertura quedan intactos.

## Validacion

- 153 pruebas de regresion correctas y validacion estructural del conjunto de datos.
- Probada la lectura de este JSON con el codigo existente de Android y CodePen: 87 puestos de dificil cobertura el dia 24 y ninguno el dia 25, incluso con el mismo JSON en cache.
- El detector Android genera solo el nuevo evento de ofertas de dificil cobertura, no repite las notificaciones de adjudicaciones continuas ni de inicio. El evento caduca tambien el dia 25.
- Inspeccion visual de filas representativas para horas decimales, requisito ingles, itinerancia, composicion y observaciones multilínea.
