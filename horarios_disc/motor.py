"""Motor: localizar/instalar `fet-cl`, ejecutarlo con varias semillas y leer sus soluciones."""
import datetime as dt
import glob
import os
import random
import shutil
import subprocess
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from .config import DIA_IDX, FET_VERSION
from .modelo import sets_estudiantes

URL_FET_CL = f"https://github.com/nico-alvz/fet-mirror/releases/download/v{FET_VERSION}/fet-cl-{FET_VERSION}-linux-x86_64.tar.gz"
_ENV = dict(os.environ, QT_QPA_PLATFORM="offscreen")


def localizar_fet_cl(raiz="."):
    """FET_CL (variable de entorno) > <raiz>/fet-bin/... > PATH. None si no está instalado."""
    cands = [os.environ.get("FET_CL"), os.path.join(raiz, "fet-bin", f"fet-cl-{FET_VERSION}", "bin", "fet-cl"), shutil.which("fet-cl")]
    return next((c for c in cands if c and os.path.isfile(c)), None)


def instalar_fet_cl(raiz="."):
    """Descarga el binario (solo si no está). Llamada explícita: importar el paquete nunca descarga nada."""
    if localizar_fet_cl(raiz): return localizar_fet_cl(raiz)
    d = os.path.join(raiz, "fet-bin"); os.makedirs(d, exist_ok=True)
    tar = os.path.join(d, "fet-cl.tar.gz")
    subprocess.run(["curl", "-sL", "-o", tar, URL_FET_CL], check=True)
    subprocess.run(["tar", "xzf", tar, "-C", d], check=True)
    return localizar_fet_cl(raiz)


def doctor(raiz="."):
    """Diagnóstico de entorno: devuelve (ok, líneas de texto)."""
    import sys
    fet = localizar_fet_cl(raiz); lineas = [f"Python {sys.version.split()[0]}"]
    for m in ("pandas", "openpyxl", "matplotlib"):
        try: lineas.append(f"{m} {__import__(m).__version__}")
        except ImportError: lineas.append(f"{m}: FALTA"); fet = None
    if fet:
        v = subprocess.run([fet, "--version"], capture_output=True, text=True, env=_ENV).stdout.splitlines()
        lineas.append(f"fet-cl: {fet} ({v[0] if v else '?'})")
    else:
        lineas.append("fet-cl: NO encontrado (ejecuta motor.instalar_fet_cl())")
    return fet is not None and "FALTA" not in " ".join(lineas), lineas


def semillas(cfg, i):
    r = random.Random(cfg.semilla_base * 1000 + i)
    return [r.randint(1, 4294967000) for _ in range(3)] + [r.randint(1, 4294944000) for _ in range(3)]


def ejecutar_version(p, fet_input, run_dir, i, tag="v", offset=0, fet_cl=None):
    fet_cl = fet_cl or localizar_fet_cl()
    out = os.path.join(run_dir, f"{tag}{i:02d}"); shutil.rmtree(out, ignore_errors=True); os.makedirs(out)
    s = semillas(p.cfg, i + offset)
    cmd = [fet_cl, f"--inputfile={fet_input}", f"--outputdir={out}", f"--timelimitseconds={p.cfg.tiempo_limite_s}",
           "--writetimetablesxml=true", "--writetimetablesactivities=true", "--writetimetableconflicts=true",
           "--writetimetablesstatistics=false", "--writetimetablesdayshorizontal=false", "--writetimetablesdaysvertical=false",
           "--writetimetablestimehorizontal=false", "--writetimetablestimevertical=false", "--writetimetablessubgroups=false",
           "--writetimetablesgroups=false", "--writetimetablesyears=false", "--writetimetablesteachers=false",
           "--writetimetablesteachersfreeperiods=false", "--writetimetablesbuildings=false", "--writetimetablesrooms=false",
           "--writetimetablessubjects=false", "--writetimetablesactivitytags=false", "--htmllevel=0",
           "--randomseeds10=%d" % s[0], "--randomseeds11=%d" % s[1], "--randomseeds12=%d" % s[2],
           "--randomseeds20=%d" % s[3], "--randomseeds21=%d" % s[4], "--randomseeds22=%d" % s[5]]
    t0 = dt.datetime.now()
    r = subprocess.run(cmd, capture_output=True, text=True, env=_ENV)
    xmls = glob.glob(os.path.join(out, "timetables", "*", "*_activities.xml"))
    return dict(version=i, tag=tag, ok=("Generation successful" in r.stdout) and bool(xmls), seg=(dt.datetime.now() - t0).total_seconds(),
                xml=xmls[0] if xmls else None, semillas=s, log=r.stdout[-400:] + r.stderr[-200:])


def generar_corridas(p, fet_input, run_dir, n=None, tag="v", offset=0):
    """Ejecuta `n` corridas de fet-cl en paralelo (una por semilla) y devuelve la lista de resultados."""
    n = n or p.cfg.n_versiones; fet_cl = localizar_fet_cl()
    if not fet_cl: raise FileNotFoundError("No se encontró fet-cl: ejecuta horarios_disc.motor.instalar_fet_cl()")
    with ThreadPoolExecutor(max_workers=min(n, os.cpu_count() or 2)) as ex:
        return list(ex.map(lambda i: ejecutar_version(p, fet_input, run_dir, i, tag, offset, fet_cl), range(1, n + 1)))


def cargar_solucion(p, xml_path):
    horas_idx = {h: i for i, h in enumerate(p.horas_fet)}
    sol = {}
    for a in ET.parse(xml_path).getroot().findall("Activity"):
        sol[int(a.find("Id").text)] = (DIA_IDX[a.find("Day").text], horas_idx[a.find("Hour").text],
                                       (a.find("Room").text or "") if a.find("Room") is not None else "")
    return sol


def tabla_horario(p, sol):
    """DataFrame con una fila por sesión ubicada."""
    filas = []
    for a in p.acts.itertuples():
        c = p.clase_por_id[a.ClaseId]; d, h, sala = sol[a.Id]
        filas.append(dict(Id=a.Id, ClaseId=a.ClaseId, NRC=c.NRC, Codigo=c.Codigo, Asignatura=c.Asignatura, Seccion=c.Seccion,
                          Programas=c.Programas, Cupo=c.Cupo, Docentes=", ".join(n for _, n in c.Docentes),
                          RUTs=[r for r, _ in c.Docentes], Sets=sets_estudiantes(c), Dia=d, Hora=h, Dur=a.Dur, Sala=sala,
                          DiaCliente=a.DiaCliente, HoraCliente=a.BloqueCliente, Sesion=a.Sesion))
    return pd.DataFrame(filas)
