# Chao Felicevich — futbolero, automatizado 24/7

Python-first system for collecting fresh football headlines and preparing
original Spanish Instagram posts. Configured to target up to 60 high-quality posts per day
when there is enough real news, **not** made-up content to hit a quota.

## Estado actual: AUTOPUBLICACIÓN ACTIVADA

Cuenta verificada: **@chaofelicevich**. Groq redacta, `graphics.py` crea artes propios y Meta publica por su API oficial. Se ejecuta cada **15 minutos** mediante GitHub Actions, sin requerir PC encendido. Meta: **60 publicaciones diarias como objetivo**, distribuidas en 48 turnos y 12 publicaciones adicionales durante el día. Solo publica noticias reales y frescas, y respeta la cuota vigente de la cuenta de Instagram. Si no hay noticias fiables, no inventa.

- Run history: **Actions → Football News Engine**
- Image previews: latest workflow run → **Artifacts → football-news-previews**
- Raw RSS archive: data/news.json
- Editorial queue: data/queue.json

By default, preview cards use the **original RSS headline** and status
awaiting_ai. When a configured FREE LLM provider (Groq / Gemini / Cerebras / OpenRouter Free) is available, cards use Spanish headlines and
short captions grounded ONLY in the RSS title and summary.

## LLM de texto — solo niveles gratuitos (23/11/2026)

El bot usa `free_llm.py` y solo prueba proveedores configurados:

1. **Groq (Free plan)**: `GROQ_API_KEY` ya funciona en la cuenta. Límite de seguridad local 75 solicitudes por día.
2. **Gemini**: `GEMINI_API_KEY` de [Google AI Studio](https://aistudio.google.com/api-keys) y variable de Actions `GEMINI_FREE_TIER_CONFIRMED=true` **solo después de comprobar que el proyecto sigue en el plan Free sin facturación**. Usa `gemini-3.1-flash-lite`. Límite local 20 solicitudes diarias.
3. **Cerebras Free**: `CEREBRAS_API_KEY` de [Cerebras Cloud](https://cloud.cerebras.ai/) y `CEREBRAS_FREE_TIER_CONFIRMED=true` **solo después de confirmar cuenta Free sin facturación**. Modelo `gpt-oss-120b`. Límite local 35 solicitudes diarias.
4. **OpenRouter Free**: `OPENROUTER_API_KEY` de [OpenRouter](https://openrouter.ai/settings/keys). Usa **exclusivamente** `openrouter/free`, que enruta a modelos de precio cero; el bot prohíbe cambiar a otros modelos con costo. Límite local 40 solicitudes por día, por debajo de las 50 que OpenRouter documenta para cuentas gratuitas sin créditos.

**No hay fallback a OpenAI de pago.** Aunque exista `OPENAI_API_KEY` en Secrets, el bot ya no la utiliza. La generación de imágenes con Replicate está desactivada en código y workflow, aunque quede un token antiguo en Secrets.

En [Actions Secrets](https://github.com/rchiup/futbol-news-bot/settings/secrets/actions), agrega las claves que falten sin enviarlas por chat. En [Actions Variables](https://github.com/rchiup/futbol-news-bot/settings/variables/actions), marca el nivel gratuito de Gemini/Cerebras únicamente tras confirmarlo. El orden es `groq,gemini,cerebras,openrouter`, configurable vía `FREE_LLM_ORDER`. Cada solicitud registra proveedor, latencia, éxito/error y puntaje heurístico de claridad en `data/llm_free_usage.json`.

El workflow [Compare Free Sports News LLMs](https://github.com/rchiup/futbol-news-bot/actions/workflows/benchmark-free-llms.yml) compara a diario los modelos disponibles con **la misma noticia real** sin publicar sus pruebas. Guarda `data/llm_benchmark.json`, `data/llm_benchmark_history.json` y `data/llm_ranking.json`. El ranking no declara vencedor antes de contar con varias muestras, y **claridad no significa verificación factual**. Los hechos deben seguir sustentados en una fuente de noticias real.

Los niveles gratuitos tienen restricciones propias y los cupos pueden variar: las APIs no pueden comprobar por sí solas si un proyecto externo activó facturación. Mantén Groq, Gemini y Cerebras en Free y sin facturación, y no habilites créditos automáticos. Si los cupos se agotan, las noticias se quedan en cola; el bot no compra capacidad.

## Cobertura multideporte (23/11/2026)

El motor editorial RSS ahora considera **fútbol, tenis, golf, F1 y NBA**.
Cada fuente tiene categoría explícita y se generan gráficas originales específicas
para tenis, golf, F1 y NBA, sin depender de descargar fotografías.

**Importante:** estos feeds incorporan noticias, **no** marcan automáticamente
el instante exacto en que terminó un partido o una carrera. El módulo de
resultados inmediatos necesita integrar APIs de datos con cuotas y credenciales:
tenis (ATP/WTA), golf (torneos y clasificación final), F1 (resultado oficial
de carrera) y NBA (marcador final/box score). No hay claves nuevas conectadas
ni publicación instantánea multideporte habilitada todavía.

## Pipeline

1. **bot.py** archives raw RSS titles.
2. **editorial.py** fetches verified-fresh news with actual RSS publication
   timestamps, scores importance, removes tracking parameters, deduplicates
   similar headlines, drafts text using Groq (preferred) or OpenAI (fallback). `graphics.py` genera 5 estilos originales 1080×1350: fichajes, partidos, selecciones, lesiones, actualidad. **Olé Argentina** y medios internacionales entre las fuentes.
3. **publisher.py** (opt-in) uploads images to Cloudinary with a signed request,
   creates an Instagram container via Meta Graph API, waits for its status, then
   publishes it. Supports Instagram Login and Facebook Login.
4. **GitHub Actions** runs automatically at minutes 7 and 37 of every hour,
   performs safety tests, uploads JPG previews, and commits the queue.
   A separate CI workflow tests code changes without calling paid APIs.

No unlicensed celebrity or team photos/logos are used.

### Fotos gratuitas y derechos de uso

El bot busca fotografías reales del protagonista en Wikimedia Commons,
Google Imágenes (solo descubrimiento con verificación posterior), Openverse
y Pixabay. Agrega `PIXABAY_API_KEY` como GitHub Actions Secret para habilitar
la búsqueda gratuita de Pixabay. Solo se aceptan resultados que nombren al
protagonista en los metadatos y cumplan las comprobaciones de resolución y
dominio. Se conserva el enlace de origen; el autor se acredita cuando aplica.

Google y Bing no son licencias: el bot no descarga fotos por aparecer en un
buscador. La generación con Replicate/FLUX está desactivada tanto en el
workflow como en el código editorial, aun si queda un token antiguo en Secrets.
Si ninguna fuente entrega una foto pertinente con derechos verificables, se
conserva una gráfica original para preview y la publicación queda retenida
para revisión. No se usan fotos genéricas para aparentar que muestran el evento.

### Actualización de noticias nuevas (23/11/2026)

- **Sin repetir protagonistas y titulares:** `news_novelty.py` compara contenido
  entre medios y entre inglés/español, aplica una ventana de **36 horas** para
  el mismo hecho/protagonista y permite otro evento si es claramente distinto
  (por ejemplo, una lesión frente a un gol posterior).
- **Primero lo reciente:** a la hora de seleccionar noticias, la novedad y
  el interés en Chile pesan antes que tener una foto fácil. «La roja» como
  sinónimo de tarjeta roja ya no se confunde con la selección de Chile.
- **Más medios chilenos:** `Cooperativa Deportes Chile` se sumó a RSS.
- **Más fotos pertinentes:** incorporamos Lamine Yamal (Bryan Berlin,
  CC BY-SA 4.0) y Eduardo Vargas (Voltmetro, CC BY-SA 4.0) al banco
  de retratos de Wikimedia. No se publica una fotografía de otro evento
  presentándola como imagen del partido actual.
- **Fotos sin costo de generación:** búsqueda en Wikimedia Commons, Openverse
  y Pixabay (requiere una clave API gratuita), con comprobaciones de identidad,
  licencia, dominio y resolución. Google sirve para descubrir archivos de
  Commons y la licencia se verifica en la fuente original.
- **Sin cargos de Replicate:** el workflow y el código editorial no invocan
  generación de imágenes. Sin una foto libre pertinente, se crea una gráfica
  original para preview y la noticia queda retenida para revisión.
- **Nunca inventar noticias:** Groq escribe titulares/captions únicamente
  sobre noticias RSS fechadas; el generador visual no crea hechos noticiosos.
  Las decisiones automáticas se guardan en `data/queue.json` y
  `data/engine_status.json`, con contadores de duplicados bloqueados.

### Diseño editorial V5 — sin fotos genéricas (23/11/2026)

- El feed ahora utiliza **fotografía real del protagonista**, ocupando toda
  la gráfica 1080×1350, degradado cinematográfico para leer el titular,
  marca discreta y una sola etiqueta de categoría.
- Eliminamos **«IMAGEN REFERENCIAL»**, «LA NOTICIA», canchas ajenas a la
  noticia, barras y lemas de relleno.
- Cuando no hay fotografía pertinente con derechos verificados, el bot **no
  publica esa noticia automáticamente**. Puede seguir apareciendo una
  gráfica abstracta original en previews internos, pero no en Instagram.
  Esta decisión privilegia calidad visual y puede reducir la frecuencia.
- Foto CC BY-SA: caption en una línea con **autor y licencia**; el archivo
  de la cola conserva los detalles completos de autoría, modificaciones,
  URL original y licencia (`portrait_info`, `photo_credit_full`).
- La automatización sigue funcionando sin cambiar tokens ni comprar servicios.

### Banco de fotos reales (V4)

`curated_portraits.py` incluye **12 protagonistas con archivos de Wikimedia Commons
y metadatos fotográficos/CC BY-SA verificados**. No usa API de búsqueda para esos
nombres, y construye el enlace de descarga de la imagen directamente desde el
nombre de archivo. Los enlaces de Commons se comprobaron al integrar cada foto.
Incluye Messi, Cristiano, Mbappé, Haaland, Infantino, Alexis Sánchez, Arturo Vidal,
Désiré Doué, Pochettino, Thiago Almada, Bruno Fernandes y Rayan Cherki.

Descarga en capas: original Wikimedia con Referer conforme, CDN oficial de
miniaturas y, si Wikimedia devuelve 429/5xx, proxy público `wsrv.nl` para
**ese mismo archivo previamente verificado**. El proxy no cambia autoría ni
licencia y no recibe secretos. Las imágenes CC BY-SA llevan autor, enlace
original y licencia explícitos; la gráfica derivada sigue la licencia
correspondiente. El modo foto no implica que la imagen muestre el evento actual.

Las previews no hacen búsquedas de fotos externas, evitando bloquear el
proceso de publicación. Solo se permite una nueva búsqueda dinámica por
ejecución; si no hay foto comprobable, se utiliza gráfica ilustrada propia.
La prueba de descarga real vive en `photo_probe.py` y deja resultados en
`data/photo_diagnostics.json`.

### Foto protagonista (V3)

El LLM sugiere el nombre exacto de la persona protagonista, y el sistema
exige que aparezca de manera explícita en el título RSS. Luego resuelve
su entidad futbolera única en Wikidata y examina la imagen P18 en Wikimedia
Commons. **Solo usa fotos con metadatos CC0, dominio público, CC BY o CC BY-SA verificables**;
las fotos CC BY o CC BY-SA llevan crédito del fotógrafo, enlace al archivo y a su licencia en el caption. Las gráficas derivadas de CC BY-SA se comparten bajo la misma licencia.
Si no aparece una imagen segura o la foto falla, muestra nuestro diseño
gráfico original. Nunca copia fotos de Google, agencias ni medios.

El sistema deja en la cola editorial los metadatos de la licencia y del
archivo para auditoría. No coloca el nombre del medio noticioso ni su URL
en el post o la gráfica. La disponibilidad de fotos de futbolistas actuales
sin atribución obligatoria es limitada: por eso **no todas las publicaciones
tendrán una foto**. Para ampliar cobertura, se necesitará contratar una
fototeca con derechos o aportar retratos autorizados.

Si el retrato principal en Wikidata no es reutilizable, el bot busca alternativas en Wikimedia Commons por el nombre completo del protagonista. Si Commons no responde o no devuelve una foto reutilizable, intenta Openverse: fotos Creative Commons de Flickr con nombre exacto, autor, licencia verificable y dominio de descarga permitido. Descarta imágenes de camisetas, murales, ilustraciones o personas diferentes. No descarga fotos aleatorias de Google. Nuevos titulares usan español simple, sin frases ambiguas y sin captions cortados por la mitad.

Las gráficas de fútbol usan composiciones 4:5, titular protagonista,
tratamiento editorial fotográfico y 5 acentos de categoría.


**Public-facing content:** Posts and graphic cards do **not** display source names
or raw news URLs. Source metadata is retained in the internal editorial queue for
verification, duplicate detection and auditability. Headlines and summaries must
be original paraphrases; this does not grant permission to copy publishers'
photographs or protected text.

**Volume:** target 60 posts/day, one every 30 minutes, plus 12 extra posts at
09:07–20:07 America/Santiago. This is a target rather than a guarantee: no
fabricated or recycled news to fill slots. Before each run, the bot queries the
account-specific Instagram publishing quota. If unavailable, a conservative
40-post rolling-24h fallback applies. No photo is required: original illustrated
cards are generated when a licensed real portrait is unavailable.

## Set up secrets

In your GitHub repository: Settings → Secrets and variables → Actions →
Repository secrets.

| Secret | Why |
| --- | --- |
| GROQ_API_KEY | Preferred text-generation key (GroqCloud free tier, usage limits apply) |
| OPENAI_API_KEY | Optional paid OpenAI fallback if Groq key is absent |
| PIXABAY_API_KEY | Optional free API key for licensed player-photo discovery |
| IG_USER_ID | Professional Instagram account ID |
| IG_ACCESS_TOKEN | Token with Instagram publishing access |
| CLOUDINARY_CLOUD_NAME | Media hosting destination |
| CLOUDINARY_API_KEY | Signed upload |
| CLOUDINARY_API_SECRET | Signed upload |

Repository **variables** (not secrets):

| Variable | Default | Description |
| --- | --- | --- |
| BRAND_NAME | CHAO FELICEVICH | Brand rendered on the cards |
| GROQ_MODEL | openai/gpt-oss-120b | Default Groq-hosted open-weight model |
| OPENAI_MODEL | gpt-4.1-mini | Optional OpenAI fallback model |
| MAX_DRAFTS_PER_DAY | 75 | Max new selected headlines and AI drafts/day |
| MAX_DRAFTS_PER_RUN | 5 | Max new candidates and Groq/OpenAI calls per execution |
| MORNING_POSTS_PER_RUN | (legacy) | No longer used by the half-hour scheduler |
| MORNING_MAX_POSTS | (legacy) | No longer used by the half-hour scheduler |
| POST_SPACING_SECONDS | 12 | Spacing between multiple posts in one run |
| ENABLE_AI_ART | false | Image generation is disabled in code and workflow |
| AI_ART_MAX_DAILY | 0 | No paid image generation |
| MAX_POSTS_PER_DAY | 60 | Hard local cap on Meta publication |
| ENABLE_PUBLISH | true | Publishing gate, configure variable false to pause |
| AUTO_APPROVE | true | Second gate, configure false to pause |
| META_GRAPH_VERSION | v27.0 | Meta Graph API version (pinned in workflow) |
| META_AUTH_MODE | facebook | Verified Unified Login / Facebook graph path |
| PUBLISH_TIMEZONE | America/Santiago | Local-time daily quota and publishing hours |

**To publish**, first verify the Instagram Business/Creator account, permissions,
tokens and Cloudinary. Inspect the drafts. Only then set BOTH
ENABLE_PUBLISH=true and AUTO_APPROVE=true.

Meta publication requires public image URLs. The publisher supports Instagram
Login (graph.instagram.com) and Facebook Login (graph.facebook.com); their
permissions and token types are different. See [SETUP_INSTAGRAM.md](SETUP_INSTAGRAM.md).
Publication can run **24 hours a day**. Scheduled jobs can be delayed by GitHub. The local date uses America/Santiago.

### Safety and limitations

- RSS feeds may be unavailable, unlicensed for redistribution, misleading, or
  missing timestamps. Missing-date and old stories are excluded from auto drafts.
- The selected LLM gets only the RSS title/summary: it is not independently fact-checking.
  Do not present rumors as confirmed transfers.
- API publishing errors are not automatically retried, to reduce duplicate risk.
- Stories with no meaningful RSS summary, mixed sports, old dates, or untrusted grades are excluded from the automatic feed.
- GitHub Actions scheduling is best effort, not a real-time news wire.
- GitHub JSON state is an MVP, **not an exactly-once publishing ledger**. For
  production-grade unattended volume, move queue and publication checkpoints
  to Postgres or another transactional store.
- Tokens and API keys MUST stay in GitHub Secrets, never source files.
- For a private repository, review GitHub Actions usage quotas.
- Groq has free-tier rate limits that can change; keep a budget/usage eye on it.
- OpenAI API usage is billed separately from ChatGPT Plus if you configure the fallback.
- Github Actions standard hosted runners are free in public repositories; Cloudinary Free includes 25 credits per rolling 30-day usage window (storage / transfer / transformations). See provider dashboards.
- **Never paste API keys into chats, README files or code**. If exposed, revoke and rotate them.

## Local run

~~~bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
python bot.py
python editorial.py
~~~

Files are saved to data/queue.json and output/previews/*.jpg.
