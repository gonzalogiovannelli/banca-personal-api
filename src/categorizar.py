"""Categorización: reglas con puntaje de confianza, una pasada de IA para lo que las reglas no
resuelven, y tus correcciones, que mandan sobre todo.

Orden de las reglas (devuelve categoria, confianza, origen):
  1. reglas_concepto   1.0  "regla-concepto"  regex sobre el concepto. Manda sobre la contraparte: la
                                              comisión de un banco no es un gasto en ese banco
  2. contraparte_exacta 1.0 "base-exacta"
  3. keywords          0.9  "regla-keyword"   la primera que aparezca en el texto gana
  4. nada              0.0  "sin-match"       queda para la IA o para vos

Las reglas viven en reglas/categorias.yml y tus correcciones puntuales en reglas/correcciones.yml.

Qué NO se pisa nunca: una fila con origen manual o IA que ya tenga categoría, ni una que corregiste a
mano en el CSV (su categoria ya no coincide con categoria_sistema) aunque todavía no corriste aprender.

CLI:
  python -m src.categorizar aplicar                 # categoriza lo nuevo de la tabla
  python -m src.categorizar pendientes [archivo]    # lo que las reglas no resuelven, en JSON, para la IA
  python -m src.categorizar ia-aplicar <archivo>    # escribe lo que clasificó la IA
  python -m src.categorizar conflictos              # reglas que se contradicen
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata

import yaml

from src import movimientos, perfiles, rutas

REGLAS_PATH = rutas.REGLAS / "categorias.yml"
CORRECCIONES_PATH = rutas.REGLAS / "correcciones.yml"
UMBRAL_IA = 0.85   # por debajo, la clasificación de la IA queda marcada para revisar


def cargar_reglas(path=None) -> dict:
    with open(path or REGLAS_PATH, encoding="utf-8") as f:
        reglas = yaml.safe_load(f) or {}
    for k in ("alias", "reglas_concepto", "contraparte_exacta", "keywords", "conflictos_aceptados"):
        reglas.setdefault(k, {} if k in ("alias", "contraparte_exacta", "conflictos_aceptados") else [])
    return reglas


CABECERA_REGLAS = """# Reglas de categorización. Ver el README y src/categorizar.py.
#
# categorias:          la lista de categorías válidas. La IA solo puede usar estas sin quedar marcada
# alias:               variantes de un mismo nombre -> el nombre canónico (una contraparte, un nombre)
# reglas_concepto:     regex sobre el concepto (en mayúsculas y SIN tildes: "comision", no "comisión"). Gana sobre todo lo demás
# contraparte_exacta:  contraparte exacta -> categoría
# keywords:            [palabra, contraparte_limpia, categoria]. ORDEN = PRIORIDAD: la primera que aparece gana
# conflictos_aceptados: palabra -> por qué está bien que choque con otra regla
#
# Este archivo lo reescribe `aprender`: los comentarios que agregues a mano se pierden. Los motivos van
# en conflictos_aceptados.

"""


def guardar_reglas(reglas: dict, path=None):
    rutas.escribir_atomico(path or REGLAS_PATH, CABECERA_REGLAS + yaml.safe_dump(
        reglas, allow_unicode=True, sort_keys=False, width=200))


def cargar_correcciones(path=None) -> dict:
    p = path or CORRECCIONES_PATH
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def norm(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "")).strip().upper()
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def canonizar(contraparte: str, reglas: dict) -> str:
    """Una contraparte, un nombre: 'ACME S.L.' y 'TRANSFERENCIA ACME' son el mismo cliente.
    Sin esto el mismo cliente queda partido en dos y los totales por contraparte cuentan de menos."""
    m = norm(contraparte)
    if not m:
        return contraparte or ""
    for k, v in (reglas.get("alias") or {}).items():
        if norm(k) == m:
            return v
    return contraparte


def categorizar(contraparte: str, concepto: str, reglas: dict, concepto_solo: bool = False) -> tuple:
    """-> (categoria | None, confianza, origen, contraparte_limpia).

    concepto_solo (bancos sin contraparte estructurada, como los de Redsys): las reglas miran SOLO el
    concepto, porque la contraparte se dedujo de ese mismo texto y no aporta señal nueva."""
    contraparte = canonizar(contraparte, reglas)
    texto = norm(concepto) if concepto_solo else norm(contraparte + " " + concepto)
    m = norm(contraparte)

    solo_concepto = norm(concepto)
    for r in reglas["reglas_concepto"]:   # solo el concepto, en mayúsculas y sin tildes
        if re.search(r["regex"], solo_concepto, re.IGNORECASE):
            return r["categoria"], 1.0, "regla-concepto", ""

    exactas = reglas["contraparte_exacta"]
    if concepto_solo:
        for clave in sorted(exactas, key=len, reverse=True):   # las más específicas primero
            if clave and norm(clave) in texto:
                return exactas[clave], 1.0, "base-exacta", ""
    else:
        normalizadas = {norm(k): v for k, v in exactas.items()}
        if m and m in normalizadas:
            # se devuelve la contraparte tal cual: si coincidió exacta, ya está limpia. Devolver ""
            # haría que la corrida siguiente leyera otro texto y la categoría oscilara entre corridas.
            return normalizadas[m], 1.0, "base-exacta", contraparte

    for fila in reglas["keywords"]:
        palabra, limpia, cat = fila[0], fila[1], fila[2]
        if norm(palabra) in texto:
            return cat, 0.9, "regla-keyword", limpia

    return None, 0.0, "sin-match", ""


def aplicar():
    reglas = cargar_reglas()
    correcciones = cargar_correcciones()
    solo = perfiles.concepto_solo_por_fuente()
    filas = movimientos.leer()
    cuenta = {}
    for r in filas:
        r["contraparte"] = canonizar(r["contraparte"], reglas)   # el nombre se unifica siempre
        if r["categoria"].strip() and r["categoria"] != r["categoria_sistema"]:
            origen = "corregida-sin-aprender"   # la cambiaste a mano: se respeta hasta que corra aprender
        elif r["id"] in correcciones:
            r.update(categoria=correcciones[r["id"]], confianza="1.0", origen_categoria="manual",
                     categoria_sistema=correcciones[r["id"]])
            origen = "manual"
        elif r["origen_categoria"] in ("manual", "IA") and r["categoria"].strip():
            origen = r["origen_categoria"]
        else:
            cat, conf, origen, limpia = categorizar(r["contraparte"], r["concepto"], reglas,
                                                    solo.get(r["fuente"], False))
            if limpia:
                r["contraparte"] = canonizar(limpia, reglas)
            r.update(categoria=cat or "", confianza=str(conf), origen_categoria=origen,
                     categoria_sistema=cat or "")
        cuenta[origen] = cuenta.get(origen, 0) + 1
    movimientos.escribir(filas)
    print("Categorizadas %d filas:" % len(filas))
    for origen, n in sorted(cuenta.items(), key=lambda x: -x[1]):
        print("  %-16s %d" % (origen, n))
    if cuenta.get("sin-match"):
        print("Siguiente: python -m src.categorizar pendientes datos/pendientes.json  (pasada de IA)")


def pendientes(path=None) -> list:
    out = [{"id": r["id"], "contraparte": r["contraparte"], "concepto": r["concepto"],
            "importe": r["importe"], "moneda": r["moneda"], "fuente": r["fuente"]}
           for r in movimientos.leer() if r["origen_categoria"] == "sin-match" and not r["categoria"].strip()]
    txt = json.dumps(out, ensure_ascii=False, indent=1)
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(txt)
        print("%d pendientes en %s" % (len(out), path))
    else:
        print(txt)
    return out


def ia_aplicar(path):
    """Lee {id: {categoria, confianza, razon}}. Lo de confianza < UMBRAL_IA queda con nota REVISAR."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    categorias = set(categorias_conocidas())
    filas = movimientos.leer()
    por_id = {r["id"]: r for r in filas}
    ok = revisar = saltadas = 0
    for idt, v in data.items():
        r = por_id.get(idt)
        cat = (v.get("categoria") or "").strip()
        if (not r or not cat or r["origen_categoria"] == "manual"
                or (r["categoria"].strip() and r["categoria"] != r["categoria_sistema"])):
            saltadas += 1
            continue
        conf = float(v.get("confianza") or 0)
        nota = "IA: " + (v.get("razon") or "").strip()
        if cat not in categorias:
            nota = "REVISAR: categoría nueva, no está en las reglas. " + nota
            conf = min(conf, UMBRAL_IA - 0.01)
        elif conf < UMBRAL_IA:
            nota = "REVISAR: " + nota
        r.update(categoria=cat, confianza="%.2f" % conf, origen_categoria="IA", categoria_sistema=cat, nota=nota)
        if conf >= UMBRAL_IA:
            ok += 1
        else:
            revisar += 1
    movimientos.escribir(filas)
    print("IA aplicada: %d con confianza, %d para revisar, %d saltadas." % (ok, revisar, saltadas))


def categorias_conocidas() -> list:
    reglas = cargar_reglas()
    cats = set(reglas["contraparte_exacta"].values())
    cats |= {r["categoria"] for r in reglas["reglas_concepto"]}
    cats |= {f[2] for f in reglas["keywords"]}
    cats |= set(reglas.get("categorias") or [])
    return sorted(cats)


def conflictos(verbose: bool = True) -> list:
    """Reglas que se contradicen y harían que una categoría cambie sola entre corridas.

    - Un keyword cuya contraparte_limpia está en contraparte_exacta con OTRA categoría: aplicar escribe
      la limpia, la corrida siguiente la lee y cae en la exacta.
    - Un alias cuyo nombre canónico no es punto fijo, o un keyword con limpia sin canonizar."""
    reglas = cargar_reglas()
    exactas = {norm(k): v for k, v in reglas["contraparte_exacta"].items()}
    aceptados = {norm(k) for k in reglas["conflictos_aceptados"]}
    out = []
    for k, v in reglas["alias"].items():
        if norm(canonizar(v, reglas)) != norm(v):
            out.append("alias %r -> %r no es estable (canoniza a %r)" % (k, v, canonizar(v, reglas)))
    for palabra, limpia, cat in (f[:3] for f in reglas["keywords"]):
        if limpia and norm(canonizar(limpia, reglas)) != norm(limpia):
            out.append("keyword %r: la contraparte %r no está canonizada" % (palabra, limpia))
        otra = exactas.get(norm(limpia)) if limpia else None
        if otra and otra != cat and norm(palabra) not in aceptados:
            out.append("keyword %r -> %s, pero contraparte_exacta %r -> %s" % (palabra, cat, limpia, otra))
    if verbose:
        if out:
            print("%d conflicto(s):" % len(out))
            for c in out:
                print("  " + c)
            print("Arreglo: que las reglas digan lo mismo. Si es a propósito, anotalo con el motivo en "
                  "conflictos_aceptados.")
        else:
            print("Sin conflictos.")
    return out


def main(argv):
    cmd = argv[0] if argv else ""
    if cmd == "aplicar":
        aplicar()
    elif cmd == "pendientes":
        pendientes(argv[1] if len(argv) > 1 else None)
    elif cmd == "ia-aplicar" and len(argv) > 1:
        ia_aplicar(argv[1])
    elif cmd == "conflictos":
        sys.exit(1 if conflictos() else 0)
    elif cmd == "categorias":
        print("\n".join(categorias_conocidas()))
    else:
        sys.exit("Uso: python -m src.categorizar aplicar | pendientes [archivo] | ia-aplicar <archivo> "
                 "| conflictos | categorias")


if __name__ == "__main__":
    main(sys.argv[1:])
