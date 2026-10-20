# MediVision AI — MRI research workflow

This is a deployable **research prototype foundation**, based on the project scope recorded in `medivision_ai_conversation_archive.md`. The archive itself says earlier project details are a retained summary rather than a verbatim specification. Where it describes the project, this implementation follows the later MRI-only scope, a human-reviewed report workflow, and a free/local-first deployment approach.

## Implemented

- FastAPI service with request validation, bounded upload sizes, paginated case listing, health/readiness endpoints, and bearer API-key protection for data endpoints.
- Persistent SQLAlchemy case and report state, Alembic schema migrations, PostgreSQL deployment, and SQLite for local development.
- Revision/version increments and append-only workflow audit events when drafts are saved, returned, or signed.
- MRI-region validation for brain, spine, knee, and other; image formats accepted for metadata validation: DICOM, NIfTI, PNG, and JPEG.
- Browser workspace for entering manual drafts and recording the review workflow.
- Docker image runs as a non-root user; Compose includes a health-checked PostgreSQL service and only publishes the API on localhost by default.

The upload endpoint counts file bytes and retains only file format and size metadata. It **discards the image contents**. No image interpretation, ML inference/training, AI report drafting, RAG, automated verification, or urgency detection is wired into this build. The only report text is entered by the user. Urgency is always marked **not assessed**.

## Local development

Requires Python 3.11 or newer. In PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:APP_ENV = "development"
$env:DATABASE_URL = "sqlite:///./data/medivision.db"
$env:API_KEY = "development-only-change-me"
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\uvicorn.exe backend.app:app --reload
```

Open <http://127.0.0.1:8000>. Enter the development API key in the workspace connection field. The health endpoints are `/api/health` and `/api/ready`; interactive API docs are at `/docs`.

For the test suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

For development, the application can create its SQLite schema at startup. Alembic migrations are the recommended schema-management path and are required for production.

## Docker deployment

Install Docker Desktop, then create a private `.env` file from `.env.example`. Set unique random secrets; do not use the development default. For example, in PowerShell:

```powershell
Copy-Item .env.example .env
$apiKey = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
$dbPassword = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
(Get-Content .env) -replace '^API_KEY=.*$', "API_KEY=$apiKey" | Set-Content .env
Add-Content .env "MEDIVISION_API_KEY=$apiKey"
Add-Content .env "POSTGRES_PASSWORD=$dbPassword"
docker compose up --build
```

Then visit <http://127.0.0.1:8000> and enter `MEDIVISION_API_KEY` as the workspace access key. PostgreSQL persists data in the Compose-managed `postgres_data` volume. Schema migrations run before the API starts.

The included Compose deployment intentionally binds to localhost. Before exposing it to a network, place it behind a properly configured TLS-terminating reverse proxy and an organization-managed identity/access layer. The shared bearer key is a prototype access gate, **not individual authentication or radiologist credential verification**. Do not upload identifiable patient data.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENV` | `development` | `development`, `test`, or `production`; production refuses short/default API keys |
| `DATABASE_URL` | `sqlite:///./data/medivision.db` | SQLAlchemy connection URL; PostgreSQL is used by Compose |
| `API_KEY` | development-only key | Shared bearer key for `/api/*` except health/readiness probes |
| `MAX_UPLOAD_BYTES` | `104857600` | Maximum total file content per case (100 MiB) |
| `UPLOAD_FILE_LIMIT` | `20` | Maximum files per case |

The upload proxy/server must enforce a compatible request-size limit as well. The app does not persist scan files.

## Scope from the project archive

- **MRI-only**: the archive explicitly records MRI-only scope and exclusion of X-rays/chest-X-ray datasets, even though the presentation title mentions both MRI and X-ray.
- **Body-region-specific model routing**: regions are recorded, but no modality/region model is configured or implied to exist.
- **Dataset and model**: BraTS, UTSW-Glioma, UPENN-GBM, fastMRI knee, and PRETREAT-MetsToBrain-Masks are listed in the archive as candidate research datasets, not downloaded or included here. They have different labels and licensing/usage conditions; they are not interchangeable and do not all include paired radiology reports. No dataset was included in the source folder, so no model was trained.
- **Agent/RAG/LLM**: Chroma, local embeddings, Ollama and an agent pipeline are project ideas in the summary, not runnable dependencies or verified components in this build. No external or local model is called.
- **Evaluation**: BLEU, ROUGE-L, METEOR and BERTScore were suggested in the summary. These do not alone establish clinical accuracy; there are no reference reports or validation results in this folder, so no scores are claimed.
- **Safety**: there is no automatic triage or clinical decision support. A typed reviewer name and shared key are not a verified clinical sign-off. This research prototype is not a certified device and must not be used for diagnosis, treatment, or unsupervised care.

## Production-readiness boundary

The Compose stack is suitable for deploying an isolated software demonstration, not for clinical deployment or storing identifiable health records. A real clinical service additionally requires individually authenticated and authorized users, verified reviewer credentials, security/privacy and retention controls, encrypted storage and backups, threat modeling, monitoring, incident response, clinical validation on appropriately licensed datasets, bias/performance evaluation, and applicable institutional/regulatory approvals. These are not provided by this repository.
