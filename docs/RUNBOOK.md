# Runbook — internal beta operations

Audience: whoever operates the deployment (today: the project owner). Everything here
is designed to be executable from a clean machine with Docker and this repository.

## 1. Local acceptance stack (default, D-011)

```bash
(umask 077; touch .env; grep -q '^POSTGRES_PASSWORD=.' .env || printf 'POSTGRES_PASSWORD=%s\n' "$(openssl rand -hex 24)" >> .env) && docker compose up --build
```

Then add to the ignored `.env` (see `.env.example`):

- `OPENROUTER_API_KEY` — required for real research runs.
- `OPENROUTER_MODELS` / `ALLOW_PAID_MODELS` — D-008 model policy.

Bootstrap the first admin (no password ever touches a shell command):

```bash
docker compose exec api jacaranda-invite --role admin
```

Open <http://localhost:3000>, register with the printed code, then mint further
invites from 邀请码管理 (admin menu). Roles: member (create/run/edit), reviewer
(verify/approve/reject), admin (invites).

## 2. Server deployment

Prerequisites: a small VPS with Docker, a DNS record pointing at it, ports 80/443 open.
If members are mainland-China side, first verify AKShare endpoints and OpenRouter are
reachable from the box.

```bash
git clone https://github.com/eggy1011/jacaranda-research-os.git && cd jacaranda-research-os
umask 077 && printf 'POSTGRES_PASSWORD=%s\nSITE_ADDRESS=research.example.org\nOPENROUTER_API_KEY=...\nAPP_ENV=production\n' > .env
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose exec api jacaranda-invite --role admin
```

Caddy provisions TLS automatically for `SITE_ADDRESS`. Database/Redis/API/web are not
published on the host in the prod overlay; Caddy is the only entry point.

### Release / rollback

- Deploys are tagged: `git tag beta-YYYYMMDD && git push --tags` before `up -d --build`.
- Rollback: `git checkout <previous-tag>` then rebuild. If a migration must be undone:
  `docker compose exec api alembic -c alembic.ini downgrade -1` **before** checking out
  the older code.
- The API container runs `alembic upgrade head` on every start; migrations are additive
  and idempotent.

## 3. Backup and restore

Nightly cron on the server (adjust paths):

```bash
docker compose exec -T postgres pg_dump -U postgres jacaranda | gzip > /backups/db-$(date +%F).sql.gz
docker run --rm --volumes-from "$(docker compose ps -q api)" -v /backups:/backups alpine tar czf /backups/data-$(date +%F).tar.gz /data
```

Copy `/backups` off the machine (rclone to any object storage). Retain 14 days.

**Restore drill** (run at least once before inviting members):

```bash
docker compose down && docker volume rm jacaranda-research-os_postgres_data jacaranda-research-os_app_data
docker compose up -d postgres && gunzip -c /backups/db-<date>.sql.gz | docker compose exec -T postgres psql -U postgres jacaranda
docker run --rm -v jacaranda-research-os_app_data:/data -v /backups:/backups alpine tar xzf /backups/data-<date>.tar.gz -C /
docker compose up -d
```

Acceptance: a previously generated research package opens in the web UI and its PPTX
downloads intact.

## 4. Monitoring

- Uptime: point a free checker (e.g. UptimeRobot) at `https://<site>/api/health`.
- Errors: `docker compose logs -f api worker` (structured stdout). Sentry can be added
  later by setting DSNs in the api/web environments — not required for the beta.
- Job health: the run page shows per-stage progress; a run stuck in `queued` means the
  worker is down (`docker compose ps`, `docker compose restart worker`).

## 5. Incident quick reference

| Symptom | Action |
|---|---|
| Run fails at `01-extraction` with `llm_configuration_error` | `OPENROUTER_API_KEY` missing/invalid in `.env`; fix and Retry (resumes from checkpoint) |
| Run fails with `llm_rate_limited` repeatedly | Add more candidates to `OPENROUTER_MODELS`; consider `ALLOW_PAID_MODELS=true` (D-008 budget applies) |
| `08-pdf-export` stage failed | LibreOffice missing in image (rebuild) or conversion crash; PPTX is still available; Retry re-exports |
| Quote/financials unavailable | AKShare upstream flake; Retry later — the evidence stage is checkpointed |
| Disk filling up | Old runs under `/data/artifacts/<run-id>` can be deleted; packages live in Postgres |

## 6. Security notes

- All provider keys live in the server-side `.env`; the browser only ever sees the
  same-origin proxy. Never add `NEXT_PUBLIC_` provider settings.
- Sessions are httpOnly cookies backed by DB rows; delete a row in `sessions` to force
  sign-out. Deactivate a user by setting `users.is_active=false`.
- Invite codes and session tokens are stored as SHA-256 digests only.
- Mock packages can never be approved — enforced at the API and renderer layers.
