"""Proceso hijo: ejecuta UN motor en aislamiento (OR-Tools y HiGHS no pueden convivir en un mismo proceso).
Uso interno: python -m motores_horarios._worker entrada.pkl salida.pkl"""
import pickle
import sys

from horarios_disc import cargar_problema

from .adaptadores import Motor, MotorFactory
from .comparar import aplicar


def main(ent, sal):
    d = pickle.load(open(ent, "rb"))
    p = cargar_problema(d["xlsx"], d["cfg"])
    k = d["motor"]; m = k if isinstance(k, Motor) else MotorFactory(k)
    with aplicar(p, d["reglas"]):
        r = m.resolver(p, d["reglas"], d["tiempo_s"])
    pickle.dump(r, open(sal, "wb"))


if __name__ == "__main__":
    main(*sys.argv[1:3])
