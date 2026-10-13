"""Conector Enable Banking (open banking PSD2). SOLO LECTURA.

Autenticación: un JWT RS256 firmado con la clave privada de tu app (header kid = Application ID),
que va como Bearer en cada pedido. Base URL: https://api.enablebanking.com

Flujo de un consentimiento:
  1. bancos ES                  -> los bancos disponibles en un país, con su nombre exacto
  2. auth <perfil>              -> URL de consentimiento: la abrís, entrás a tu banco y aprobás
  3. el banco redirige a ENABLEBANKING_REDIRECT_URL?code=...  (la página no carga: es normal)
  4. sesion <perfil> <code>     -> cambia el code por una sesión con tus cuentas y la guarda
  5. estado                     -> cuándo vence cada consentimiento

Los movimientos los baja `src.movimientos pull <perfil>`, no este módulo.

CLI:
  python -m src.enablebanking app
  python -m src.enablebanking bancos ES
  python -m src.enablebanking auth sabadell
  python -m src.enablebanking sesion sabadell <code>
  python -m src.enablebanking estado
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
import uuid

import jwt
import requests

from src import perfiles, rutas

BASE = "https://api.enablebanking.com"
# Tiene que coincidir EXACTO con el que registraste en la app de Enable Banking.
REDIRECT_URL = os.environ.get("ENABLEBANKING_REDIRECT_URL") or "https://localhost/"


class EnableBanking:
    def __init__(self, app_id: str | None = None, key_path=None):
        self.app_id = app_id or os.environ.get("ENABLEBANKING_APP_ID")
        if not self.app_id:
            sys.exit("Falta ENABLEBANKING_APP_ID en secretos/.env (ver .env.example).")
        kp = key_path or rutas.clave_eb()
        if not kp.exists():
            sys.exit("Falta la clave privada de Enable Banking en %s." % kp)
        self.key = kp.read_text()

    # --- autenticación ---
    def _token(self, ttl: int = 3600) -> str:
        now = int(time.time())
        return jwt.encode(
            {"iss": "enablebanking.com", "aud": "api.enablebanking.com", "iat": now, "exp": now + ttl},
            self.key, algorithm="RS256", headers={"kid": self.app_id},
        )

    def _headers(self) -> dict:
        return {"Authorization": "Bearer " + self._token(), "Content-Type": "application/json"}

    def _get(self, path: str, **params):
        r = requests.get(BASE + path, headers=self._headers(), timeout=60,
                         params={k: v for k, v in params.items() if v is not None} or None)
        _falla_legible(r)
        return r.json()

    def _post(self, path: str, body: dict):
        r = requests.post(BASE + path, headers=self._headers(), json=body, timeout=60)
        _falla_legible(r)
        return r.json()

    # --- endpoints ---
    def application(self) -> dict:
        """Datos de tu app. Sirve para probar que las credenciales funcionan."""
        return self._get("/application")

    def bancos(self, pais: str) -> list:
        return self._get("/aspsps", country=pais).get("aspsps", [])

    def start_auth(self, banco: str, pais: str, dias: int = 90, psu_type: str = "personal") -> dict:
        """Devuelve {url, ...}. Abrís la url, aprobás en el banco, y el banco redirige con ?code=..."""
        valid_until = (dt.datetime.now(dt.timezone.utc)
                       + dt.timedelta(days=dias)).replace(microsecond=0).isoformat()
        return self._post("/auth", {
            "access": {"valid_until": valid_until},
            "aspsp": {"name": banco, "country": pais},
            "state": str(uuid.uuid4()),
            "redirect_url": REDIRECT_URL,
            "psu_type": psu_type,
        })

    def create_session(self, code: str) -> dict:
        return self._post("/sessions", {"code": code})

    def balances(self, uid: str) -> list:
        return self._get("/accounts/%s/balances" % uid).get("balances", [])

    def transactions(self, uid: str, date_from: str | None = None, date_to: str | None = None) -> list:
        """Todos los movimientos del rango, siguiendo la paginación (continuation_key)."""
        out, cont = [], None
        while True:
            data = self._get("/accounts/%s/transactions" % uid,
                             date_from=date_from, date_to=date_to, continuation_key=cont)
            out.extend(data.get("transactions", []))
            cont = data.get("continuation_key")
            if not cont:
                return out


def _falla_legible(r: requests.Response):
    """Un error del banco se muestra con su texto: el código solo no alcanza para saber qué pasó."""
    if r.ok:
        return
    texto = r.text[:400]
    pista = ""
    if r.status_code == 429:
        pista = ("\nPista: los bancos que pasan por Redsys permiten unas 4 consultas por día y por "
                 "consentimiento. Esperá a mañana o renová el consentimiento (ver docs/aprendizajes.md).")
    elif r.status_code == 401:
        pista = ("\nPista: si falló `app`, el ENABLEBANKING_APP_ID no corresponde a la clave .pem. Si falló al "
                 "bajar movimientos, la sesión está vencida o invalidada: renová el consentimiento.")
    raise SystemExit("Enable Banking respondió %d: %s%s" % (r.status_code, texto, pista))


def etiqueta_cuenta(ac: dict) -> str:
    """'EUR 123456': moneda y los últimos 6 caracteres del IBAN o del identificador."""
    aid = ac.get("account_id") or {}
    ident = aid.get("iban") or (aid.get("other") or {}).get("identification") or ""
    return ("%s %s" % (ac.get("currency", ""), str(ident)[-6:])).strip()


def cargar_sesion(perfil: str) -> dict:
    p = rutas.sesion(perfil)
    if not p.exists():
        sys.exit("No hay sesión para '%s'. Corré: auth %s, y después sesion %s <code>." % (perfil, perfil, perfil))
    return json.loads(p.read_text(encoding="utf-8"))


def _vence(sess: dict) -> str:
    return ((sess.get("access") or {}).get("valid_until") or "")[:10]


def main(argv: list):
    cmd = argv[0] if argv else ""

    if cmd == "estado":   # no llama al banco: lee las sesiones guardadas
        hoy = dt.date.today()
        for nombre in perfiles.cargar():
            p = rutas.sesion(nombre)
            if not p.exists():
                print("  %-12s sin sesión" % nombre)
                continue
            v = _vence(json.loads(p.read_text(encoding="utf-8")))
            if not v:
                print("  %-12s vencimiento desconocido" % nombre)
                continue
            dias = (dt.date.fromisoformat(v) - hoy).days
            aviso = "VENCIDO" if dias < 0 else ("renovar pronto" if dias < 14 else "ok")
            print("  %-12s vence %s (%d días) %s" % (nombre, v, dias, aviso))
        return

    eb = EnableBanking()
    if cmd == "app":
        print(json.dumps(eb.application(), indent=2, ensure_ascii=False))

    elif cmd == "bancos":
        pais = argv[1] if len(argv) > 1 else "ES"
        for a in eb.bancos(pais):
            print("-", a.get("name"), "|", a.get("country"), "| psu:", ",".join(a.get("psu_types", [])))

    elif cmd == "auth":
        if len(argv) < 2:
            sys.exit("Uso: auth <perfil>")
        p = perfiles.uno(argv[1])
        res = eb.start_auth(p["banco"], p["pais"])
        print("Abrí esta URL, aprobá en el banco y copiá el `code` de la barra de direcciones:\n")
        print(res.get("url"))
        print("\nSi tenés dos usuarios en el mismo banco, abrila en una ventana de incógnito.")

    elif cmd == "sesion":
        if len(argv) < 3:
            sys.exit("Uso: sesion <perfil> <code>")
        nombre, code = argv[1], argv[2]
        p = perfiles.uno(nombre)
        sess = eb.create_session(code)
        banco = ((sess.get("aspsp") or {}).get("name") or "")
        if p["banco"].lower() not in banco.lower() and banco.lower() not in p["banco"].lower():
            sys.exit("La sesión es de %r y el perfil '%s' es de %r. No se guardó." % (banco, nombre, p["banco"]))
        cuentas = sess.get("accounts", [])
        if not cuentas:   # no se pisa la sesión que ya había: puede seguir sirviendo
            sys.exit("La sesión no trae cuentas: la autorización no sirvió y NO se guardó. Repetí el flujo.")
        rutas.escribir_atomico(rutas.sesion(nombre), json.dumps(sess, indent=2, ensure_ascii=False))
        print("Sesión guardada en %s. Vence: %s. Cuentas: %d" % (rutas.sesion(nombre).name, _vence(sess) or "?", len(cuentas)))
        for ac in cuentas:
            print("  ", etiqueta_cuenta(ac), "|", ac.get("name", ""))

    else:
        sys.exit("Comandos: app | bancos [PAIS] | auth <perfil> | sesion <perfil> <code> | estado")


if __name__ == "__main__":
    main(sys.argv[1:])
