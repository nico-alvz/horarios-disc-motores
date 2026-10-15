"""Formulación neutral del problema: un programa lineal binario que todos los motores pueden resolver.

`construir_modelo(p, reglas)` traduce el `Problema` (horarios_disc) y las `Reglas` a:
  - variables binarias: x[actividad, día, bloque inicial, sala] y auxiliares (ocupación, huecos, ...)
  - filas: sum(coef * var) entre lo y hi (tipos 'exo' = exactamente una, 'amo' = a lo más una, 'lin' = general)
  - objetivo lineal a minimizar.
Cada adaptador (CP-SAT, HiGHS, Gurobi, SCIP, MiniZinc) solo traduce esta estructura a su API."""
from dataclasses import dataclass, field

from horarios_disc.config import DIA_IDX, DIAS, N_H
from horarios_disc.modelo import inicios_validos, salas_candidatas, sets_estudiantes
from horarios_disc.restricciones import inicios_permitidos, resolver, sesion_cumple

TIPOS_LAB = {"Laboratorio", "Taller", "Electivo - Taller"}


@dataclass
class ModeloBinario:
    info: list = field(default_factory=list)      # por variable: (act_id, dia, hora, sala) o None si es auxiliar
    obj: dict = field(default_factory=dict)       # índice de variable -> coeficiente
    filas: list = field(default_factory=list)     # (tipo, [índices], [coefs], lo, hi)
    infactible: list = field(default_factory=list)  # actividades sin ningún horario posible (explican un "sin solución")

    @property
    def n(self): return len(self.info)

    def var(self, clave=None):
        self.info.append(clave); return len(self.info) - 1

    def exo(self, v): self.filas.append(("exo", list(v), [1] * len(v), 1, 1))
    def amo(self, v):
        v = list(v)
        if len(v) > 1: self.filas.append(("amo", v, [1] * len(v), None, 1))
    def lin(self, idx, coef, lo=None, hi=None): self.filas.append(("lin", list(idx), list(coef), lo, hi))
    def costo(self, v, w):
        if w: self.obj[v] = self.obj.get(v, 0) + w

    def asignacion(self, valores):
        """{id de actividad: (día, bloque, sala)} a partir del vector de valores 0/1."""
        return {k[0]: (k[1], k[2], k[3]) for j, k in enumerate(self.info) if k is not None and valores[j] > .5}


def construir_modelo(p, reglas):
    cfg = p.cfg
    m = ModeloBinario()
    acts = {a.Id: a for a in p.acts.itertuples()}
    resueltas = resolver(p, reglas.usuario) if reglas.usuario else []
    duras = {}                                   # id actividad -> lista de restricciones duras del usuario
    blandas = {}
    for r, ids in resueltas:
        for i in ids: (duras if r.duro else blandas).setdefault(i, []).append(r)
    por_act, x = {}, {}
    for a in acts.values():
        c = p.clase_por_id[a.ClaseId]
        salas = salas_candidatas(p, c) or [""]
        if reglas.salas_laboratorio and c.Tipo in TIPOS_LAB and (set(salas) & set(reglas.salas_laboratorio)):
            salas = [s for s in salas if s in reglas.salas_laboratorio]                           # H7
        if a.Fijo: slots = [(DIA_IDX[a.DiaCliente], int(a.BloqueCliente))]                      # H10: sábado fijo
        else: slots = [(d, h) for d in range(5) for h in inicios_validos(a.Dur)]               # H8
        for rut, _ in c.Docentes:                                                              # H11
            d_ = p.docentes[rut]
            if reglas.disponibilidad and rut in reglas.disponibilidad:
                if not a.Fijo:
                    disp = reglas.disponibilidad[rut]
                    slots = [(d, h) for d, h in slots if all((d, k) in disp for k in range(h, h + a.Dur))]
            elif cfg.dias_hora_acotados and "Hora" in d_["contrato"] and d_["dias"]:
                slots = [(d, h) for d, h in slots if DIAS[d] in d_["dias"]]
        for r in duras.get(a.Id, []):                                                          # H12
            slots = sorted(inicios_permitidos(r, a.Dur, set(slots)))
        if not slots or not salas: m.infactible.append(a.Id)
        for d, h in slots:
            for s in salas:
                x[a.Id, d, h, s] = v = m.var((a.Id, d, h, s)); por_act.setdefault(a.Id, []).append(v)
    for a in acts.values():
        if a.Id in por_act: m.exo(por_act[a.Id])
    ocup = {}
    for (i, d, h, s), v in x.items():
        a = acts[i]; c = p.clase_por_id[a.ClaseId]
        for k in range(h, h + a.Dur):
            for rut, _ in c.Docentes: ocup.setdefault((("doc", rut), d, k), []).append(v)       # H2
            if s: ocup.setdefault((("sala", s), d, k), []).append(v)                            # H3
            for st in sets_estudiantes(c):                                                      # H4
                yr = "-".join(st.split("-")[:2]); ocup.setdefault((("est", yr, st), d, k), []).append(v)
    est = {}
    for (key, d, k), l in ocup.items():
        if key[0] in ("doc", "sala"): m.amo(l)
        else: est.setdefault((key[1], d, k), {})[key[2]] = l
    for (yr, d, k), g in est.items():
        todo = g.get(yr, [])
        m.amo(todo)
        for st, l in g.items():
            if st != yr: m.amo(l); m.amo(l + todo) if todo else None
    por_clase = {}                                                                              # H9
    for (i, d, h, s), v in x.items(): por_clase.setdefault((acts[i].ClaseId, d), []).append(v)
    for (cid, d), l in por_clase.items():
        if len(p.acts[p.acts.ClaseId == cid]) > 1: m.amo(l)

    def huecos(series, peso, tope):
        """series: {(id, dia): {bloque: [vars]}}; crea ocupación o, prefijo/sufijo y huecos g (lineales)."""
        por_id = {}
        for (ident, d), ks in series.items():
            o = {}
            for k, l in ks.items():
                b = m.var(); o[k] = b; m.lin(list(l) + [b], [1] * len(l) + [-1], 0, 0)          # b = suma(l) (0 o 1)
            pre = [m.var() for _ in range(N_H)]; suf = [m.var() for _ in range(N_H)]
            for k in range(N_H):
                if k and (k - 1) in o: m.lin([o[k - 1], pre[k]], [1, -1], None, 0)
                if k: m.lin([pre[k - 1], pre[k]], [1, -1], None, 0)
                if k < N_H - 1 and (k + 1) in o: m.lin([o[k + 1], suf[k]], [1, -1], None, 0)
                if k < N_H - 1: m.lin([suf[k + 1], suf[k]], [1, -1], None, 0)
            for k in range(1, N_H - 1):
                g = m.var(); idx, co = [pre[k], suf[k], g], [1, 1, -1]
                if k in o: idx.append(o[k]); co.append(-1)
                m.lin(idx, co, None, 1)                                                           # g >= pre + suf - 1 - o
                m.costo(g, peso); por_id.setdefault(ident, []).append(g)
        if tope is not None:
            for gl in por_id.values(): m.lin(gl, [1] * len(gl), None, tope)                       # H13

    sem, doc = {}, {}
    for (key, d, k), l in ocup.items():
        if key[0] == "doc": doc.setdefault((key[1], d), {})[k] = l
    for (yr, d, k), g in est.items():
        if g.get(yr): sem.setdefault((yr, d), {})[k] = g[yr]
    huecos(sem, reglas.w_hueco, reglas.tope_huecos)                                              # S1
    huecos(doc, reglas.w_ventana, reglas.tope_ventanas)                                          # S2
    for (i, d, h, s), v in x.items():
        a = acts[i]; c = p.clase_por_id[a.ClaseId]
        m.costo(v, reglas.w_tarde * sum(1 for k in range(h, h + a.Dur) if k >= 5))              # S3
        if reglas.w_sala and s: m.costo(v, reglas.w_sala * (p.cap[s] - c.Cupo))                  # S10
        for r in blandas.get(i, []):                                                           # S4
            if not sesion_cumple(r, d, h, a.Dur): m.costo(v, r.peso)
    if reglas.w_estabilidad:                                                                    # S5
        for a in acts.values():
            if isinstance(a.DiaCliente, str) and not a.Fijo and a.Id in por_act:
                igual = [v for (i, d, h, s), v in x.items() if i == a.Id and d == DIA_IDX[a.DiaCliente] and h == a.BloqueCliente]
                for (i, d, h, s), v in x.items():
                    if i == a.Id and not (d == DIA_IDX[a.DiaCliente] and h == a.BloqueCliente): m.costo(v, reglas.w_estabilidad)
    return m
