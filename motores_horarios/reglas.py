"""Reglas del horario, declaradas en un solo lugar. Duras = no negociables; blandas = pesos del costo."""
from dataclasses import dataclass, field

import pandas as pd

from horarios_disc.restricciones import Restricciones


@dataclass
class Reglas:
    # ---- blandas: pesos (0 desactiva)
    w_hueco: int = 3            # S1: bloque libre entre clases de un mismo semestre
    w_ventana: int = 2          # S2: ventana en la jornada de un docente
    w_tarde: int = 1            # S3: sesión que comienza en los bloques F o G
    w_estabilidad: int = 0      # S5: por sesión movida respecto del horario original del cliente
    w_sala: int = 0             # S10: por asiento libre (capacidad de sala menos cupo)
    # ---- duras configurables
    sala_libre: bool = False                 # False: solo salas del cliente; True: cualquiera con capacidad suficiente
    tope_huecos: int | None = 2              # H13: máx. bloques libres por semestre (None = sin tope)
    tope_ventanas: int | None = 2            # H13: máx. ventanas por docente (None = sin tope)
    disponibilidad: dict | None = None       # H11: {rut: {(dia, bloque)}}; None = se infiere de los días actuales
    salas_laboratorio: set | None = None     # H7: salas donde pueden ir laboratorios/talleres; None = sin regla
    usuario: Restricciones = field(default_factory=Restricciones)   # H12 y S4: .solo_en(...) / .preferir(...)

    def tabla(self):
        """Resumen legible de las reglas activas, para mostrar tras definirlas."""
        D, B = "dura", "blanda"
        sal = "cualquiera con capacidad" if self.sala_libre else "las del cliente"
        filas = [
            ("H1-H4", D, "Cada actividad se ubica una vez; sin choques de docente, sala ni semestre", True, "siempre", "E/P"),
            ("H5", D, "La capacidad de la sala alcanza para el cupo (cursos compartidos suman cupos)", True, f"salas: {sal}", "E"),
            ("H6", D, "La sesión cabe en el día y no cruza el almuerzo (C y D)", True, "siempre", "P"),
            ("H7", D, "Laboratorios y talleres solo en salas de laboratorio", self.salas_laboratorio is not None,
             f"{len(self.salas_laboratorio)} salas" if self.salas_laboratorio else "-", "B"),
            ("H9", D, "Sesiones de una clase en días distintos; sábado fijo", True, "siempre", "P"),
            ("H11", D, "Docente por hora solo dentro de su disponibilidad", True,
             f"declarada para {len(self.disponibilidad)} docentes" if self.disponibilidad else "inferida de sus días actuales", "E"),
            ("H12", D, "Restricciones duras del usuario", bool(self.usuario.duras), f"{len(self.usuario.duras)}", "P"),
            ("H13", D, "Topes de bloques libres por semestre y de ventanas por docente", self.tope_huecos is not None or self.tope_ventanas is not None,
             f"{self.tope_huecos} / {self.tope_ventanas}", "P"),
            ("S1", B, "Menos bloques libres entre clases de un semestre", self.w_hueco > 0, self.w_hueco, "P"),
            ("S2", B, "Menos ventanas en la jornada de cada docente", self.w_ventana > 0, self.w_ventana, "P"),
            ("S3", B, "Menos sesiones que empiezan en los bloques F o G", self.w_tarde > 0, self.w_tarde, "P"),
            ("S4", B, "Preferencias del usuario (pesos propios 1 a 99)", bool(self.usuario.blandas), f"{len(self.usuario.blandas)}", "E"),
            ("S5", B, "Parecerse al horario original (por sesión movida)", self.w_estabilidad > 0, self.w_estabilidad, "E"),
            ("S10", B, "Desperdiciar pocos asientos de sala (por asiento libre)", self.w_sala > 0, self.w_sala, "B"),
        ]
        return pd.DataFrame(filas, columns=["Id", "Tipo", "Regla", "Activa", "Valor", "Procedencia"])
