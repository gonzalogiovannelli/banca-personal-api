"""Dónde vive cada archivo. Única fuente de verdad de las rutas.

  secretos/   credenciales: .env, la clave .pem de Enable Banking, las sesiones sesion_<perfil>.json
  datos/      lo que genera una corrida:
    movimientos.csv       la tabla de movimientos (fuente de verdad)
    volcados/<perfil>.json  lo que bajó el último pull de cada banco (el rebuild lo lee offline)
    backups/              copia completa de movimientos.csv antes de cada rebuild
    saldos.json           el saldo real que informó cada banco en su último pull
  config/perfiles.yml     tus bancos (se copia de perfiles.example.yml)
  reglas/                 las reglas de categorización y tus correcciones

secretos/ y datos/ están en .gitignore. Importar este módulo carga secretos/.env.
TRACKER_DATOS, TRACKER_PERFILES y TRACKER_REGLAS apuntan a otro lugar (las usan las pruebas).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
SECRETOS = ROOT / "secretos"
CONFIG = ROOT / "config"

load_dotenv(SECRETOS / ".env")

DATOS = Path(os.environ.get("TRACKER_DATOS") or ROOT / "datos")
MOVIMIENTOS = DATOS / "movimientos.csv"
SALDOS = DATOS / "saldos.json"
PERFILES = Path(os.environ.get("TRACKER_PERFILES") or CONFIG / "perfiles.yml")
REGLAS = Path(os.environ.get("TRACKER_REGLAS") or ROOT / "reglas")


def _carpeta(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def clave_eb() -> Path:
    """La clave privada de la app de Enable Banking. Relativa a secretos/ si no es absoluta."""
    p = Path(os.environ.get("ENABLEBANKING_KEY_PATH") or "enablebanking.pem")
    return p if p.is_absolute() else SECRETOS / p


def sesion(perfil: str) -> Path:
    return _carpeta(SECRETOS) / ("sesion_%s.json" % perfil)


def volcado(perfil: str) -> Path:
    return _carpeta(DATOS / "volcados") / ("%s.json" % perfil)


def backup(perfil: str, marca: str) -> Path:
    return _carpeta(DATOS / "backups") / ("movimientos_%s_antes-de-%s.csv" % (marca, perfil))


def escribir_atomico(path: Path, texto: str):
    """Escribe a un temporal y lo reemplaza de un golpe: si el proceso muere a mitad, queda el archivo viejo entero."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, path)
