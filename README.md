# Fútbol al Día — automated football newsroom

Python-first system for collecting fresh football headlines and preparing
original Spanish Instagram posts. Designed for 20–30 high-quality posts per day
when there is enough real news, **not** made-up content to hit a quota.

## Current status: safe preview mode

No Instagram publishing and no OpenAI API charges by default.

- Run history: **Actions → Football News Engine**
- Image previews: latest workflow run → **Artifacts → football-news-previews**
- Raw RSS archive: data/news.json
- Editorial queue: data/queue.json

By default, preview cards use the **original RSS headline** and status
awaiting_ai. When OPENAI_API_KEY is configured, cards use Spanish headlines and
short captions grounded ONLY in the RSS title and summary.

## Pipeline

1. **bot.py** archives raw RSS titles.
2. **editorial.py** fetches verified-fresh news with actual RSS publication
   timestamps, scores importance, removes tracking parameters, deduplicates
   similar headlines, drafts text using OpenAI (optional), and generates original
   1080×1350 JPEGs with Pillow.
3. **publisher.py** (opt-in) uploads images to Cloudinary with a signed request,
   creates an Instagram container via Meta Graph API, waits for its status, then
   publishes it.
4. **GitHub Actions** runs automatically at minutes 11 and 41 of every hour,
   performs all automated tests, uploads JPG previews, and commits the queue.

No unlicensed celebrity or team photos/logos are used.

## Set up secrets

In your GitHub repository: Settings → Secrets and variables → Actions →
Repository secrets.

| Secret | Why |
| --- | --- |
| OPENAI_API_KEY | Optional Spanish copywriting; paid OpenAI API usage |
| IG_USER_ID | Professional Instagram account ID |
| IG_ACCESS_TOKEN | Token with Instagram publishing access |
| CLOUDINARY_CLOUD_NAME | Media hosting destination |
| CLOUDINARY_API_KEY | Signed upload |
| CLOUDINARY_API_SECRET | Signed upload |

Repository **variables** (not secrets):

| Variable | Default | Description |
| --- | --- | --- |
| BRAND_NAME | FÚTBOL AL DÍA | Brand rendered on the cards |
| OPENAI_MODEL | gpt-4.1-mini | JSON-capable text model |
| MAX_DRAFTS_PER_DAY | 30 | Max new selected headlines and AI drafts/day |
| MAX_DRAFTS_PER_RUN | 3 | Max new candidates and OpenAI calls per execution |
| MAX_POSTS_PER_DAY | 30 | Hard local cap on Meta publication |
| ENABLE_PUBLISH | false | First switch for real Instagram publication |
| AUTO_APPROVE | false | Second independent switch |
| META_GRAPH_VERSION | v24.0 | Meta Facebook-Login Graph API version |

**To publish**, first verify the Instagram Business/Creator account, permissions,
tokens and Cloudinary. Inspect the drafts. Only then set BOTH
ENABLE_PUBLISH=true and AUTO_APPROVE=true.

Meta publication requires public image URLs. This system supports the
professional-account Facebook Login API route. Instagram-Login-only setups
may require different permissions/host configuration.

### Safety and limitations

- RSS feeds may be unavailable, unlicensed for redistribution, misleading, or
  missing timestamps. Missing-date and old stories are excluded from auto drafts.
- OpenAI gets only the RSS title/summary: it is not independently fact-checking.
  Do not present rumors as confirmed transfers.
- API publishing errors are not automatically retried, to reduce duplicate risk.
- GitHub Actions scheduling is best effort, not a real-time news wire.
- GitHub JSON state is an MVP, **not an exactly-once publishing ledger**. For
  production-grade unattended volume, move queue and publication checkpoints
  to Postgres or another transactional store.
- Tokens and API keys MUST stay in GitHub Secrets, never source files.
- For a private repository, review GitHub Actions usage quotas.
- OpenAI API usage is billed separately from ChatGPT Plus.

## Local run

~~~bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
python bot.py
python editorial.py
~~~

Files are saved to data/queue.json and output/previews/*.jpg.
