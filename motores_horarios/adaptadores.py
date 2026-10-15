"""Patrón adaptador: cada motor traduce la misma formulación (`ModeloBinario`) a su propia API y devuelve un `Resultado`.

Para agregar un motor: heredar de `MotorLineal`, implementar `disponible()` y `_resolver_modelo(m, tiempo_s)`
y registrarlo en `REGISTRO`. El resto (verificación, tabla comparativa, descargas) no cambia."""
import importlib.util
import os
import shutil
import subprocess
import tempfile
import time
from abc import ABC, abstractmethod

from horarios_disc.motor import tabla_horario

from .modelo import ModeloBinario, construir_modelo
from .resultado import Resultado


class Motor(ABC):
    nombre = ""
    familia = ""

    @abstractmethod
    def disponible(self):
        """(bool, motivo): si el motor puede ejecutarse en este entorno."""

    @abstractmethod
    def resolver(self, p, reglas, tiempo_s=40):
        """Devuelve un `Resultado` con la tabla de horario (sin verificar: lo hace `comparar.ejecutar`)."""

    def _no(self, motivo, estado="NO_DISPONIBLE"):
        return Resultado(self.nombre, self.familia, estado, nota=motivo)


class MotorLineal(Motor):
    """Motores que resuelven el `ModeloBinario`. Subclases implementan `_resolver_modelo`."""

    def resolver(self, p, reglas, tiempo_s=40):
        ok, motivo = self.disponible()
        if not ok: return self._no(motivo)
        t0 = time.time()
        m = construir_modelo(p, reglas)
        if m.infactible:
            return self._no(f"{len(m.infactible)} actividades quedan sin horario posible con estas reglas duras", "SIN_SOLUCION")
        try:
            estado, valores, obj, cota, nota = self._resolver_modelo(m, tiempo_s)
        except Exception as e:                                           # licencia, memoria, API: se informa y se sigue
            return self._no(f"{type(e).__name__}: {str(e)[:160]}", "ERROR")
        r = Resultado(self.nombre, self.familia, estado, objetivo=obj, cota=cota, segundos=round(time.time() - t0, 2), nota=nota)
        if valores is not None:
            r.tabla = tabla_horario(p, m.asignacion(valores))
        return r

    @abstractmethod
    def _resolver_modelo(self, m: ModeloBinario, tiempo_s): ...


def _filas_csr(m):
    """Filas del modelo en formato CSR (inicios, índices, valores, lo, hi) con infinitos explícitos."""
    inf = 1e30
    ini, idx, val, lo, hi = [0], [], [], [], []
    for tipo, v, c, a, b in m.filas:
        idx += v; val += c; ini.append(len(idx))
        lo.append(-inf if a is None else a); hi.append(inf if b is None else b)
    return ini, idx, val, lo, hi


class CPSATMotor(MotorLineal):
    nombre, familia = "OR-Tools CP-SAT", "CP"

    def disponible(self):
        return (importlib.util.find_spec("ortools") is not None), "pip install ortools"

    def _resolver_modelo(self, m, tiempo_s):
        from ortools.sat.python import cp_model
        cm = cp_model.CpModel(); x = [cm.NewBoolVar("") for _ in range(m.n)]
        for tipo, v, c, lo, hi in m.filas:
            if tipo == "exo": cm.AddExactlyOne([x[j] for j in v])
            elif tipo == "amo": cm.AddAtMostOne([x[j] for j in v])
            else:
                e = sum(cc * x[j] for j, cc in zip(v, c))
                if lo is not None and hi is not None and lo == hi: cm.Add(e == lo)
                else:
                    if lo is not None: cm.Add(e >= lo)
                    if hi is not None: cm.Add(e <= hi)
        cm.Minimize(sum(w * x[j] for j, w in m.obj.items()))
        s = cp_model.CpSolver(); s.parameters.max_time_in_seconds = tiempo_s; s.parameters.num_workers = os.cpu_count() or 4
        st = s.Solve(cm)
        if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return ("SIN_SOLUCION", None, None, None, "infactible" if st == cp_model.INFEASIBLE else "sin solución en el tiempo dado")
        return ("OPTIMO" if st == cp_model.OPTIMAL else "FACTIBLE", [s.Value(v) for v in x], s.ObjectiveValue(), s.BestObjectiveBound(), "")


class HiGHSMotor(MotorLineal):
    nombre, familia = "HiGHS (MIP)", "MIP"

    def disponible(self):
        return (importlib.util.find_spec("highspy") is not None), "pip install highspy"

    def _resolver_modelo(self, m, tiempo_s):
        import numpy as np
        import highspy
        h = highspy.Highs(); h.setOptionValue("output_flag", False); h.setOptionValue("time_limit", float(tiempo_s))
        inf = highspy.kHighsInf
        h.addVars(m.n, np.zeros(m.n), np.ones(m.n))
        h.changeColsIntegrality(m.n, np.arange(m.n, dtype=np.int32), np.array([highspy.HighsVarType.kInteger] * m.n))
        costo = np.zeros(m.n)
        for j, w in m.obj.items(): costo[j] = w
        h.changeColsCost(m.n, np.arange(m.n, dtype=np.int32), costo)
        ini, idx, val, lo, hi = _filas_csr(m)
        lo = [-inf if a <= -1e29 else a for a in lo]; hi = [inf if b >= 1e29 else b for b in hi]
        h.addRows(len(lo), np.array(lo), np.array(hi), len(idx), np.array(ini[:-1], dtype=np.int32), np.array(idx, dtype=np.int32), np.array(val, dtype=float))
        h.run()
        st = h.getModelStatus(); info = h.getInfo()
        sol = list(h.getSolution().col_value)
        if info.primal_solution_status != 2:
            return ("SIN_SOLUCION", None, None, None, "infactible" if st == highspy.HighsModelStatus.kInfeasible else "sin solución en el tiempo dado")
        opt = st == highspy.HighsModelStatus.kOptimal
        return ("OPTIMO" if opt else "FACTIBLE", sol, info.objective_function_value, info.mip_dual_bound if not opt else info.objective_function_value, "")


class GurobiMotor(MotorLineal):
    nombre, familia = "Gurobi (MIP)", "MIP"

    def disponible(self):
        return (importlib.util.find_spec("gurobipy") is not None), "pip install gurobipy (la licencia gratuita admite solo 2000 variables)"

    def _resolver_modelo(self, m, tiempo_s):
        import gurobipy as gp
        from gurobipy import GRB
        env = gp.Env(empty=True); env.setParam("OutputFlag", 0); env.start()
        gm = gp.Model(env=env); gm.Params.TimeLimit = tiempo_s
        x = gm.addVars(m.n, vtype=GRB.BINARY)
        for tipo, v, c, lo, hi in m.filas:
            e = gp.LinExpr(c, [x[j] for j in v])
            if lo is not None and hi is not None and lo == hi: gm.addLConstr(e, GRB.EQUAL, lo)
            else:
                if lo is not None: gm.addLConstr(e, GRB.GREATER_EQUAL, lo)
                if hi is not None: gm.addLConstr(e, GRB.LESS_EQUAL, hi)
        gm.setObjective(gp.LinExpr(list(m.obj.values()), [x[j] for j in m.obj]), GRB.MINIMIZE)
        gm.optimize()
        if gm.SolCount == 0: return ("SIN_SOLUCION", None, None, None, "sin solución en el tiempo dado")
        return ("OPTIMO" if gm.Status == GRB.OPTIMAL else "FACTIBLE", [x[j].X for j in range(m.n)], gm.ObjVal, gm.ObjBound, "")

    def resolver(self, p, reglas, tiempo_s=40):
        r = super().resolver(p, reglas, tiempo_s)
        if r.estado == "ERROR" and "size" in r.nota.lower():
            r.estado, r.nota = "NO_DISPONIBLE", "la licencia restringida de gurobipy admite 2000 variables y este modelo es mayor; se requiere licencia académica (WLS)"
        return r


class SCIPMotor(MotorLineal):
    nombre, familia = "SCIP (OR-Tools)", "MIP"

    def disponible(self):
        return (importlib.util.find_spec("ortools") is not None), "pip install ortools (incluye SCIP)"

    def _resolver_modelo(self, m, tiempo_s):
        from ortools.linear_solver import pywraplp
        s = pywraplp.Solver.CreateSolver("SCIP"); s.SetTimeLimit(int(tiempo_s * 1000))
        x = [s.BoolVar("") for _ in range(m.n)]
        for tipo, v, c, lo, hi in m.filas:
            r = s.Constraint(-s.infinity() if lo is None else lo, s.infinity() if hi is None else hi)
            for j, cc in zip(v, c): r.SetCoefficient(x[j], cc)
        o = s.Objective()
        for j, w in m.obj.items(): o.SetCoefficient(x[j], w)
        o.SetMinimization()
        st = s.Solve()
        if st not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE): return ("SIN_SOLUCION", None, None, None, "sin solución en el tiempo dado")
        return ("OPTIMO" if st == pywraplp.Solver.OPTIMAL else "FACTIBLE", [v.solution_value() for v in x], o.Value(), o.BestBound(), "")


_MZN = """% Programa lineal binario generado desde el modelo neutral (patrón adaptador).
int: n; int: m; int: nnz;
array[1..m+1] of int: ptr; array[1..nnz] of int: idx; array[1..nnz] of int: coef;
array[1..m] of int: lo; array[1..m] of int: hi; array[1..n] of int: c;
array[1..n] of var 0..1: x;
constraint forall(r in 1..m)(let { var int: e = sum(k in ptr[r]..ptr[r+1]-1)(coef[k] * x[idx[k]]) } in lo[r] <= e /\\ e <= hi[r]);
solve minimize sum(j in 1..n)(c[j] * x[j]);
"""


class MiniZincMotor(MotorLineal):
    familia = "modelado"

    def __init__(self, solver="cp-sat"):
        self.solver = solver
        self.nombre = f"MiniZinc + {solver}"

    @staticmethod
    def _exe():
        e = shutil.which("minizinc")
        if e: return e
        for base in (os.environ.get("MINIZINC_DIR", ""), os.path.expanduser("~/minizinc")):
            for r, _, fs in os.walk(base) if base else []:
                if "minizinc" in fs and r.endswith("bin"): return os.path.join(r, "minizinc")
        return None

    def disponible(self):
        return (self._exe() is not None), "MiniZinc no está instalado (ver la celda opcional de instalación del cuaderno)"

    def _resolver_modelo(self, m, tiempo_s):
        exe = self._exe(); ini, idx, val, lo, hi = _filas_csr(m)
        big = 10 ** 6
        lo = [-big if a <= -1e29 else int(a) for a in lo]; hi = [big if b >= 1e29 else int(b) for b in hi]
        c = [m.obj.get(j, 0) for j in range(m.n)]
        with tempfile.TemporaryDirectory() as d:
            open(f"{d}/m.mzn", "w").write(_MZN)
            lista = lambda v: "[" + ",".join(map(str, v)) + "]"
            open(f"{d}/d.dzn", "w").write(f"n={m.n};m={len(lo)};nnz={len(idx)};ptr={lista([k + 1 for k in ini])};idx={lista([j + 1 for j in idx])};"
                                           f"coef={lista([int(v) for v in val])};lo={lista(lo)};hi={lista(hi)};c={lista(c)};")
            env = dict(os.environ); bin_dir = os.path.dirname(exe)
            env["LD_LIBRARY_PATH"] = os.path.join(bin_dir, "..", "lib") + ":" + env.get("LD_LIBRARY_PATH", "")
            cmd = [exe, "--solver", self.solver, "--time-limit", str(int(tiempo_s * 1000)), "--output-mode", "dzn", "-s", f"{d}/m.mzn", f"{d}/d.dzn"]
            try: out = subprocess.run(cmd, capture_output=True, text=True, timeout=tiempo_s + 120, env=env).stdout
            except subprocess.TimeoutExpired: return ("SIN_SOLUCION", None, None, None, "tiempo agotado")
        import re
        sols = re.findall(r"x\s*=\s*array1d\(1\.\.\d+,\s*\[([^\]]*)\]\)", out)
        if not sols: return ("SIN_SOLUCION", None, None, None, "sin solución en el tiempo dado")
        valores = [int(v) for v in sols[-1].replace(" ", "").split(",")]
        opt = "==========" in out
        obj = sum(w * valores[j] for j, w in m.obj.items())
        return ("OPTIMO" if opt else "FACTIBLE", valores, obj, obj if opt else None, "")


class FETMotor(Motor):
    """FET es un programa externo con su propio formato (XML): el adaptador escribe el .fet y lee la solución."""
    nombre, familia = "FET", "heurístico"

    def __init__(self, versiones=3):
        self.versiones = versiones

    def disponible(self):
        from horarios_disc.motor import localizar_fet_cl
        try: return (localizar_fet_cl() is not None), "fet-cl no está instalado (horarios_disc.motor.instalar_fet_cl())"
        except Exception as e: return False, str(e)

    def resolver(self, p, reglas, tiempo_s=40):
        import copy
        import xml.etree.ElementTree as ET
        from horarios_disc.config import DIAS, N_H
        from horarios_disc.modelo import escribir_fet
        from horarios_disc.motor import cargar_solucion, generar_corridas
        from .modelo import TIPOS_LAB
        ok, motivo = self.disponible()
        if not ok: return self._no(motivo)
        t0 = time.time(); p2 = copy.copy(p); p2.cfg = copy.copy(p.cfg); p2.cfg.tiempo_limite_s = int(tiempo_s); p2.cfg.n_versiones = self.versiones
        with tempfile.TemporaryDirectory() as d:
            fet = escribir_fet(p2, f"{d}/p.fet", restr=reglas.usuario)
            if reglas.disponibilidad or reglas.salas_laboratorio:
                tree = ET.parse(fet); raiz = tree.getroot(); tc, sc = raiz.find("Time_Constraints_List"), raiz.find("Space_Constraints_List")
                horas = [h.find("Name").text for h in raiz.find("Hours_List").findall("Hour")]
                for rut, disp in (reglas.disponibilidad or {}).items():
                    nodo = ET.SubElement(tc, "ConstraintTeacherNotAvailableTimes")
                    ET.SubElement(nodo, "Weight_Percentage").text = "100"
                    ET.SubElement(nodo, "Teacher").text = f"{p.docentes[rut]['nombre']} [{rut}]"
                    no = [(dd, h) for dd in range(5) for h in range(N_H) if (dd, h) not in disp]
                    ET.SubElement(nodo, "Number_of_Not_Available_Times").text = str(len(no))
                    for dd, h in no:
                        t = ET.SubElement(nodo, "Not_Available_Time"); ET.SubElement(t, "Day").text = DIAS[dd]; ET.SubElement(t, "Hour").text = horas[h]
                    ET.SubElement(nodo, "Active").text = "true"; ET.SubElement(nodo, "Comments").text = ""
                if reglas.salas_laboratorio:
                    for nodo in sc.findall("ConstraintActivityPreferredRooms"):
                        aid = int(nodo.find("Activity_Id").text); c = p.clase_por_id[p.acts.set_index("Id").at[aid, "ClaseId"]]
                        if c.Tipo not in TIPOS_LAB: continue
                        sel = [r.text for r in nodo.findall("Preferred_Room") if r.text in reglas.salas_laboratorio]
                        if sel:
                            for r in nodo.findall("Preferred_Room"): nodo.remove(r)
                            nodo.find("Number_of_Preferred_Rooms").text = str(len(sel))
                            for s in sel:
                                e = ET.Element("Preferred_Room"); e.text = s; nodo.insert(list(nodo).index(nodo.find("Active")), e)
                tree.write(fet, encoding="utf-8", xml_declaration=True)
            corridas = generar_corridas(p2, fet, f"{d}/run", n=self.versiones)
            tablas = [tabla_horario(p, cargar_solucion(p, c["xml"])) for c in corridas if c["ok"]]
        seg = round(time.time() - t0, 2)
        if not tablas: return Resultado(self.nombre, self.familia, "SIN_SOLUCION", segundos=seg, nota="fet-cl no encontró solución")
        r = Resultado(self.nombre, self.familia, "FACTIBLE", segundos=seg, tabla=tablas, nota=f"{len(tablas)} versiones; se conserva la mejor según la métrica común")
        return r


REGISTRO = {
    "fet": FETMotor, "cp-sat": CPSATMotor, "highs": HiGHSMotor, "gurobi": GurobiMotor, "scip": SCIPMotor,
    "minizinc-cp-sat": lambda: MiniZincMotor("cp-sat"), "minizinc-highs": lambda: MiniZincMotor("highs"),
    "minizinc-chuffed": lambda: MiniZincMotor("chuffed"),
}


def disponibles():
    """{clave: (disponible, motivo)} para mostrar qué motores se pueden usar en este entorno."""
    return {k: MotorFactory(k).disponible() for k in REGISTRO}


def MotorFactory(clave):
    return REGISTRO[clave]()
