# Actualizador de adjudicaciones docentes CV

Este paquete mantiene `data/adjudicaciones.json` actualizado desde las fuentes oficiales de la Conselleria.

## Que contiene

- `data/adjudicaciones.json`: base inicial con centros oficiales, cortes de inicio 2025/2026 y cortes acumulados de durante el curso hasta el 02/06/2026.
- `scripts/update_adjudicaciones.py`: lee las paginas oficiales, descarga PDFs, detecta si son de maestros o de secundaria/otros cuerpos y actualiza el JSON.
- `.github/workflows/update-adjudicaciones.yml`: automatizacion de GitHub Actions.
- `requirements.txt`: dependencia de lectura de PDFs.

## Calendario

- Julio y agosto: revisa `https://ceice.gva.es/es/web/rrhh-educacion/adjudicacion3` cada 5 minutos y actualiza la seccion `inicio`.
- Del 1 de septiembre al 30 de junio: revisa `https://ceice.gva.es/es/web/rrhh-educacion/resolucion` los martes y jueves cada 5 minutos y actualiza la seccion `curso`.
- Fuera de esas ventanas, el script no consulta las paginas oficiales.

GitHub programa los horarios en UTC. Por eso el workflow tiene algo de margen y el script comprueba siempre el calendario real en la zona `Europe/Madrid`.

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
