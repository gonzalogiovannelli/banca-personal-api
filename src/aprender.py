"""Aprender de tus correcciones.

Corregís en datos/movimientos.csv: cambiás la `categoria` de una fila. El sistema sabe que la
cambiaste porque deja de coincidir con `categoria_sistema`, que es lo que él había puesto.

En cada corrida:
  1. Toda fila corregida se guarda como corrección puntual por id en reglas/correcciones.yml, y queda
     con origen manual: ya no la pisa nada.
  2. Si además pusiste `si` en la columna `aprender`, se aprende la REGLA contraparte -> categoría
     (se agrega arriba en reglas/categorias.yml, así gana sobre las más generales), y se avisa si
     choca con una regla existente.
  3. La columna `aprender` se vacía en las filas ya procesadas.

Uso:
  python -m src.aprender            # muestra qué detectó, sin guardar
  python -m src.aprender --write    # guarda
"""
from __future__ import annotations

import sys

import yaml

from src import movimientos, rutas
from src.categorizar import (CORRECCIONES_PATH, canonizar, cargar_correcciones, cargar_reglas,
                             guardar_reglas, norm)

_SI = {"si", "sí", "x", "true", "1", "yes"}


def aprender(write: bool = False) -> dict:
    reglas = cargar_reglas()
    correcciones = cargar_correcciones()
    filas = movimientos.leer()
    nuevas_corr, nuevas_reglas, choques, a_resetear = {}, [], [], []

    for r in filas:
        quiere = r["aprender"].strip().lower() in _SI
        corregida = r["categoria"].strip() and r["categoria"] != r["categoria_sistema"]
        if not corregida and not quiere:
            continue
        if quiere:
            a_resetear.append(r)
        if corregida:
            nuevas_corr[r["id"]] = r["categoria"].strip()
        if quiere and r["categoria"].strip():
            clave = norm(r["contraparte"])
            if not clave:
                choques.append("%s: no tiene contraparte, no hay de qué aprender una regla" % r["id"])
                continue
            existente = next((f for f in reglas["keywords"] if norm(f[0]) == clave), None)
            if existente:
                if existente[2] != r["categoria"].strip():
                    choques.append("%r ya tiene la regla -> %s y pediste %s: no se cambió. Editala en "
                                   "reglas/categorias.yml si querés que cambie." % (clave, existente[2], r["categoria"]))
                continue
            if any(norm(n[0]) == clave for n in nuevas_reglas):
                continue
            exacta = {norm(k): v for k, v in reglas["contraparte_exacta"].items()}.get(clave)
            if exacta and exacta != r["categoria"].strip():
                choques.append("%r está en contraparte_exacta -> %s, que gana sobre cualquier keyword: la "
                               "regla nueva no tendría efecto. No se aprendió; cambiá la exacta." % (clave, exacta))
                continue
            for palabra, _, cat in (f[:3] for f in reglas["keywords"]):
                if (norm(palabra) in clave or clave in norm(palabra)) and cat != r["categoria"]:
                    choques.append("%r (-> %s) se solapa con la regla %r (-> %s)"
                                   % (clave, r["categoria"], palabra, cat))
            nuevas_reglas.append([clave, canonizar(r["contraparte"].strip(), reglas), r["categoria"].strip()])

    print("Correcciones: %d | reglas a aprender: %d | avisos: %d"
          % (len(nuevas_corr), len(nuevas_reglas), len(choques)))
    for idt, c in list(nuevas_corr.items())[:10]:
        print("  corrección %s -> %s" % (idt, c))
    for clave, _, c in nuevas_reglas[:10]:
        print("  regla      %s -> %s" % (clave, c))
    for c in choques:
        print("  AVISO      " + c)
    if not write:
        print("(no se guardó nada; agregá --write)")
        return {"correcciones": nuevas_corr, "reglas": nuevas_reglas, "choques": choques}

    if nuevas_corr:
        correcciones.update(nuevas_corr)
        rutas.escribir_atomico(CORRECCIONES_PATH,
                               "# Correcciones puntuales por id de movimiento (id -> categoría). Las escribe aprender.\n"
                               + yaml.safe_dump(correcciones, allow_unicode=True, sort_keys=True))
    if nuevas_reglas:
        reglas["keywords"] = nuevas_reglas + reglas["keywords"]   # específicas arriba
        guardar_reglas(reglas)
    for r in filas:
        if r["id"] in nuevas_corr:
            r.update(origen_categoria="manual", confianza="1.0", categoria_sistema=r["categoria"])
    for r in a_resetear:
        r["aprender"] = ""
    movimientos.escribir(filas)
    print("Guardado. Corré `python -m src.categorizar aplicar` para que las reglas nuevas alcancen al resto.")
    return {"correcciones": nuevas_corr, "reglas": nuevas_reglas, "choques": choques}


if __name__ == "__main__":
    aprender(write="--write" in sys.argv[1:])
