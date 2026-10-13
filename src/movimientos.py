"""Bajar movimientos del banco y guardarlos en datos/movimientos.csv sin duplicar ni perder nada.

Dos pasos, a propósito:
  pull <perfil>              ÚNICO comando que toca el banco. Baja desde (última fecha cargada de esa
                             cuenta - 8 días) y el saldo, y lo vuelca a datos/volcados/<perfil>.json.
  rebuild <perfil> [--write] OFFLINE. Lee el volcado y reemplaza en la tabla SOLO la ventana que bajó.

Por qué partirlo: los bancos que pasan por Redsys permiten unas 4 consultas por día y por
consentimiento. Todo lo que haya que probar o repetir se prueba contra el volcado, nunca contra el banco.

Por qué una ventana que se reemplaza y no un "agregar lo nuevo": un movimiento pendiente cambia al
confirmarse (de fecha, a veces de importe), y en los bancos sin identificador propio su id es un hash del
contenido, así que cambia de id. Agregando, quedaría duplicado. Reemplazando la ventana, gana el estado final.

CLI:
  python -m src.movimientos pull sabadell
  python -m src.movimientos rebuild sabadell            # muestra qué haría
  python -m src.movimientos rebuild sabadell --write    # lo hace
"""
from __future__ import annotations

import base64
import csv
import datetime as dt
import hashlib
import json
import os
import re
import sys
from collections import defaultdict

from src import perfiles, rutas
from src.conceptos import contraparte_es, tarjeta_wise

COLUMNAS = ["id", "fuente", "cuenta", "fecha", "concepto", "contraparte", "importe", "moneda",
            "importe_compra", "moneda_compra", "tipo", "estado",
            "categoria", "confianza", "origen_categoria", "categoria_sistema", "aprender", "nota"]
# Lo que decidió el sistema o el usuario sobre una fila. Al reemplazar la ventana se recupera de la fila vieja.
# Una fila que cargás a mano (un ajuste, efectivo) lleva un id que empieza por "manual-": el rebuild no la toca.
CAMPOS_DE_CATEGORIA = ["categoria", "confianza", "origen_categoria", "categoria_sistema", "aprender", "nota"]
VENTANA_DIAS = 8


# --- la tabla ---
def leer(path=None) -> list:
    path = path or rutas.MOVIMIENTOS
    if not path.exists():
        return []
    # utf-8-sig y `;`: si lo abriste y guardaste con Excel, que graba con BOM y, en español, con punto y coma
    with open(path, encoding="utf-8-sig", newline="") as f:
        primera = f.readline()
        f.seek(0)
        lector = csv.DictReader(f, delimiter=";" if primera.count(";") > primera.count(",") else ",")
        if lector.fieldnames != COLUMNAS:
            sys.exit("Las columnas de %s no son las esperadas.\nEsperadas: %s\nEncontradas: %s"
                     % (path, COLUMNAS, lector.fieldnames))
        return list(lector)


def escribir(filas: list, path=None):
    """Escribe a un temporal y lo reemplaza de un golpe: si el proceso muere a mitad, la tabla vieja sigue entera."""
    path = path or rutas.MOVIMIENTOS
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".csv.tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS)
        w.writeheader()
        for fila in sorted(filas, key=lambda r: (r["fecha"], r["fuente"], r["id"])):
            w.writerow({c: fila.get(c, "") for c in COLUMNAS})
    os.replace(tmp, path)


def num(s) -> float:
    """Lee '-5.00', '-5,00' y '1.234,56': una planilla en español puede haber guardado coma decimal."""
    t = str(s or "").strip()
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return 0.0


# --- de Enable Banking a una fila ---
def a_fila(tx: dict, fuente: str, cuenta: str) -> dict:
    ta = tx.get("transaction_amount") or {}
    importe = float(ta.get("amount", 0) or 0)
    debito = tx.get("credit_debit_indicator") == "DBIT"
    if debito:
        importe = -abs(importe)
    moneda = ta.get("currency") or ""
    rem = tx.get("remittance_information") or []
    concepto = " || ".join(rem) if isinstance(rem, list) else str(rem)

    contraparte, importe_compra, moneda_compra = "", importe, moneda
    tarjeta = tarjeta_wise(concepto)
    if tarjeta:   # compra con tarjeta en otra moneda: se guarda lo que costó y lo que se debitó
        imp, mon, comercio = tarjeta
        if imp is not None:
            importe_compra = -imp if importe < 0 else imp
            moneda_compra = mon or moneda
        contraparte = comercio
    else:
        acreedor = (tx.get("creditor") or {}).get("name") or ""
        deudor = (tx.get("debtor") or {}).get("name") or ""
        contraparte = (acreedor if debito else deudor) or deudor or acreedor
    if not contraparte:   # bancos sin contraparte estructurada: leerla del concepto
        contraparte = contraparte_es(concepto)

    return {
        "id": tx.get("entry_reference") or tx.get("transaction_id") or "",
        "fuente": fuente, "cuenta": cuenta,
        "fecha": (tx.get("booking_date") or tx.get("value_date") or tx.get("transaction_date") or "")[:10],
        "concepto": concepto, "contraparte": contraparte,
        "importe": "%.2f" % importe, "moneda": moneda,
        "importe_compra": "%.2f" % importe_compra, "moneda_compra": moneda_compra,
        "tipo": (tx.get("bank_transaction_code") or {}).get("code", "") or "",
        "estado": tx.get("status", "") or "",
    }


def id_por_contenido(tx: dict, perfil: str) -> str:
    """Id estable para movimientos sin id del banco: el mismo movimiento da siempre el mismo id."""
    ta = tx.get("transaction_amount") or {}
    rem = tx.get("remittance_information") or []
    rem = " ".join(rem) if isinstance(rem, list) else str(rem)
    partes = ((tx.get("creditor") or {}).get("name") or "") + ((tx.get("debtor") or {}).get("name") or "")
    fecha = tx.get("booking_date") or tx.get("value_date") or tx.get("transaction_date") or ""
    canon = "|".join([fecha, str(ta.get("amount", "")),
                      str(ta.get("currency", "")), rem, partes, tx.get("credit_debit_indicator") or "",
                      tx.get("_cuenta", "")])
    h = base64.urlsafe_b64encode(hashlib.sha1(canon.encode("utf-8")).digest()).decode()[:15]
    return "%s-%s" % (perfil, h)


def saldo_contable(balances: list):
    """El saldo que cuadra con los movimientos asentados. El 'disponible' (ITAV) ya descuenta las
    compras con tarjeta retenidas, y comparado contra la suma de movimientos da diferencias falsas.
    Preferencia: CLBD > ITBD > ITAV > CLAV > XPCD > el primero."""
    if not balances:
        return None

    def monto(b):
        return num((b.get("balance_amount") or {}).get("amount", 0))
    for tipo in ("CLBD", "ITBD", "ITAV", "CLAV", "XPCD"):
        for b in balances:
            if b.get("balance_type") == tipo:
                return monto(b)
    return monto(balances[0])


# --- pull: lo único que toca el banco ---
def ventana_desde(filas: list, fuente: str, cuenta: str | None = None) -> str:
    """Desde dónde pedir: (última fecha cargada de esa fuente - 8 días), sin pasar de hoy, y nunca después
    del pendiente más viejo que siga abierto (una retención de hotel puede durar semanas: si quedara fuera
    de la ventana, al confirmarse quedaría duplicado). Anclada al dato: si una corrida falló, la siguiente
    cubre el hueco sola. Se calcula por cuenta: una cuenta nueva sin filas baja todo lo que dé el banco."""
    fechas, pendientes = [], []
    for r in filas:
        if (r["fuente"] != fuente or not r["fecha"] or r["id"].startswith("manual-")
                or (cuenta is not None and r["cuenta"] != cuenta)):
            continue
        try:
            f = dt.date.fromisoformat(r["fecha"][:10])
        except ValueError:
            continue
        fechas.append(f)
        if r["estado"] == "PDNG":
            pendientes.append(f)
    if not fechas:
        return "2000-01-01"
    desde = min(max(fechas), dt.date.today()) - dt.timedelta(days=VENTANA_DIAS)
    if pendientes:
        desde = min(desde, min(pendientes))
    return desde.isoformat()


def pull(perfil: str):
    from src.enablebanking import EnableBanking, cargar_sesion, etiqueta_cuenta
    p = perfiles.uno(perfil)
    sess = cargar_sesion(perfil)
    banco = ((sess.get("aspsp") or {}).get("name") or "")
    if p["banco"].lower() not in banco.lower() and banco.lower() not in p["banco"].lower():
        sys.exit("La sesión de '%s' es de %r, no de %r. Renová el consentimiento." % (perfil, banco, p["banco"]))
    tabla = leer()
    print("Pull %s" % p["fuente"])
    eb = EnableBanking()
    out = {"perfil": perfil, "fuente": p["fuente"], "desde": "", "desde_por_cuenta": {},
           "bajado": dt.datetime.now().replace(microsecond=0).isoformat(),
           "cuentas": [], "saldos": {}, "transacciones": []}
    path = rutas.volcado(perfil)
    for ac in sess.get("accounts", []):
        cuenta = etiqueta_cuenta(ac)
        desde = ventana_desde(tabla, p["fuente"], cuenta)
        out["desde_por_cuenta"][cuenta] = desde
        out["desde"] = min(out["desde"] or desde, desde)
        try:
            s = saldo_contable(eb.balances(ac["uid"]))
            if s is not None:
                out["saldos"][cuenta] = s
        except SystemExit as e:
            print("  aviso: no pude leer el saldo de %s: %s" % (cuenta, e))
        try:
            txs = eb.transactions(ac["uid"], date_from=desde)
        except SystemExit:
            # Lo ya bajado se guarda igual: la consulta ya se gastó. `cuentas` dice qué cuentas trae
            # el volcado, y el rebuild solo toca esas.
            rutas.escribir_atomico(path, json.dumps(out, ensure_ascii=False, indent=1))
            print("  falló %s. Lo bajado hasta acá quedó en %s." % (cuenta, path))
            raise
        for t in txs:
            t["_cuenta"] = cuenta
        out["cuentas"].append(cuenta)
        out["transacciones"].extend(txs)
        print("  %s: %d movimientos desde %s" % (cuenta, len(txs), desde))
    rutas.escribir_atomico(path, json.dumps(out, ensure_ascii=False, indent=1))
    print("Volcado en %s. Ahora, sin tocar el banco: python -m src.movimientos rebuild %s" % (path, perfil))


# --- rebuild: offline ---
EMPAREJAR_DIAS = 10            # un movimiento que el banco reasienta rara vez se corre más que esto
EMPAREJAR_DIAS_PENDIENTE = 45  # una retención (hotel, alquiler de coche) puede tardar semanas en confirmarse


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().upper()


def _dias(a: str, b: str) -> int:
    try:
        return abs((dt.date.fromisoformat(a[:10]) - dt.date.fromisoformat(b[:10])).days)
    except ValueError:
        return 9999


def _marcar(r: dict, texto: str):
    if not r.get("nota", "").startswith("REVISAR"):
        r["nota"] = ("REVISAR: %s %s" % (texto, r.get("nota", ""))).strip()


def _corregida(r: dict) -> bool:
    return r.get("origen_categoria") == "manual" or bool(
        r["categoria"].strip() and r["categoria"] != r["categoria_sistema"])


def rebuild(perfil: str, write: bool = False, volcado_path=None) -> dict:
    p = perfiles.uno(perfil)
    fuente = p["fuente"]
    path = volcado_path or rutas.volcado(perfil)
    if not path.exists():
        sys.exit("No hay volcado en %s. Corré primero: python -m src.movimientos pull %s" % (path, perfil))
    doc = json.loads(path.read_text(encoding="utf-8"))
    desde_cuenta = doc.get("desde_por_cuenta") or {}

    def desde_de(cuenta):
        return desde_cuenta.get(cuenta, doc["desde"])
    nativo = p["id"] == "nativo"
    avisos = []

    # 1) filas del volcado, con su id
    nuevas, vistos, sin_fecha, sin_id = [], defaultdict(int), 0, 0
    for tx in doc.get("transacciones", []):
        fila = a_fila(tx, fuente, tx.get("_cuenta", ""))
        if not fila["fecha"]:
            sin_fecha += 1
            continue
        if fila["fecha"] < desde_de(fila["cuenta"]):
            continue
        id_banco = fila["id"] if nativo else ""
        if not id_banco:   # sin id del banco: hash del contenido
            sin_id += 1 if nativo else 0
            fila["id"] = id_por_contenido(tx, perfil)
        clave = (fila["cuenta"], fila["id"])   # un banco puede numerar los movimientos por cuenta
        vistos[clave] += 1
        if vistos[clave] > 1:
            if id_banco:
                continue   # el banco repitió el mismo id en la misma cuenta
            fila["id"] = "%s.%d" % (fila["id"], vistos[clave])   # dos cafés iguales el mismo día
        nuevas.append(fila)
    if sin_fecha:
        avisos.append("%d movimientos del banco sin ninguna fecha: no se cargaron." % sin_fecha)
    if sin_id:
        avisos.append("%d movimientos sin id del banco: se les calculó uno por contenido." % sin_id)

    # 2) qué se reemplaza: por cuenta. Una cuenta que no vino en el volcado, o un tramo que el banco ya
    # no devuelve, se conservan.
    cuentas = doc.get("cuentas") or sorted({t.get("_cuenta", "") for t in doc.get("transacciones", [])})
    inicio = {}
    for c in cuentas:
        fechas = [f["fecha"] for f in nuevas if f["cuenta"] == c]
        if not fechas:
            continue
        desde = desde_de(c)
        inicio[c] = desde
        # Si lo más viejo que vino está mucho después de lo pedido, el banco probablemente ya no llega
        # tan atrás (en PSD2 lo habitual son unos 90 días): ese tramo se conserva en vez de borrarse. Un
        # hueco chico es normal (días sin movimientos, o un movimiento reasentado un día después).
        if desde != "2000-01-01" and min(fechas) > desde and _dias(min(fechas), desde) > VENTANA_DIAS:
            inicio[c] = min(fechas)
            avisos.append("%s: se pidió desde %s y lo más viejo que devolvió el banco es del %s. Lo "
                          "anterior se conserva; si faltan movimientos en el medio, bajalos en extracto."
                          % (c, desde, inicio[c]))
    tabla = leer()
    otras = [r for r in tabla if r["fuente"] != fuente]
    propias = [r for r in tabla if r["fuente"] == fuente]
    no_consultadas = {r["cuenta"] for r in propias if r["cuenta"] and r["cuenta"] not in cuentas}
    if no_consultadas:
        avisos.append("cuentas que no vinieron en el volcado y no se tocaron: %s" % ", ".join(sorted(no_consultadas)))

    def en_ventana(r):
        # un pendiente de la ventana pedida entra siempre, aunque el banco no haya devuelto nada tan viejo:
        # es justo lo que se espera que cambie
        if r["id"].startswith("manual-") or r["cuenta"] not in inicio:
            return False
        return r["fecha"] >= inicio[r["cuenta"]] or (r["estado"] == "PDNG" and r["fecha"] >= desde_de(r["cuenta"]))
    conservadas = [r for r in propias if not en_ventana(r)]
    viejas = [r for r in propias if en_ventana(r)]

    # 3) emparejar cada fila vieja con su versión nueva, para no perder la categoría.
    # Primero por id idéntico. Después por (cuenta, importe, concepto) con la fecha más cercana, asignando
    # de a pares en orden de distancia y no en el orden del volcado: si no, con dos cargos iguales (una
    # suscripción mensual) tu corrección podría quedar en el movimiento equivocado.
    pareja, usadas = {}, set()   # índice en nuevas -> índice en viejas
    por_id = {(r["cuenta"], r["id"]): i for i, r in enumerate(viejas)}
    for j, f in enumerate(nuevas):
        i = por_id.get((f["cuenta"], f["id"]))
        if i is not None and i not in usadas:
            pareja[j] = i
            usadas.add(i)
    candidatos = []
    for j, f in enumerate(nuevas):
        if j in pareja:
            continue
        for i, r in enumerate(viejas):
            if (i not in usadas and r["cuenta"] == f["cuenta"] and _norm(r["concepto"]) == _norm(f["concepto"])
                    and round(num(r["importe"]), 2) == round(num(f["importe"]), 2)):
                d = _dias(r["fecha"], f["fecha"])
                if d <= (EMPAREJAR_DIAS_PENDIENTE if r["estado"] == "PDNG" else EMPAREJAR_DIAS):
                    candidatos.append((d, j, i))
    for d, j, i in sorted(candidatos):
        if j not in pareja and i not in usadas:
            pareja[j] = i
            usadas.add(i)
    for j, i in pareja.items():
        nuevas[j].update({c: viejas[i].get(c, "") for c in CAMPOS_DE_CATEGORIA})

    # 4) lo viejo que el banco ya no devolvió
    huerfanas, mantenidas, descartadas = [], [], 0
    for i, r in enumerate(viejas):
        if i in usadas:
            continue
        if _corregida(r):
            _marcar(r, "la corregiste a mano y no apareció en el último pull (¿anulada?).")
            huerfanas.append(r)   # no se tira una decisión tuya
        elif nativo and r["estado"] != "PDNG":
            mantenidas.append(r)  # id estable y confirmado: se conserva aunque el banco no lo reenvíe
        else:
            descartadas += 1      # pendiente cancelado, o reemplazado por su versión confirmada

    resultado = otras + conservadas + huerfanas + mantenidas + nuevas
    resumen = {"desde": desde, "nuevas": len(nuevas), "descartadas": descartadas,
               "conservadas": len(conservadas) + len(mantenidas), "recuperadas": len(pareja),
               "huerfanas": len(huerfanas), "total": len(resultado), "avisos": avisos}
    print("Rebuild %s desde %s: %d del banco, %d categorías recuperadas, %d viejas que ya no vienen "
          "descartadas, %d huérfanas marcadas, %d conservadas. Total de la tabla: %d."
          % (fuente, desde, len(nuevas), len(pareja), descartadas, len(huerfanas),
             resumen["conservadas"], len(resultado)))
    for a in avisos:
        print("  AVISO: " + a)
    if not write:
        print("(no se escribió nada; agregá --write)")
        return resumen

    if rutas.MOVIMIENTOS.exists():   # copia COMPLETA antes de tocar, no solo la ventana
        marca = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        rutas.backup(perfil, marca).write_bytes(rutas.MOVIMIENTOS.read_bytes())
    escribir(resultado)
    if doc.get("saldos"):
        _guardar_saldos(fuente, doc["saldos"], doc.get("bajado", ""))
    print("Escrito en %s. Siguiente: python -m src.categorizar aplicar" % rutas.MOVIMIENTOS)
    return resumen


def _guardar_saldos(fuente: str, saldos: dict, cuando: str):
    doc = json.loads(rutas.SALDOS.read_text(encoding="utf-8")) if rutas.SALDOS.exists() else {}
    doc[fuente] = {"saldos": {k: round(float(v), 2) for k, v in saldos.items()}, "al": cuando}
    rutas.escribir_atomico(rutas.SALDOS, json.dumps(doc, indent=2, ensure_ascii=False))


def main(argv):
    if len(argv) < 2 or argv[0] not in ("pull", "rebuild"):
        sys.exit("Uso: python -m src.movimientos pull <perfil>  |  rebuild <perfil> [--write]")
    if argv[0] == "pull":
        pull(argv[1])
    else:
        rebuild(argv[1], write="--write" in argv)


if __name__ == "__main__":
    main(sys.argv[1:])
