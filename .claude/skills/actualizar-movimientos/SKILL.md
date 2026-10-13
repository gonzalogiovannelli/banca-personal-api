---
name: actualizar-movimientos
description: Baja los movimientos nuevos de los bancos conectados, los guarda en datos/movimientos.csv sin duplicar, los categoriza con las reglas, clasifica con IA lo que las reglas no resuelven y aprende de las correcciones del usuario. Úsala cuando el usuario diga "actualizá los movimientos", "bajá el banco", "categorizá", "aprendé mis correcciones".
---

# Actualizar los movimientos

## Antes de empezar

- `python -m src.enablebanking estado`. Si un consentimiento está vencido, primero `conectar-banco`.
- En Windows, anteponé `PYTHONIOENCODING=utf-8` a los comandos.

## Pasos, por cada perfil que haya que actualizar

**1. Tus correcciones primero.** `python -m src.aprender`. Si muestra correcciones o reglas, confirmá
con el usuario y corré `python -m src.aprender --write`. Va antes del pull para que lo corregido quede
blindado.

**2. Bajar.** `python -m src.movimientos pull <perfil>`. **Una sola vez.** Si falla con 429, el banco
llegó al límite del día: no reintentes, se sigue mañana.

**3. Guardar.** `python -m src.movimientos rebuild <perfil>` muestra qué haría. Si los números tienen
sentido, `python -m src.movimientos rebuild <perfil> --write`. Si algo no cuadra, se investiga contra el
volcado (`datos/volcados/<perfil>.json`), no contra el banco.

**4. Reglas.** `python -m src.categorizar aplicar`.

**5. Lo que queda, con IA.** `python -m src.categorizar pendientes datos/pendientes.json`. Si hay
pendientes:
- `python -m src.categorizar categorias` da las categorías válidas. **Usá solo esas.**
- Clasificá cada movimiento y escribí `datos/ia.json` con la forma
  `{"<id>": {"categoria": "...", "confianza": 0.0-1.0, "razon": "..."}}`.
- **Confianza honesta:** si no podés saber qué es (una transferencia a una persona, un comercio
  desconocido), poné confianza baja. Por debajo de 0,85 queda marcado para que el usuario lo revise, y
  eso es lo que tiene que pasar.
- `python -m src.categorizar ia-aplicar datos/ia.json`.

**6. Coherencia de las reglas.** `python -m src.categorizar conflictos`. Si hay conflictos, mostralos;
no los resuelvas sin el usuario.

## Informe al usuario

- Cuántos movimientos entraron por banco y el saldo que informó el banco (`datos/saldos.json`).
- Cuántos categorizaron las reglas y cuántos la IA.
- **La lista de filas con nota `REVISAR`**, que son las que necesitan su ojo.
- Cómo corregir: cambiar la `categoria` en el CSV, y poner `si` en `aprender` si quiere que se vuelva
  regla. La próxima corrida lo aprende.

## Qué no hacer

- **No edites `datos/movimientos.csv` a mano** salvo para lo que hace el usuario: la categoría y la
  casilla `aprender`.
- **No pises una categoría manual.** El código ya lo impide; no lo rodees.
