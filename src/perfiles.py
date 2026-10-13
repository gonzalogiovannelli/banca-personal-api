"""Lee config/perfiles.yml: qué bancos tenés conectados y cómo se trata cada uno."""
from __future__ import annotations

import sys

import yaml

from src import rutas

_IDS = ("hash", "nativo")


def cargar() -> dict:
    if not rutas.PERFILES.exists():
        sys.exit("Falta %s. Copiá config/perfiles.example.yml y dejá tus bancos." % rutas.PERFILES)
    with open(rutas.PERFILES, encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}
    perfiles = doc.get("perfiles") or {}
    for nombre, p in perfiles.items():
        faltan = [k for k in ("banco", "pais", "fuente", "id") if not p.get(k)]
        if faltan:
            sys.exit("Perfil '%s': faltan %s en %s." % (nombre, ", ".join(faltan), rutas.PERFILES))
        if p["id"] not in _IDS:
            sys.exit("Perfil '%s': id debe ser hash o nativo, no %r." % (nombre, p["id"]))
        p.setdefault("concepto_solo", False)
    fuentes = [p["fuente"] for p in perfiles.values()]
    repetidas = sorted({f for f in fuentes if fuentes.count(f) > 1})
    if repetidas:
        sys.exit("La fuente %s está en más de un perfil. Cada perfil necesita su propia fuente: el rebuild "
                 "de uno reemplazaría los movimientos del otro." % ", ".join(repetidas))
    return perfiles


def uno(nombre: str) -> dict:
    perfiles = cargar()
    if nombre not in perfiles:
        sys.exit("No hay un perfil '%s'. Perfiles: %s." % (nombre, ", ".join(perfiles) or "ninguno"))
    return perfiles[nombre]


def concepto_solo_por_fuente() -> dict:
    """{fuente: concepto_solo}, para que la categorización sepa qué mirar en cada fila."""
    return {p["fuente"]: bool(p["concepto_solo"]) for p in cargar().values()}
