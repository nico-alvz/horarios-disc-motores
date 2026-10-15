"""Casos de uso: generar opciones de horario (con restricciones) y replanificar parcialmente un ramo."""
import datetime as dt
import os
from dataclasses import dataclass, field

import pandas as pd

from .config import BLOQUES, DIA_CORTO, DIAS
from .exportar import exportar_version
from .modelo import escribir_fet, inicios_validos, sets_estudiantes
from .motor import cargar_solucion, generar_corridas, tabla_horario
from .tipos import Version
from .verificacion import referencia_cliente, resumen, verificar


@dataclass
class Resultado:
    """Opciones generadas por una corrida: cada `Version` ya verificada y exportada a Excel."""
    nombre: str
    versiones: dict
    resumen: pd.DataFrame
    carpeta: str
    fet: str
    restr: list = field(default_factory=list)

    def __getitem__(self, etq): return self.versiones[etq]

    @property
    def mejor(self):
        ok = [v for v in self.versiones.values() if v.aprobable and v.rank]
        return min(ok, key=lambda v: v.rank) if ok else None

    @property
    def archivos(self): return [v.xlsx for v in self.versiones.values() if v.xlsx]


def _carpeta(p, nombre):
    if not hasattr(p, "_sesion"): p._sesion = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    d = os.path.join(p.cfg.salida, p._sesion, nombre); os.makedirs(d, exist_ok=True); return d


def _versiones(p, corridas, prefijo, nombre, restr, extra=None):
    vs = {}
    for c in corridas:
        if not c["ok"]: continue
        t = tabla_horario(p, cargar_solucion(p, c["xml"])); viol, ind = verificar(p, t, restr)
        if extra: viol, ind = extra(t, viol, ind)
        etq = f"{prefijo}{c['version']:02d}"
        vs[etq] = Version(etq, t, list(dict.fromkeys(viol)), ind, c, nombre, list(restr or []))
    return vs


def generar(p, nombre="base", restr=None, n=None, prefijo="V", exportar=True):
    """Escribe el .fet, corre fet-cl con `n` semillas, verifica cada solución y exporta a Excel las aprobables."""
    carpeta = _carpeta(p, nombre); fet = os.path.join(carpeta, "problema.fet")
    escribir_fet(p, fet, restr=restr)
    corridas = generar_corridas(p, fet, os.path.join(carpeta, "fet"), n=n, tag=prefijo.lower())
    vs = _versiones(p, corridas, prefijo, nombre, restr)
    if not vs: raise RuntimeError("fet-cl no encontró solución: relaja las restricciones o sube tiempo_limite_s. " + corridas[0]["log"][-200:])
    res = resumen(vs, ref_fila(p))
    if exportar:
        for v in vs.values(): exportar_version(p, v, carpeta)
    return Resultado(nombre, vs, res, carpeta, fet, list(restr or []))


def ref_fila(p):
    """Fila 'Cliente (ref.)' para el resumen: la planilla original pasada por el mismo verificador."""
    r = referencia_cliente(p)
    return r[1] if r else None


def replanificar(p, base, cambios, liberar="relacionadas", n=3, nombre="replan", restr=None, prefijo="R", exportar=True):
    """Fija lo no afectado exactamente como en `base` (Version), aplica `cambios` [dict(nrc=, evitar_horario_actual=, prohibir_dias=,
    solo_dias=, solo_bloques=, sala=)] y regenera `n` alternativas; informa qué sesiones cambiaron respecto de la base."""
    tb = base.t.set_index("Id")
    clases_de = lambda nrc: [c for c in p.clase_por_id.values() if str(nrc) in c.NRC.split(" / ")]
    mod = {}
    for cb in cambios:
        cs = clases_de(cb["nrc"]); assert cs, f"NRC {cb['nrc']} no está entre las clases programadas"
        for c in cs: mod[c.ClaseId] = (c, cb)
    libres = set(mod)
    yr = lambda s: s.split("-S")[0] + "-S" + s.split("-S")[1].split("-")[0]
    if liberar == "relacionadas":
        ruts = {r for c, _ in mod.values() for r, _ in c.Docentes}
        yrs = {yr(s) for c, _ in mod.values() for s in sets_estudiantes(c)}
        for c in p.clase_por_id.values():
            if {r for r, _ in c.Docentes} & ruts or {yr(s) for s in sets_estudiantes(c)} & yrs: libres.add(c.ClaseId)
    fijos = {a.Id: (int(tb.loc[a.Id, "Dia"]), int(tb.loc[a.Id, "Hora"]), tb.loc[a.Id, "Sala"]) for a in p.acts.itertuples() if a.ClaseId not in libres}
    permitidos, forzadas = {}, {}
    for cid, (c, cb) in mod.items():
        for a in p.acts[p.acts.ClaseId == cid].itertuples():
            d0, h0 = int(tb.loc[a.Id, "Dia"]), int(tb.loc[a.Id, "Hora"])
            ok = {(d, h) for d in range(5) for h in inicios_validos(a.Dur)}
            if cb.get("solo_dias"): ok = {(d, h) for d, h in ok if DIAS[d] in cb["solo_dias"]}
            if cb.get("prohibir_dias"): ok = {(d, h) for d, h in ok if DIAS[d] not in cb["prohibir_dias"]}
            if cb.get("solo_bloques"): ok = {(d, h) for d, h in ok if BLOQUES[h] in cb["solo_bloques"]}
            if cb.get("evitar_horario_actual") == "bloque": ok.discard((d0, h0))
            if cb.get("evitar_horario_actual") == "dia": ok = {(d, h) for d, h in ok if d != d0}
            permitidos[a.Id] = ok
            if cb.get("sala"): forzadas[a.Id] = list(cb["sala"])
    carpeta = _carpeta(p, nombre); fet = os.path.join(carpeta, "problema.fet")
    escribir_fet(p, fet, restr=restr, fijos=fijos, permitidos=permitidos, salas_forzadas=forzadas)
    corridas = generar_corridas(p, fet, os.path.join(carpeta, "fet"), n=n, tag=prefijo.lower(), offset=500)

    def extra(t, viol, ind):                       # lo fijado no puede moverse y lo pedido debe cumplirse
        viol = list(viol)
        for r in t.itertuples():
            if r.Id in fijos and (r.Dia, r.Hora, r.Sala) != fijos[r.Id]: viol.append(f"Se movió una asignación fijada: {r.Asignatura} ({r.NRC})")
            if r.Id in permitidos and (r.Dia, r.Hora) not in permitidos[r.Id]: viol.append(f"No se respetó el cambio pedido en {r.Asignatura} ({r.NRC})")
        return viol, ind
    vs = _versiones(p, corridas, prefijo, nombre, restr, extra)
    if not vs: raise RuntimeError("fet-cl no encontró alternativas: usa liberar='relacionadas', menos restricciones o más tiempo_limite_s")
    for v in vs.values():
        filas = []
        for r in v.t.itertuples():
            b = tb.loc[r.Id]
            if (r.Dia, r.Hora, r.Sala) != (b.Dia, b.Hora, b.Sala):
                filas.append({"NRC": r.NRC, "Asignatura": r.Asignatura, "Sección": r.Seccion, "Docente(s)": r.Docentes, "Sesión": r.Sesion,
                              "Antes": f"{DIA_CORTO[DIAS[int(b.Dia)]]} {''.join(BLOQUES[int(b.Hora):int(b.Hora) + r.Dur])} {b.Sala}".strip(),
                              "Ahora": f"{DIA_CORTO[DIAS[r.Dia]]} {''.join(BLOQUES[r.Hora:r.Hora + r.Dur])} {r.Sala}".strip(),
                              "Motivo": "cambio pedido" if r.ClaseId in mod else "reacomodo por el cambio"})
        v.cambios = pd.DataFrame(filas, columns=["NRC", "Asignatura", "Sección", "Docente(s)", "Sesión", "Antes", "Ahora", "Motivo"])
        v.ind = dict(v.ind, **{"Sesiones cambiadas vs base": len(v.cambios), "Clases cambiadas vs base": v.cambios[["NRC", "Sección"]].drop_duplicates().shape[0]})
    res = resumen(vs)
    res["Puntaje (menor = mejor)"] += 2 * res["Sesiones cambiadas vs base"]      # se prefieren pocos cambios respecto de la base
    res["Ranking"] = res["Puntaje (menor = mejor)"].rank(method="min").astype("Int64")
    for etq, v in vs.items(): v.rank = int(res.loc[etq, "Ranking"])
    if exportar:
        for v in vs.values(): exportar_version(p, v, carpeta)
    return Resultado(nombre, vs, res, carpeta, fet, list(restr or []))
