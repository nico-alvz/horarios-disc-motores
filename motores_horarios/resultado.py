"""Resultado homogéneo que devuelve cualquier motor."""
from dataclasses import dataclass, field


@dataclass
class Resultado:
    motor: str
    familia: str = ""                  # "heurístico", "CP", "MIP", "modelado"
    estado: str = "SIN_SOLUCION"       # OPTIMO | FACTIBLE | SIN_SOLUCION | NO_DISPONIBLE | ERROR
    valido: bool = False
    violaciones: list = field(default_factory=list)
    indicadores: dict = field(default_factory=dict)
    costo: float | None = None         # 3*huecos + 2*ventanas + F-G (métrica común, medida por el verificador)
    objetivo: float | None = None      # valor que el motor minimizó (incluye estabilidad, capacidad y preferencias)
    cota: float | None = None
    segundos: float | None = None
    tabla: object = None               # DataFrame de horarios_disc.motor.tabla_horario
    desperdicio: int | None = None
    extras_violaciones: int | None = None
    nota: str = ""

    @property
    def brecha_pct(self):
        if self.objetivo is None or self.cota is None: return None
        return 0.0 if self.objetivo == self.cota else 100 * (self.objetivo - self.cota) / max(abs(self.objetivo), 1e-9)
