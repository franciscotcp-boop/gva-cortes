# Automatizacion de datos de AdjudicApp

GitHub Actions es el unico ejecutor automatico de este proyecto. La automatizacion de Codeberg esta desactivada para evitar consultas duplicadas a la Conselleria.

## Fuentes oficiales

- `adjudicacion3`: adjudicaciones de inicio de curso.
- `resolucion`: adjudicaciones continuas durante el curso.
- `participantes2`: listados anuales de posicion de maestros y de secundaria/otros cuerpos.
- `listados-definitivos`: acreditaciones de ingles B2, C1 y C2 publicadas por provincias.
- `convocatoria-y-peticion-telematica`: ultima relacion de puestos ofertados en las adjudicaciones continuas.

Los lectores aceptan un documento nuevo solo despues de identificar su cuerpo, curso y estructura, procesar el PDF completo y superar controles minimos. Los JSON se escriben primero en un archivo temporal y se sustituyen de forma atomica; una descarga incompleta o un PDF inesperado no reemplaza los datos publicados.

## Calendario de Madrid

- Inicio de curso: julio y agosto, de lunes a sabado, a las 09:20, 12:20, 15:20, 18:20 y 21:20.
- Durante el curso: martes y jueves del 1 de septiembre al 30 de junio, cada media hora de 09:17 a 14:47, mas 15:17, 18:17 y 21:17.
- Posiciones anuales: todos los dias del 1 de junio al 31 de julio, a las 09:20, 11:20, 13:20, 15:20, 17:20 y 19:20.
- Acreditaciones de ingles: todos los viernes del 1 de septiembre al 31 de julio, a las 12:20, 14:20, 16:20, 18:20 y 20:20.
- Puestos ofertados: lunes y miercoles del 1 de septiembre al 1 de julio, cada media hora de 13:07 a 15:37, mas 09:07, 11:07, 17:07, 19:07 y 20:07.
- Dificil cobertura: jueves del 1 de septiembre al 30 de junio, cada media hora de 13:20 a 15:50, mas 09:20, 11:20, 17:20, 19:20, 21:20 y 23:20.
- Limpieza de dificil cobertura caducada: diariamente a las 00:20, de septiembre a junio, sin consultar Conselleria.

El workflow principal expresa sus turnos en `Europe/Madrid`, incluido el cambio de hora. `scripts/automation_schedule.py` reconoce la fuente aunque el evento llegue tarde, hasta 24 horas despues. No reabre temporadas cerradas ni recupera dificil cobertura caducada. GitHub puede retrasar u omitir eventos; estos horarios son los programados, no una garantia de entrega puntual.

## Datos mantenidos

- `data/adjudicaciones.json`: centros y cortes acumulativos de inicio y durante el curso.
- `data/posiciones_bolsa.json`: personas, especialidades, posiciones, estados, detalles de adjudicacion y contexto provincial.
- `data/english_accreditations.json.gz`: acreditaciones acumulativas B2/C1/C2 de ingles, comprimidas porque son datos internos y no los descarga la web.
- `data/position_context_state.json`: historial interno necesario para el contexto provincial.
- `data/source_monitor_state.json`: huellas SHA-256 y fechas de control de las fuentes nuevas.
- `data/puestos_ofertados.json`: ultima instantanea completa de puestos ofertados durante el curso.

La publicacion conserva las URL y el esquema que consumen CodePen y Android. Por eso los cambios de automatizacion no requieren otra web, APK o AAB.

## Reglas importantes

- Durante el curso es acumulativo: una adjudicacion posterior reemplaza a la anterior solo para la misma persona y especialidad.
- En Secundaria y otros cuerpos una adjudicacion cuenta para una especialidad solo cuando coincide la especialidad del encabezado con la especialidad real de la plaza.
- Los listados anuales actualizan personas, orden, especialidades, habilitaciones desactivadas, buscador y etiqueta del curso.
- Las acreditaciones son acumulativas y solo admiten ingles B2, C1 o C2. Al cambiar, se recalculan las posiciones con requisito ingles de las especialidades de maestros compatibles, nunca Ingles (121).
- Cuando hay dos documentos de la misma provincia y fecha, se prioriza la correccion de errores.
- Los puestos ofertados no son acumulativos: un PDF nuevo sustituye por completo al anterior y nunca modifica cortes, posiciones, centros ni acreditaciones.
- Un PDF de puestos de un curso anterior se ignora. Si empieza un curso nuevo sin ofertas publicadas, el JSON queda vacio con el estado de espera correspondiente.

## Vigilante

El workflow `Vigilar adjudicaciones` se activa al terminar el workflow principal, al publicar cambios de automatizacion y cada 15 minutos (minutos 03, 18, 33 y 48 UTC). Aplica el calendario de Madrid y revisa las ultimas 24 horas, tambien despues de medianoche. El pulso del vigilante no implica consultar todas las fuentes en cada ejecucion.

- Cancela una ejecucion que lleve mas de 40 minutos bloqueada; respeta el limite de 35 minutos del procesamiento principal.
- Detecta el primer fallo del workflow principal, incluidos errores de acceso a la Conselleria.
- Recupera las fuentes fallidas o los turnos omitidos con 15 minutos de margen. Comprueba el exito de cada fuente, no solo el color verde del workflow. Una fuente ya comprobada no se vuelve a recuperar.
- Si dificil cobertura fallo y ya cambio el dia de Madrid, recupera la limpieza en lugar de volver a publicar puestos caducados.
- Crea una incidencia asignada al propietario para activar el aviso por correo e informa del resultado.
- Tras un intento fallido, espera 60 minutos antes del siguiente. Una incidencia abierta no bloquea indefinidamente los reintentos; una recuperacion verificada cierra la alerta.
- `generated_at` es informativo y no provoca falsas alarmas cuando no hay documentos nuevos.

El vigilante solo tiene permisos de lectura sobre los datos. Puede administrar Actions e incidencias, pero no puede modificar la web, la app ni los JSON.

Diagnostico y limites de la programacion: [revision del 03/11/2026](docs/automation-recovery-2026-11-03.md). Un resultado manual correcto no demuestra que el siguiente evento programado vaya a llegar a tiempo.

## Ejecucion manual

Desde Actions se puede elegir `auto`, `inicio`, `curso`, `posiciones`, `acreditaciones`, `puestos` o `all`. Para una prueba local:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/update_adjudicaciones.py --force all
python scripts/update_source_data.py --force posiciones
python scripts/update_source_data.py --force acreditaciones
python scripts/update_offered_positions.py
```
