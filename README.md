# Techcombank FY25 Results Assistant

A chat assistant that answers questions about Techcombank's FY25 (fiscal year ended 31 Dec 2025)
results, grounded exclusively in the official FY25 press release. It is deliberately not a
"paste the whole PDF into an LLM" solution and not a generic vector-database RAG stack — it's a
right-sized retrieval design built around where naive RAG actually breaks on *this* document. The
full reasoning is in [`SOLUTION.md`](./SOLUTION.md).

> **TODO (pending):** demo video — recorded last, once the rest of the submission (including the
> live deploy below) is finalized.

> **TODO (pending):** live URL — not deployed as of this write-up; `infra/bootstrap`'s apply is a
> manual one-time step (see "AWS deployment" below) that hasn't been run yet. It will be deployed
> before final submission and the URL shared here / in the demo video. It may be torn down
> afterward to control AWS cost — redeploying is a single `git push` to `main`, since the whole
> build → infra-apply → smoke-test pipeline is automated end to end.

---

## Quickstart (local, < 3 minutes)

```bash
git clone https://github.com/ngotoandev/tcb-fy25-chatbot.git
cd tcb-fy25-chatbot
cp .env.example .env        # pick a provider (see below)
docker compose up --build   # ~2 min build (frontend + backend, one multi-stage image)
```

Then open **http://localhost:8080** — the FastAPI container serves both the API and the built
React SPA.

**Pick a provider in `.env`** (`LLM_PROVIDER`) — the LLM layer is pluggable, so a reviewer can run
real answers whichever key they have:

| `.env` setting | What runs |
|---|---|
| `MOCK_LLM=true` | No credentials at all — canned deterministic replies, full clickable UI. For inspecting the product without provisioning anything. |
| `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY=…` | **Real answers via Claude, no AWS needed.** Retrieval is BM25-only (Anthropic has no embeddings API); metric answers are exact-lookup and unaffected. |
| `LLM_PROVIDER=openai` + `OPENAI_API_KEY=…` | Real answers via GPT (BM25-only, same as above). |
| `LLM_PROVIDER=bedrock` + AWS creds (us-east-1, Bedrock enabled) | Full path: Nova on Bedrock + Titan embeddings (hybrid BM25 + vector retrieval). |

Nothing needs to be built or ingested before this works: `data/artifacts/` (chunks, hand-verified
metrics, glossary, embeddings) is pre-built and committed to the repo, and gets baked into the
image by the `Dockerfile`. Rebuilding those artifacts from the source PDF — only needed if the
source document itself changes — is `make ingest` (requires Bedrock, for the embeddings step
only).

---

## Architecture

```mermaid
flowchart LR
    subgraph buildtime [Build time - ingestion pipeline]
        PDF[FY25 press release PDF] --> P[parse and section-aware chunk]
        P --> C[chunks.json]
        P --> M[metrics.json - hand-verified]
        P --> G[glossary.json]
        C --> E[Titan Embeddings V2] --> V[embeddings.npz]
    end

    subgraph runtime [Runtime - one Fargate container]
        UI[React chat SPA] --> API[FastAPI]
        API --> R{Router - Nova Lite}
        R -->|metric| MS[Structured metric lookup]
        R -->|narrative| H[Hybrid retrieval BM25 + cosine]
        R -->|hybrid| MS & H
        R -->|chitchat / out-of-scope| DIRECT[No retrieval]
        MS --> A[Answer model: Nova Lite simple / Nova Pro analytical]
        H --> A
        DIRECT --> A
        A --> UI
        API <--> S[(SessionStore: DynamoDB on AWS / in-memory local)]
    end

    V -.baked into image.-> API
    C -.-> API
    M -.-> API
    G -.-> API
```

This 14-page document yields 25 section-aware narrative chunks across pages 1–11 (pages 12–14 —
the acronym glossary, the financial summary table, and a blank closing page — are deliberately
*not* chunked as narrative; see `SOLUTION.md` §1). In-process hybrid search (numpy cosine + BM25)
over 25 chunks is exact, sub-5ms, and needs zero extra infrastructure — a vector database here
would be solving a problem this corpus doesn't have. `SOLUTION.md` §4 names the graduation path
(Bedrock Knowledge Bases / OpenSearch) and the trigger for when that stops being true.

---

## Repo map

- **`backend/`** — FastAPI service: config, request/response models, `api/chat.py`, and the
  pipeline services (`router_svc`, `retrieval`, `metrics_store`, `llm`, `answerer`), plus
  pluggable session stores (in-memory / DynamoDB).
- **`frontend/`** — React + TypeScript + Vite + Tailwind chat SPA: message thread, citation
  chips, route/model badges, session persistence.
- **`ingest/`** — build-time pipeline (not run at request time): PDF parsing, section-aware
  chunking, hand-verified metrics/glossary extraction, Titan embeddings.
- **`data/artifacts/`** — the pipeline's output, committed to the repo: `chunks.json`,
  `metrics.json`, `glossary.json`, `embeddings.npz`. Baked into the Docker image so the app boots
  with zero Bedrock dependency.
- **`reports/`** — the source FY25 press release (PDF + parsed text) — public on
  techcombank.com.
- **`infra/bootstrap/`** — one-time, hand-applied Terraform: state bucket, GitHub OIDC provider +
  CI role, ECR repo.
- **`infra/main/`** — CI-applied Terraform: VPC, ALB, ECS Fargate service, DynamoDB sessions
  table, CloudWatch logs, AWS Budget alert.
- **`.github/workflows/`** — `deploy.yml` (push to `main`) and `pr.yml` (tests + `terraform
  plan`).
- **`tests/`** — pytest suite: unit/integration (no AWS) plus the golden-eval suite (opt-in,
  needs Bedrock — see `SOLUTION.md` §5).
- **`docs/superpowers/`** — the design spec and implementation plan this project was built from.
- **`Dockerfile`, `docker-compose.yml`** — multi-stage build (frontend → static assets, backend →
  FastAPI) and the single-command local run.
- **`Makefile`** — `make ingest` / `dev` / `test` / `evals`.
- **`pytest.ini`, `requirements-dev.txt`** — test configuration and dev-only dependencies.

---

## AWS deployment

One-time bootstrap — creates the Terraform state bucket, the GitHub OIDC role CI assumes, and the
ECR repo. Applied once by hand, never by CI:

```powershell
terraform -chdir=infra/bootstrap init
terraform -chdir=infra/bootstrap apply -var "github_repo=ngotoandev/tcb-fy25-chatbot"
```

Type `yes`, then record the three outputs (`ci_role_arn`, `tfstate_bucket`, `ecr_repo_url`).

Then, in the repo's **Settings → Secrets and variables → Actions**, set these **Variables**:

- `AWS_ROLE_ARN` = the `ci_role_arn` output
- `TFSTATE_BUCKET` = the `tfstate_bucket` output
- `ALERT_EMAIL` = an email address for the budget alert
- `LLM_PROVIDER` = `bedrock` (default; Nova + Titan) — **or** `anthropic` / `openai` to deploy on a
  direct vendor API when Bedrock isn't available. Non-`bedrock` runs BM25-only retrieval.

And, **only if `LLM_PROVIDER` is `anthropic` or `openai`**, add one **Secret**:

- `LLM_API_KEY` = your Anthropic (or OpenAI) API key. CI passes it to Terraform, which stores it in
  Secrets Manager and injects it into the ECS task as a secret env var — it's never placed in the
  task definition or committed. (When `LLM_PROVIDER=anthropic`, the CI embeddings-guard is skipped
  since BM25-only needs no Titan vectors, so the committed placeholder `embeddings.npz` is fine.)

From there, deployment is fully automated: **push to `main` → the pipeline deploys.**
`.github/workflows/deploy.yml` runs on every push to `main` (and on manual dispatch): `test`
(pytest + frontend build + `terraform fmt`/`validate`) → `build-and-push` (Docker image → ECR,
tagged with the git SHA) → `terraform-apply` (OIDC-authenticated `terraform apply` against
`infra/main`) → `smoke-test` (waits for the ECS service to stabilize, polls `/api/health`, then
posts one real chat question to the live ALB and asserts the reply is grounded — contains the
correct FY25 PBT figure, not just a 200 status) → `deployment-status`. Pull requests run the
lighter `pr.yml`: tests + `terraform plan` only, no apply.

No AWS credentials are stored as GitHub secrets — the CI role is assumed via OpenID Connect
(`infra/bootstrap`'s `aws_iam_openid_connect_provider` + a trust policy scoped to
`repo:ngotoandev/tcb-fy25-chatbot:*`).

---

## Testing

```bash
pytest                 # unit + integration — no credentials needed
# golden evals against a LIVE provider — set LLM_PROVIDER + key in .env, then load it:
set -a; . ./.env; set +a && pytest -m eval -s
```

The eval suite was last run **15/15** on the Anthropic provider (Claude Haiku/Sonnet) — see
[`docs/eval-results.md`](docs/eval-results.md). It runs against whatever `LLM_PROVIDER` (+ key) is
set; on `bedrock` it additionally exercises the Titan/vector retrieval path.

`pytest` runs the unit/integration suite (40 tests as of this writing) with the LLM mocked or
bypassed entirely: PDF chunker boundaries, metric alias/period matching, hybrid-retrieval RRF
fusion (including its out-of-vocabulary fallback path), router JSON parsing, the Bedrock client's
retry/backoff logic, and the `/api/chat` pipeline end-to-end via `MOCK_LLM`. None of it touches a
real AWS account.

`pytest -m eval` is opt-in — excluded by default via `pytest.ini`'s `addopts = -m "not eval"` —
and is designed to hit live Bedrock for a 15-case golden suite (exact-metric questions, narrative
questions, a multi-turn follow-up chain, and out-of-scope refusal traps). As of this write-up the
suite is fully specified but not yet implemented as runnable test files — both wait on Bedrock
model access for this AWS account; see `SOLUTION.md` §5 for the full design and the current
status.

CI runs the non-eval half automatically on every push/PR (`test` job: pytest + frontend build +
`terraform validate`/`fmt`), plus a live **smoke test** post-deploy that hits the real ALB —
`curl /api/health`, then one real `/api/chat` question with an assertion that the reply is
grounded, not just that it returns 200.
