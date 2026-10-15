"""Datos de DEMOSTRACIÓN (inventados o inferidos; no provienen del cliente)."""
import random

from horarios_disc.config import DIA_IDX, DIAS, N_H

TIPOS_LAB = {"Laboratorio", "Taller", "Electivo - Taller"}


def disponibilidad_sintetica(p, semilla=7):
    """{rut: {(dia, bloque)}} para docentes 'Hora': sus días actuales completos + 1 medio día extra inventado."""
    rnd, disp = random.Random(semilla), {}
    for rut, d in sorted(p.docentes.items()):
        if "Hora" not in d["contrato"] or not d["dias"]: continue
        dias = {DIA_IDX[x] for x in d["dias"] if x in DIA_IDX and DIA_IDX[x] < 5}
        s = {(dd, h) for dd in dias for h in range(N_H)}
        extra = rnd.choice([x for x in range(5) if x not in dias] or [None])
        if extra is not None:
            s |= {(extra, h) for h in (range(0, 3) if rnd.random() < .5 else range(3, N_H))}
        disp[rut] = s
    return disp


def salas_laboratorio(p):
    """Salas donde el cliente ya dicta alguna clase de laboratorio o taller (inferencia, a confirmar)."""
    return {s for _, c in p.clases.iterrows() if c.Tipo in TIPOS_LAB for s in c.SalasCliente}


def verificar_extras(p, t, disp=None, labs=None):
    v = []
    for r in t.itertuples():
        for rut in r.RUTs:
            if disp and r.Dia < 5 and rut in disp and any((r.Dia, k) not in disp[rut] for k in range(r.Hora, r.Hora + r.Dur)):
                v.append(f"Docente por hora fuera de su disponibilidad: {p.docentes[rut]['nombre']} {DIAS[r.Dia]}")
        if labs and p.clase_por_id[r.ClaseId].Tipo in TIPOS_LAB and r.Sala and r.Sala not in labs:
            v.append(f"Clase de laboratorio o taller en sala común: {r.Asignatura} en {r.Sala}")
    return list(dict.fromkeys(v))


def desperdicio(p, t):
    """Suma de (capacidad de la sala menos cupo) sobre las sesiones con sala."""
    return int(sum(p.cap[r.Sala] - r.Cupo for r in t.itertuples() if r.Sala))
