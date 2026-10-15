"""Ejecución comparada de motores sobre el mismo problema y las mismas reglas, con verificación independiente."""
import contextlib
import copy
import os
import pickle
import re
import subprocess
import sys
import tempfile

import pandas as pd

from horarios_disc.config import BLOQUES, DIAS
from horarios_disc.verificacion import verificar

from .adaptadores import REGISTRO, Motor, MotorFactory
from .demo import desperdicio, verificar_extras
from .resultado import Resultado


@contextlib.contextmanager
def aplicar(p, reglas):
    """Ajusta temporalmente la configuración del problema según las reglas (el verificador y el modelo leen `p.cfg`)."""
    cfg = p.cfg; antes = copy.copy(cfg)
    cfg.modo_salas = "libre" if reglas.sala_libre else "cliente"
    cfg.dias_hora_acotados = not bool(reglas.disponibilidad)
    cfg.max_huecos_semana, cfg.max_ventanas_docente = reglas.tope_huecos, reglas.tope_ventanas
    try: yield p
    finally:
        for k, v in vars(antes).items(): setattr(cfg, k, v)


def costo_comun(ind):
    return 3 * ind["Bloques libres estudiantes"] + 2 * ind["Ventanas docentes"] + ind["Sesiones en bloques F-G"]


def _evaluar(p, reglas, tabla):
    viol, ind = verificar(p, tabla, reglas.usuario)
    ext = verificar_extras(p, tabla, reglas.disponibilidad, reglas.salas_laboratorio)
    return viol, ind, ext


def _en_proceso(p, reglas, motor, tiempo_s):
    """Cada motor corre en su propio proceso: aísla librerías incompatibles entre sí (OR-Tools y HiGHS), caídas y tiempos."""
    with tempfile.TemporaryDirectory() as d:
        pickle.dump(dict(xlsx=p.xlsx, cfg=p.cfg, reglas=reglas, motor=motor, tiempo_s=tiempo_s), open(f"{d}/e.pkl", "wb"))
        env = dict(os.environ); env["PYTHONPATH"] = os.pathsep.join([x for x in sys.path if x] + [env.get("PYTHONPATH", "")])
        nombre = motor.nombre if isinstance(motor, Motor) else motor
        try:
            pr = subprocess.run([sys.executable, "-m", "motores_horarios._worker", f"{d}/e.pkl", f"{d}/s.pkl"], capture_output=True, text=True,
                                timeout=tiempo_s * 3 + 300, env=env)
        except subprocess.TimeoutExpired:
            return Resultado(nombre, "", "ERROR", nota="el motor no respondió a tiempo")
        if pr.returncode != 0 or not os.path.exists(f"{d}/s.pkl"):
            return Resultado(nombre, "", "ERROR", nota=(pr.stderr.strip().splitlines() or ["falló sin mensaje"])[-1][:200])
        return pickle.load(open(f"{d}/s.pkl", "rb"))


def ejecutar(p, reglas, motores=None, tiempo_s=40, verbose=True):
    """Corre cada motor con las mismas reglas. `motores`: claves de REGISTRO, instancias de Motor o None (todos los disponibles)."""
    claves = motores or [k for k in REGISTRO if MotorFactory(k).disponible()[0]]   # solo comprueba disponibilidad; no importa los solvers a la vez
    out = {}
    with aplicar(p, reglas):
        for k in claves:
            r = _en_proceso(p, reglas, k, tiempo_s)
            tablas = r.tabla if isinstance(r.tabla, list) else ([r.tabla] if r.tabla is not None else [])
            if tablas:
                ev = [(t, *_evaluar(p, reglas, t)) for t in tablas]
                t, viol, ind, ext = min(ev, key=lambda e: (len(e[1]) + len(e[3]), costo_comun(e[2])))
                r.tabla, r.violaciones, r.indicadores, r.extras_violaciones = t, viol + ext, ind, len(ext)
                r.valido, r.costo, r.desperdicio = not (viol or ext), costo_comun(ind), desperdicio(p, t)
            out[r.motor] = r
            if verbose: print(f"{r.motor:24} {r.estado:13} {'' if r.costo is None else 'costo ' + str(int(r.costo)):10} {'' if r.segundos is None else str(r.segundos) + ' s'} {r.nota}")
    return out


def tabla(resultados):
    filas = []
    for r in resultados.values():
        ind = r.indicadores or {}
        filas.append({"Motor": r.motor, "Familia": r.familia, "Estado": r.estado, "Válido": r.valido if r.tabla is not None else None,
                      "Choques": len(r.violaciones) if r.tabla is not None else None, "Huecos": ind.get("Bloques libres estudiantes"),
                      "Ventanas": ind.get("Ventanas docentes"), "F-G": ind.get("Sesiones en bloques F-G"), "Costo": r.costo,
                      "Objetivo": r.objetivo, "Cota": r.cota, "Brecha %": None if r.brecha_pct is None else round(r.brecha_pct, 2),
                      "Asientos libres": r.desperdicio, "Segundos": r.segundos, "Nota": r.nota})
    return pd.DataFrame(filas)


def _codigos(p, anonimizar):
    if not anonimizar: return {rut: d["nombre"] for rut, d in p.docentes.items()}
    return {rut: f"Docente {i:02d}" for i, rut in enumerate(sorted(p.docentes), 1)}


def exportar(resultado, carpeta, p=None, anonimizar=True):
    """Escribe un Excel (4 hojas) y un CSV desde cero. Con `anonimizar` los docentes salen como códigos y no se incluye RUT."""
    if resultado.tabla is None: raise ValueError(f"{resultado.motor} no produjo horario")
    if p is None: raise ValueError("pasa el Problema: exportar(res, carpeta, p=p)")
    os.makedirs(carpeta, exist_ok=True)
    cod = _codigos(p, anonimizar); t = resultado.tabla
    filas = []
    for r in t.itertuples():
        for k in range(1):
            filas.append({"Asignatura": r.Asignatura, "NRC": r.NRC, "Sección": r.Seccion, "Semestres": ", ".join(r.Sets),
                          "Docentes": ", ".join(cod[x] for x in r.RUTs), "Día": DIAS[r.Dia], "Bloque inicial": BLOQUES[r.Hora],
                          "Bloques": r.Dur, "Sala": r.Sala, "Cupo": r.Cupo, "Capacidad sala": p.cap.get(r.Sala) if r.Sala else None})
    df = pd.DataFrame(filas).sort_values(["Día", "Bloque inicial", "Asignatura"])
    grillas = []
    for sem in sorted({s.rsplit("-", 1)[0] if re.search(r"-C\d+$", s) else s for x in t.Sets for s in x}):
        nd = 6 if (t.Dia == 5).any() else 5
        g = {(d, b): [] for d in range(nd) for b in range(7)}
        for r in t.itertuples():
            if any(s == sem or s.startswith(sem + "-") for s in r.Sets):
                for k in range(r.Dur): g[(r.Dia, r.Hora + k)].append(f"{r.Asignatura} ({r.Sala})")
        m = pd.DataFrame([[" / ".join(g[(d, b)]) for d in range(nd)] for b in range(7)], index=list(BLOQUES), columns=DIAS[:nd])
        m.insert(0, "Semestre", sem); grillas.append(m.reset_index(names="Bloque"))
    sal = []
    for r in t.itertuples():
        if r.Sala:
            for k in range(r.Dur): sal.append((r.Sala, DIAS[r.Dia], BLOQUES[r.Hora + k], r.Asignatura))
    sal = pd.DataFrame(sal, columns=["Sala", "Día", "Bloque", "Asignatura"])
    res = pd.DataFrame([("Motor", resultado.motor), ("Estado", resultado.estado), ("Válido", resultado.valido), ("Costo S1-S3", resultado.costo),
                        ("Objetivo", resultado.objetivo), ("Cota", resultado.cota), ("Segundos", resultado.segundos), ("Violaciones", len(resultado.violaciones)),
                        *[(k, v) for k, v in (resultado.indicadores or {}).items()]], columns=["Dato", "Valor"])
    base = os.path.join(carpeta, re.sub(r"[^A-Za-z0-9]+", "_", resultado.motor).strip("_"))
    with pd.ExcelWriter(base + ".xlsx", engine="openpyxl") as w:
        df.to_excel(w, sheet_name="Horario", index=False); pd.concat(grillas).to_excel(w, sheet_name="Por semestre", index=False)
        sal.to_excel(w, sheet_name="Ocupación de salas", index=False); res.to_excel(w, sheet_name="Resumen", index=False)
        w.book.properties.creator = w.book.properties.lastModifiedBy = "Comparación de motores"
        for ws in w.book.worksheets:
            ws.freeze_panes = "A2"
            for col in ws.columns: ws.column_dimensions[col[0].column_letter].width = min(46, max(10, max(len(str(c.value or "")) for c in col[:60]) + 2))
    df.to_csv(base + ".csv", index=False)
    return [base + ".xlsx", base + ".csv"]
