"""Leer la contraparte del texto del concepto, cuando el banco no la manda como campo.

Los bancos españoles que pasan por Redsys (Sabadell, BBVA) devuelven `creditor` y `debtor` vacíos: el
comercio viene escrito dentro del concepto, y cada banco lo escribe a su manera. Wise sí manda la
contraparte, pero en las compras con tarjeta la esconde en una frase en inglés.

Si sumás un banco con otro formato, este es el archivo que se toca.
"""
from __future__ import annotations

import re

_WISE_TARJETA_IMPORTE = re.compile(r"of (-?[\d.,]+) (\w{3})")
_WISE_TARJETA_COMERCIO = re.compile(r"issued by (.+?)(?:\s*\(fee:|$)")


def tarjeta_wise(concepto: str):
    """'Card transaction of 12.50 GBP issued by PRET A MANGER LONDON (fee: ...)'
    -> (12.5, 'GBP', 'PRET A MANGER LONDON'). None si no es ese formato."""
    if "Card transaction of" not in concepto and "issued by" not in concepto:
        return None
    mi = _WISE_TARJETA_IMPORTE.search(concepto)
    mc = _WISE_TARJETA_COMERCIO.search(concepto)
    importe = abs(float(mi.group(1).replace(",", ""))) if mi else None
    return importe, (mi.group(2) if mi else None), (mc.group(1).strip() if mc else "")


def contraparte_es(concepto: str) -> str:
    """El comercio o la persona, leído del concepto de un banco español. "" si no se identifica."""
    c = (concepto or "").strip()
    if not c:
        return ""
    u = c.upper()

    # BBVA parte el concepto en tres con '//': '<qué es> // <tipo de operación> // <detalle>'. En las
    # compras con tarjeta el detalle es de ANCHO FIJO: comercio (25) + ciudad (13) + país (2), sin
    # separador, así que no sirve cortar por espacios ('MERCADONA PLAZA DE ESPAAACARTAGENA DE ES').
    if "//" in c:
        partes = c.split("//")
        if len(partes) >= 3 and partes[1].strip().upper().startswith("PAGO CON TARJETA"):
            det = partes[2].lstrip()
            s = (det[:25] if len(det.rstrip()) > 25 else det).strip()
            if s:
                return s

    # Sabadell: 'COMPRA TARJ. <nº> <COMERCIO>-<CIUDAD>', y sus devoluciones y anulaciones
    m = (re.match(r"^(?:ANUL\s+)?COMPRA TARJ\.\s+\S+\s+(.+)$", c, re.I)
         or re.match(r"^DEVOLUCION TAR\.\s*\S*\s+(.+)$", c, re.I))
    if m:
        s = re.sub(r"-[^-]+$", "", m.group(1).strip()).strip()
        s = re.sub(r"^\d{2}\.\d{2}\s+", "", s)
        return s or c

    if "CASHBACK" in u:
        return "Cashback"
    if u.startswith("REINTEGRO"):
        return "Cajero automático"
    if u.startswith("INGRESO EFECTIVO"):
        return "Ingreso en efectivo"

    # Bizum o transferencia con una persona: el nombre es la contraparte
    m = (re.match(r"^PAGO BIZUM\s+(.+)$", c, re.I)
         or re.match(r"^ABONO BIZUM DE\s+(.+)$", c, re.I)
         or re.match(r"^ABONO (?:TRANSFERENCIA|TRANSF\.?)\s+DE\s+(.+)$", c, re.I))
    if m:
        return m.group(1).strip().title()

    # Bizum a un comercio: 'COMPRA BIZUM <COMERCIO> [BIZUM <lugar>] ES'
    m = re.match(r"^COMPRA BIZUM\s+(.+)$", c, re.I)
    if m:
        s = re.sub(r"\s+ES$", "", m.group(1).strip(), flags=re.I)
        return re.split(r"\s+BIZUM\s+", s, flags=re.I)[0].strip()

    if u.startswith("IMPUESTOS"):
        return "Impuestos"
    if u.startswith("INTERESES Y/O COMISIONES") or u.startswith("COMISION"):
        return "Comisiones del banco"
    if u.startswith("LIQUIDACION"):
        return "Liquidación del banco"
    m = re.match(r"^(?:ABONO\s+)?TRANSFERENCIA\s+(?:A|DE|FAVOR)\s+(.+)$", c, re.I)
    if m:
        return m.group(1).strip().title()
    if len(c) <= 25:
        return c.title()

    # BBVA que no es tarjeta (adeudos, promociones): el tercer segmento es una referencia interna. El
    # primero sí describe la operación, y sin una etiqueta el aprendizaje no puede generalizar nada.
    if "//" in c:
        s = c.split("//")[0].strip()
        if s:
            return s.title()
    return ""
