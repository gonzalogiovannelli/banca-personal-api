# banca-personal-api

Conectá tus cuentas bancarias personales por open banking (PSD2), bajá los movimientos a un CSV en tu
computadora y categorizalos solos: con reglas, con IA para lo que las reglas no resuelven, y aprendiendo
de cada corrección tuya. Está pensado para usarse con [Claude Code](https://claude.com/claude-code),
que trae dos skills para operarlo, pero el código funciona sin él.

Funciona con los bancos que ofrece [Enable Banking](https://enablebanking.com) (la mayoría de los
europeos). Se probó con Sabadell, BBVA y Wise.

**Solo lectura.** El conector baja saldos y movimientos; no puede mover dinero.

## Qué tiene de distinto

- **Respeta los límites del banco.** Los bancos españoles que pasan por Redsys permiten unas 4 consultas
  por día. Bajar y procesar son dos pasos separados: se baja una vez y se procesa las veces que haga falta.
- **No duplica ni pierde.** Un pago pendiente que se confirma con otra fecha no aparece dos veces, dos
  cafés iguales el mismo día no se pisan, y lo que corregiste a mano no se borra aunque el banco cambie
  el movimiento.
- **Aprende de vos.** Cambiás una categoría en el CSV, marcás `aprender`, y la próxima vez ese comercio
  sale solo.
- **La IA dice cuándo duda.** Lo que clasifica con poca confianza queda marcado para que lo revises.
- **Lo que no dice la documentación de la API** está en [docs/aprendizajes.md](docs/aprendizajes.md).

## Cómo fluye

```
tu banco ──pull──> datos/volcados/<perfil>.json ──rebuild──> datos/movimientos.csv
 (1 consulta)          (lo crudo, en disco)        (offline)        │
                                                                    ├─ categorizar aplicar  (reglas)
                                                                    ├─ categorizar pendientes / ia-aplicar  (IA)
                                                                    └─ aprender  (tus correcciones)
```

## Primera vez

0. **Tu copia, privada.** Usá el botón *Use this template* de GitHub y elegí **Private**. No hagas fork:
   el fork de un repositorio público es público, y ahí terminarían tus reglas (los comercios y las
   personas a las que les pagás).
1. **Python 3.10 o más nuevo**, y `pip install -r requirements.txt`.
2. **Da de alta tu aplicación en Enable Banking** siguiendo el
   [instructivo paso a paso](docs/enable-banking.md). Para leer tus propias cuentas alcanza con el modo
   restringido, y el instructivo trae las páginas legales que pide el registro, listas para publicar.
3. Copiá `.env.example` a `secretos/.env` y completalo. Guardá la clave en `secretos/enablebanking.pem`.
4. Copiá `config/perfiles.example.yml` a `config/perfiles.yml` y dejá tus bancos.
5. Probá: `python -m src.enablebanking app` tiene que responder con los datos de tu aplicación.
6. Conectá cada banco con la skill `conectar-banco`, o a mano:
   ```
   python -m src.enablebanking auth sabadell
   python -m src.enablebanking sesion sabadell <code>
   ```
7. Reemplazá las categorías de ejemplo de `reglas/categorias.yml` por las tuyas.

Para ver que todo funciona sin tocar ningún banco: `python scripts/probar.py` corre el circuito completo
sobre datos inventados.

En Windows, si la consola muestra mal los acentos, anteponé `PYTHONIOENCODING=utf-8`.

## Uso

Con Claude Code: *"actualizá los movimientos"* (skill `actualizar-movimientos`). A mano:

```
python -m src.aprender --write              # primero, lo que corregiste
python -m src.movimientos pull sabadell      # toca el banco, una vez
python -m src.movimientos rebuild sabadell --write
python -m src.categorizar aplicar
python -m src.categorizar pendientes datos/pendientes.json
```

Cada consentimiento dura 90 días: `python -m src.enablebanking estado` dice cuánto le queda a cada uno.

## El CSV

`datos/movimientos.csv`, separado por comas y con punto decimal. Las columnas que tocás vos son dos:
`categoria` y `aprender`. Todo lo demás lo escribe el sistema. Se puede editar con Excel: si al guardar
lo deja con punto y coma o con coma decimal, el sistema lo lee igual y en la próxima corrida lo vuelve a
escribir en su formato.

Si cargás un movimiento a mano (un pago en efectivo, un ajuste), su `id` tiene que empezar por
`manual-`: así el sistema sabe que no viene del banco y nunca lo reemplaza.

## Dónde queda cada cosa

| Carpeta | Qué hay | ¿Va a git? |
|---|---|---|
| `src/` | El código | Sí |
| `docs/` | El instructivo de Enable Banking y lo aprendido con bancos reales | Sí |
| `legal/` | Plantillas de privacidad y términos para el registro en Enable Banking | Sí |
| `reglas/` | Tus categorías, reglas y correcciones | Sí, si tu copia es privada |
| `config/perfiles.yml` | Tus bancos | No |
| `secretos/` | Credenciales y sesiones | **Nunca** |
| `datos/` | Movimientos, volcados, saldos, copias de seguridad | **Nunca** |

Por eso tu copia tiene que ser **privada** (paso 0): los nombres de los comercios y de las personas a
las que les transferís dicen mucho de vos.

## Licencia

MIT. Ver [LICENSE](LICENSE).
