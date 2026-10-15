"""Tipos compartidos entre motor, verificación, exportación y vistas."""
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Version:
    """Una opción de horario: la solución, su verificación y (cuando existe) su archivo Excel."""
    etq: str                      # "V01", "R02", ...
    t: pd.DataFrame               # una fila por sesión ubicada (ver motor.tabla_horario)
    viol: list                    # choques / reglas incumplidas ([] = aprobable)
    ind: dict                     # indicadores de calidad
    corrida: dict                 # semillas, segundos, xml, log
    escenario: str = ""
    restr: list = field(default_factory=list)   # Restricciones aplicadas al generarla
    cambios: pd.DataFrame | None = None         # solo replanificación: diferencias vs la base
    rank: int | None = None
    xlsx: str | None = None       # ruta del Excel exportado
    csv: str | None = None

    @property
    def aprobable(self): return not self.viol
