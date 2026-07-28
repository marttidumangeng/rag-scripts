# Cursor Automation (v2) — Robot Research Agent

Use this after validating the manual Cursor agent workflow from `.cursor/skills/robot-research-agent/SKILL.md`.

**Before prod import:** follow [docs/checklists/prod-manufacturer-import.md](docs/checklists/prod-manufacturer-import.md). For catalog OEMs, start with [docs/playbooks/catalog-oem-import.md](docs/playbooks/catalog-oem-import.md).

## Recommended automation (fully automated)

| Setting | Value |
|---------|-------|
| **Name** | Robot DB weekly backfill |
| **Trigger** | Schedule — weekly (e.g. Monday 09:00 UTC) or manual |
| **Tools** | Shell |
| **Repo** | `robot-ai-geek` |

### One-time runner setup

```bash
pip install -r scripts/research/requirements.txt
pip install playwright && playwright install chromium   # HubSpot/SPA image extraction
```

Add to `robotaigeek-server/.env`:

```env
IMPORT_SYNC_API_BASE_URL=http://127.0.0.1:8000/api/v1/
IMPORT_SYNC_API_KEY=...
RESEARCH_CREATED_BY_ID=1
RESEARCH_USE_PLAYWRIGHT=true
```

## Prompt (automated pipeline)

```
Load the robot-research-agent skill.

From robotaigeek-server/ (venv active):

1. python manage.py research_agent backfill next-company
2. Note company id from output. If none, stop.
3. python manage.py research_agent backfill apply-company --file ../scripts/research/staging/companies/{slug}.json --apply
   (skip if company staging not ready)
4. python manage.py research_agent auto pipeline --company-id {ID} --apply-import --created-by-id 1
   (add --stealth or --playwright only if plain fetch fails — see robot-research-agent skill)
5. python manage.py research_agent state mark --type company --id {ID}

Post summary from staging/reports/{run_id}.md
```

This replaces manual per-robot JSON writing — `auto pipeline` crawls official sites for images, YouTube URLs, and specs.

## Legacy prompt (manual staging)

```
1. Run: python scripts/research/cli.py backfill next-company
2. Research missing fields from official sources only.
3. Write scripts/research/staging/companies/{slug}.json
4. Run: python scripts/research/cli.py backfill robots --company-id {id}
5. python manage.py research_agent auto robots --company-id {id} --playwright
6. Validate: python scripts/research/cli.py validate --dir scripts/research/staging/robots/{slug}/
7. python manage.py research_agent import --dir ... --patch --apply --created-by-id 1
```

## Safety

- Default import status: `pending_review`
- Use `--patch` for backfill (default in `auto pipeline`)
- Cap companies per run to 1 in scheduled automation
