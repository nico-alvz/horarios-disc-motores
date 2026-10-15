"""Modelo de FET: reglas de dominio y escritura del archivo `.fet` (XML)."""
from xml.sax.saxutils import escape as x

from .config import DIA_IDX, DIAS, FET_VERSION, N_H
from .restricciones import inicios_permitidos, resolver


def inicios_validos(dur):
    """Bloques de inicio permitidos: la sesión cabe en el día y no cruza el almuerzo (entre C y D)."""
    return [h for h in range(N_H - dur + 1) if not (h < 3 < h + dur)]


def nombre_docente(p, rut): return p.docentes[rut]["nombre"]
def nombre_year(pr, s): return f"{pr}-S{s}"


def sets_estudiantes(c):
    if not c.Grupos: return []
    return [nombre_year(pr, s) if c.Seccion == "C1" else f"{nombre_year(pr, s)}-{c.Seccion}" for pr, s in c.Grupos]


def salas_candidatas(p, c):
    if not c.SalasCliente: return []          # p. ej. Práctica Pre-Profesional: sin sala
    if p.cfg.modo_salas == "cliente":
        cand = [s for s in c.SalasCliente if p.cap[s] >= c.Cupo]
        if cand: return cand
        # las salas del cliente no alcanzan (p. ej. cupo 21 en una sala de 20): se buscan otras con capacidad
    return [s for s in p.salas if p.cap[s] >= c.Cupo]     # [] = ninguna sala alcanza: se reporta como choque


def _pref_time(act_id, peso, starts, horas_fet):
    return (f"<ConstraintActivityPreferredStartingTimes>\n\t<Weight_Percentage>{peso}</Weight_Percentage>\n\t<Activity_Id>{act_id}</Activity_Id>\n"
            f"\t<Number_of_Preferred_Starting_Times>{len(starts)}</Number_of_Preferred_Starting_Times>\n"
            + "".join(f"\t<Preferred_Starting_Time>\n\t\t<Day>{DIAS[d]}</Day>\n\t\t<Hour>{horas_fet[h]}</Hour>\n\t</Preferred_Starting_Time>\n" for d, h in sorted(starts))
            + "\t<Active>true</Active>\n\t<Comments></Comments>\n</ConstraintActivityPreferredStartingTimes>\n")


def escribir_fet(p, path, restr=None, fijos=None, permitidos=None, salas_forzadas=None):
    """restr: Restricciones del usuario (duras -> inicios permitidos; blandas -> preferencias con peso).
    fijos: {IdActividad: (dia_idx, hora_idx, sala)} bloqueadas; permitidos: {Id: set((dia_idx, hora))} inicios permitidos;
    salas_forzadas: {Id: [salas]}. Los tres últimos sirven para la replanificación parcial."""
    cfg, acts, clases, DOCENTES = p.cfg, p.acts, p.clases, p.docentes
    fijos, salas_forzadas = fijos or {}, salas_forzadas or {}
    permitidos = {k: set(v) for k, v in (permitidos or {}).items()}
    HORAS_FET = p.horas_fet
    resueltas = resolver(p, restr)
    dur_de = acts.set_index("Id")["Dur"].to_dict()
    for r, ids in resueltas:                       # duras: se intersectan con los inicios permitidos de cada actividad
        if not r.duro: continue
        for i in ids:
            base = permitidos.get(i) or {(d, h) for d in range(5) for h in inicios_validos(dur_de[i])}
            permitidos[i] = inicios_permitidos(r, dur_de[i], base)

    P = []; w = P.append
    w(f'<?xml version="1.0" encoding="UTF-8"?>\n<fet version="{FET_VERSION}">\n<Mode>Official</Mode>\n')
    w(f"<Institution_Name>UCN - DISC - Oferta {cfg.periodo}</Institution_Name>\n<Comments>Generado desde datos cliente.xlsx</Comments>\n")
    w(f"<Days_List>\n<Number_of_Days>{len(DIAS)}</Number_of_Days>\n" + "".join(f"<Day>\n\t<Name>{d}</Name>\n</Day>\n" for d in DIAS) + "</Days_List>\n")
    w(f"<Hours_List>\n<Number_of_Hours>{N_H}</Number_of_Hours>\n" + "".join(f"<Hour>\n\t<Name>{h}</Name>\n</Hour>\n" for h in HORAS_FET) + "</Hours_List>\n")
    asigs = clases.drop_duplicates("Asignatura")
    w("<Subjects_List>\n" + "".join(f"<Subject>\n\t<Name>{x(a)}</Name>\n\t<Comments></Comments>\n</Subject>\n" for a in asigs.Asignatura) + "</Subjects_List>\n")
    w("<Activity_Tags_List>\n</Activity_Tags_List>\n<Buildings_List>\n</Buildings_List>\n")
    w("<Teachers_List>\n")
    for rut, d in DOCENTES.items():
        w(f"<Teacher>\n\t<Name>{x(d['nombre'])} [{rut}]</Name>\n\t<Target_Number_of_Hours>0</Target_Number_of_Hours>\n"
          f"\t<Qualified_Subjects>\n\t</Qualified_Subjects>\n\t<Comments>{x(d['contrato'])}</Comments>\n</Teacher>\n")
    w("</Teachers_List>\n<Rooms_List>\n")
    for s in p.salas:
        w(f"<Room>\n\t<Name>{x(s)}</Name>\n\t<Building></Building>\n\t<Capacity>{p.cap[s]}</Capacity>\n\t<Virtual>false</Virtual>\n\t<Comments></Comments>\n</Room>\n")
    w("</Rooms_List>\n")
    # estudiantes: un Year por (programa, semestre); las secciones paralelas son Groups del Year.
    years = {}
    for _, c in clases.iterrows():
        for pr, s in c.Grupos:
            yr = years.setdefault(nombre_year(pr, s), set())
            if c.Seccion != "C1": yr.add(f"{nombre_year(pr, s)}-{c.Seccion}")
    w("<Students_List>\n")
    for yn in sorted(years):
        w(f"<Year>\n\t<Name>{yn}</Name>\n\t<Number_of_Students>0</Number_of_Students>\n\t<Comments></Comments>\n\t<Number_of_Categories>0</Number_of_Categories>\n\t<Separator> </Separator>\n")
        for g in sorted(years[yn]):
            w(f"\t<Group>\n\t\t<Name>{g}</Name>\n\t\t<Number_of_Students>0</Number_of_Students>\n\t\t<Comments></Comments>\n\t</Group>\n")
        w("</Year>\n")
    w("</Students_List>\n<Activities_List>\n")
    for a in acts.itertuples():
        c = p.clase_por_id[a.ClaseId]
        w("<Activity>\n" + "".join(f"\t<Teacher>{x(nombre_docente(p, r))} [{r}]</Teacher>\n" for r, _ in c.Docentes)
          + f"\t<Subject>{x(c.Asignatura)}</Subject>\n" + "".join(f"\t<Students>{e}</Students>\n" for e in sets_estudiantes(c))
          + f"\t<Duration>{a.Dur}</Duration>\n\t<Total_Duration>{a.TotalDur}</Total_Duration>\n\t<Id>{a.Id}</Id>\n"
          + f"\t<Activity_Group_Id>{a.GrupoId}</Activity_Group_Id>\n\t<Active>true</Active>\n\t<Comments>{x(c.Codigo)}</Comments>\n</Activity>\n")
    w("</Activities_List>\n")

    # ---------------- restricciones de tiempo
    w("<Time_Constraints_List>\n<ConstraintBasicCompulsoryTime>\n\t<Weight_Percentage>100</Weight_Percentage>\n\t<Active>true</Active>\n\t<Comments></Comments>\n</ConstraintBasicCompulsoryTime>\n")
    for a in acts.itertuples():
        if a.Id in fijos:
            d_, h_, _ = fijos[a.Id]
            w(f"<ConstraintActivityPreferredStartingTime>\n\t<Weight_Percentage>100</Weight_Percentage>\n\t<Activity_Id>{a.Id}</Activity_Id>\n"
              f"\t<Day>{DIAS[d_]}</Day>\n\t<Hour>{HORAS_FET[h_]}</Hour>\n\t<Permanently_Locked>false</Permanently_Locked>\n\t<Active>true</Active>\n\t<Comments></Comments>\n</ConstraintActivityPreferredStartingTime>\n")
        elif a.Fijo:
            w(f"<ConstraintActivityPreferredStartingTime>\n\t<Weight_Percentage>100</Weight_Percentage>\n\t<Activity_Id>{a.Id}</Activity_Id>\n"
              f"\t<Day>{a.DiaCliente}</Day>\n\t<Hour>{HORAS_FET[a.BloqueCliente]}</Hour>\n\t<Permanently_Locked>false</Permanently_Locked>\n\t<Active>true</Active>\n\t<Comments></Comments>\n</ConstraintActivityPreferredStartingTime>\n")
        else:
            st = [(d, h) for d in DIAS[:5] for h in inicios_validos(a.Dur)]
            if a.Id in permitidos:
                st = [(d, h) for d, h in st if (DIA_IDX[d], h) in permitidos[a.Id]]
                if not st: raise ValueError(f"Las restricciones dejan sin ningún horario posible a la actividad {a.Id} ({p.clase_por_id[a.ClaseId].Asignatura})")
            w(f"<ConstraintActivityPreferredStartingTimes>\n\t<Weight_Percentage>100</Weight_Percentage>\n\t<Activity_Id>{a.Id}</Activity_Id>\n\t<Number_of_Preferred_Starting_Times>{len(st)}</Number_of_Preferred_Starting_Times>\n"
              + "".join(f"\t<Preferred_Starting_Time>\n\t\t<Day>{d}</Day>\n\t\t<Hour>{HORAS_FET[h]}</Hour>\n\t</Preferred_Starting_Time>\n" for d, h in st)
              + "\t<Active>true</Active>\n\t<Comments></Comments>\n</ConstraintActivityPreferredStartingTimes>\n")
    for cid, g in acts.groupby("ClaseId"):
        if len(g) > 1:
            w(f"<ConstraintMinDaysBetweenActivities>\n\t<Weight_Percentage>100</Weight_Percentage>\n\t<Consecutive_If_Same_Day>true</Consecutive_If_Same_Day>\n\t<Number_of_Activities>{len(g)}</Number_of_Activities>\n"
              + "".join(f"\t<Activity_Id>{i}</Activity_Id>\n" for i in g.Id) + "\t<MinDays>1</MinDays>\n\t<Active>true</Active>\n\t<Comments></Comments>\n</ConstraintMinDaysBetweenActivities>\n")
    if cfg.dias_hora_acotados:
        for rut, d in DOCENTES.items():
            if "Hora" in d["contrato"] and d["dias"]:
                libres = [dd for dd in DIAS if dd not in d["dias"]]
                if libres:
                    w(f"<ConstraintTeacherNotAvailableTimes>\n\t<Weight_Percentage>100</Weight_Percentage>\n\t<Teacher>{x(d['nombre'])} [{rut}]</Teacher>\n"
                      f"\t<Number_of_Not_Available_Times>{len(libres) * N_H}</Number_of_Not_Available_Times>\n"
                      + "".join(f"\t<Not_Available_Time>\n\t\t<Day>{dd}</Day>\n\t\t<Hour>{h}</Hour>\n\t</Not_Available_Time>\n" for dd in libres for h in HORAS_FET)
                      + "\t<Active>true</Active>\n\t<Comments></Comments>\n</ConstraintTeacherNotAvailableTimes>\n")
    if cfg.max_huecos_semana is not None:
        for yn in sorted(years):
            w(f"<ConstraintStudentsSetMaxGapsPerWeek>\n\t<Weight_Percentage>100</Weight_Percentage>\n\t<Max_Gaps>{cfg.max_huecos_semana}</Max_Gaps>\n\t<Students>{yn}</Students>\n\t<Active>true</Active>\n\t<Comments></Comments>\n</ConstraintStudentsSetMaxGapsPerWeek>\n")
    if cfg.max_ventanas_docente is not None:
        w(f"<ConstraintTeachersMaxGapsPerWeek>\n\t<Weight_Percentage>100</Weight_Percentage>\n\t<Max_Gaps>{cfg.max_ventanas_docente}</Max_Gaps>\n\t<Active>true</Active>\n\t<Comments></Comments>\n</ConstraintTeachersMaxGapsPerWeek>\n")
    for r, ids in resueltas:                       # blandas: preferencia de inicio con peso < 100 (la actividad fijada se respeta)
        if r.duro: continue
        for i in ids:
            if i in fijos or bool(acts.set_index("Id").at[i, "Fijo"]): continue
            pref = inicios_permitidos(r, dur_de[i], {(d, h) for d in range(5) for h in inicios_validos(dur_de[i])})
            if pref: w(_pref_time(i, r.peso, pref, HORAS_FET))
    w("</Time_Constraints_List>\n")

    # ---------------- restricciones de espacio
    w("<Space_Constraints_List>\n<ConstraintBasicCompulsorySpace>\n\t<Weight_Percentage>100</Weight_Percentage>\n\t<Active>true</Active>\n\t<Comments></Comments>\n</ConstraintBasicCompulsorySpace>\n")
    for a in acts.itertuples():
        if a.Id in fijos:
            cand = [fijos[a.Id][2]] if fijos[a.Id][2] else []
        else:
            cand = salas_forzadas.get(a.Id) or salas_candidatas(p, p.clase_por_id[a.ClaseId])
        if cand:
            w(f"<ConstraintActivityPreferredRooms>\n\t<Weight_Percentage>100</Weight_Percentage>\n\t<Activity_Id>{a.Id}</Activity_Id>\n\t<Number_of_Preferred_Rooms>{len(cand)}</Number_of_Preferred_Rooms>\n"
              + "".join(f"\t<Preferred_Room>{x(s)}</Preferred_Room>\n" for s in cand) + "\t<Active>true</Active>\n\t<Comments></Comments>\n</ConstraintActivityPreferredRooms>\n")
    w("</Space_Constraints_List>\n<Timetable_Generation_Options_List>\n</Timetable_Generation_Options_List>\n</fet>\n")
    with open(path, "w", encoding="utf-8") as f: f.write("".join(P))
    return path
