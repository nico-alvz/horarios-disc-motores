"""Gráficos del contrato API.md: reciben datos y devuelven Figure, sin show().

El estilo se aplica en un contexto local: no cambia rcParams del cuaderno.
Los gráficos comparativos excluyen soluciones inválidas o sin datos numéricos.
Costo comparable = 3*Huecos + 2*Ventanas + F-G; Objetivo puede incluir otros pesos.
"""
from __future__ import annotations

from functools import wraps
import hashlib
import textwrap

import matplotlib as mpl
from matplotlib import pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm, to_rgba
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd

FONDO = "#0d1116"
SUPERFICIE = "#141a21"
TEXTO = "#e8ecf0"
TENUE = "#9caab7"
ACENTO = "#4fe0b0"
COLORES = {"FET": "#86a3c2", "MINIZINC": "#e0b84f", "GUROBI": "#a99bd0",
           "CP-SAT": ACENTO, "HIGHS": "#72b9df", "SCIP": "#efa77a"}
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
BLOQUES = list("ABCDEFG")
ESTILO = {
    "figure.facecolor": FONDO, "axes.facecolor": SUPERFICIE,
    "savefig.facecolor": FONDO, "text.color": TEXTO, "axes.labelcolor": TENUE,
    "axes.edgecolor": "#34414c", "axes.titleweight": "bold", "axes.titlesize": 14,
    "axes.titlepad": 18, "xtick.color": TENUE, "ytick.color": TENUE,
    "grid.color": "#33414d", "grid.alpha": 0.45, "font.family": "DejaVu Sans",
    "font.size": 10, "legend.facecolor": SUPERFICIE, "legend.edgecolor": "#34414c",
    "figure.dpi": 110, "savefig.dpi": 160,
}


def _estilo(func):
    @wraps(func)
    def aplicar(*args, **kwargs):
        with mpl.rc_context(ESTILO):
            return func(*args, **kwargs)
    return aplicar


def _texto(valor):
    return str(valor).replace(chr(0x2014), "-")


def _color(motor):
    nombre = _texto(motor).upper()
    return next((color for clave, color in COLORES.items() if clave in nombre), ACENTO)


def _fig(titulo, figsize=(11, 5.8)):
    fig, ax = plt.subplots(figsize=figsize, layout="constrained")
    ax.set_title(titulo, loc="left")
    for borde in ("top", "right"):
        ax.spines[borde].set_visible(False)
    return fig, ax


def _vacio(titulo, mensaje):
    fig, ax = _fig(titulo)
    ax.text(0.5, 0.5, mensaje, ha="center", va="center", color=TENUE,
            transform=ax.transAxes, wrap=True)
    ax.set_axis_off()
    return fig


def _datos(df, columnas):
    """Copia el DataFrame para no modificar datos del llamador."""
    df = pd.DataFrame(df).copy()
    if any(c not in df for c in columnas):
        return pd.DataFrame()
    if "Válido" in df:
        df = df[df["Válido"].fillna(False).astype(bool)]
    for c in columnas:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "Motor" not in df:
        df["Motor"] = df.index.map(str)
    df["Motor"] = df["Motor"].map(_texto)
    return df.replace([np.inf, -np.inf], np.nan).dropna(subset=columnas)


def _etiquetas(df):
    return [textwrap.fill(x, 28) for x in df["Motor"]]


@_estilo
def barras_costo(df):
    """Costo comparable S1-S3 de las soluciones válidas, ordenado de menor a mayor."""
    d = _datos(df, ["Costo"])
    if d.empty:
        return _vacio("Costo de horarios válidos", "No hay soluciones válidas con costo disponible.")
    d = d.sort_values("Costo")
    fig, ax = _fig("Costo de horarios válidos", (11, max(4.5, 0.6 * len(d) + 1.6)))
    y = np.arange(len(d))
    ax.barh(y, d["Costo"], color=[_color(n) for n in d["Motor"]], height=0.6)
    ax.set_yticks(y, _etiquetas(d))
    ax.invert_yaxis()
    limite = max(float(d["Costo"].max()), 1)
    for yy, valor in zip(y, d["Costo"]):
        ax.text(valor + limite * 0.02, yy, f"{valor:g}", va="center", color=TEXTO,
                fontfamily="DejaVu Sans Mono")
    ax.set_xlim(0, limite * 1.24)
    ax.set_xlabel("Costo S1-S3 (menor es mejor; pesos comparables 3, 2, 1)")
    ax.xaxis.grid(True)
    ax.set_axisbelow(True)
    return fig


@_estilo
def desglose_costo(df):
    """Barras apiladas de 3*Huecos, 2*Ventanas y F-G, no del objetivo completo."""
    d = _datos(df, ["Huecos", "Ventanas", "F-G"])
    if d.empty:
        return _vacio("De dónde viene el costo", "No hay soluciones válidas con desglose disponible.")
    d["_total"] = 3 * d["Huecos"] + 2 * d["Ventanas"] + d["F-G"]
    d = d.sort_values("_total")
    fig, ax = _fig("De dónde viene el costo", (11, max(4.5, len(d) * 0.6 + 1.8)))
    y, izquierda = np.arange(len(d)), np.zeros(len(d))
    for col, peso, color, etiqueta in (("Huecos", 3, ACENTO, "Huecos x 3"),
                                     ("Ventanas", 2, "#86a3c2", "Ventanas x 2"),
                                     ("F-G", 1, "#e0b84f", "Inicios F-G x 1")):
        valores = d[col].to_numpy() * peso
        ax.barh(y, valores, left=izquierda, color=color, label=etiqueta, height=0.6)
        izquierda += valores
    limite = max(float(izquierda.max()), 1)
    for yy, valor in zip(y, izquierda):
        ax.text(valor + limite * 0.02, yy, f"{valor:g}", va="center")
    ax.set_yticks(y, _etiquetas(d))
    ax.invert_yaxis()
    ax.set_xlim(0, limite * 1.25)
    ax.set_xlabel("Contribución al costo comparable S1-S3")
    ax.legend(loc="lower right")
    ax.xaxis.grid(True)
    ax.set_axisbelow(True)
    return fig


@_estilo
def tiempo_vs_calidad(df):
    """Tiempo reportado frente a costo; tiempos cero o ausentes quedan fuera del log."""
    d = _datos(df, ["Segundos", "Costo"])
    d = d[d["Segundos"] > 0] if not d.empty else d
    if d.empty:
        return _vacio("Tiempo y calidad", "No hay soluciones válidas con tiempo positivo y costo.")
    fig, ax = _fig("Tiempo y calidad")
    for j, (_, row) in enumerate(d.iterrows()):
        ax.scatter(row["Segundos"], row["Costo"], s=95, color=_color(row["Motor"]),
                   edgecolors=FONDO, linewidth=1, zorder=3)
        ax.annotate(row["Motor"], (row["Segundos"], row["Costo"]), xytext=(8, 9 if j % 2 else -16),
                    textcoords="offset points", fontsize=9)
    ax.set_xscale("log")
    ax.set_xlabel("Segundos reportados (escala logarítmica)")
    ax.set_ylabel("Costo comparable S1-S3")
    ax.grid(True, which="both")
    ax.margins(x=0.35, y=0.2)
    fig.supxlabel("Comparar el mismo alcance temporal: el adaptador puede incluir construcción y resolución.",
                  fontsize=9, color=TENUE)
    return fig


@_estilo
def brecha(df):
    """Objetivo y cota interna de motores exactos; no equipara objetivo con costo S1-S3."""
    d = _datos(df, ["Objetivo", "Cota"])
    if not d.empty:
        d = d[~d["Motor"].str.contains("FET", case=False)]
        if "Familia" in d:
            d = d[~d["Familia"].astype(str).str.contains("heur", case=False)]
    if d.empty:
        return _vacio("Objetivo y cota", "No hay cotas disponibles de motores exactos.")
    fig, ax = _fig("Objetivo y cota", (11, max(4.5, len(d) * 0.7 + 1.8)))
    y = np.arange(len(d))
    ax.hlines(y, d["Cota"], d["Objetivo"], color="#607585", linewidth=4)
    ax.scatter(d["Cota"], y, marker="|", s=200, color="#e0b84f", label="Cota inferior", zorder=3)
    ax.scatter(d["Objetivo"], y, s=70, color=ACENTO, label="Objetivo de la solución", zorder=4)
    for yy, (_, row) in zip(y, d.iterrows()):
        ax.annotate(f"  {row['Cota']:g} / {row['Objetivo']:g}", (max(row["Cota"], row["Objetivo"]), yy),
                    xytext=(6, 0), textcoords="offset points", va="center", fontsize=9)
    ax.set_yticks(y, _etiquetas(d))
    ax.invert_yaxis()
    ax.set_xlabel("Valor del objetivo configurado (puede incluir estabilidad o capacidad)")
    ax.margins(x=0.3)
    ax.xaxis.grid(True)
    ax.legend(loc="lower right")
    return fig


def _sesiones(tabla):
    t = pd.DataFrame(tabla).copy()
    requeridas = {"Dia", "Hora", "Dur", "Asignatura"}
    if not requeridas <= set(t):
        return pd.DataFrame()
    for col in ("Dia", "Hora", "Dur"):
        t[col] = pd.to_numeric(t[col], errors="coerce")
    return t.dropna(subset=["Dia", "Hora", "Dur"])


def _pertenece(sets, semestre):
    if not isinstance(sets, (list, tuple, set)):
        return False
    return any(s == semestre or s.startswith(semestre + "-") or semestre.startswith(s + "-") for s in sets)


@_estilo
def grilla_semestre(tabla, semestre):
    """Semana Lu-Vi, A-G, por semestre/subgrupo; conserva simultáneas en carriles.

    Un semestre base reúne sus subgrupos: coincidencias entre paralelos no
    significan automáticamente un choque. Los sábados se cuentan al pie.
    """
    t = _sesiones(tabla)
    if t.empty or "Sets" not in t:
        return _vacio("Horario por semestre", "No hay sesiones con conjuntos de estudiantes.")
    t = t[t["Sets"].map(lambda sets: _pertenece(sets, str(semestre)))]
    fuera = len(t[~t["Dia"].between(0, 4)])
    t = t[t["Dia"].between(0, 4) & t["Hora"].between(0, 6) & (t["Dur"] > 0)]
    if t.empty:
        return _vacio("Horario: " + _texto(semestre), f"No hay sesiones Lu-Vi para este grupo. Fuera de vista: {fuera}.")
    fig, ax = _fig("Horario: " + _texto(semestre), (15, 10))
    pausa = 0.22
    def yy(h):
        return h + (pausa if h >= 3 else 0)
    for d in range(5):
        for h in range(7):
            ax.add_patch(Rectangle((d, yy(h)), 1, 1, facecolor=SUPERFICIE,
                                   edgecolor="#2a3540", linewidth=0.7))
    ax.axhspan(3, 3 + pausa, color=FONDO)
    ax.text(2.5, 3 + pausa / 2, "ALMUERZO", ha="center", va="center", color=TENUE,
            fontsize=8, fontfamily="DejaVu Sans Mono")
    colores = plt.get_cmap("tab20")
    for d in range(5):
        eventos = t[t["Dia"] == d].sort_values(["Hora", "Dur", "Asignatura"])
        finales, asignadas = [], []
        for _, r in eventos.iterrows():
            inicio, fin = int(r.Hora), int(r.Hora + r.Dur)
            lane = next((j for j, end in enumerate(finales) if end <= inicio), len(finales))
            if lane == len(finales):
                finales.append(fin)
            else:
                finales[lane] = fin
            asignadas.append((r, lane))
        n = max(len(finales), 1)
        for r, lane in asignadas:
            inicio, fin = int(r.Hora), min(int(r.Hora + r.Dur), 7)
            ancho = 0.94 / n
            x, y = d + 0.03 + lane * ancho, yy(inicio) + 0.045
            alto = yy(fin - 1) + 1 - yy(inicio) - 0.09
            idx = int.from_bytes(hashlib.blake2b(str(r.Asignatura).encode(), digest_size=2).digest(), "big") % 20
            color = colores(idx)
            ax.add_patch(Rectangle((x, y), ancho - 0.035, alto, facecolor=to_rgba(color, 0.22),
                                   edgecolor=color, linewidth=1.5, joinstyle="round"))
            texto = "\n".join(textwrap.wrap(_texto(r.Asignatura), width=max(12, int(25 / n)))[:3])
            sala = _texto(r.get("Sala", "")) or "Sin sala física"
            ax.text(x + 0.045, y + 0.1, texto + "\n" + sala, va="top", color=TEXTO,
                    fontsize=9 if n == 1 else 7.5, clip_on=True)
    ax.set_xlim(0, 5)
    ax.set_ylim(7 + pausa, 0)
    ax.set_xticks(np.arange(5) + 0.5, DIAS[:5])
    ax.xaxis.tick_top()
    ax.tick_params(axis="both", length=0, pad=10)
    ax.set_yticks([yy(h) + 0.5 for h in range(7)], BLOQUES)
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.supxlabel(f"{len(t)} sesiones Lu-Vi; {fuera} sesiones fuera de esta vista. "
                  "El semestre base incluye paralelos, que pueden coincidir.", fontsize=9, color=TENUE)
    return fig


@_estilo
def ocupacion_salas(tabla):
    """Ocupación por sala y bloque, incluyendo sábado si existe; 2+ señala solape."""
    t = _sesiones(tabla)
    if t.empty or "Sala" not in t:
        return _vacio("Ocupación de salas", "No hay sesiones con sala física.")
    t = t[t["Sala"].fillna("").ne("") & t["Dia"].between(0, 5)]
    if t.empty:
        return _vacio("Ocupación de salas", "No hay sesiones con sala física.")
    salas = sorted(t["Sala"].unique())
    dias = 6 if (t["Dia"] == 5).any() else 5
    ocupacion = np.zeros((len(salas), dias * 7), dtype=int)
    indice = {s: j for j, s in enumerate(salas)}
    for r in t.itertuples():
        for h in range(max(0, int(r.Hora)), min(7, int(r.Hora + r.Dur))):
            ocupacion[indice[r.Sala], int(r.Dia) * 7 + h] += 1
    fig, ax = _fig("Ocupación de salas", (16, max(5, len(salas) * 0.34 + 2)))
    cmap = ListedColormap([SUPERFICIE, ACENTO, "#f38181"])
    imagen = ax.imshow(np.minimum(ocupacion, 2), cmap=cmap, norm=BoundaryNorm([-0.5, 0.5, 1.5, 2.5], 3),
                       aspect="auto", interpolation="nearest")
    ax.set_yticks(range(len(salas)), [_texto(s) for s in salas])
    ax.set_xticks(range(dias * 7), BLOQUES * dias, fontsize=8)
    for d in range(dias):
        ax.text(d * 7 + 3, 1.02, DIAS[d], ha="center", transform=ax.get_xaxis_transform(), color=TEXTO)
        if d:
            ax.axvline(d * 7 - 0.5, color=TENUE, linewidth=0.9)
    for row, col in np.argwhere(ocupacion > 1):
        ax.text(col, row, str(ocupacion[row, col]), ha="center", va="center", color=FONDO, fontsize=8)
    barra = fig.colorbar(imagen, ax=ax, ticks=[0, 1, 2], shrink=0.55, pad=0.02)
    barra.ax.set_yticklabels(["Libre", "1 sesión", "2+ sesiones"])
    ax.set_xlabel("Bloque dentro de cada día")
    return fig


@_estilo
def desperdicio_salas(tabla, cap):
    """Suma capacidad-cupo por sesión con sala; no pondera por duración."""
    t = pd.DataFrame(tabla).copy()
    if not {"Sala", "Cupo"} <= set(t):
        return _vacio("Capacidad sin utilizar", "No hay datos de sala y cupo.")
    t = t[t["Sala"].fillna("").ne("")]
    t["_cap"] = pd.to_numeric(t["Sala"].map(cap), errors="coerce")
    t["_cupo"] = pd.to_numeric(t["Cupo"], errors="coerce")
    desconocidas = int(t["_cap"].isna().sum())
    t = t.dropna(subset=["_cap", "_cupo"])
    if t.empty:
        return _vacio("Capacidad sin utilizar", "No hay capacidades conocidas para las salas utilizadas.")
    t["_libres"] = t["_cap"] - t["_cupo"]
    valores = t.groupby("Sala")["_libres"].sum().sort_values()
    fig, ax = _fig("Capacidad sin utilizar", (11, max(5, len(valores) * 0.36 + 2)))
    y = np.arange(len(valores))
    ax.barh(y, valores, color=[ACENTO if v >= 0 else "#f38181" for v in valores], height=0.68)
    ax.set_yticks(y, [_texto(s) for s in valores.index])
    ax.invert_yaxis()
    ax.set_xlabel("Asientos libres acumulados por sesión (capacidad menos cupo)")
    ax.axvline(0, color=TENUE, linewidth=0.8)
    ax.xaxis.grid(True)
    ax.set_axisbelow(True)
    fig.supxlabel(f"Total: {valores.sum():g}. Sesiones con sobrecupo: {(t['_libres'] < 0).sum()}. "
                  f"Sin capacidad conocida: {desconocidas}.", fontsize=9, color=TENUE)
    return fig


@_estilo
def curva_estabilidad(puntos):
    """Compromiso observado entre parecido y costo; acepta JSON histórico o puntos del cuaderno."""
    d = pd.DataFrame(puntos).copy()
    aliases = {"costo": ["costo_S1S3", "Costo"],
               "pct_igual": ["pct_igual_cliente", "% igual al horario del cliente", "pct_igual"]}
    for target, opciones in aliases.items():
        if target not in d:
            col = next((c for c in opciones if c in d), None)
            if col is not None:
                d[target] = d[col]
    if not {"costo", "pct_igual", "w5"} <= set(d):
        return _vacio("Estabilidad y calidad", "No hay puntos con peso S5, costo y porcentaje de coincidencia.")
    for c in ("costo", "pct_igual", "w5"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.replace([np.inf, -np.inf], np.nan).dropna(subset=["costo", "pct_igual", "w5"])
    if "valido" in d:
        d = d[d["valido"].fillna(False)]
    if "violaciones" in d:
        d = d[d["violaciones"].eq(0)]
    d = d[d["pct_igual"].between(0, 100)].sort_values("pct_igual")
    if d.empty:
        return _vacio("Estabilidad y calidad", "No hay puntos válidos para el gráfico.")
    fig, ax = _fig("Estabilidad y calidad: compromiso observado")
    ax.plot(d["pct_igual"], d["costo"], "o-", color=ACENTO, linewidth=2, markersize=8)
    for j, (_, r) in enumerate(d.iterrows()):
        ax.annotate(f"w5={r['w5']:g}", (r["pct_igual"], r["costo"]),
                    xytext=(7, 10 if j % 2 == 0 else -17), textcoords="offset points", color=TEXTO)
    ax.set_xlim(-2, 105)
    ax.margins(y=0.22)
    ax.set_xlabel("Sesiones con día e inicio iguales al cliente (%)")
    ax.set_ylabel("Costo comparable S1-S3 (menor es mejor)")
    ax.grid(True)
    fig.supxlabel("Cada punto es una ejecución; una curva de puntos no demuestra una frontera de Pareto completa.",
                  fontsize=9, color=TENUE)
    return fig
