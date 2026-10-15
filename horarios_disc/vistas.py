"""Vistas para el cuaderno: preview semanal, comparación entre versiones y descargas."""
import os

import matplotlib.pyplot as plt
import pandas as pd

from .config import BLOQUES, DIA_CORTO, DIAS, N_H


def grafico_semanal(p, t, columna, valor, titulo):
    """Grilla semanal (bloques x días) de las sesiones donde `columna` contiene/igual `valor` (p. ej. 'Sets', 'ICCI-S6')."""
    sub = t[t[columna].map(lambda z: valor in z if isinstance(z, list) else z == valor)]
    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.set_xlim(0, 5); ax.set_ylim(0, N_H); ax.invert_yaxis()
    ax.set_xticks([i + .5 for i in range(5)]); ax.set_xticklabels(DIAS[:5])
    ax.set_yticks([i + .5 for i in range(N_H)]); ax.set_yticklabels(p.horas_fet, fontsize=8); ax.grid(True, color="#ddd")
    for r in sub.itertuples():
        if r.Dia > 4: continue
        ax.add_patch(plt.Rectangle((r.Dia + .03, r.Hora + .04), .94, r.Dur - .08, color=plt.cm.tab20(r.ClaseId % 20), alpha=.9))
        ax.text(r.Dia + .5, r.Hora + r.Dur / 2, f"{r.Asignatura[:26]}\n{r.Sala or ''}", ha="center", va="center", fontsize=7)
    ax.set_title(titulo); plt.tight_layout(); plt.show()


def preview(p, v, semestre="ICCI-S6", docente=None):
    """Vista previa de una `Version`: un semestre (por defecto) o, con `docente=`, el horario de ese docente."""
    if not docente: return grafico_semanal(p, v.t, "Sets", semestre, f"{v.etq} — {semestre}")
    sub = v.t[v.t.Docentes.str.contains(docente, case=False)]
    grafico_semanal(p, sub, "Docentes", sub.Docentes.iloc[0], f"{v.etq} — {sub.Docentes.iloc[0]}")


def comparar(a, b):
    """Sesiones que cambian de día/bloque/sala entre dos `Version` (a -> b)."""
    ta, tb = a.t.set_index("Id"), b.t.set_index("Id"); filas = []
    fmt = lambda r: f"{DIA_CORTO[DIAS[int(r.Dia)]]} {''.join(BLOQUES[int(r.Hora):int(r.Hora) + int(r.Dur)])} {r.Sala}".strip()
    for i in ta.index:
        if (ta.at[i, "Dia"], ta.at[i, "Hora"], ta.at[i, "Sala"]) != (tb.at[i, "Dia"], tb.at[i, "Hora"], tb.at[i, "Sala"]):
            filas.append({"NRC": ta.at[i, "NRC"], "Asignatura": ta.at[i, "Asignatura"], "Sección": ta.at[i, "Seccion"], "Docente(s)": ta.at[i, "Docentes"],
                          a.etq: fmt(ta.loc[i]), b.etq: fmt(tb.loc[i])})
    return pd.DataFrame(filas)


def comparar_resultados(**resultados):
    """Indicadores de la mejor versión de cada Resultado, lado a lado (p. ej. base vs con restricciones)."""
    filas = {nombre: dict(Versión=r.mejor.etq, **r.mejor.ind) for nombre, r in resultados.items() if r.mejor}
    return pd.DataFrame(filas).T


def descargas(*objs):
    """Enlaces de descarga (o descarga directa en Colab) de Excel: acepta Version, Resultado o rutas."""
    rutas = []
    for o in objs:
        if isinstance(o, str): rutas.append(o)
        elif hasattr(o, "archivos"): rutas += o.archivos
        elif getattr(o, "xlsx", None): rutas.append(o.xlsx)
    try:
        from google.colab import files
        for r in rutas: files.download(r)
    except ImportError:
        from IPython.display import FileLink, display
        for r in rutas: display(FileLink(os.path.relpath(r), result_html_prefix="Descargar: "))


def pedir_archivo(nombre):
    """Colab: abre el selector de archivos. Jupyter/Binder: botón para subir el .xlsx (los datos del cliente no viven en el repositorio)."""
    try:
        from google.colab import files
        for nom, contenido in files.upload().items():
            open(nombre, "wb").write(contenido)
    except ImportError:
        import ipywidgets as w
        from IPython.display import display
        up = w.FileUpload(accept=".xlsx", multiple=False, description="Subir .xlsx")
        def _guardar(_):
            for f in (up.value if not isinstance(up.value, dict) else [dict(name=k, **d) for k, d in up.value.items()]):
                open(nombre, "wb").write(bytes(f["content"])); print("Guardado:", nombre, "-> vuelve a ejecutar la celda")
        up.observe(_guardar, names="value"); display(up)
