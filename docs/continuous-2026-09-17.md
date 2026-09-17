# Adjudicaciones continuas: 17/09/2026

## Fuentes y controles

- Maestros: `260917_lis_mae.pdf`, SHA256 `8e2edc1f265b890bcd17aa6cd3979f320843eca2f5e8a0fb1c11bff000d3db1d`.
- Secundaria: `260917_lis_sec.pdf`, SHA256 `e77aaac6db8f3d271312a2a678af9e117655d28918692755bd897c38370463c3`.
- Ambos documentos proceden de la resolucion del 17/09/2026 y de los archivos aportados por el responsable del proyecto.
- 252 adjudicaciones del cuerpo de Maestros y 211 de Secundaria y otros cuerpos, sin duplicar adjudicaciones repetidas en otras bolsas.
- 463 fichas adjudicadas conciliadas con especialidad, centro, fecha, jornada, tipo de plaza, requisito de ingles e itinerancia.
- 100 adjudicaciones conservan observaciones de los puestos ofertados.
- 567 puestos ofertados anteriores menos 463 cubiertos: 104 permanecen disponibles.
- Sin cambios en los cortes de inicio de curso, posiciones iniciales ni directorio de centros.
- Lectura independiente: 254 bloques Adjudicat en 885 paginas de Maestros y 281 en 1568 paginas de Secundaria; coinciden con los bloques extraidos antes de eliminar repeticiones entre bolsas/cuerpos.
- 134 pruebas de regresion y validacion completa de los JSON.
- Detector real de Android: nuevo evento continuous_results, sin generar evento nuevo de puestos ofertados ni de inicio de curso.

## Casos revisados con el responsable

El PDF repite estos puestos de ambito/programa bajo distintas especialidades de origen. No se ha elegido una bolsa automaticamente. Las decisiones expresas del responsable se guardan en `data/program_assignment_reviews.json` y solo se aplican al SHA256 indicado.

| Puesto | Docente | Bolsa de origen | Orden en esa bolsa | Nota |
| --- | --- | --- | --- | --- |
| 883769 | LLOPIS ENRIQUE, MARIA DEL CARMEN | 207 | 19 | 276 / AMBIT CIENTIFIC |
| 871064 | MAGALLO SANCHEZ, MARIA CRISTINA | 207 | 33 | 276 / AMBIT CIENTIFIC |
| 212420 | SANCHEZ LOPEZ, LUCIA | 203 | 61 | 275 / CULTURA CLASSICA (acentos conservados en los datos) |
| 905381 | HERMOSIN CUQUERELLA, PEDRO | 256 | 276 | 277 / AMBIT SOCIOLINGUISTIC (acentos conservados en los datos) |
| 832674 | GIMENO DOMINGUEZ, FRANCESC XAVIER | 256 | 94 | 277 / AMBIT SOCIOLINGUISTIC (acentos conservados en los datos) |

El parser comprueba conjuntamente documento, puesto, nombre, centro, codigo del programa y que exista exactamente un registro adjudicado en la bolsa elegida. Los numeros se leen de esa bolsa, nunca de otra especialidad.

## Proximos casos ambiguos

Consultar al responsable antes de atribuir una especialidad de origen cuando el PDF no permita resolverla. Facilitar nombre, puesto, centro, programa, paginas y especialidades candidatas. No extrapolar estas cinco decisiones a documentos nuevos ni resolver ambiguedades escogiendo el primer registro o el numero mas bajo. Conservar los datos publicados hasta completar la revision y las validaciones.
