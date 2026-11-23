# Football News Bot

Python RSS football news collector. It **does not publish to Instagram yet**.

## Local run

```bash
pip install -r requirements.txt
python bot.py
```

Collected headlines are saved to `data/news.json` with `pending_review` status. The GitHub Actions workflow also runs every 30 minutes (GitHub may delay scheduled jobs). Trigger manually from Actions > Collect football news > Run workflow.

## Next steps

1. Add editorial ranking and source verification.
2. Generate original graphic templates.
3. Configure Meta Instagram professional-account API and secrets.
4. Add explicit approval and dry-run tests before enabling publishing.

**Never commit API tokens or passwords.** RSS availability and reuse rights vary by publisher.
