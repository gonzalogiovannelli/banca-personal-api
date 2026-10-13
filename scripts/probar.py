"""Prueba de punta a punta con datos inventados. No toca ningún banco ni tus datos.

Corre el circuito completo sobre ejemplos/ en una carpeta temporal y comprueba lo que tiene que pasar:
ids sin duplicar, categorías, aprendizaje, la ventana que se reemplaza, y que nada tuyo se pierda.

Uso:  python scripts/probar.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
EJ = RAIZ / "ejemplos"
TMP = Path(tempfile.mkdtemp(prefix="banca-prueba-"))
shutil.copytree(EJ / "reglas", TMP / "reglas")
os.environ.update(TRACKER_DATOS=str(TMP / "datos"), TRACKER_PERFILES=str(EJ / "perfiles.yml"),
                  TRACKER_REGLAS=str(TMP / "reglas"))
sys.path.insert(0, str(RAIZ))

from src import aprender, categorizar, movimientos  # noqa: E402

fallos = 0


def comprobar(nombre: str, condicion: bool):
    global fallos
    print("  %s  %s" % ("ok   " if condicion else "FALLA", nombre))
    fallos += 0 if condicion else 1


def fila(cond):
    return next((r for r in movimientos.leer() if cond(r)), None)


def editar(cond, **cambios):
    filas = movimientos.leer()
    for r in filas:
        if cond(r):
            r.update(cambios)
    movimientos.escribir(filas)


def concepto(texto):
    return lambda r: texto in r["concepto"]


try:
    print("1. Primer pull del banco sin identificadores propios")
    movimientos.rebuild("demo-banco", write=True, volcado_path=EJ / "volcado-banco-1.json")
    filas = movimientos.leer()
    comprobar("entran los 8 movimientos", len(filas) == 8)
    cafes = sorted(r["id"] for r in filas if "CAFETERIA" in r["concepto"])
    comprobar("dos cafés iguales no se pisan (el segundo lleva .2)", len(cafes) == 2 and cafes[1] == cafes[0] + ".2")
    comprobar("la contraparte se lee del concepto", fila(concepto("MERCADONA"))["contraparte"] == "MERCADONA AV PUERTO")

    print("2. Categorización con las reglas")
    categorizar.aplicar()
    comprobar("Mercadona -> Supermercado", fila(concepto("MERCADONA"))["categoria"] == "Supermercado")
    comprobar("el alias unifica el cliente", fila(concepto("ACME"))["contraparte"] == "Acme Consulting")
    comprobar("el cliente -> Ingresos", fila(concepto("ACME"))["categoria"] == "Ingresos")
    comprobar("el concepto manda: comisión", fila(concepto("COMISION"))["categoria"] == "Comisiones")
    comprobar("lo desconocido queda sin categoría", fila(concepto("GIMNASIO"))["origen_categoria"] == "sin-match")

    print("3. Tus correcciones y lo que se aprende")
    editar(concepto("GIMNASIO"), categoria="Salud", aprender="si")
    editar(concepto("KIOSCO"), categoria="Restaurantes")
    primer_cafe = cafes[0]
    editar(lambda r: r["id"] == primer_cafe, categoria="Restaurantes")
    categorizar.aplicar()
    comprobar("aplicar no pisa una corrección todavía sin aprender", fila(concepto("KIOSCO"))["categoria"] == "Restaurantes")
    res = aprender.aprender(write=True)
    comprobar("se registran 3 correcciones", len(res["correcciones"]) == 3)
    comprobar("se aprende la regla del gimnasio", any(r[0] == "GIMNASIO CENTRO" and r[2] == "Salud" for r in res["reglas"]))
    comprobar("la casilla aprender se vacía", fila(concepto("GIMNASIO"))["aprender"] == "")

    print("4. La IA clasifica lo que queda, y lo dudoso se marca")
    pend = categorizar.pendientes(str(TMP / "pendientes.json"))
    comprobar("queda pendiente solo el segundo café", [p["id"] for p in pend] == [primer_cafe + ".2"])
    (TMP / "ia.json").write_text(json.dumps({primer_cafe + ".2": {"categoria": "Restaurantes", "confianza": 0.6,
                                                                  "razon": "parece una cafetería"}}), encoding="utf-8")
    categorizar.ia_aplicar(str(TMP / "ia.json"))
    comprobar("confianza baja queda para revisar", fila(lambda r: r["id"] == primer_cafe + ".2")["nota"].startswith("REVISAR"))

    print("5. Una fila que cargás a mano")
    filas = movimientos.leer()
    filas.append({c: "" for c in movimientos.COLUMNAS} | {
        "id": "manual-1", "fuente": "Banco Demo", "fecha": "2026-09-09", "concepto": "Ajuste de caja",
        "importe": "-5.00", "moneda": "EUR", "categoria": "Efectivo", "categoria_sistema": "Efectivo",
        "origen_categoria": "manual"})
    movimientos.escribir(filas)

    print("6. Segundo pull: un pendiente se confirma con otra fecha y otro se cancela")
    movimientos.rebuild("demo-banco", write=True, volcado_path=EJ / "volcado-banco-2.json")
    categorizar.aplicar()
    filas = movimientos.leer()
    comprobar("el histórico anterior a la ventana no se toca", fila(concepto("MERCADONA")) is not None)
    gim = sorted((r for r in filas if "GIMNASIO" in r["concepto"]), key=lambda r: r["fecha"])
    comprobar("el gimnasio confirmado no se duplica", len(gim) == 2)
    comprobar("y conserva tu categoría aunque cambió la fecha", gim[0]["fecha"] == "2026-09-12"
              and gim[0]["categoria"] == "Salud" and gim[0]["origen_categoria"] == "manual")
    comprobar("el gimnasio nuevo sale por la regla aprendida", gim[1]["categoria"] == "Salud"
              and gim[1]["origen_categoria"] == "regla-keyword")
    kiosco = fila(concepto("KIOSCO"))
    comprobar("el cancelado que corregiste se conserva y se marca", kiosco is not None and kiosco["nota"].startswith("REVISAR"))
    comprobar("la fila cargada a mano se conserva", fila(lambda r: r["id"] == "manual-1") is not None)
    comprobar("queda una copia completa antes de cada rebuild", len(list((TMP / "datos" / "backups").glob("*.csv"))) >= 1)

    print("7. Banco con identificador propio (Wise)")
    movimientos.rebuild("demo-wise", write=True, volcado_path=EJ / "volcado-wise.json")
    categorizar.aplicar()
    pret = fila(concepto("PRET A MANGER"))
    comprobar("compra con tarjeta: se guarda el importe original", pret["importe_compra"] == "-12.50" and pret["moneda_compra"] == "GBP")
    comprobar("y el comercio", pret["contraparte"] == "PRET A MANGER LONDON")
    comprobar("la comisión de Wise va a Comisiones", fila(concepto("Wise Charges"))["categoria"] == "Comisiones")
    movimientos.rebuild("demo-wise", write=True, volcado_path=EJ / "volcado-wise.json")
    comprobar("repetir el mismo pull no duplica nada", len([r for r in movimientos.leer() if r["fuente"] == "Wise Demo"]) == 3)

    print("8. Las reglas del ejemplo no se contradicen")
    comprobar("sin conflictos", categorizar.conflictos(verbose=False) == [])

    print("9. Una corrección nueva sobre una ya aprendida")
    editar(concepto("MERCADONA"), categoria="Restaurantes")
    aprender.aprender(write=True)
    editar(concepto("MERCADONA"), categoria="Salud")
    categorizar.aplicar()
    comprobar("aplicar no vuelve a la corrección anterior", fila(concepto("MERCADONA"))["categoria"] == "Salud")
    editar(concepto("MERCADONA"), aprender="si")
    res = aprender.aprender(write=True)
    comprobar("pedir aprender sobre una regla existente avisa", any("ya tiene la regla" in c for c in res["choques"]))
    editar(concepto("ACME"), categoria="Restaurantes", aprender="si")
    res = aprender.aprender(write=True)
    comprobar("y sobre una contraparte exacta también", any("contraparte_exacta" in c for c in res["choques"])
              and not res["reglas"])

    print("10. Casos de borde del rebuild (cada uno sobre una tabla vacía)")

    def tx(fecha, imp, texto, cuenta="EUR 000001", estado="BOOK", ident=None, fecha_campo="booking_date"):
        d = {"credit_debit_indicator": "DBIT", "transaction_amount": {"amount": "%.2f" % imp, "currency": "EUR"},
             "remittance_information": [texto], "status": estado, "_cuenta": cuenta, "entry_reference": ident}
        if fecha:
            d[fecha_campo] = fecha
        return d

    def pull(nombre, desde, txs, cuentas=None):
        p = TMP / ("%s.json" % nombre)
        p.write_text(json.dumps({"desde": desde, "cuentas": cuentas or sorted({t["_cuenta"] for t in txs}),
                                 "transacciones": txs}), encoding="utf-8")
        return p

    def de_cero():
        movimientos.escribir([])

    C = "COMPRA TARJ. 5402XXXXXXXX1234 STREAMING TV-MADRID"
    de_cero()
    movimientos.rebuild("demo-banco", True, pull("a1", "2026-08-01", [tx("2026-08-05", 9.99, C), tx("2026-09-05", 9.99, C, estado="PDNG")]))
    editar(lambda r: r["fecha"] == "2026-09-05", categoria="Suscripciones")
    movimientos.rebuild("demo-banco", True, pull("a2", "2026-08-01", [tx("2026-09-07", 9.99, C), tx("2026-08-05", 9.99, C)]))
    f = {r["fecha"]: r["categoria"] for r in movimientos.leer()}
    comprobar("dos cargos iguales: la corrección no salta al otro mes aunque el banco cambie el orden",
              f.get("2026-09-07") == "Suscripciones" and f.get("2026-08-05") == "")

    de_cero()   # los dos cambian de id (se reasientan un día después): solo la fecha decide quién es quién
    movimientos.rebuild("demo-banco", True, pull("b1", "2026-08-25", [tx("2026-09-01", 9.99, C), tx("2026-09-08", 9.99, C)]))
    editar(lambda r: r["fecha"] == "2026-09-08", categoria="Suscripciones")
    movimientos.rebuild("demo-banco", True, pull("b2", "2026-08-25", [tx("2026-09-09", 9.99, C), tx("2026-09-02", 9.99, C)]))
    f = {r["fecha"]: r["categoria"] for r in movimientos.leer()}
    comprobar("y tampoco cuando los dos cambian de fecha", f.get("2026-09-09") == "Suscripciones" and f.get("2026-09-02") == "")
    comprobar("y no quedan duplicados", len(movimientos.leer()) == 2)

    de_cero()
    movimientos.rebuild("demo-banco", True, pull("c1", "2026-09-01", [tx("2026-09-02", 200, "RETENCION HOTEL", estado="PDNG"), tx("2026-09-20", 5, "PAN")]))
    desde = movimientos.ventana_desde(movimientos.leer(), "Banco Demo")
    comprobar("un pendiente viejo estira la ventana hasta él", desde == "2026-09-02")
    movimientos.rebuild("demo-banco", True, pull("c2", desde, [tx("2026-09-22", 200, "RETENCION HOTEL"), tx("2026-09-20", 5, "PAN")]))
    comprobar("y al confirmarse no queda duplicado", len([r for r in movimientos.leer() if "HOTEL" in r["concepto"]]) == 1)

    de_cero()
    movimientos.rebuild("demo-banco", True, pull("d1", "2026-09-01", [tx("2026-09-03", 10, "LUZ", "EUR 000001"), tx("2026-09-04", 20, "AGUA", "EUR 000002")]))
    movimientos.rebuild("demo-banco", True, pull("d2", "2026-09-01", [tx("2026-09-03", 10, "LUZ", "EUR 000001")], ["EUR 000001"]))
    comprobar("una cuenta que no vino en el volcado no se toca", fila(concepto("AGUA")) is not None)

    de_cero()
    movimientos.rebuild("demo-banco", True, pull("e1", "2026-05-01", [tx("2026-05-03", 10, "ALQUILER"), tx("2026-05-10", 4, "CAFE")]))
    res = movimientos.rebuild("demo-banco", True, pull("e2", "2026-05-02", [tx("2026-08-01", 7, "TAXI")]))
    comprobar("si el banco ya no devuelve tan atrás, lo anterior se conserva", fila(concepto("ALQUILER")) is not None)
    comprobar("y se avisa", any("lo más viejo que devolvió" in a for a in res["avisos"]))

    de_cero()
    movimientos.rebuild("demo-wise", True, pull("f1", "2026-09-01", [tx("2026-09-03", 20, "TIENDA", estado="PDNG", ident="P1")]))
    movimientos.rebuild("demo-wise", True, pull("f2", "2026-09-01", [tx("2026-09-04", 20, "TIENDA", ident="B1")]))
    comprobar("Wise: el pendiente que cambia de id al confirmarse no queda duplicado",
              len([r for r in movimientos.leer() if "TIENDA" in r["concepto"]]) == 1)
    de_cero()
    movimientos.rebuild("demo-wise", True, pull("f3", "2026-09-01", [tx("2026-09-03", 15, "CANCELADA", estado="PDNG", ident="P2"),
                                                                 tx("2026-09-03", 2, "CONFIRMADA", ident="B2")]))
    movimientos.rebuild("demo-wise", True, pull("f4", "2026-09-01", [tx("2026-09-04", 1, "OTRA", ident="B3")]))
    comprobar("Wise: un pendiente cancelado desaparece y lo confirmado se conserva",
              fila(concepto("CANCELADA")) is None and fila(concepto("CONFIRMADA")) is not None)

    de_cero()
    res = movimientos.rebuild("demo-wise", True, pull("g1", "2026-09-01", [
        tx(None, 3, "SIN FECHA"), tx("2026-09-05", 3, "SOLO FECHA DE OPERACION", fecha_campo="transaction_date"),
        tx("2026-09-06", 8, "SIN ID")]))
    comprobar("un movimiento sin fecha se informa", any("sin ninguna fecha" in a for a in res["avisos"]))
    comprobar("uno con solo fecha de operación entra", fila(concepto("SOLO FECHA")) is not None)
    comprobar("en Wise, uno sin id entra con id calculado", fila(concepto("SIN ID")) is not None)

    de_cero()
    movimientos.rebuild("demo-banco", True, pull("h1", "2026-09-01", [tx("2026-09-05", 12, "KIOSCO", estado="PDNG")]))
    editar(concepto("KIOSCO"), categoria="Restaurantes")
    for n in range(3):
        movimientos.rebuild("demo-banco", True, pull("h2", "2026-09-01", [tx("2026-09-06", 1, "OTRA")]))
    comprobar("la marca REVISAR no se acumula", fila(concepto("KIOSCO"))["nota"].count("REVISAR") == 1)

    de_cero()   # un banco que numera los movimientos por cuenta
    movimientos.rebuild("demo-wise", True, pull("i1", "2026-09-01", [tx("2026-09-03", 10, "LUZ", "EUR 000001", ident="1"),
                                                                 tx("2026-09-03", 20, "AGUA", "EUR 000002", ident="1")]))
    comprobar("el mismo id en dos cuentas no pierde ningún movimiento", fila(concepto("AGUA")) is not None
              and fila(concepto("LUZ")) is not None)

    movimientos.escribir([])
    filas = [{c: "" for c in movimientos.COLUMNAS} | {"id": "x1", "fuente": "Banco Demo", "cuenta": "EUR 000001",
                                                     "fecha": "2026-09-20", "estado": "BOOK"}]
    comprobar("una cuenta nueva baja todo su historial", movimientos.ventana_desde(filas, "Banco Demo", "EUR 000009") == "2000-01-01"
              and movimientos.ventana_desde(filas, "Banco Demo", "EUR 000001") == "2026-09-12")
    pv = TMP / "pv.json"
    pv.write_text(json.dumps({"desde": "2026-09-12", "desde_por_cuenta": {"EUR 000001": "2026-09-12", "EUR 000009": "2000-01-01"},
                              "cuentas": ["EUR 000001", "EUR 000009"],
                              "transacciones": [tx("2026-09-21", 1, "NUEVO"), tx("2025-03-01", 5, "VIEJO NUEVA CUENTA", "EUR 000009")]}),
                  encoding="utf-8")
    movimientos.rebuild("demo-banco", True, pv)
    comprobar("y el rebuild la carga entera", fila(concepto("VIEJO NUEVA CUENTA")) is not None)

    print("11. Otros")
    ruta = movimientos.rutas.MOVIMIENTOS
    texto = ruta.read_text(encoding="utf-8")
    ruta.write_text(texto.replace(",", ";"), encoding="utf-8-sig")
    try:
        leido = len(movimientos.leer()) > 0
    except SystemExit:
        leido = False
    comprobar("un CSV guardado por Excel (BOM y punto y coma) se lee", leido)
    reglas = categorizar.cargar_reglas()
    comprobar("la regla de concepto mira solo el concepto", categorizar.categorizar("Banco X", "COMISION MANTENIMIENTO", reglas, False)[0] == "Comisiones")
    comprobar("una coma decimal se lee bien", movimientos.num("-5,00") == -5.0 and movimientos.num("1.234,56") == 1234.56)
    dup = TMP / "perfiles-dup.yml"
    dup.write_text("perfiles:\n  a: {banco: X, pais: ES, fuente: Igual, id: hash}\n  b: {banco: Y, pais: ES, fuente: Igual, id: hash}\n",
                   encoding="utf-8")
    from src import perfiles, rutas as _rutas
    original, _rutas.PERFILES = _rutas.PERFILES, dup
    try:
        perfiles.cargar()
        comprobar("dos perfiles con la misma fuente se rechazan", False)
    except SystemExit:
        comprobar("dos perfiles con la misma fuente se rechazan", True)
    finally:
        _rutas.PERFILES = original

    from src import enablebanking
    _rutas.SECRETOS = TMP / "secretos"   # que la prueba no escriba en tus secretos/
    sesion = _rutas.sesion("demo-banco")
    sesion.write_text('{"buena": true}', encoding="utf-8")

    class Falso(enablebanking.EnableBanking):
        def __init__(self):
            pass

        def create_session(self, code):
            return {"aspsp": {"name": "Banco Demo"}, "accounts": []}
    real, enablebanking.EnableBanking = enablebanking.EnableBanking, Falso
    try:
        enablebanking.main(["sesion", "demo-banco", "x"])
    except SystemExit:
        pass
    finally:
        enablebanking.EnableBanking = real
    comprobar("una sesión con 0 cuentas no pisa la que había", "buena" in sesion.read_text(encoding="utf-8"))
    sesion.unlink()
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print()
if fallos:
    print("FALLARON %d comprobaciones." % fallos)
    sys.exit(1)
print("Todo en orden.")
