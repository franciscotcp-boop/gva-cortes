# Automatizacion de datos de AdjudicApp

GitHub Actions es el unico ejecutor automatico de este proyecto. La automatizacion de Codeberg esta desactivada para evitar consultas duplicadas a la Conselleria.

## Fuentes oficiales

- `adjudicacion3`: adjudicaciones de inicio de curso.
- `resolucion`: adjudicaciones continuas durante el curso.
- `participantes2`: listados anuales de posicion de maestros y de secundaria/otros cuerpos.
- `listados-definitivos`: acreditaciones de ingles B2, C1 y C2 publicadas por provincias.

Los lectores aceptan un documento nuevo solo despues de identificar su cuerpo, curso y estructura, procesar el PDF completo y superar controles minimos. Los JSON se escriben primero en un archivo temporal y se sustituyen de forma atomica; una descarga incompleta o un PDF inesperado no reemplaza los datos publicados.

## Calendario de Madrid

- Inicio de curso: julio y agosto, de lunes a sabado, a las 09:00, 12:00, 15:00, 18:00 y 21:00.
- Durante el curso: martes y jueves del 1 de septiembre al 30 de junio, a las 09:00, 12:00, 15:00, 18:00 y 21:00.
- Posiciones anuales: todos los dias del 1 de junio al 31 de julio, a las 09:00, 11:00, 13:00, 15:00, 17:00 y 19:00.
- Acreditaciones de ingles: todos los viernes del 1 de septiembre al 31 de julio, a las 12:00, 14:00, 16:00, 18:00 y 20:00.

El cron usa una ventana UTC amplia. `scripts/automation_schedule.py` aplica despues la fecha y hora exactas en `Europe/Madrid`, incluido el cambio de hora.

## Datos mantenidos

- `data/adjudicaciones.json`: centros y cortes acumulativos de inicio y durante el curso.
- `data/posiciones_bolsa.json`: personas, especialidades, posiciones, estados, detalles de adjudicacion y contexto provincial.
- `data/english_accreditations.json.gz`: acreditaciones acumulativas B2/C1/C2 de ingles, comprimidas porque son datos internos y no los descarga la web.
- `data/position_context_state.json`: historial interno necesario para el contexto provincial.
- `data/source_monitor_state.json`: huellas SHA-256 y fechas de control de las fuentes nuevas.

La publicacion conserva las URL y el esquema que consumen CodePen y Android. Por eso los cambios de automatizacion no requieren otra web, APK o AAB.

## Reglas importantes

- Durante el curso es acumulativo: una adjudicacion posterior reemplaza a la anterior solo para la misma persona y especialidad.
- En Secundaria y otros cuerpos una adjudicacion cuenta para una especialidad solo cuando coincide la especialidad del encabezado con la especialidad real de la plaza.
- Los listados anuales actualizan personas, orden, especialidades, habilitaciones desactivadas, buscador y etiqueta del curso.
- Las acreditaciones son acumulativas y solo admiten ingles B2, C1 o C2. Al cambiar, se recalculan las posiciones con requisito ingles de las especialidades de maestros compatibles, nunca Ingles (121).
- Cuando hay dos documentos de la misma provincia y fecha, se prioriza la correccion de errores.

## Vigilante

El workflow `Vigilar adjudicaciones` se ejecuta cada 15 minutos dentro de una ventana horaria amplia y aplica el mismo calendario de Madrid.

- Cancela una ejecucion que lleve mas de 30 minutos bloqueada.
- Detecta el primer fallo del workflow principal, incluidos errores de acceso a la Conselleria.
- Realiza un solo intento de recuperacion con las fuentes que correspondan a esa fecha.
- Crea una incidencia asignada al propietario para activar el aviso por correo e informa del resultado.
- Mientras exista una incidencia abierta no encadena nuevos reintentos; una ejecucion posterior correcta cierra la alerta.
- `generated_at` es informativo y no provoca falsas alarmas cuando no hay documentos nuevos.

El vigilante solo tiene permisos de lectura sobre los datos. Puede administrar Actions e incidencias, pero no puede modificar la web, la app ni los JSON.

## Ejecucion manual

Desde Actions se puede elegir `auto`, `inicio`, `curso`, `posiciones`, `acreditaciones` o `all`. Para una prueba local:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/update_adjudicaciones.py --force all
python scripts/update_source_data.py --force posiciones
python scripts/update_source_data.py --force acreditaciones
```
