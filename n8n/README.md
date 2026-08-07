# n8n pipeline driver

`suncomply-145-pipeline.json` is the workflow that drives a case through the
platform when `PIPELINE_DRIVER=n8n`. A document upload fires the webhook and
the flow walks the case from intake to the CA review queue.

```
upload -> webhook -> extract -> classify -> checklist -> awaiting CA (human)
                        |
                        +-- low confidence or missing fields -> exception (human triage)
                        +-- document gaps -> pending documents (reminders chase)
```

## How responsibility is split

n8n sequences the steps. The platform enforces the rules. Every node on the
canvas is an HTTP call into `app/api/routes/internal.py`, which wraps the same
services the Celery driver uses. This matters:

- Part A to D classification comes only from `app/rules/classifier.py`. The
  canvas holds no copy of the rules, so it cannot drift from them.
- Tenant isolation, the state machine and the append only audit trail behave
  identically under either driver.
- Nothing this flow can call is able to certify or file a case. The service
  layer refuses, because those steps belong to the CA.
- Each step is state gated and returns 409 on the wrong state, so a retry or a
  duplicate delivery stops cleanly instead of running twice.

## Configuration

In the platform `.env`:

```
PIPELINE_DRIVER=n8n
N8N_WEBHOOK_URL=http://host.docker.internal:5678/webhook/suncomply-intake
INTERNAL_API_TOKEN=<48 hex character shared secret>
```

The token travels inside the webhook payload and n8n echoes it back on every
callback. The `/internal` endpoints reject any request without it.

If the webhook call fails because n8n is down or unreachable, the application
falls back to Celery and logs `n8n_dispatch_failed_falling_back_to_celery`. A
case never gets stuck in intake because the orchestrator is offline.

## Running n8n

```bash
docker run -d --name suncomply-n8n --restart unless-stopped \
  -p 5678:5678 \
  -e N8N_SECURE_COOKIE=false \
  -e GENERIC_TIMEZONE=Asia/Kolkata \
  --add-host host.docker.internal:host-gateway \
  -v suncomply_n8n_data:/home/node/.n8n \
  docker.n8n.io/n8nio/n8n
```

The editor is then at http://localhost:5678. Create the owner account on first
run before importing.

## Importing the workflow

```bash
docker cp n8n/suncomply-145-pipeline.json <container>:/tmp/wf.json
docker exec <container> n8n import:workflow --input=/tmp/wf.json
```

Note for n8n 1.12x and later: the CLI import does not create the row in
`workflow_history`, so the workflow cannot be activated and reports
"Active version not found". Two ways to fix it:

1. Open the workflow in the editor and toggle Active. Saving from the UI
   creates the version row.
2. Seed the row directly:

```bash
docker exec <container> sqlite3 /home/node/.n8n/database.sqlite "
INSERT OR REPLACE INTO workflow_history
  (versionId, workflowId, authors, createdAt, updatedAt, nodes, connections, name, autosaved, description)
SELECT versionId, id, 'import', datetime('now'), datetime('now'),
       nodes, connections, name, 0, ''
FROM workflow_entity WHERE id='suncomply145';"
```

## Exporting after edits

Edit on the canvas, then write the change back into the repository so the file
and the running flow stay in step:

```bash
docker exec <container> sh -c 'n8n export:workflow --id=suncomply145 --output=/home/node/.n8n/export.json'
docker cp <container>:/home/node/.n8n/export.json n8n/suncomply-145-pipeline.json
```

The exported file contains no credentials. The shared secret stays in `.env`
and is never written into the workflow.

## Checking that it is live

```bash
curl -X POST http://localhost:5678/webhook/suncomply-intake \
  -H "Content-Type: application/json" -d '{"ping":"check"}'
```

A 200 response means the webhook is registered and the workflow is active.
