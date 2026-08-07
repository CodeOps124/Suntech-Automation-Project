# SunComply 145

Workflow automation for Form 145 and Form 146 filings, formerly 15CA and 15CB.
Built by Suntech Business Solutions for chartered accountancy firms.

Every time an Indian business pays a foreign vendor, a filing is required. The
clerical work around that filing is repetitive and error prone: reading the
invoice, checking the vendor, working out the tax path, chasing missing
paperwork, assembling the pack the bank will accept. SunComply does that work.

The certification itself stays with the CA. The platform prepares the case and
stops at the review queue. A CA reviews it, signs with a digital signature and
records the UDIN. That step is never automated.

## What it does

| Stage | Handled by |
| --- | --- |
| Intake of the invoice and supporting documents | Platform |
| Data extraction with a confidence score | Platform |
| Part A to D tax classification | Platform, deterministic rules |
| Document checklist and follow up reminders | Platform |
| Review pack assembly | Platform |
| Certification with DSC and UDIN | The CA, always |
| Filing on the government portal | The client or the CA |
| Bank ready PDF pack | Platform |

## Running it

```bash
cp .env.example .env
docker compose up -d --build
docker compose run --rm api alembic upgrade head
docker compose run --rm api python -m scripts.seed
```

Open http://localhost:8000 and sign in.

The seed script creates a demo workspace with three users. All of them use the
password `suntech123`:

| Email | Role | Can certify |
| --- | --- | --- |
| admin@suntech.example | Admin | Yes |
| priya@suntech.example | Analyst | No |
| ramesh@suntech.example | CA reviewer | Yes |

Other services: API reference at http://localhost:8000/docs, object storage
console at http://localhost:9001 with `minioadmin` and `minioadmin`.

To run the tests without any infrastructure:

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -e ".[dev]"
pytest
```

## Seeing the automation work

Sign in and open **Live Demo** in the sidebar, then press Run. It creates a
real client, vendor and case in your workspace, uploads a generated invoice and
follows the case through extraction and classification until it reaches the CA
queue. Nothing on that screen is simulated. A typical run finishes in three to
five seconds.

To do it by hand instead: **New Remittance**, fill in the amount and vendor,
attach an invoice, then watch the case detail page. The audit timeline updates
as each stage completes.

## Screens

| Screen | Purpose |
| --- | --- |
| Dashboard | Daily counts, plan usage, the case pipeline, live automation activity |
| E-Invoices | Every document received across all cases, with confidence scores and download |
| Cases | The full case list with status filters |
| New Remittance | Open a case and optionally attach the invoice in one step |
| Clients and Vendors | The firm directory |
| Live Demo | Runs a real case end to end |
| Settings | Profile, workspace plan, automation configuration, theme |

## How it is built

Python 3.12 and FastAPI for the API and the web application. PostgreSQL for
storage, with row level security as the tenant boundary. Redis and Celery for
background work. Any S3 compatible object store for documents, MinIO in
development. Alembic for migrations. n8n optionally drives the pipeline in
place of Celery.

| Path | Contents |
| --- | --- |
| `app/core/` | Settings, logging, security, domain constants |
| `app/db/` | Database engine and the tenant scoped session helpers |
| `app/models/` | Firms, users, clients, vendors, cases, documents, events, rule versions |
| `app/rules/classifier.py` | The Part A to D rules engine |
| `app/services/` | State machine and audit, classification, checklist, cases, billing, bank pack |
| `app/workers/` | Celery application, extraction providers, pipeline tasks, reminders |
| `app/api/` | HTTP routes |
| `app/web/static/` | The web application |
| `alembic/versions/` | Database migrations |
| `n8n/` | The n8n pipeline workflow and its notes |
| `scripts/seed.py` | Demo workspace data |
| `tests/` | Test suite, no database required |

## Rules that the code enforces

These are not conventions. Each one is enforced somewhere a mistake would be
caught rather than merely discouraged.

**Certification stays human.** `transition()` raises if automation tries to move
a case into certified or filed. The certify endpoint requires a DSC reference,
a UDIN and a reviewer role.

**Classification is deterministic.** `app/rules/classifier.py` is a pure
function with no database or network access. Every result records the rule
version that produced it, and every case stores its reason codes.

**Tenants cannot see each other.** Migration `0002` enables forced row level
security keyed on a session variable. The application connects as a restricted
role that cannot bypass it, and the API refuses to start in production if that
role turns out to be privileged.

**The audit trail cannot be rewritten.** A database trigger blocks updates and
deletes on `case_events`.

**Certification fees are never billed through the platform.**
`app/services/billing.py` raises on any attempt to add a line item for a CA
fee, UDIN generation, bank charges, exchange spread or a tax opinion.

## Before production

The build is complete and works end to end. These items are deliberately open
and should be closed before the platform handles real filings.

- Sign in issues a signed token, but route authorisation still relies on the
  workspace header. Token verification needs to move into a dependency that
  every route uses.
- Document extraction runs against a deterministic stub. Connect a real
  document AI provider in `app/workers/ocr.py`.
- Reminders are recorded in the audit trail but not yet sent. Connect an email
  or messaging provider in `send_document_reminders`.
- Amounts in foreign currency are compared against rupee thresholds without
  conversion. This pushes borderline cases toward CA review rather than away
  from it, which is the safe direction, but it needs a rate source.
- The demo password is shared across seeded users. Real deployments need a
  password policy and an invitation flow.
- Run the application as a non superuser database role. The development compose
  file uses a privileged role for convenience and warns at startup.

## Out of scope

The platform does not sign or submit anything on the government portal, hold
client funds, act as a payment aggregator, or produce tax opinions. It prepares
the filing. People with the authority to do so complete it.
