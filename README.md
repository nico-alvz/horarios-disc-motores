# Horarios DISC: válido primero, óptimo si se puede probar

Sitio estático (HTML, CSS y JavaScript sin dependencias ni paso de compilación) con la comparación de motores de optimización de horarios (FET, OR-Tools CP-SAT, MiniZinc y Gurobi) sobre los datos de un departamento universitario.

- `index.html`, `css/`, `js/`, `fonts/`: la página.
- `data/`: resultados y horarios en JSON.
- `descargas/`: cada horario en Excel y CSV.

## Anonimización

Los docentes se reemplazan por códigos (`Docente 01`, ...) y no se publica ningún RUT. Salas, asignaturas, NRC, programas, semestres, bloques y cupos se mantienen sin cambios. Parte de los datos usados en la demostración (disponibilidad de docentes por hora, lista de salas de laboratorio) es inventada o inferida y está señalada como tal en la página.

## Ver localmente

```bash
python -m http.server 8000
# abrir http://localhost:8000
```

## Publicación

GitHub Pages sirve la rama principal desde la raíz del repositorio.

## Cuaderno

`cuaderno/comparar_motores.ipynb` funciona en Google Colab y en local: carga la planilla, declara las reglas y compara los motores (FET, OR-Tools CP-SAT, HiGHS, SCIP, MiniZinc y Gurobi) mediante un patrón adaptador. El paquete `motores_horarios/` define el modelo común y los adaptadores; `horarios_disc/` contiene la lectura de la planilla, FET y el verificador.

[Abrir en Colab](https://colab.research.google.com/github/nico-alvz/horarios-disc-motores/blob/main/cuaderno/comparar_motores.ipynb)

La planilla del cliente no está en este repositorio: se sube al ejecutar el cuaderno.
