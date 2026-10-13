---
name: conectar-banco
description: Conecta un banco nuevo por Enable Banking (open banking PSD2) o renueva el consentimiento de uno ya conectado, que vence cada 90 días. Úsala cuando el usuario diga "conectá mi banco", "agregá una cuenta", "renová el consentimiento", "se venció el banco", o cuando un pull falle por consentimiento vencido o 401.
---

# Conectar un banco, o renovar su consentimiento

Es asistida: **el usuario entra a su banco y aprueba.** Vos generás el link, guardás la sesión y
comprobás que funcionó.

## Antes de empezar

- `secretos/.env` con `ENABLEBANKING_APP_ID`, y la clave privada en `secretos/enablebanking.pem`. Si
  faltan, es la primera vez: guiá al usuario por [docs/enable-banking.md](../../../docs/enable-banking.md)
  **un paso por vez**, esperando que confirme cada uno, y no sigas hasta que
  `python -m src.enablebanking app` responda. Si en el panel algo no coincide con el instructivo,
  decíselo y buscá el equivalente con él; no inventes nombres de botones.
- Leé [docs/aprendizajes.md](../../../docs/aprendizajes.md), sección "Autorizar".
- En Windows, anteponé `PYTHONIOENCODING=utf-8` a los comandos.

## Pasos

**0. ¿Qué toca?** `python -m src.enablebanking estado`. Se renueva lo vencido o lo que vence en menos de
14 días. Si es un banco nuevo, seguí al paso 1.

**1. El perfil.** Si el banco no está en `config/perfiles.yml`:
- `python -m src.enablebanking bancos ES` (o el país que corresponda) para el nombre exacto.
- Preguntá al usuario cómo quiere llamar a la cuenta (`fuente`).
- `id` y `concepto_solo`: los bancos españoles que pasan por Redsys llevan `hash` y `true`; Wise,
  `nativo` y `false`. Para otro banco, no lo adivines: después del primer pull mirá el volcado; si
  `entry_reference` viene vacío es `hash`, y si `creditor`/`debtor` vienen vacíos es `concepto_solo: true`.
- Dos titulares en el mismo banco son **dos perfiles**.

**2. El link.** `python -m src.enablebanking auth <perfil>`. Pasale la URL al usuario y decile:
- que la abra, entre a su banco y apruebe;
- que la página de destino no carga y es normal: tiene que copiar el `code` de la barra de direcciones;
- **si tiene otro usuario en el mismo banco, que la abra en incógnito.**

**3. La sesión.** `python -m src.enablebanking sesion <perfil> <code>`.
- Si vuelve `error=` en vez de `code=`, o la sesión trae **0 cuentas**, la autorización no sirvió:
  volvé al paso 2. No sigas sin cuentas.

**4. Comprobar.** Que aparezcan las cuentas que el usuario espera. Si renovaste un banco donde hay otro
titular conectado, pedile que compruebe que el otro siga funcionando (con su próximo pull).

**5. Bajar los datos.** Seguí con la skill `actualizar-movimientos` para ese perfil.

## Qué no hacer

- **No reintentes contra el banco en un loop.** Los bancos de Redsys permiten unas 4 consultas por día.
- **No muestres ni copies el contenido de `secretos/`.**
