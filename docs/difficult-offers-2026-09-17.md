# Puestos de dificil cobertura publicados el 17/09/2026

- Archivo: `260918_pue_prov.pdf`.
- Fuente: https://ceice.gva.es/documents/162909733/414892733/260918_pue_prov.pdf
- SHA256: `23256ce1e01482413d10e60aa1306f55b44544907c443c04a12ecd889b94083b`.
- Fecha interna de publicacion: 17/09/2026. El nombre del archivo corresponde a la convocatoria del dia 18, no a la fecha de publicacion.
- El responsable solicita que se oculten al cambiar de dia: desde el 18/09/2026. Se conserva la regla existente de caducidad diaria, sin modificar aplicaciones ni calendarios.

## Resultado

- 14 paginas, 102 puestos identificados tanto por el extractor principal como por una segunda lectura independiente.
- 33 puestos de Maestros y 69 de otros cuerpos; 48 especialidades.
- 29 vacantes, 44 sustituciones indeterminadas y 29 determinadas.
- 10 puestos con requisito de ingles y 6 itinerantes.
- 100 puestos coinciden con puestos ordinarios pendientes: prevalece dificil cobertura y no se duplican.
- Se conservan otros 4 puestos ordinarios sin cubrir: 106 puestos visibles hoy y 4 tras la caducidad.
- Sin centros desconocidos ni observaciones terminadas en un fragmento de fecha incompleto.
- Cortes, posiciones personales y adjudicaciones ya publicadas permanecen sin cambios.

## Validacion

- 134 pruebas de regresion correctas y validacion estructural de todos los datos de ejecucion.
- El codigo de presentacion existente de Android se prueba con el mismo JSON para los dias 17 y 18: 102 puestos de dificil cobertura hoy, ninguno manana; los 4 ordinarios se conservan.
- El detector de notificaciones existente genera unicamente el nuevo evento de dificil cobertura. No repite los avisos de adjudicaciones continuas, puestos ordinarios ni inicio de curso. El evento de dificil cobertura no se emite el dia siguiente.
- Inspeccion visual de paginas representativas, incluida la separacion de observaciones, requisitos, horas e itinerancia y las fechas completas hasta el 30/06/2027.
