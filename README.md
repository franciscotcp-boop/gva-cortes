# Actualizador de adjudicaciones docentes CV

Este paquete mantiene `data/adjudicaciones.json` actualizado desde las fuentes oficiales de la Conselleria.

## Que contiene

- `data/adjudicaciones.json`: base inicial con centros oficiales, cortes de inicio 2025/2026 y cortes acumulados de durante el curso hasta el 02/06/2026.
- `scripts/update_adjudicaciones.py`: lee las paginas oficiales, descarga PDFs, detecta si son de maestros o de secundaria/otros cuerpos y actualiza el JSON.
- `.github/workflows/update-adjudicaciones.yml`: automatizacion de GitHub Actions.
- `requirements.txt`: dependencia de lectura de PDFs.

## Calendario

- Julio y agosto: revisa `https://ceice.gva.es/es/web/rrhh-educacion/adjudicacion3` cada 4 horas y actualiza la seccion `inicio`.
- Del 1 de septiembre al 30 de junio: revisa `https://ceice.gva.es/es/web/rrhh-educacion/resolucion` los martes y jueves cada 4 horas y actualiza la seccion `curso`.
- Fuera de esas ventanas, el script no consulta las paginas oficiales.

GitHub activa un temporizador simple cada 4 horas. Antes de descargar dependencias o consultar las paginas oficiales, el workflow comprueba el calendario real en la zona `Europe/Madrid`; el script vuelve a validarlo como segunda proteccion. No existe ninguna cadena interna de relanzamientos entre comprobaciones.

## Vigilante de recuperacion

`.github/workflows/watchdog-adjudicaciones.yml` se ejecuta 35 minutos despues de cada comprobacion principal, con un grupo de concurrencia independiente. Solo actua dentro del mismo calendario que el actualizador.

- Comprueba las ejecuciones del workflow principal y `generated_at`.
- Considera bloqueada una ejecucion que lleve mas de 30 minutos en cola o en curso.
- Considera retrasado el JSON cuando `generated_at` supera las 4 horas.
- Cancela la ejecucion bloqueada y solicita una nueva comprobacion.
- Espera el resultado y verifica que `generated_at` vuelva a estar actualizado.
- Crea o actualiza una incidencia dirigida al propietario del repositorio. GitHub envia esa notificacion al correo configurado en la cuenta.

El vigilante hace como maximo un intento de recuperacion por cada ciclo de cuatro horas. Tiene permisos `contents: read`, `actions: write` e `issues: write`; no puede modificar `data/adjudicaciones.json`, la web ni la app. La opcion manual `dry_run` permite comprobar su diagnostico sin cancelar o relanzar nada; `test_alert` verifica el canal de correo sin intervenir en el actualizador.

## Como subirlo

1. Sube todo el contenido de esta carpeta a la raiz de un repositorio de GitHub.
2. En GitHub, entra en `Settings > Actions > General > Workflow permissions` y marca `Read and write permissions`.
3. En la pestana `Actions`, ejecuta manualmente `Actualizar adjudicaciones` una primera vez si quieres comprobar que todo queda operativo.
4. Publica `data/adjudicaciones.json` con GitHub Pages o usa su URL raw. Esa sera la URL que se integrara en la web.

En una ejecucion manual puedes indicar un curso concreto, por ejemplo `2025-2026`. Si lo dejas vacio, el script usa el curso escolar activo segun la fecha de Madrid.

## Formato del JSON

`center_format` describe el orden de columnas de `centers`.

`cut_format` describe el orden de columnas de `cuts.inicio.rows` y `cuts.curso.rows`:

```json
[
  "codigoCentro",
  "codigoEspecialidad",
  "numeroCorte",
  "nombreEspecialidad",
  "nombreCentro",
  "municipio",
  "cuerpo",
  "tipoPlaza",
  "origen"
]
```

En `cuts.curso.rows`, `tipoPlaza` puede ser `sub_indeterminada`, `sub_determinada`, `vacante` o una cadena vacia. `origen` indica si el corte vigente procede de `inicio` o de una adjudicacion de `curso`.

## Ejecucion manual

Desde el repositorio:

```bash
python -m pip install -r requirements.txt
python scripts/update_adjudicaciones.py --force all
```

Tambien se puede forzar solo una parte:

```bash
python scripts/update_adjudicaciones.py --force inicio
python scripts/update_adjudicaciones.py --force curso
python scripts/update_adjudicaciones.py --force all --school-year 2025-2026
```

El script filtra por curso escolar para evitar que se mezclen listados antiguos que aun puedan aparecer enlazados en la pagina oficial.
