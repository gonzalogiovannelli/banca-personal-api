# Instructivo: dar de alta Enable Banking para tus propias cuentas

Enable Banking es el intermediario autorizado (PSD2) que conecta este repositorio con tu banco. Para
usarlo registrás una "aplicación" a tu nombre. **Para leer tus propias cuentas no hace falta ser empresa
ni pagar:** la aplicación queda en *modo restringido*, que solo puede leer las cuentas que vos mismo
vinculaste.

Todo esto se hace una sola vez.

> **Fuentes y fecha.** Los pasos salen de la documentación oficial
> ([Control Panel Overview](https://enablebanking.com/docs/api/control-panel/), consultada el
> 2026-10-13) y de dar de alta una aplicación real en julio de 2026. El panel puede cambiar: si un botón no
> se llama igual, buscá el equivalente. Que el modo restringido sea gratis es lo que pasó en ese alta; la
> documentación oficial no habla de precios, así que comprobalo al registrarte.

## 1. Crear la cuenta

1. Entrá a [enablebanking.com/sign-in](https://enablebanking.com/sign-in/) y poné tu email.
2. Te llega un link de un solo uso. Al abrirlo, la cuenta queda creada y entrás al panel.

## 2. Publicar una política de privacidad y unos términos

Para registrar la aplicación en **producción** (la que lee bancos reales), Enable Banking pide dos URL
públicas: una política de privacidad y unos términos de servicio. Para uso personal alcanza con dos
páginas simples que digan la verdad: que la aplicación la usás solo vos, para tus cuentas, en modo
lectura.

En [`legal/`](../legal/) hay dos plantillas, `privacy.html` y `terms.html`. La forma más simple de
publicarlas es GitHub Pages:

1. Creá un repositorio **público** nuevo en GitHub, por ejemplo `mis-paginas-legales`. Tiene que ser
   otro repositorio: tu copia de este proyecto conviene que sea privada.
2. Subí las dos plantillas, reemplazando en cada una `{{NOMBRE_APP}}`, `{{EMAIL}}` y `{{FECHA}}`.
3. En el repositorio: **Settings → Pages → Branch: main → Save.** En un par de minutos quedan en
   `https://<tu-usuario>.github.io/mis-paginas-legales/privacy.html` y `.../terms.html`.
4. Abrí las dos URL en el navegador antes de seguir: tienen que cargar.

Las plantillas son un punto de partida para uso personal, no asesoramiento legal.

## 3. Registrar la aplicación

En el panel, menú superior: **API applications**.

| Campo | Qué poner |
|---|---|
| Entorno | **Production**. Sandbox solo da bancos de prueba |
| Infraestructura | La que viene por defecto, si te pregunta |
| Clave | **Que la genere el navegador.** La clave privada queda en tu computadora |
| Nombre | El que quieras, por ejemplo "Finanzas personales" |
| Redirect URLs | `https://localhost/` exactamente así, con la barra final |
| Descripción | Se le muestra al que autoriza (vos). Por ejemplo "Lectura de mis propias cuentas para uso personal" |
| Email de protección de datos | Tu email |
| Privacy policy URL / Terms URL | Las dos del paso 2 |

Apretá **Register**. Pasan dos cosas:

- La aplicación recibe un **Application ID** (un UUID). Copialo.
- Se descarga un archivo `.pem` con el nombre del ID. **Es tu clave privada: no la compartas ni la subas a
  ningún lado.**

## 4. Activarla en modo restringido: vincular tus cuentas

Una aplicación de producción recién registrada no lee nada hasta que se activa. Para uso personal, se
activa **vinculando tus propias cuentas** desde el panel: en la página de la aplicación, la opción para
vincular cuentas (en el alta de julio de 2026 era *Link accounts*). Elegís el banco, entrás con tu usuario
y aprobás.

- **Seleccioná todas las cuentas que quieras leer** cuando el banco te las muestre. Una cuenta que no
  vinculás acá no la vas a poder leer después, y la sesión aparece con 0 cuentas.
- Hacelo con **cada banco**. Si dos personas tienen cuenta en el mismo banco, cada una vincula la suya, y
  cada vez **en una ventana de incógnito** (ver [aprendizajes](aprendizajes.md)).

## 5. Llevarlo a este repositorio

1. Creá la carpeta `secretos/` en la raíz del repositorio (está en `.gitignore`).
2. Mové el `.pem` descargado a `secretos/enablebanking.pem`.
3. Copiá `.env.example` a `secretos/.env` y pegá el Application ID en `ENABLEBANKING_APP_ID`.
4. Probá: `python -m src.enablebanking app`. Si responde con los datos de tu aplicación, las credenciales
   funcionan.
5. Fijate que tu banco esté y cómo se llama exactamente: `python -m src.enablebanking bancos ES` (Wise
   aparece con `BE`).

## 6. Conectar cada banco

Copiá `config/perfiles.example.yml` a `config/perfiles.yml`, dejá tus bancos, y seguí con la skill
`conectar-banco` (o a mano: `auth <perfil>` y `sesion <perfil> <code>`). Ese consentimiento es el que
dura 90 días y se renueva.

## Si algo falla

| Síntoma | Causa probable |
|---|---|
| `app` responde 401 | El Application ID no corresponde a la clave, o la clave no es la de esa aplicación |
| La sesión se crea con 0 cuentas | La cuenta no se vinculó en el paso 4, o no la seleccionaste al aprobar en el banco |
| El banco vuelve con `error=` en vez de `code=` | Reintentá con un link nuevo; si hay otro usuario del mismo banco, en incógnito |
| 429 al bajar movimientos | El límite de consultas diarias del banco (unas 4 en los de Redsys). Mañana |
| El redirect no coincide | La URL de `ENABLEBANKING_REDIRECT_URL` tiene que ser idéntica a la registrada |
