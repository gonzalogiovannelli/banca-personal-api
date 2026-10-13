# Instrucciones para Claude

Este repositorio conecta las cuentas bancarias del usuario por Enable Banking (PSD2, solo lectura),
guarda los movimientos en `datos/movimientos.csv` y los categoriza. Leé el README y
[docs/aprendizajes.md](docs/aprendizajes.md) antes de tocar el código.

## Reglas

- **Nunca leas, muestres ni copies el contenido de `secretos/`.** Si un comando necesita una
  credencial, la lee el código.
- **El banco se toca solo con `pull`, y una vez.** Los bancos de Redsys permiten unas 4 consultas por día.
  Todo lo que haya que probar o repetir se hace con `rebuild` sobre el volcado.
- **La categoría manual manda.** Una fila con origen `manual`, o cuya `categoria` difiere de
  `categoria_sistema`, es una decisión del usuario: no se pisa.
- **La IA solo usa categorías que existen** (`python -m src.categorizar categorias`) y declara una
  confianza honesta. Inventar una categoría o inflar la confianza esconde exactamente lo que el usuario
  tiene que revisar.
- **Si cambiás `src/`, corré `python scripts/probar.py`.** Y si agregás un comportamiento, agregale su
  comprobación, y rompelo a propósito para ver que la comprobación salta.
- **Un banco nuevo con otro formato de concepto** se resuelve en `src/conceptos.py`, con un caso en el
  ejemplo.

## Skills

- `conectar-banco`: alta de un banco o renovación del consentimiento (cada 90 días).
- `actualizar-movimientos`: bajar, guardar, categorizar, pasada de IA y aprender.
