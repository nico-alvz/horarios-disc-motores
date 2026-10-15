"""Comparación de motores de optimización de horarios con patrón adaptador.
Flujo: cargar problema -> definir `Reglas` -> `ejecutar` con varios motores -> `tabla`, gráficos y `exportar`."""
from .reglas import Reglas
from .resultado import Resultado
from .comparar import ejecutar, tabla, exportar
from .adaptadores import REGISTRO, disponibles

__all__ = ["Reglas", "Resultado", "ejecutar", "tabla", "exportar", "REGISTRO", "disponibles"]
