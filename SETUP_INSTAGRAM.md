# Conectar Instagram y dejarlo publicando

El bot YA recopila noticias y genera gráficas de prueba. Para publicar faltan
credenciales de tus propias cuentas. No hay que compartirlas con nadie ni
pegarlas en un chat; guárdalas en GitHub Actions Secrets.

## 1. Cuenta profesional

Convierte tu cuenta de Instagram en Business o Creator. Abre
https://developers.facebook.com/apps/ y crea una aplicación que pueda
utilizar la Instagram API.

Hay dos modos compatibles en el código:

### Opción A: Instagram Login (más simple)

- Usa el producto **Instagram API con inicio de sesión en Instagram**.
- Solicita los permisos instagram_business_basic e
  instagram_business_content_publish para tu cuenta profesional.
- Obtén un token de Instagram User válido y el IG professional account ID.
- Variable GitHub: META_AUTH_MODE = instagram (predeterminado).
- El host de publicación será graph.instagram.com.

### Opción B: Facebook Login

- Vincula tu Instagram profesional a una página de Facebook que controles.
- Usa Facebook Login y permisos de Instagram Publishing en la app Meta:
  instagram_basic, instagram_content_publish, pages_read_engagement y
  los permisos de Page requeridos según tu configuración.
- Obtén el ID de la cuenta profesional vinculada y el token apropiado.
- Variable GitHub: META_AUTH_MODE = facebook.
- El host de publicación será graph.facebook.com.

La revisión/aprobación de la aplicación depende del acceso y permisos de Meta.
No asumimos que un token cualquiera sirve para publicar.

Docs oficiales:
https://developers.facebook.com/docs/instagram-platform/
https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api

## 2. Hosting de imágenes

Crea una cuenta en https://cloudinary.com/ y obtén Cloud name, API Key y API
Secret en su dashboard. El bot usa *signed upload*, nunca URLs temporales.

## 3. GroqCloud (opción gratis por defecto)

Crea tu API key en https://console.groq.com/keys y guárdala como **GROQ_API_KEY**
en GitHub Secrets. Modelo predeterminado: **openai/gpt-oss-120b** en Groq.

El bot puede usar **OPENAI_API_KEY** como alternativa si no configuraste Groq.
NO necesitas pagar OpenAI ni tener ChatGPT Plus para usar Groq. El servicio
gratis tiene límites de solicitudes y tokens: revisa tu cuota en GroqCloud.

Nunca pegues tus claves en chats, código ni archivos del repositorio. Si una
clave se expuso, **revócala y genera otra** antes de configurarla.

Límites del bot: máximo 3 borradores nuevos por ejecución y 30 al día
(predeterminados).

## 4. GitHub Secrets

Repositorio → Settings → Secrets and variables → Actions → New repository secret.

Guarda:

- GROQ_API_KEY (recomendado; gratis dentro de límites)
- OPENAI_API_KEY (opcional, respaldo)
- IG_USER_ID
- IG_ACCESS_TOKEN
- CLOUDINARY_CLOUD_NAME
- CLOUDINARY_API_KEY
- CLOUDINARY_API_SECRET

No guardes tokens en archivos del repositorio.

## 5. Probar ANTES de publicar

En GitHub: Actions → Football News Engine → Run workflow.

Descarga el artifact **football-news-previews** y revisa las gráficas y los
borradores generados en data/queue.json. Mantén ENABLE_PUBLISH=false.

## 6. Activar publicación automática

En Settings → Secrets and variables → Actions → Variables agrega:

- ENABLE_PUBLISH = true
- AUTO_APPROVE = true
- META_AUTH_MODE = instagram (o facebook, según tus credenciales)
- BRAND_NAME = el nombre de tu medio

Solo cuando ambas variables están en true, los secretos están completos y el
borrador tiene copy generado con OpenAI, el bot intenta publicar.

El horario de publicación predeterminado es **08:00 a 23:59, horario chileno**,
máximo una publicación por ejecución cada 30 minutos y 30 por día. La
recolección funciona todo el día.

## Antes de escalar

Este es un MVP sólido, pero un medio comercial con 20–35 posts diarios
necesitará más fuentes confiables, seguimiento de errores, métricas de
Instagram, hosting estable y una base de datos transaccional. No vuelvas a
intentar publicaciones fallidas sin revisar Instagram primero: podrían haber
sido publicadas pese a una respuesta de error.

La calidad editorial y los derechos de uso de imágenes son críticos.
