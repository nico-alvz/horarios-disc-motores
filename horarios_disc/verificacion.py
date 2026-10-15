"""Verificador independiente, indicadores y ranking del notebook original."""
import pandas as pd

from .config import BLOQUES, DIA_IDX, DIAS, N_H
from .modelo import salas_candidatas
from .restricciones import resolver, sesion_cumple
from .tipos import Version


def verificar(p, t, restr=None, reglas_de_modelo=True):
    """Devuelve (lista de choques y reglas incumplidas, dict de indicadores)."""
    viol = []
    # completitud: cada actividad del problema aparece exactamente una vez, con su duración
    esperado = p.acts.set_index("Id")["Dur"].to_dict()
    if sorted(t.Id) != sorted(esperado): viol.append(f"Solución incompleta o duplicada: faltan {sorted(set(esperado) - set(t.Id))[:5]}, sobran {sorted(set(t.Id) - set(esperado))[:5]}")
    if any(esperado.get(r.Id) != r.Dur for r in t.itertuples()): viol.append("Duración de una sesión distinta de la esperada")
    ocup_doc, ocup_sala, ocup_est = {}, {}, {}
    for r in t.itertuples():
        for hh in range(r.Hora, r.Hora + r.Dur):
            for rut in r.RUTs:
                ocup_doc.setdefault((rut, r.Dia, hh), []).append(r)
            if r.Sala: ocup_sala.setdefault((r.Sala, r.Dia, hh), []).append(r)
            for st in r.Sets:
                yr = st.split("-")[0] + "-" + st.split("-")[1]
                ocup_est.setdefault((yr, r.Dia, hh), []).append((st, r))
        # reglas por sesión
        if reglas_de_modelo and r.Dia > 4 and not (p.cfg.fijar_sabado and r.DiaCliente == "Sábado"): viol.append(f"Sesión en sábado no permitida: {r.Asignatura} ({r.NRC})")
        if r.Hora <= 2 and r.Hora + r.Dur - 1 >= 3: viol.append(f"Sesión cruza el almuerzo (entre bloques C y D): {r.Asignatura}")
        if r.Hora + r.Dur > N_H: viol.append(f"Sesión se sale del día: {r.Asignatura}")
        if p.clase_por_id[r.ClaseId].SalasCliente and not r.Sala: viol.append(f"Clase sin sala: {r.Asignatura} ({r.NRC})")
        if r.Sala and r.Cupo > p.cap[r.Sala]: viol.append(f"Sobrecupo de sala: {r.Asignatura} (cupo {r.Cupo}) en {r.Sala} (capacidad {p.cap[r.Sala]})")
        if reglas_de_modelo and r.Sala and r.Sala not in salas_candidatas(p, p.clase_por_id[r.ClaseId]): viol.append(f"Sala no permitida por MODO_SALAS: {r.Asignatura} en {r.Sala}")
        if reglas_de_modelo and p.cfg.dias_hora_acotados:
            for rut in r.RUTs:
                d = p.docentes[rut]
                if "Hora" in d["contrato"] and d["dias"] and DIAS[r.Dia] not in d["dias"]:
                    viol.append(f"Profesor hora fuera de sus días: {d['nombre']} el {DIAS[r.Dia]}")
        if reglas_de_modelo and p.cfg.fijar_sabado and r.DiaCliente == "Sábado" and (r.Dia, r.Hora) != (5, r.HoraCliente): viol.append(f"Sábado fijo movido: {r.Asignatura}")
    for (rut, d, h), l in ocup_doc.items():
        if len(l) > 1: viol.append(f"Choque de docente {p.docentes[rut]['nombre']} ({DIAS[d]} {BLOQUES[h]}): " + " vs ".join(sorted({f'{q.Asignatura} {q.Seccion}' for q in l})))
    for (s, d, h), l in ocup_sala.items():
        if len(l) > 1: viol.append(f"Choque de sala {s} ({DIAS[d]} {BLOQUES[h]}): " + " vs ".join(sorted({q.Asignatura for q in l})))
    for (yr, d, h), l in ocup_est.items():
        # dentro de un semestre: choca si hay 2+ actividades y alguna es del nivel del semestre completo,
        # o si dos comparten el mismo subgrupo
        if len(l) > 1:
            nombres = [s for s, _ in l]; ids = {q.Id for _, q in l}
            if len(ids) > 1 and (yr in nombres or len(set(nombres)) < len(nombres)):
                viol.append(f"Choque de estudiantes {yr} ({DIAS[d]} {BLOQUES[h]}): " + " vs ".join(sorted({q.Asignatura for _, q in l})))
    # sesiones de una misma clase en días distintos
    for cid, g in t.groupby("ClaseId"):
        if len(g) > 1 and g.Dia.duplicated().any(): viol.append(f"Dos sesiones el mismo día: {g.iloc[0].Asignatura} ({g.iloc[0].NRC})")

    # ---------------- indicadores de calidad
    huecos = 0
    por_year = {}
    for (yr, d, h), l in ocup_est.items():
        if any(st == yr for st, _ in l): por_year.setdefault((yr, d), []).append(h)
    for hs in por_year.values():
        hs = sorted(hs); huecos += (hs[-1] - hs[0] + 1) - len(hs)
    por_doc = {}
    for (rut, d, h) in ocup_doc: por_doc.setdefault((rut, d), []).append(h)
    ventanas = sum((max(hs) - min(hs) + 1) - len(hs) for hs in por_doc.values())
    dias_por_doc = {}
    for (rut, d) in por_doc: dias_por_doc[rut] = dias_por_doc.get(rut, 0) + 1
    dias_doc = [dias_por_doc.get(r, 0) for r in p.docentes]
    if reglas_de_modelo and p.cfg.max_huecos_semana is not None:
        por_y = {}
        for (yr, d), hs in por_year.items(): por_y[yr] = por_y.get(yr, 0) + (max(hs) - min(hs) + 1) - len(set(hs))
        for yr, n in por_y.items():
            if n > p.cfg.max_huecos_semana: viol.append(f"Tope de bloques libres superado en {yr}: {n} > {p.cfg.max_huecos_semana}")
    if reglas_de_modelo and p.cfg.max_ventanas_docente is not None:
        por_d = {}
        for (rut, d), hs in por_doc.items(): por_d[rut] = por_d.get(rut, 0) + (max(hs) - min(hs) + 1) - len(set(hs))
        for rut, n in por_d.items():
            if n > p.cfg.max_ventanas_docente: viol.append(f"Tope de ventanas superado para {p.docentes[rut]['nombre']}: {n} > {p.cfg.max_ventanas_docente}")
    con_cliente = t[t.DiaCliente.notna()]
    igual = ((con_cliente.Dia.map(lambda i: DIAS[i]) == con_cliente.DiaCliente) & (con_cliente.Hora == con_cliente.HoraCliente)).mean()
    # Se cuentan pares (preferencia, sesión), sin ponderar por el peso de FET.
    preferencias_total = preferencias_incumplidas = 0
    for restriccion, ids in resolver(p, restr):
        for sesion in t[t.Id.isin(ids)].itertuples():
            cumple = sesion_cumple(restriccion, sesion.Dia, sesion.Hora, sesion.Dur)
            if restriccion.duro:
                if not cumple:
                    viol.append(f"Restricción dura incumplida: {restriccion} -> {sesion.Asignatura} ({sesion.NRC})")
            else:
                preferencias_total += 1
                preferencias_incumplidas += int(not cumple)
    viol = list(dict.fromkeys(viol))
    ind = {"Choques": len(viol), "Bloques libres estudiantes": huecos, "Ventanas docentes": ventanas,
           "Días promedio por docente": round(sum(dias_doc) / len(dias_doc), 2),
           "Sesiones en bloques F-G": int((t.Hora >= 5).sum()), "% igual al horario del cliente": round(100 * igual, 1)}
    if any(not r.duro for r in (restr or [])):
        ind["Preferencias incumplidas"] = preferencias_incumplidas
        ind["Preferencias cumplidas %"] = (
            round(100 * (preferencias_total - preferencias_incumplidas) / preferencias_total, 1)
            if preferencias_total else 0.0
        )
    return viol, ind


def detalle_preferencias(p, t, restr):
    """Cumplimiento por preferencia blanda; cada sesión cuenta una vez por preferencia."""
    filas = []
    for r, ids in resolver(p, restr):
        if r.duro:
            continue
        sesiones = t[t.Id.isin(ids)]
        cumplidas = sum(sesion_cumple(r, s.Dia, s.Hora, s.Dur) for s in sesiones.itertuples())
        total = len(sesiones)
        filas.append({"Restricción": str(r), "Sesiones afectadas": total,
                      "Cumplidas": cumplidas, "%": round(100 * cumplidas / total, 1) if total else 0.0})
    return pd.DataFrame(filas, columns=["Restricción", "Sesiones afectadas", "Cumplidas", "%"])


def referencia_cliente(p):
    """Verifica la referencia original cuando todas las actividades tienen horario."""
    from .motor import tabla_horario

    sol = {a.Id: (DIA_IDX[a.DiaCliente], a.BloqueCliente,
                  a.SalaCliente if isinstance(a.SalaCliente, str) else "")
           for a in p.acts.itertuples() if isinstance(a.DiaCliente, str)}
    if len(sol) != len(p.acts):
        return None
    return verificar(p, tabla_horario(p, sol), reglas_de_modelo=False)


def resumen(versiones: dict[str, Version], ref=None):
    """Mismo puntaje y empates del notebook; la referencia no participa del ranking."""
    tabla = pd.DataFrame({etq: v.ind for etq, v in versiones.items()}).T
    if ref is not None:
        indicadores_ref = ref if isinstance(ref, dict) else ref[1]
        if tabla.empty:
            tabla = pd.DataFrame([indicadores_ref], index=["Cliente (ref.)"])
        else:
            tabla.loc["Cliente (ref.)"] = indicadores_ref
    if tabla.empty:
        tabla["Puntaje (menor = mejor)"] = pd.Series(dtype=float)
        tabla["Ranking"] = pd.Series(dtype="Int64")
        return tabla
    puntaje = tabla["Choques"] * 1000 + tabla["Bloques libres estudiantes"] + 0.5 * tabla["Ventanas docentes"]
    if "Preferencias incumplidas" in tabla:
        puntaje = puntaje + tabla["Preferencias incumplidas"].fillna(0)
    tabla["Puntaje (menor = mejor)"] = puntaje
    tabla["Ranking"] = tabla.drop(index="Cliente (ref.)", errors="ignore")["Puntaje (menor = mejor)"].rank(method="min")
    tabla["Ranking"] = tabla["Ranking"].astype("Int64")
    for etq, v in versiones.items():
        v.rank = int(tabla.loc[etq, "Ranking"])
    return tabla


def pruebas_verificador(p, v):
    if not v.aprobable:
        return []
    base = v.t
    casos = {}
    t1 = base.copy(); t1["Sala"] = ""; casos["vaciar todas las salas"] = t1
    casos["eliminar una actividad"] = base.iloc[1:].copy()
    t3 = base.copy(); fila = t3[t3.RUTs.map(len) > 0]
    a_, b_ = fila.iloc[0], fila[fila.RUTs.map(lambda L: L[0]) == fila.iloc[0].RUTs[0]].iloc[-1]
    if a_.Id != b_.Id: t3.loc[t3.Id == b_.Id, ["Dia", "Hora"]] = [a_.Dia, a_.Hora]; casos["mismo docente en dos clases a la vez"] = t3
    t4 = base.copy(); i = t4[(t4.Sala != "")].index[0]; t4.loc[i, "Sala"] = min(p.cap, key=p.cap.get); t4.loc[i, "Cupo"] = 99; casos["sobrecupo de sala"] = t4
    t5 = base.copy(); i = t5[t5.Dur == 1].index[0]; t5.loc[i, "Hora"] = 2; t5.loc[t5.index[t5.Dur == 2][0], "Hora"] = 2; casos["sesión doble cruzando el almuerzo"] = t5
    return [(nombre, bool(verificar(p, tt)[0])) for nombre, tt in casos.items()]
