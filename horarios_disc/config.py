"""Parámetros editables y constantes del dominio (calendario DISC-UCN)."""
from dataclasses import dataclass

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
DIA_ABR = {"Lu": "Lunes", "Ma": "Martes", "Mi": "Miércoles", "Ju": "Jueves", "Vi": "Viernes", "Sa": "Sábado"}
DIA_CORTO = {v: k for k, v in DIA_ABR.items()}
DIA_IDX = {d: i for i, d in enumerate(DIAS)}
BLOQUES = list("ABCDEFG")
N_H = len(BLOQUES)
ALIAS_SALA = {"V3": "V3-Rob", "V3-ROB-2": "V3-Rob", "V3-ROB": "V3-Rob", "V2-ROB-1": "V2-Rob", "V2-ROB": "V2-Rob",
              "V2-UNI": "V2-Univ", "V2-UNIV": "V2-Univ", "V2-UNIV.": "V2-Univ"}
FET_VERSION = "7.10.5"


@dataclass
class Config:
    n_versiones: int = 3            # opciones de horario por generación
    tiempo_limite_s: int = 40       # segundos máximos de fet-cl por versión
    semilla_base: int = 2026        # misma semilla base => mismas versiones
    modo_salas: str = "cliente"     # "cliente": solo salas ya asignadas | "libre": cualquiera con capacidad
    dias_hora_acotados: bool = True  # profesores hora: solo los días en que hoy ya dictan
    fijar_sabado: bool = True       # sesiones de sábado fijas
    max_huecos_semana: int | None = 2      # tope duro de bloques libres por semestre (None = sin tope)
    max_ventanas_docente: int | None = 2   # tope duro de ventanas por docente (None = sin tope)
    periodo: str = "2026-20"
    salida: str = "salida_horarios"  # carpeta raíz de las descargas
