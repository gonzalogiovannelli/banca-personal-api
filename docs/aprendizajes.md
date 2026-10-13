# Lo que se aprende conectando bancos reales por Enable Banking

Esto no está en la documentación de la API: salió de usarla con cuentas reales de Sabadell, BBVA y Wise
entre julio y octubre de 2026. Cada punto explica una decisión del código.

## Límites

**Los bancos que pasan por Redsys (Sabadell, BBVA) permiten unas 4 consultas por día y por
consentimiento.** Pasado el límite responden `HTTP 429 [HUB046] Allowed number of accesses exceeded for
consent`. Wise no tiene ese límite. Un consentimiento nuevo reinicia el contador.

De ahí sale la arquitectura en dos pasos: `pull` es lo único que toca el banco (saldo y movimientos, dos
consultas por cuenta) y lo vuelca a disco; `rebuild` trabaja sobre ese volcado todas las veces que haga
falta. **Nunca se prueba ni se reintenta contra el banco.**

**El consentimiento dura 90 días** (PSD2). Al vencer, el pull falla y hay que volver a autorizar desde el
banco. `python -m src.enablebanking estado` dice cuánto le queda a cada uno.

**Cuánto historial devuelve cada banco varía.** Wise devolvió más de un año hacia atrás. En los bancos de
Redsys no llegamos a medirlo con precisión: lo habitual en PSD2 son unos 90 días. Si necesitás historial
más viejo, bajalo una vez en extracto desde la web del banco.

## Lo que viene, y lo que no

**Todos los bancos devuelven la misma estructura** (el estándar Berlin Group, unos 24 campos por
movimiento), así que hay un solo conversor y no uno por banco. Campos útiles además del importe y la
fecha: `status` (BOOK confirmado, PDNG pendiente), `bank_transaction_code` (tarjeta, transferencia),
`merchant_category_code`, `balance_after_transaction`.

**Los bancos de Redsys no mandan la contraparte ni un identificador por movimiento.** `creditor`,
`debtor` y `entry_reference` vienen vacíos. Por eso:
- la contraparte se lee del texto del concepto (`src/conceptos.py`), y cada banco lo escribe distinto;
- el identificador se calcula como un hash del contenido, y dos movimientos idénticos el mismo día (dos
  cafés) se distinguen con un sufijo `.2`.

**El concepto de BBVA en las compras con tarjeta es de ancho fijo**: comercio (25 caracteres), ciudad
(13) y país (2), pegados sin separador. Cortar por espacios no funciona.

**Wise sí manda contraparte e identificador**, pero en las compras con tarjeta esconde el comercio y el
importe original en una frase: `Card transaction of 12.50 GBP issued by ...`. Se guardan las dos cosas:
lo que costó en su moneda y lo que se debitó.

## Movimientos que cambian

**Un movimiento pendiente cambia al confirmarse**, a veces de fecha, y en los bancos sin identificador eso
le cambia el hash. Si se agregara "lo nuevo", quedaría duplicado. Por eso cada pull baja desde la última
fecha cargada menos 8 días, y el rebuild **reemplaza esa ventana entera** con lo que trajo el banco. Tu
categoría se recupera emparejando por importe y concepto, con la fecha más cercana.

**Si un movimiento que corregiste a mano desaparece del banco** (una compra anulada), no se borra: se
conserva con una nota `REVISAR`.

## Saldos

**Hay varios saldos y no son lo mismo.** El "disponible" (`ITAV`) ya descuenta las compras con tarjeta
retenidas; el contable (`CLBD`) es el que cuadra con la suma de movimientos confirmados. Comparar la suma
contra el disponible da diferencias falsas. Se guarda el contable cuando el banco lo manda (BBVA y
Sabadell sí, Wise solo el disponible).

## Autorizar

- **El banco redirige a `https://localhost/?code=...` y la página no carga.** Es normal: se copia el
  `code` de la barra de direcciones.
- **Si en lugar de `code=` vuelve `error=`**, se genera un link nuevo y se repite.
- **Si la sesión se crea con 0 cuentas**, la autorización no sirvió. Hay que repetirla: con 0 cuentas no
  hay nada que bajar.
- **Dos personas con cuenta en el mismo banco: cada link en una ventana de incógnito.** Una vez, un
  intento hecho con la sesión del banco abierta con el otro usuario dio `server_error` y **le invalidó la
  sesión al otro titular** (401), aunque no estaba vencida. Después de renovar uno, comprobá que el otro
  siga funcionando.
- **Wise se autoriza con país BE**, no ES.

## Proveedor

Al 2026-07, GoCardless (antes Nordigen), la opción gratuita más conocida para esto, había cerrado las altas
nuevas. Enable Banking ofrece acceso a tus propias cuentas registrando una aplicación en su panel.
Comprobá sus condiciones actuales antes de empezar.
