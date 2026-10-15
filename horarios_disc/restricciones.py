"""Restricciones agregadas por el usuario sobre un docente o una clase (duras o blandas)."""
from dataclasses import dataclass

from .config import BLOQUES, DIAS
from .etl import norm


@dataclass
class Restriccion:
    """Las sesiones del objetivo deben (dura) o preferentemente deben (blanda) caer en `dias` x `bloques`."""
    objetivo: str            # "docente" | "clase"
    ref: str                 # docente: RUT o parte del nombre | clase: NRC
    dias: list | None = None     # días permitidos/preferidos (None = todos)
    bloques: list | None = None  # bloques A–G permitidos/preferidos (None = todos)
    duro: bool = True
    peso: int = 100          # blandas: 1–99 (% de importancia para el motor)

    def __str__(self):
        d = ",".join(x[:2] for x in self.dias) if self.dias else "todos los días"
        b = "".join(self.bloques) if self.bloques else "todos los bloques"
        modo = "DURA" if self.duro else f"BLANDA {self.peso}%"
        return f"{modo}: {self.objetivo} {self.ref} {'solo en' if self.duro else 'prefiere'} {d} · {b}"


class Restricciones(list):
    """Lista de `Restriccion` con atajos: `r.solo_en(...)` (dura) y `r.preferir(...)` (blanda)."""

    def solo_en(self, objetivo, ref, dias=None, bloques=None):
        self.append(Restriccion(objetivo, str(ref), dias, bloques, True, 100)); return self

    def preferir(self, objetivo, ref, dias=None, bloques=None, peso=70):
        if not 1 <= peso <= 99: raise ValueError("el peso de una restricción blanda debe estar entre 1 y 99")
        self.append(Restriccion(objetivo, str(ref), dias, bloques, False, peso)); return self

    @property
    def duras(self): return [r for r in self if r.duro]

    @property
    def blandas(self): return [r for r in self if not r.duro]


def actividades_de(p, r):
    """Ids de actividad afectados por la restricción; ValueError si el objetivo no existe o es ambiguo."""
    if r.objetivo == "clase":
        ids = [c.ClaseId for c in p.clase_por_id.values() if str(r.ref) in c.NRC.split(" / ")]
        if not ids: raise ValueError(f"NRC {r.ref} no está entre las clases programadas")
    elif r.objetivo == "docente":
        toks = norm(r.ref)
        ruts = [rut for rut, d in p.docentes.items() if rut == str(r.ref).upper() or all(t in norm(d["nombre"]) for t in toks)]
        if len(ruts) != 1:
            raise ValueError(f"docente '{r.ref}': " + ("sin coincidencias" if not ruts else f"ambiguo ({[p.docentes[x]['nombre'] for x in ruts]})"))
        ids = [c.ClaseId for c in p.clase_por_id.values() if any(rut == ruts[0] for rut, _ in c.Docentes)]
    else:
        raise ValueError(f"objetivo desconocido: {r.objetivo}")
    return [a.Id for a in p.acts.itertuples() if a.ClaseId in ids]


def resolver(p, restr):
    """[(Restriccion, [ids de actividad])] — falla pronto si alguna restricción no se refiere a elementos existentes."""
    return [(r, actividades_de(p, r)) for r in (restr or [])]


def sesion_cumple(r, dia, hora, dur):
    """¿La sesión (dia idx, bloque inicial idx, duración) está dentro de lo que pide la restricción?"""
    if r.dias and DIAS[dia] not in r.dias: return False
    return not r.bloques or all(BLOQUES[h] in r.bloques for h in range(hora, hora + dur))


def inicios_permitidos(r, dur, candidatos):
    """Filtra `candidatos` [(dia_idx, hora)] dejando los que cumplen la restricción."""
    return {(d, h) for d, h in candidatos if sesion_cumple(r, d, h, dur)}
