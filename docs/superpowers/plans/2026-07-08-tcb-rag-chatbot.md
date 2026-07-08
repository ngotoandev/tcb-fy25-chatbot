# TCB FY25 RAG Chatbot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the take-home: a grounded FY25-results chatbot (FastAPI + React) on AWS ECS Fargate, deployed by Terraform via GitHub Actions, in 48h.

**Architecture:** Build-time ingestion splits the press release into narrative chunks (hybrid BM25+vector retrieval), a hand-verified structured metrics store (exact number lookups), and a glossary (acronym expansion). At runtime a Haiku router classifies intent & rewrites follow-ups; answers come from Haiku (simple) or Sonnet (analytical) with strict grounding, page citations, and refusals. One container serves API + SPA.

**Tech Stack:** Python 3.12, FastAPI, boto3 (Bedrock Converse), numpy, rank-bm25, pdfplumber (ingest only), React 19 + TypeScript + Vite 7 + Tailwind 4, Terraform ≥ 1.10 (AWS provider ~> 6.0), GitHub Actions with OIDC.

## Global Constraints

- Region: **us-east-1** for all AWS resources and Bedrock calls.
- Model IDs (Bedrock cross-region inference profiles):
  - Router + simple answers + judge: `us.anthropic.claude-haiku-4-5-20251001-v1:0`
  - Analytical answers: `us.anthropic.claude-sonnet-4-5-20250929-v1:0`
  - Embeddings: `amazon.titan-embed-text-v2:0` (1024-d, normalized)
- Resource name prefix: `tcb-chatbot`. Container/service port: **8000**; local compose maps **8080**.
- LLM temperature ≤ 0.2 everywhere; retrieval `top_k = 6`.
- No long-lived AWS secrets in the repo or GitHub: CI authenticates via **OIDC** only. Local `.env` is gitignored.
- `data/artifacts/*` (chunks/metrics/glossary/embeddings) are **committed** and baked into the image; the app never calls Bedrock at startup.
- `pytest` from repo root must pass **without AWS credentials** (evals are opt-in via `-m eval`).
- The image must boot and serve the UI with zero AWS credentials when `MOCK_LLM=true`.
- Python imports: backend code imported as `app.*`, ingest as `ingest.*` (root `pytest.ini` sets `pythonpath = backend .`).
- Commit after every task (messages given per task). Never commit `.env`, tfstate, or the assignment PDF (`requirements/` is gitignored).

## File Structure (final)

```
.github/workflows/deploy.yml, pr.yml
Makefile  pytest.ini  requirements-dev.txt  docker-compose.yml  Dockerfile  .dockerignore  .env.example
reports/fy25-press-release-eng-12022026.pdf      # source (already committed)
data/artifacts/{chunks.json, metrics.json, glossary.json, embeddings.npz}
ingest/{__init__.py, parse.py, chunker.py, metrics_data.py, glossary_data.py, embed.py, run.py, requirements.txt}
backend/requirements.txt
backend/app/{__init__.py, main.py, config.py, models.py}
backend/app/api/{__init__.py, chat.py}
backend/app/services/{__init__.py, llm.py, retrieval.py, metrics_store.py, router_svc.py, answerer.py, pipeline.py}
backend/app/stores/{__init__.py, base.py, memory.py, dynamo.py}
frontend/{package.json, vite.config.ts, tsconfig.json, index.html}
frontend/src/{main.tsx, App.tsx, api.ts, types.ts, index.css}
frontend/src/components/{Chat.tsx, Message.tsx, Composer.tsx}
infra/bootstrap/{main.tf, variables.tf, outputs.tf}
infra/main/{backend.tf, providers.tf, variables.tf, vpc.tf, alb.tf, ecs.tf, iam.tf, dynamodb.tf, s3.tf, budget.tf, outputs.tf}
tests/{test_chunker.py, test_metrics_store.py, test_retrieval.py, test_router_parsing.py, test_sessions.py, test_api_chat.py}
tests/evals/{golden.yaml, test_evals.py}
README.md  SOLUTION.md
```

Phase → schedule map: Phase 0 = H0–3 · Phase 1 = H3–12 · Phase 2 = H12–24 (frontend) · Phase 3 = H24–36 (infra/CI) · Phase 4 = H36–48 (evals/docs/video).

---

## Phase 0 — Accounts & skeleton (H0–3)

### Task 1: ⚠️ USER ACTION — AWS account, Bedrock access, CLI

**Claude cannot do this. Do it first; Bedrock approval latency is the only uncontrollable.**

- [ ] **Step 1: Create AWS account** at https://aws.amazon.com → root email + card. Enable MFA on root (IAM → root user → assign MFA).
- [ ] **Step 2: Create IAM admin user for CLI**: IAM → Users → Create `deployer` → Attach policies directly → `AdministratorAccess` → Create. Then Security credentials tab → Create access key → CLI → download keys.
- [ ] **Step 3: Configure CLI locally**:
```powershell
aws configure --profile tcb   # paste key id/secret, region us-east-1, output json
$env:AWS_PROFILE = "tcb"
aws sts get-caller-identity   # expect your account id JSON
```
- [ ] **Step 4: Request Bedrock model access**: Console (region **us-east-1**) → Amazon Bedrock → Model access → Modify → enable **Anthropic Claude Haiku 4.5**, **Claude Sonnet 4.5**, **Amazon Titan Text Embeddings V2** → for Anthropic fill use case: "Internal evaluation chatbot for a take-home assignment; grounded Q&A over one public financial document." → Submit. Usually granted in minutes.
- [ ] **Step 5: Verify all three models work**:
```powershell
aws bedrock-runtime converse --model-id us.anthropic.claude-haiku-4-5-20251001-v1:0 --messages '[{\"role\":\"user\",\"content\":[{\"text\":\"say ok\"}]}]' --region us-east-1
aws bedrock-runtime converse --model-id us.anthropic.claude-sonnet-4-5-20250929-v1:0 --messages '[{\"role\":\"user\",\"content\":[{\"text\":\"say ok\"}]}]' --region us-east-1
aws bedrock-runtime invoke-model --model-id amazon.titan-embed-text-v2:0 --body '{\"inputText\":\"hello\",\"dimensions\":1024,\"normalize\":true}' --cli-binary-format raw-in-base64-out --region us-east-1 out.json; cat out.json | Select-String embedding | Out-Null; echo OK
```
Expected: each returns JSON without `AccessDeniedException`.
- [ ] **Step 6: Create GitHub repo** (public) named `tcb-fy25-chatbot` under your account. Don't push yet.

### Task 2: Repo skeleton, pytest wiring, env template

**Files:** Create: `pytest.ini`, `requirements-dev.txt`, `backend/requirements.txt`, `ingest/requirements.txt`, `.env.example`, `Makefile`, `backend/app/__init__.py`, `ingest/__init__.py`, `tests/__init__.py` (empty file)

**Interfaces produced:** `pytest` runs from root; `make ingest|dev|test` targets exist.

- [ ] **Step 1: Write the files**

`pytest.ini`:
```ini
[pytest]
addopts = -m "not eval" -q
markers =
    eval: golden evals hitting real Bedrock (opt-in: pytest -m eval)
pythonpath = backend .
testpaths = tests
```

`requirements-dev.txt`:
```
-r backend/requirements.txt
-r ingest/requirements.txt
pytest==8.4.*
httpx==0.28.*
pyyaml==6.0.*
```

`backend/requirements.txt`:
```
fastapi==0.128.*
uvicorn[standard]==0.35.*
pydantic-settings==2.10.*
boto3==1.40.*
numpy==2.3.*
rank-bm25==0.2.2
```

`ingest/requirements.txt`:
```
pdfplumber==0.11.*
boto3==1.40.*
numpy==2.3.*
```

`.env.example`:
```
# Copy to .env — used by docker compose. Only needed for real LLM answers.
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=us-east-1
# Set true to run the UI with zero AWS credentials (canned answers):
MOCK_LLM=false
```

`Makefile`:
```makefile
.PHONY: ingest dev test evals
ingest:
	python -m ingest.run
dev:
	docker compose up --build
test:
	pytest
evals:
	pytest -m eval -q -s
```

- [ ] **Step 2: Install and sanity-check**
```powershell
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pytest
```
Expected: `no tests ran` (exit 5 is fine at this point).
- [ ] **Step 3: Commit**
```bash
git add -A && git commit -m "chore: repo skeleton, pytest wiring, env template"
```

---

## Phase 1 — Ingestion & backend core (H3–12)

### Task 3: PDF parse + section-aware chunker (TDD)

**Files:** Create: `ingest/parse.py`, `ingest/chunker.py`, `tests/test_chunker.py`

**Interfaces produced:**
- `ingest.parse.extract_pages(pdf_path) -> list[dict]` — `[{"page": int, "text": str}]`
- `ingest.chunker.build_chunks(pages, max_chars=1400) -> list[dict]` — `[{"chunk_id": str, "section": str, "page": int, "text": str}]`. Pages 12 (glossary) and 13 (financial table) are **excluded** — they live in glossary/metrics stores; naive-chunking them is the RAG failure mode we're avoiding.

- [ ] **Step 1: Write the failing test** `tests/test_chunker.py`:
```python
from pathlib import Path
from ingest.parse import extract_pages
from ingest.chunker import build_chunks

PDF = Path("reports/fy25-press-release-eng-12022026.pdf")

def pages():
    return extract_pages(PDF)

def test_extract_pages_count_and_content():
    p = pages()
    assert len(p) == 14
    assert "FY25 HIGHLIGHTS" in p[0]["text"]
    assert p[0]["page"] == 1

def test_chunks_have_metadata_and_size():
    chunks = build_chunks(pages())
    assert len(chunks) >= 20
    for c in chunks:
        assert c["chunk_id"] and c["section"] and c["page"] >= 1
        assert 0 < len(c["text"]) <= 1600

def test_table_and_glossary_pages_excluded():
    chunks = build_chunks(pages())
    assert all(c["page"] not in (12, 13, 14) for c in chunks)
    assert not any("978,799" in c["text"] for c in chunks)  # table row only on p13

def test_sections_detected():
    sections = {c["section"] for c in build_chunks(pages())}
    assert "INCOME STATEMENT" in sections
    assert "BALANCE SHEET" in sections
    assert "FY25 HIGHLIGHTS" in sections
```
- [ ] **Step 2: Run to verify failure**: `pytest tests/test_chunker.py -v` → FAIL (`ModuleNotFoundError`).
- [ ] **Step 3: Implement**

`ingest/parse.py`:
```python
from pathlib import Path
import pdfplumber

def extract_pages(pdf_path: Path) -> list[dict]:
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            pages.append({"page": i, "text": page.extract_text() or ""})
    return pages
```

`ingest/chunker.py`:
```python
import re

# Ordered heading patterns -> canonical section name. Matched at line starts.
SECTION_PATTERNS: list[tuple[str, str]] = [
    (r"FY25 HIGHLIGHTS", "FY25 HIGHLIGHTS"),
    (r"INCOME STATEMENT", "INCOME STATEMENT"),
    (r"BALANCE SHEET", "BALANCE SHEET"),
    (r"Liquidity and capital", "LIQUIDITY AND CAPITAL"),
    (r"Asset quality", "ASSET QUALITY"),
    (r"Techcom Securities leads", "TECHCOM SECURITIES (TCBS)"),
    (r"Techcom Life debuts", "TECHCOM LIFE"),
    (r"Techcom Insurance marks", "TECHCOM INSURANCE (TCGI)"),
    (r"CUSTOMER AND OTHER HIGHLIGHTS", "CUSTOMER HIGHLIGHTS"),
    (r"New customers & E-banking", "CUSTOMER HIGHLIGHTS"),
    (r"Fitch Ratings assigned", "RATINGS"),
    (r"The 8th Techcombank Ho Chi Minh", "MARATHON & COMMUNITY"),
    (r"TCBS official listing on HOSE", "TCBS LISTING & MSCI"),
    (r"Techcombank cooperates with the Vietnam Tax", "TAX PARTNERSHIP (VTCA)"),
    (r"AWARDS AND RECOGNITION", "AWARDS"),
    (r"Learn more about Techcombank", "INVESTOR INFORMATION"),
    (r"About Techcombank", "ABOUT TECHCOMBANK"),
]
EXCLUDED_PAGES = {12, 13, 14}  # glossary -> glossary.json, table -> metrics.json, blank


def _section_for(line: str, current: str) -> str:
    for pat, name in SECTION_PATTERNS:
        if re.match(pat, line.strip(), flags=re.IGNORECASE):
            return name
    return current


def build_chunks(pages: list[dict], max_chars: int = 1400) -> list[dict]:
    chunks: list[dict] = []
    section = "FY25 HIGHLIGHTS"
    for p in pages:
        if p["page"] in EXCLUDED_PAGES:
            continue
        buf: list[str] = []
        seq = 1

        def flush():
            nonlocal seq, buf
            text = "\n".join(buf).strip()
            if text:
                chunks.append({
                    "chunk_id": f"p{p['page']}-{seq}",
                    "section": section,
                    "page": p["page"],
                    "text": text,
                })
                seq += 1
            buf = []

        for line in p["text"].splitlines():
            new_section = _section_for(line, section)
            if new_section != section:
                flush()
                section = new_section
            if sum(len(x) + 1 for x in buf) + len(line) > max_chars:
                flush()
            buf.append(line)
        flush()
    return chunks
```
- [ ] **Step 4: Run to verify pass**: `pytest tests/test_chunker.py -v` → 4 PASS. If a section assert fails, print detected sections (`pytest -s` + temporary print) and adjust the regex — the PDF's line breaks are authoritative, not this plan.
- [ ] **Step 5: Commit**: `git add -A && git commit -m "feat(ingest): pdf parsing and section-aware chunker"`

### Task 4: Curated metrics + glossary data (the structured store contents)

**Files:** Create: `ingest/metrics_data.py`, `ingest/glossary_data.py`, `tests/test_metrics_data.py`

**Interfaces produced:**
- `ingest.metrics_data.METRICS: list[dict]` — each: `{"metric_id": str, "name": str, "aliases": list[str], "unit": "VND bn"|"%"|str, "values": {PERIOD: number|str}, "qoq": str|None, "yoy": str|None, "note": str|None, "source_page": int}`. Periods: `"4Q24","1Q25","2Q25","3Q25","4Q25","FY24","FY25"`.
- `ingest.glossary_data.GLOSSARY: dict[str, str]` — acronym → expansion.

Every number below was verified against the rendered PDF (pages 1–13). **Verify again as you copy** — this table is the anti-hallucination backbone.

- [ ] **Step 1: Write the failing test** `tests/test_metrics_data.py`:
```python
from ingest.metrics_data import METRICS

def by_id(mid):
    return next(m for m in METRICS if m["metric_id"] == mid)

def test_key_fy25_figures():
    assert by_id("pbt")["values"]["FY25"] == 32538
    assert by_id("toi")["values"]["FY25"] == 53391
    assert by_id("casa_ratio")["values"]["4Q25"] == 40.4
    assert by_id("npl")["values"]["4Q25"] == 1.13
    assert by_id("car_basel2")["values"]["4Q25"] == 14.6
    assert by_id("total_assets")["values"]["4Q25"] == 1192344

def test_schema():
    for m in METRICS:
        assert m["metric_id"] and m["name"] and m["unit"] and m["source_page"]
        assert isinstance(m["aliases"], list) and m["values"]
```
- [ ] **Step 2: Run to verify failure**: `pytest tests/test_metrics_data.py -v` → FAIL.
- [ ] **Step 3: Implement** `ingest/metrics_data.py` (complete dataset):
```python
"""Hand-curated structured metrics from the FY25 press release.

Source of truth: page 13 summary table + headline figures in body text.
Every value was manually verified against the rendered PDF. This curation
step IS the 'process to turn unstructured into structured data'.
"""

def m(metric_id, name, aliases, unit, values, qoq=None, yoy=None, note=None, source_page=13):
    return {"metric_id": metric_id, "name": name, "aliases": aliases, "unit": unit,
            "values": values, "qoq": qoq, "yoy": yoy, "note": note, "source_page": source_page}

Q = ("4Q24", "1Q25", "2Q25", "3Q25", "4Q25")

def qv(*vals):
    return dict(zip(Q, vals))

METRICS: list[dict] = [
    # ---- Balance sheet (p13) ----
    m("total_assets", "Total assets", ["assets"], "VND bn",
      qv(978799, 989216, 1037645, 1129570, 1192344), qoq="+5.6%", yoy="+21.8%"),
    m("customer_deposits", "Deposits from customers", ["deposits", "customer deposits"], "VND bn",
      qv(564536, 569855, 589078, 638453, 665550), qoq="+4.2%", yoy="+17.9%"),
    m("credit_growth_ytd", "Credit growth (YTD, bank-only)", ["credit growth", "loan growth"], "%",
      qv(20.8, 3.8, 10.6, 16.8, 18.4), qoq="+160 bps", yoy="-249 bps",
      note="Bank-only per SBV quota; press text cites 18.36% YTD"),
    m("casa_ratio", "CASA ratio", ["casa", "current account savings account ratio"], "%",
      qv(40.8, 39.4, 41.1, 42.5, 40.4), qoq="-217 bps", yoy="-44 bps",
      note="Includes Auto-earning; industry-leading"),
    m("casa_balance", "CASA balance", ["casa balance"], "VND bn",
      {"4Q25": 268700}, yoy="+16.6%", note="~VND 269 trillion; retail CASA +17.7% YoY, corporate +14.8% YoY", source_page=3),
    m("npl", "Non-performing loan ratio (NPL)", ["npl", "bad debt", "non performing"], "%",
      qv(1.17, 1.23, 1.32, 1.23, 1.13), qoq="-10 bps", yoy="-4 bps",
      note="Organic NPL (pre-CIC) 0.98% vs 0.96% at 3Q25"),
    m("credit_cost_ltm", "Credit costs (LTM)", ["credit cost"], "%",
      qv(0.8, 0.7, 0.6, 0.6, 0.6), qoq="+5 bps", yoy="-17 bps", note="0.4% after recoveries"),
    m("coverage_ratio", "Loan loss coverage ratio", ["coverage", "llr"], "%",
      qv(113.8, 111.4, 106.4, 119.1, 127.9), qoq="+879 bps", yoy="+1,407 bps",
      note="9th consecutive quarter above 100%"),
    # ---- Capital & liquidity (p13) ----
    m("car_basel2", "CAR (Basel II)", ["car", "capital adequacy"], "%",
      qv(15.4, 15.3, 15.0, 15.8, 14.6), qoq="-120 bps", yoy="-78 bps",
      note="Q4 decline reflects >VND 7tn cash dividend paid October 2025"),
    m("tier1", "Basel II Tier 1 ratio", ["tier 1"], "%",
      qv(14.7, 14.7, 14.3, 14.2, 13.7), qoq="-57 bps", yoy="-106 bps"),
    m("st_funding_mlt", "Short-term funding to medium/long-term loans", ["short term funding"], "%",
      qv(26.5, 27.1, 26.4, 24.1, 24.6), qoq="+50 bps", yoy="-190 bps", note="SBV limit 30%; bank-only"),
    m("ldr", "Loan-to-deposit ratio (LDR)", ["ldr", "loan to deposit"], "%",
      qv(77.1, 80.1, 82.4, 81.2, 76.5), qoq="-470 bps", yoy="-60 bps", note="SBV limit 85%; bank-only"),
    # ---- Profitability (p13; FY columns) ----
    m("nii", "Net interest income (NII)", ["net interest income"], "VND bn",
      {"4Q24": 8602, "4Q25": 10788, "FY24": 35508, "FY25": 38155},
      yoy="4Q +25.4%; FY +7.5%"),
    m("non_ii", "Non-interest income", ["non interest income"], "VND bn",
      {"4Q24": 953, "4Q25": 4007, "FY24": 11482, "FY25": 15236}, yoy="4Q +320.5%; FY +32.7%"),
    m("toi", "Total operating income (TOI)", ["toi", "operating income", "revenue"], "VND bn",
      {"4Q24": 9555, "4Q25": 14795, "FY24": 46990, "FY25": 53391},
      yoy="4Q +54.8%; FY +13.6%", note="4Q24 base included negative banca-termination impact"),
    m("opex", "Operating expenses", ["opex", "costs", "operating expenses"], "VND bn",
      {"4Q24": -4741, "4Q25": -4824, "FY24": -15370, "FY25": -16432},
      yoy="4Q +1.8%; FY +6.9%", note="Driven by IT investment"),
    m("pbt", "Profit before tax (PBT)", ["pbt", "profit", "pretax profit", "earnings"], "VND bn",
      {"4Q24": 4696, "4Q25": 9153, "FY24": 27538, "FY25": 32538},
      yoy="4Q +94.9%; FY +18.2%", note="4Q25 was a third consecutive quarterly PBT record; FY exceeded guidance"),
    m("nfi_toi", "NFI / TOI", ["fee income ratio"], "%",
      {"4Q24": 24.0, "4Q25": 20.4, "FY24": 22.6, "FY25": 21.5}, yoy="4Q -361 bps; FY -116 bps"),
    m("cir", "Cost-to-income ratio (CIR)", ["cir", "cost income"], "%",
      {"4Q24": 49.6, "4Q25": 32.6, "FY24": 32.7, "FY25": 30.8}, yoy="4Q -1,701 bps; FY -193 bps"),
    m("roa", "ROA (LTM)", ["roa", "return on assets"], "%",
      {"4Q24": 2.4, "4Q25": 2.4, "FY24": 2.4, "FY25": 2.4}, yoy="+5 bps"),
    m("roe", "ROE (LTM)", ["roe", "return on equity"], "%",
      {"4Q24": 15.5, "4Q25": 16.0, "FY24": 15.5, "FY25": 16.0}, yoy="+48 bps"),
    m("nim_ltm", "NIM (LTM)", ["nim", "net interest margin"], "%",
      {"4Q24": 4.4, "4Q25": 3.8, "FY24": 4.4, "FY25": 3.8}, yoy="-54 bps",
      note="Quarterly NIM edged up to 3.9% in 4Q25 (p2); NIM LTM EOP 3.7%"),
    m("cost_of_funds", "Cost of funds", ["cof", "funding cost"], "%",
      {"4Q24": 3.4, "4Q25": 3.6, "FY24": 3.3, "FY25": 3.5}, yoy="4Q +14 bps; FY +13 bps"),
    # ---- Fees by product, FY25 (p2-3) ----
    m("nfi", "Net fee income (NFI)", ["fee income", "fees"], "VND bn",
      {"FY25": 11500}, yoy="+7.8%", note="VND 11.5 trillion", source_page=2),
    m("ib_fees", "Investment banking fees", ["ib fees", "investment banking"], "VND bn",
      {"FY25": 4200, "4Q25": 797.0}, yoy="FY +20.7%; 4Q -12.9%", source_page=2),
    m("lc_fees", "LC, remittance, cash & settlement fees", ["letters of credit", "lc", "remittance"], "VND bn",
      {"FY25": 3100}, yoy="-14.0%", note="4Q25 +69.2% YoY recovery; cash & settlement VND 925.3 bn FY25 (+31.9%)", source_page=2),
    m("card_fees", "Card fees", ["cards"], "VND bn",
      {"FY25": 1700}, yoy="-15.1%", note="4Q25 +6.5% YoY; leading Visa market share", source_page=2),
    m("fx_fees", "FX sales income", ["fx", "foreign exchange"], "VND bn",
      {"FY25": 1200, "4Q25": 314.6}, yoy="FY +36.9%; 4Q +14.6%", source_page=2),
    m("banca_fees", "Bancassurance fees", ["banca", "insurance fees"], "VND bn",
      {"FY25": 1200}, yoy="+91.8%", note="Recovery after 4Q24 partnership termination", source_page=3),
    m("provisions", "Provision expenses", ["provisions"], "VND bn",
      {"FY25": 4400}, yoy="+8.3%", note="vs 18.36% credit growth", source_page=3),
    m("recoveries", "Recoveries", ["debt recoveries"], "VND bn",
      {"FY25": 1400}, yoy="+19.0%", source_page=3),
    # ---- Credit book (p3) ----
    m("retail_credit", "Retail credit balance", ["retail loans", "retail lending"], "VND bn",
      {"4Q25": 372000}, yoy="+30.8% YTD",
      note="Unsecured book 3.5x YTD; mortgage +24.7% YTD; margin lending +69.3% YTD", source_page=3),
    m("corporate_credit", "Corporate credit balance", ["corporate loans"], "VND bn",
      {"4Q25": 452100}, yoy="+13.4% YTD",
      note="Real-estate share of loans 30.7% (from 33.2% a year earlier)", source_page=3),
    # ---- Customers & subsidiaries (p4-6) ----
    m("customers", "Total customers", ["customer count", "how many customers"], "million",
      {"4Q25": 18.0}, note="+2.7m new in 2025; 62.3% of new retail acquired digitally, 30.2% branches, 7.5% ecosystem", source_page=6),
    m("ebank_txn", "Retail e-banking transactions (4Q25)", ["e-banking", "transactions"], "billion",
      {"4Q25": 1.2}, yoy="+26.9%", note="#1 market share: outbound 17.0%, inbound 15.6%", source_page=6),
    m("tcbs_pbt", "TCBS profit before tax", ["tcbs profit", "techcom securities profit"], "VND bn",
      {"4Q25": 2041, "FY25": 7109}, yoy="4Q +120%; FY +50%",
      note="123% of full-year target; ROE 16.7%, ROA 8.4%; margin lending ~VND 44tn", source_page=4),
    m("tcgi_premiums", "Techcom Insurance premiums (FY25)", ["tcgi", "insurance premiums"], "VND bn",
      {"FY25": 500}, note=">VND 500bn premiums, >650,000 customers in first full year", source_page=5),
    m("dividend", "Cash dividend paid (Oct 2025)", ["dividend"], "VND bn",
      {"FY25": 7000}, note=">VND 7 trillion paid October 2025; caused CAR decline in Q4", source_page=4),
]
```

`ingest/glossary_data.py`:
```python
GLOSSARY: dict[str, str] = {
    "CASA": "current account savings account",
    "CAR": "capital adequacy ratio",
    "CIR": "cost-to-income ratio",
    "NII": "net interest income",
    "NFI": "net fee and commission income",
    "NIM": "net interest margin",
    "NPL": "non-performing loan",
    "PBT": "profit before tax",
    "TOI": "total operating income",
    "ROA": "return on assets",
    "ROE": "return on equity",
    "LDR": "loan-to-deposit ratio",
    "LC": "letters of credit",
    "FX": "foreign exchange",
    "IB": "investment banking",
    "IPO": "initial public offering",
    "SBV": "State Bank of Vietnam",
    "TCBS": "Techcom Securities",
    "TCGI": "Techcom General Insurance",
    "YoY": "year-on-year",
    "YTD": "year-to-date",
    "QoQ": "quarter-on-quarter",
    "LTM": "last twelve months",
    "HOSE": "Ho Chi Minh Stock Exchange",
    "HNX": "Hanoi Stock Exchange",
    "UPAS LC": "usance payable at sight letter of credit",
}
```
- [ ] **Step 4: Run to verify pass**: `pytest tests/test_metrics_data.py -v` → PASS.
- [ ] **Step 5: Cross-check 6 random values against the PDF** (open `reports/fy25-press-release-eng-12022026.pdf` page 13) — this manual verification is part of the deliverable story. Record "verified" in the commit body.
- [ ] **Step 6: Commit**: `git add -A && git commit -m "feat(ingest): hand-verified structured metrics + glossary"`

### Task 5: Embeddings + artifact writer (`ingest.run`)

**Files:** Create: `ingest/embed.py`, `ingest/run.py`. Generates: `data/artifacts/{chunks,metrics,glossary}.json`, `data/artifacts/embeddings.npz`

**Interfaces produced:**
- `ingest.embed.embed_texts(texts: list[str], region="us-east-1") -> np.ndarray` — shape `(n, 1024)`, float32, normalized.
- Artifacts on disk; `embeddings.npz` holds arrays `vectors` and `chunk_ids` (aligned with chunks.json order).

- [ ] **Step 1: Implement** (no unit test — thin boto3 wrapper + I/O; exercised by the real run below and by retrieval tests via committed artifacts)

`ingest/embed.py`:
```python
import json
import boto3
import numpy as np

MODEL_ID = "amazon.titan-embed-text-v2:0"

def embed_texts(texts: list[str], region: str = "us-east-1") -> np.ndarray:
    client = boto3.client("bedrock-runtime", region_name=region)
    vecs = []
    for t in texts:
        body = json.dumps({"inputText": t[:8000], "dimensions": 1024, "normalize": True})
        resp = client.invoke_model(modelId=MODEL_ID, body=body)
        vecs.append(json.loads(resp["body"].read())["embedding"])
    return np.asarray(vecs, dtype=np.float32)
```

`ingest/run.py`:
```python
"""Build all knowledge artifacts from the source PDF. Run: python -m ingest.run"""
import json
from pathlib import Path
import numpy as np

from ingest.parse import extract_pages
from ingest.chunker import build_chunks
from ingest.metrics_data import METRICS
from ingest.glossary_data import GLOSSARY

PDF = Path("reports/fy25-press-release-eng-12022026.pdf")
OUT = Path("data/artifacts")

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    chunks = build_chunks(extract_pages(PDF))
    (OUT / "chunks.json").write_text(json.dumps(chunks, indent=1), encoding="utf-8")
    (OUT / "metrics.json").write_text(json.dumps(METRICS, indent=1), encoding="utf-8")
    (OUT / "glossary.json").write_text(json.dumps(GLOSSARY, indent=1), encoding="utf-8")
    print(f"wrote {len(chunks)} chunks, {len(METRICS)} metrics, {len(GLOSSARY)} glossary entries")

    from ingest.embed import embed_texts  # import here so json artifacts work without boto3 creds
    vectors = embed_texts([f"{c['section']}: {c['text']}" for c in chunks])
    np.savez_compressed(OUT / "embeddings.npz",
                        vectors=vectors,
                        chunk_ids=np.array([c["chunk_id"] for c in chunks]))
    print(f"wrote embeddings {vectors.shape}")

if __name__ == "__main__":
    main()
```
- [ ] **Step 2: Run for real** (needs Task 1 done; `$env:AWS_PROFILE="tcb"`):
```powershell
python -m ingest.run
```
Expected: `wrote ~30-60 chunks, 38 metrics, 26 glossary entries` then `wrote embeddings (N, 1024)`.
- [ ] **Step 3: Spot-check artifacts**: open `data/artifacts/chunks.json`, confirm readable text, sections, no page-13 rows.
- [ ] **Step 4: Commit artifacts too** (they are part of the deterministic build):
```bash
git add -A && git commit -m "feat(ingest): artifact writer + committed knowledge artifacts"
```

### Task 6: Config, DTOs, session stores (TDD)

**Files:** Create: `backend/app/config.py`, `backend/app/models.py`, `backend/app/stores/{__init__.py,base.py,memory.py,dynamo.py}`, `tests/test_sessions.py`

**Interfaces produced:**
- `app.config.Settings` (pydantic-settings, env-driven): `bedrock_region="us-east-1"`, `model_router_id`, `model_simple_id`, `model_analytical_id` (defaults = Global Constraints IDs), `session_store="memory"`, `sessions_table="tcb-chatbot-sessions"`, `mock_llm=False`, `artifacts_dir="data/artifacts"`, `static_dir="static"`, `rate_limit_per_min=20`, `session_ttl_hours=24`. `get_settings()` cached accessor.
- `app.models`: `ChatRequest{session_id: str|None, message: str}`, `Citation{page: int, snippet: str}`, `ChatResponse{session_id, reply, citations: list[Citation], route: str, model: str, latency_ms: int}`, `Turn{role: "user"|"assistant", content: str}`.
- `app.stores.base.SessionStore` protocol: `get(session_id) -> list[Turn]`, `append(session_id, turn: Turn) -> None`.
- `app.stores.memory.MemorySessionStore()`; `app.stores.dynamo.DynamoSessionStore(table_name, ttl_hours)`; factory `app.stores.make_store(settings) -> SessionStore`.

- [ ] **Step 1: Write the failing test** `tests/test_sessions.py`:
```python
from app.models import Turn
from app.stores.memory import MemorySessionStore

def test_memory_store_roundtrip():
    s = MemorySessionStore()
    assert s.get("a") == []
    s.append("a", Turn(role="user", content="hi"))
    s.append("a", Turn(role="assistant", content="hello"))
    turns = s.get("a")
    assert [t.role for t in turns] == ["user", "assistant"]
    assert s.get("b") == []
```
- [ ] **Step 2: Run to verify failure**: `pytest tests/test_sessions.py -v` → FAIL.
- [ ] **Step 3: Implement**

`backend/app/config.py`:
```python
from functools import lru_cache
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    bedrock_region: str = "us-east-1"
    model_router_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    model_simple_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    model_analytical_id: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    session_store: str = "memory"          # memory | dynamo
    sessions_table: str = "tcb-chatbot-sessions"
    mock_llm: bool = False
    artifacts_dir: str = "data/artifacts"
    static_dir: str = "static"
    rate_limit_per_min: int = 20
    session_ttl_hours: int = 24

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`backend/app/models.py`:
```python
from typing import Literal
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(min_length=1, max_length=2000)

class Citation(BaseModel):
    page: int
    snippet: str

class ChatResponse(BaseModel):
    session_id: str
    reply: str
    citations: list[Citation] = []
    route: str
    model: str
    latency_ms: int

class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str
```

`backend/app/stores/base.py`:
```python
from typing import Protocol
from app.models import Turn

class SessionStore(Protocol):
    def get(self, session_id: str) -> list[Turn]: ...
    def append(self, session_id: str, turn: Turn) -> None: ...
```

`backend/app/stores/memory.py`:
```python
from collections import defaultdict
from app.models import Turn

class MemorySessionStore:
    def __init__(self) -> None:
        self._data: dict[str, list[Turn]] = defaultdict(list)

    def get(self, session_id: str) -> list[Turn]:
        return list(self._data.get(session_id, []))

    def append(self, session_id: str, turn: Turn) -> None:
        self._data[session_id].append(turn)
```

`backend/app/stores/dynamo.py`:
```python
import time
import boto3
from app.models import Turn

class DynamoSessionStore:
    """One item per session: {session_id, turns: [{role, content}], expires_at}."""

    def __init__(self, table_name: str, ttl_hours: int = 24, region: str = "us-east-1") -> None:
        self._table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        self._ttl_hours = ttl_hours

    def get(self, session_id: str) -> list[Turn]:
        item = self._table.get_item(Key={"session_id": session_id}).get("Item")
        return [Turn(**t) for t in item["turns"]] if item else []

    def append(self, session_id: str, turn: Turn) -> None:
        expires = int(time.time()) + self._ttl_hours * 3600
        self._table.update_item(
            Key={"session_id": session_id},
            UpdateExpression=("SET turns = list_append(if_not_exists(turns, :empty), :t), "
                              "expires_at = :exp"),
            ExpressionAttributeValues={":t": [turn.model_dump()], ":empty": [], ":exp": expires},
        )
```

`backend/app/stores/__init__.py`:
```python
from app.config import Settings
from app.stores.base import SessionStore
from app.stores.memory import MemorySessionStore

def make_store(settings: Settings) -> SessionStore:
    if settings.session_store == "dynamo":
        from app.stores.dynamo import DynamoSessionStore
        return DynamoSessionStore(settings.sessions_table, settings.session_ttl_hours,
                                  settings.bedrock_region)
    return MemorySessionStore()
```
- [ ] **Step 4: Run to verify pass**: `pytest tests/test_sessions.py -v` → PASS.
- [ ] **Step 5: Commit**: `git add -A && git commit -m "feat(backend): config, DTOs, pluggable session stores"`

### Task 7: Metrics store — exact lookups (TDD)

**Files:** Create: `backend/app/services/__init__.py` (empty), `backend/app/services/metrics_store.py`, `tests/test_metrics_store.py`

**Interfaces produced:**
- `MetricsStore(path)` loads `metrics.json`.
- `.lookup(query: str) -> list[dict]` — up to 3 metric dicts matched by name/alias tokens; period-aware.
- `.render(hits: list[dict], query: str) -> str` — context block for the answer prompt: one line per relevant `{period: value}` incl. unit, QoQ/YoY, note, `[p.N]` tag.
- `PERIOD_RE` extracts periods (`fy25`, `4q25`, `q4 2025`, `2025`…) — no period ⇒ FY25/4Q25 defaults, "all periods" listed when query says trend/evolution/history.

- [ ] **Step 1: Write the failing test** `tests/test_metrics_store.py`:
```python
from app.services.metrics_store import MetricsStore, extract_periods

store = MetricsStore("data/artifacts/metrics.json")

def test_extract_periods():
    assert extract_periods("pbt in fy25") == ["FY25"]
    assert extract_periods("casa in 3Q25") == ["3Q25"]
    assert extract_periods("casa in q3 2025") == ["3Q25"]
    assert extract_periods("npl in the fourth quarter of 2025") == ["4Q25"]
    assert extract_periods("total assets") == []

def test_lookup_pbt():
    hits = store.lookup("What was profit before tax in FY25?")
    assert hits and hits[0]["metric_id"] == "pbt"

def test_lookup_casa_alias():
    hits = store.lookup("current account savings account ratio")
    assert any(h["metric_id"] == "casa_ratio" for h in hits)

def test_render_contains_value_and_page():
    hits = store.lookup("profit before tax FY25")
    text = store.render(hits, "profit before tax FY25")
    assert "32,538" in text and "[p.13]" in text

def test_render_trend_lists_quarters():
    hits = store.lookup("How did the CASA ratio evolve over 2025?")
    text = store.render(hits, "How did the CASA ratio evolve over 2025?")
    for v in ("39.4", "41.1", "42.5", "40.4"):
        assert v in text
```
- [ ] **Step 2: Run to verify failure** → FAIL.
- [ ] **Step 3: Implement** `backend/app/services/metrics_store.py`:
```python
import json
import re
from pathlib import Path

WORD_RE = re.compile(r"[a-z0-9]+")
TREND_WORDS = ("evolve", "trend", "over 2025", "history", "quarterly", "each quarter", "by quarter")

def _norm(s: str) -> set[str]:
    return set(WORD_RE.findall(s.lower()))

def extract_periods(query: str) -> list[str]:
    q = query.lower()
    periods: list[str] = []
    for m in re.finditer(r"\bfy\s?(24|25|2024|2025)\b", q):
        periods.append("FY" + m.group(1)[-2:])
    for m in re.finditer(r"\b([1-4])q\s?(24|25|2024|2025)\b", q):
        periods.append(f"{m.group(1)}Q{m.group(2)[-2:]}")
    for m in re.finditer(r"\bq([1-4])\s*(?:of\s*)?(2024|2025|24|25)\b", q):
        periods.append(f"{m.group(1)}Q{m.group(2)[-2:]}")
    ordinals = {"first": 1, "second": 2, "third": 3, "fourth": 4}
    m = re.search(r"\b(first|second|third|fourth)\s+quarter\s+(?:of\s+)?(2024|2025)\b", q)
    if m:
        periods.append(f"{ordinals[m.group(1)]}Q{m.group(2)[-2:]}")
    seen: list[str] = []
    for p in periods:
        if p not in seen:
            seen.append(p)
    return seen

def _fmt(value, unit: str) -> str:
    if isinstance(value, (int, float)) and unit == "VND bn":
        return f"VND {value:,.0f} bn".replace(",", ",")
    if isinstance(value, (int, float)) and unit == "%":
        return f"{value}%"
    return f"{value} {unit}".strip()

class MetricsStore:
    def __init__(self, path: str | Path) -> None:
        self._metrics: list[dict] = json.loads(Path(path).read_text(encoding="utf-8"))

    def lookup(self, query: str) -> list[dict]:
        qtokens = _norm(query)
        scored: list[tuple[float, dict]] = []
        for met in self._metrics:
            names = [met["name"], met["metric_id"].replace("_", " "), *met["aliases"]]
            best = 0.0
            for name in names:
                ntokens = _norm(name)
                if not ntokens:
                    continue
                overlap = len(ntokens & qtokens) / len(ntokens)
                # exact alias/id phrase match is a strong signal
                if name.lower() in query.lower():
                    overlap = max(overlap, 1.0)
                best = max(best, overlap)
            if best >= 0.6:
                scored.append((best, met))
        scored.sort(key=lambda x: -x[0])
        return [met for _, met in scored[:3]]

    def render(self, hits: list[dict], query: str) -> str:
        if not hits:
            return ""
        periods = extract_periods(query)
        want_trend = any(w in query.lower() for w in TREND_WORDS)
        lines: list[str] = []
        for met in hits:
            values: dict = met["values"]
            if want_trend or not periods:
                chosen = values if want_trend else {
                    p: values[p] for p in ("FY25", "4Q25") if p in values
                } or values
            else:
                chosen = {p: values[p] for p in periods if p in values}
                if not chosen:
                    available = ", ".join(values)
                    lines.append(f"- {met['name']}: no data for {periods}; available periods: {available} [p.{met['source_page']}]")
                    continue
            vals = "; ".join(f"{p}: {_fmt(v, met['unit'])}" for p, v in chosen.items())
            extra = " ".join(filter(None, [
                f"(QoQ {met['qoq']})" if met.get("qoq") else "",
                f"(YoY {met['yoy']})" if met.get("yoy") else "",
                f"Note: {met['note']}" if met.get("note") else "",
            ]))
            lines.append(f"- {met['name']} — {vals} {extra} [p.{met['source_page']}]".rstrip())
        return "\n".join(lines)
```
- [ ] **Step 4: Run to verify pass**: `pytest tests/test_metrics_store.py -v` → PASS (tweak thresholds only if a listed test fails; keep tests as spec).
- [ ] **Step 5: Commit**: `git add -A && git commit -m "feat(backend): structured metrics store with period-aware lookup"`

### Task 8: Hybrid retrieval — BM25 + cosine + RRF (TDD)

**Files:** Create: `backend/app/services/retrieval.py`, `tests/test_retrieval.py`

**Interfaces produced:**
- `Retriever(artifacts_dir)` — loads `chunks.json` + `embeddings.npz`, builds BM25 over tokenized chunk text.
- `.search(query: str, query_vec: np.ndarray | None, top_k=6) -> list[dict]` — chunk dicts + `"score"`. `query_vec=None` ⇒ BM25-only (mock mode / embedding failure degradation).
- `expand_query(query, glossary) -> str` — appends expansions for acronyms present.
- RRF: `score = Σ 1/(60 + rank)` across the two rankers.

- [ ] **Step 1: Write the failing test** `tests/test_retrieval.py`:
```python
import numpy as np
from app.services.retrieval import Retriever, expand_query

r = Retriever("data/artifacts")

def test_bm25_only_finds_dividend_chunk():
    hits = r.search("cash dividend payment October", query_vec=None, top_k=6)
    assert hits and any("dividend" in h["text"].lower() for h in hits)

def test_vector_path_with_self_embedding():
    # use a chunk's own vector as the query vector -> that chunk must rank #1
    vec = r.vectors[0]
    hits = r.search("zzz nonsense zzz", query_vec=vec, top_k=3)
    assert hits[0]["chunk_id"] == r.chunk_ids[0]

def test_expand_query():
    glossary = {"CASA": "current account savings account"}
    out = expand_query("What is the CASA ratio?", glossary)
    assert "current account savings account" in out

def test_results_have_metadata():
    hits = r.search("marathon", None, top_k=3)
    assert all({"chunk_id", "section", "page", "text", "score"} <= set(h) for h in hits)
```
- [ ] **Step 2: Run to verify failure** → FAIL.
- [ ] **Step 3: Implement** `backend/app/services/retrieval.py`:
```python
import json
import re
from pathlib import Path
import numpy as np
from rank_bm25 import BM25Okapi

TOKEN_RE = re.compile(r"[a-z0-9]+")
RRF_K = 60

def _tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())

def expand_query(query: str, glossary: dict[str, str]) -> str:
    extras = [exp for acro, exp in glossary.items()
              if re.search(rf"\b{re.escape(acro)}\b", query, flags=re.IGNORECASE)]
    return query + (" (" + "; ".join(extras) + ")" if extras else "")

class Retriever:
    def __init__(self, artifacts_dir: str | Path) -> None:
        d = Path(artifacts_dir)
        self.chunks: list[dict] = json.loads((d / "chunks.json").read_text(encoding="utf-8"))
        npz = np.load(d / "embeddings.npz", allow_pickle=False)
        self.vectors: np.ndarray = npz["vectors"]          # (n, 1024) normalized
        self.chunk_ids: list[str] = [str(x) for x in npz["chunk_ids"]]
        assert [c["chunk_id"] for c in self.chunks] == self.chunk_ids, "artifacts out of sync"
        self._bm25 = BM25Okapi([_tokens(c["section"] + " " + c["text"]) for c in self.chunks])

    def search(self, query: str, query_vec: np.ndarray | None, top_k: int = 6) -> list[dict]:
        n = len(self.chunks)
        bm25_rank = np.argsort(-np.asarray(self._bm25.get_scores(_tokens(query))))
        rrf = np.zeros(n)
        for rank, idx in enumerate(bm25_rank):
            rrf[idx] += 1.0 / (RRF_K + rank)
        if query_vec is not None:
            cos_rank = np.argsort(-(self.vectors @ query_vec.astype(np.float32)))
            for rank, idx in enumerate(cos_rank):
                rrf[idx] += 1.0 / (RRF_K + rank)
        order = np.argsort(-rrf)[:top_k]
        return [{**self.chunks[i], "score": float(rrf[i])} for i in order]
```
- [ ] **Step 4: Run to verify pass** → PASS.
- [ ] **Step 5: Commit**: `git add -A && git commit -m "feat(backend): hybrid BM25+vector retrieval with RRF"`

### Task 9: LLM client — Bedrock Converse wrapper with retries & mock (TDD)

**Files:** Create: `backend/app/services/llm.py`, `tests/test_llm.py`

**Interfaces produced:**
- `LLMClient(settings)` with:
  - `.converse(model_id, system: str, messages: list[dict], temperature=0.0, max_tokens=1024) -> str` — messages: `[{"role": "user"|"assistant", "content": str}]`. 3 retries, exponential backoff + jitter on `ThrottlingException`/5xx.
  - `.embed_query(text: str) -> np.ndarray | None` — Titan v2; returns `None` in mock mode or on failure (retrieval degrades to BM25).
  - Mock mode (`settings.mock_llm`): `.converse` returns `MOCK_ROUTER_JSON` when the system prompt contains `"intent"` else `"[MOCK] This is a canned grounded answer for UI testing. [p.1]"`.

- [ ] **Step 1: Write the failing test** `tests/test_llm.py`:
```python
import json
from app.config import Settings
from app.services.llm import LLMClient

def test_mock_mode_router_and_answer():
    c = LLMClient(Settings(mock_llm=True))
    out = c.converse("any", system="Classify intent as JSON", messages=[{"role": "user", "content": "hi"}])
    assert json.loads(out)["intent"]
    ans = c.converse("any", system="Answer from context", messages=[{"role": "user", "content": "hi"}])
    assert "MOCK" in ans
    assert c.embed_query("hello") is None

def test_retry_then_success(monkeypatch):
    c = LLMClient(Settings(mock_llm=False))
    calls = {"n": 0}
    class Boom(Exception): ...
    def fake_converse(**kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            err = type("E", (Exception,), {"response": {"Error": {"Code": "ThrottlingException"}}})()
            raise err
        return {"output": {"message": {"content": [{"text": "ok"}]}}}
    monkeypatch.setattr(c, "_sleep", lambda s: None)
    monkeypatch.setattr(c._client, "converse", fake_converse, raising=False)
    assert c.converse("m", "sys", [{"role": "user", "content": "x"}]) == "ok"
    assert calls["n"] == 3
```
- [ ] **Step 2: Run to verify failure** → FAIL.
- [ ] **Step 3: Implement** `backend/app/services/llm.py`:
```python
import json
import random
import time
import boto3
import numpy as np
from app.config import Settings

EMBED_MODEL = "amazon.titan-embed-text-v2:0"
RETRYABLE = {"ThrottlingException", "ServiceUnavailableException", "ModelTimeoutException",
             "InternalServerException"}
MOCK_ROUTER_JSON = json.dumps({"intent": "narrative", "standalone_query": "mock", "complexity": "simple"})

class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = None if settings.mock_llm else boto3.client(
            "bedrock-runtime", region_name=settings.bedrock_region)

    def _sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def converse(self, model_id: str, system: str, messages: list[dict],
                 temperature: float = 0.0, max_tokens: int = 1024) -> str:
        if self._settings.mock_llm:
            return MOCK_ROUTER_JSON if "intent" in system else \
                "[MOCK] This is a canned grounded answer for UI testing. [p.1]"
        last_err: Exception | None = None
        for attempt in range(4):
            try:
                resp = self._client.converse(
                    modelId=model_id,
                    system=[{"text": system}],
                    messages=[{"role": m["role"], "content": [{"text": m["content"]}]}
                              for m in messages],
                    inferenceConfig={"temperature": temperature, "maxTokens": max_tokens},
                )
                return resp["output"]["message"]["content"][0]["text"]
            except Exception as e:  # boto ClientError shape
                code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
                if code in RETRYABLE and attempt < 3:
                    self._sleep(min(8.0, 2 ** attempt) + random.random())
                    last_err = e
                    continue
                raise
        raise last_err  # pragma: no cover

    def embed_query(self, text: str) -> np.ndarray | None:
        if self._settings.mock_llm:
            return None
        try:
            body = json.dumps({"inputText": text[:8000], "dimensions": 1024, "normalize": True})
            resp = self._client.invoke_model(modelId=EMBED_MODEL, body=body)
            return np.asarray(json.loads(resp["body"].read())["embedding"], dtype=np.float32)
        except Exception:
            return None  # degrade to BM25-only retrieval
```
- [ ] **Step 4: Run to verify pass** → PASS.
- [ ] **Step 5: Commit**: `git add -A && git commit -m "feat(backend): bedrock converse client with retries and mock mode"`

### Task 10: Router — intent classification + follow-up rewriting (TDD)

**Files:** Create: `backend/app/services/router_svc.py`, `tests/test_router_parsing.py`

**Interfaces produced:**
- `RouteDecision` dataclass: `intent: str` (`metric|narrative|hybrid|chitchat|out_of_scope`), `standalone_query: str`, `complexity: str` (`simple|analytical`).
- `route(llm: LLMClient, model_id: str, history: list[Turn], message: str) -> RouteDecision` — single Haiku call, JSON out, one re-ask on bad JSON, fallback `RouteDecision("narrative", message, "analytical")`.
- `ROUTER_SYSTEM` prompt (verbatim below) — later tasks rely on its JSON contract.

- [ ] **Step 1: Write the failing test** `tests/test_router_parsing.py`:
```python
from app.models import Turn
from app.services.router_svc import parse_decision, RouteDecision, build_router_user_msg

def test_parse_valid():
    d = parse_decision('{"intent":"metric","standalone_query":"PBT FY25","complexity":"simple"}')
    assert d == RouteDecision("metric", "PBT FY25", "simple")

def test_parse_json_in_prose():
    d = parse_decision('Sure: {"intent":"chitchat","standalone_query":"hi","complexity":"simple"} done')
    assert d.intent == "chitchat"

def test_parse_garbage_returns_none():
    assert parse_decision("not json at all") is None

def test_parse_bad_enum_returns_none():
    assert parse_decision('{"intent":"banana","standalone_query":"x","complexity":"simple"}') is None

def test_build_user_msg_includes_history():
    msg = build_router_user_msg([Turn(role="user", content="CASA in FY25?"),
                                 Turn(role="assistant", content="40.4% [p.13]")],
                                "what about Q3?")
    assert "CASA in FY25?" in msg and "what about Q3?" in msg
```
- [ ] **Step 2: Run to verify failure** → FAIL.
- [ ] **Step 3: Implement** `backend/app/services/router_svc.py`:
```python
import json
import re
from dataclasses import dataclass
from app.models import Turn
from app.services.llm import LLMClient

INTENTS = {"metric", "narrative", "hybrid", "chitchat", "out_of_scope"}
COMPLEXITIES = {"simple", "analytical"}

ROUTER_SYSTEM = """You are a query router for a chatbot whose ONLY knowledge is Techcombank's FY25 results press release (fiscal year ended 31 Dec 2025, published Jan 2026). Given the conversation and the latest user message, output ONLY a JSON object:
{"intent": "...", "standalone_query": "...", "complexity": "..."}

intent — one of:
- "metric": asks for specific financial figures/ratios (PBT, TOI, CASA, NPL, CAR, NIM, ROE, deposits, credit growth, fees...).
- "narrative": asks about events, strategy, subsidiaries, ratings, awards, explanations described in prose.
- "hybrid": needs both numbers and explanation (e.g. "why did CAR fall?", comparisons with reasons).
- "chitchat": greetings, thanks, meta questions about the bot.
- "out_of_scope": anything not answerable from the FY25 press release: other fiscal years (FY23 and earlier), other companies' data, live market/stock prices, investment advice, future predictions, non-Techcombank topics.

standalone_query — rewrite the message so it is fully self-contained using conversation context: resolve pronouns and elliptical follow-ups ("what about Q3?" after a CASA question becomes "What was the CASA ratio in 3Q25?"). Expand acronyms once (e.g. "CASA (current account savings account)"). For chitchat/out_of_scope, copy the message.

complexity — "simple" for single-fact lookups and short factual answers; "analytical" for explanations, comparisons, multi-part questions, or summaries.

Output the JSON object only. No markdown, no commentary."""

@dataclass
class RouteDecision:
    intent: str
    standalone_query: str
    complexity: str

def parse_decision(text: str) -> RouteDecision | None:
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    intent, query, cx = obj.get("intent"), obj.get("standalone_query"), obj.get("complexity")
    if intent not in INTENTS or cx not in COMPLEXITIES or not isinstance(query, str) or not query:
        return None
    return RouteDecision(intent, query, cx)

def build_router_user_msg(history: list[Turn], message: str) -> str:
    lines = [f"{t.role}: {t.content}" for t in history[-6:]]
    lines.append(f"user (latest): {message}")
    return "\n".join(lines)

def route(llm: LLMClient, model_id: str, history: list[Turn], message: str) -> RouteDecision:
    user_msg = build_router_user_msg(history, message)
    for _ in range(2):  # one re-ask on malformed JSON
        raw = llm.converse(model_id, ROUTER_SYSTEM,
                           [{"role": "user", "content": user_msg}], temperature=0.0, max_tokens=300)
        decision = parse_decision(raw)
        if decision:
            return decision
    return RouteDecision("narrative", message, "analytical")
```
- [ ] **Step 4: Run to verify pass** → PASS.
- [ ] **Step 5: Commit**: `git add -A && git commit -m "feat(backend): router with intent classification and follow-up rewriting"`

### Task 11: Answerer + pipeline + /api/chat + app factory (TDD, mocked LLM)

**Files:** Create: `backend/app/services/answerer.py`, `backend/app/services/pipeline.py`, `backend/app/api/__init__.py` (empty), `backend/app/api/chat.py`, `backend/app/main.py`, `tests/test_api_chat.py`

**Interfaces produced:**
- `answerer.ANSWER_SYSTEM` (verbatim below), `answerer.build_context(metric_block: str, chunks: list[dict]) -> tuple[str, list[Citation]]`, `answerer.answer(llm, model_id, history, standalone_query, context) -> str`.
- `pipeline.ChatPipeline(settings)` — wires llm/retriever/metrics/store; `.handle(session_id: str | None, message: str) -> ChatResponse`.
- FastAPI app: `POST /api/chat`, `GET /api/health` → `{"status":"ok","chunks":N,"mock":bool}`, SPA static mount at `/` when `static_dir` exists, simple per-session+IP rate limit (429 beyond `rate_limit_per_min`).

- [ ] **Step 1: Write the failing test** `tests/test_api_chat.py`:
```python
import os
os.environ["MOCK_LLM"] = "true"          # before app import
os.environ["SESSION_STORE"] = "memory"

from fastapi.testclient import TestClient
from app.main import create_app

client = TestClient(create_app())

def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["chunks"] > 0 and body["mock"] is True

def test_chat_roundtrip_and_session_continuity():
    r1 = client.post("/api/chat", json={"message": "What was PBT in FY25?"})
    assert r1.status_code == 200
    b1 = r1.json()
    assert b1["reply"] and b1["session_id"] and b1["route"] and b1["model"]
    r2 = client.post("/api/chat", json={"session_id": b1["session_id"], "message": "and in 4Q25?"})
    assert r2.status_code == 200
    assert r2.json()["session_id"] == b1["session_id"]

def test_validation_rejects_empty():
    assert client.post("/api/chat", json={"message": ""}).status_code == 422
```
- [ ] **Step 2: Run to verify failure** → FAIL.
- [ ] **Step 3: Implement**

`backend/app/services/answerer.py`:
```python
from app.models import Citation, Turn
from app.services.llm import LLMClient

ANSWER_SYSTEM = """You are Techcombank's FY25 results assistant. Your ONLY knowledge is the CONTEXT below, taken from the official FY25 press release (fiscal year ended 31 Dec 2025).

Rules — non-negotiable:
1. Answer ONLY with facts present in CONTEXT. Never use outside knowledge or invent figures.
2. If the answer is not in CONTEXT, reply: "I don't have that information in the FY25 press release." — optionally point to what related information IS available.
3. Cite the source page after each fact, using the [p.N] tags present in CONTEXT.
4. Keep units exactly as the source (VND bn / VND trillion / %). Never convert currencies.
5. Be concise: 1-4 sentences for facts, a short structured answer for analysis.
6. This is factual reporting, not financial advice; refuse advice requests."""

def build_context(metric_block: str, chunks: list[dict]) -> tuple[str, list[Citation]]:
    parts: list[str] = []
    citations: list[Citation] = []
    if metric_block:
        parts.append("VERIFIED FINANCIAL METRICS (exact figures):\n" + metric_block)
        citations.append(Citation(page=13, snippet="FY25 financial summary table (verified figures)"))
    for c in chunks:
        parts.append(f"[p.{c['page']}] ({c['section']})\n{c['text']}")
        citations.append(Citation(page=c["page"], snippet=c["text"][:200]))
    return "\n\n---\n\n".join(parts), citations

def answer(llm: LLMClient, model_id: str, history: list[Turn],
           standalone_query: str, context: str) -> str:
    messages = [{"role": t.role, "content": t.content} for t in history[-6:]]
    messages.append({"role": "user",
                     "content": f"CONTEXT:\n{context}\n\nQUESTION: {standalone_query}"})
    return llm.converse(model_id, ANSWER_SYSTEM, messages, temperature=0.1, max_tokens=1024)
```

`backend/app/services/pipeline.py`:
```python
import json
import time
import uuid
from pathlib import Path
from app.config import Settings
from app.models import ChatResponse, Citation, Turn
from app.services import answerer
from app.services.llm import LLMClient
from app.services.metrics_store import MetricsStore
from app.services.retrieval import Retriever, expand_query
from app.services.router_svc import route
from app.stores import make_store

CHITCHAT_REPLY = ("Hi! I answer questions about Techcombank's FY25 results "
                  "(fiscal year ended 31 Dec 2025) based on the official press release. "
                  "Try: “What was profit before tax in FY25?”")
OOS_REPLY = ("I can only answer from Techcombank's FY25 results press release, so I can't help "
             "with that. I can cover FY25/quarterly financials, subsidiaries (TCBS, Techcom Life, "
             "TCGI), ratings, and business highlights.")

class ChatPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.llm = LLMClient(settings)
        self.retriever = Retriever(settings.artifacts_dir)
        self.metrics = MetricsStore(Path(settings.artifacts_dir) / "metrics.json")
        self.glossary: dict[str, str] = json.loads(
            (Path(settings.artifacts_dir) / "glossary.json").read_text(encoding="utf-8"))
        self.store = make_store(settings)

    def handle(self, session_id: str | None, message: str) -> ChatResponse:
        t0 = time.monotonic()
        sid = session_id or uuid.uuid4().hex
        history = self.store.get(sid)
        decision = route(self.llm, self.settings.model_router_id, history, message)

        citations: list[Citation] = []
        model_used = self.settings.model_router_id
        if decision.intent == "chitchat":
            reply = CHITCHAT_REPLY
        elif decision.intent == "out_of_scope":
            reply = OOS_REPLY
        else:
            metric_block = ""
            chunks: list[dict] = []
            if decision.intent in ("metric", "hybrid"):
                hits = self.metrics.lookup(decision.standalone_query)
                metric_block = self.metrics.render(hits, decision.standalone_query)
            if decision.intent in ("narrative", "hybrid") or not metric_block:
                q = expand_query(decision.standalone_query, self.glossary)
                chunks = self.retriever.search(q, self.llm.embed_query(q), top_k=6)
            context, citations = answerer.build_context(metric_block, chunks)
            model_used = (self.settings.model_simple_id if decision.complexity == "simple"
                          else self.settings.model_analytical_id)
            reply = answerer.answer(self.llm, model_used, history,
                                    decision.standalone_query, context)

        self.store.append(sid, Turn(role="user", content=message))
        self.store.append(sid, Turn(role="assistant", content=reply))
        return ChatResponse(session_id=sid, reply=reply, citations=citations,
                            route=decision.intent, model=model_used.split(".")[-1],
                            latency_ms=int((time.monotonic() - t0) * 1000))
```

`backend/app/api/chat.py`:
```python
import time
from collections import defaultdict, deque
from fastapi import APIRouter, HTTPException, Request
from app.models import ChatRequest, ChatResponse

router = APIRouter()
_hits: dict[str, deque] = defaultdict(deque)

def _rate_limited(key: str, per_min: int) -> bool:
    now = time.monotonic()
    q = _hits[key]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= per_min:
        return True
    q.append(now)
    return False

@router.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request) -> ChatResponse:
    pipeline = request.app.state.pipeline
    key = req.session_id or (request.client.host if request.client else "anon")
    if _rate_limited(key, pipeline.settings.rate_limit_per_min):
        raise HTTPException(status_code=429, detail="Too many requests — please slow down.")
    try:
        return pipeline.handle(req.session_id, req.message)
    except Exception:
        raise HTTPException(status_code=503,
                            detail="The assistant is busy right now. Please try again shortly.")
```

`backend/app/main.py`:
```python
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.chat import router as chat_router
from app.config import get_settings
from app.services.pipeline import ChatPipeline

def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="TCB FY25 Chatbot")
    app.state.pipeline = ChatPipeline(settings)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "chunks": len(app.state.pipeline.retriever.chunks),
                "mock": settings.mock_llm}

    app.include_router(chat_router)
    static = Path(settings.static_dir)
    if static.is_dir():
        app.mount("/", StaticFiles(directory=static, html=True), name="spa")
    return app

app = create_app()
```
- [ ] **Step 4: Run whole suite**: `pytest -v` → ALL PASS (chunker, metrics data/store, retrieval, sessions, llm, router, api).
- [ ] **Step 5: Manual smoke with real Bedrock** (creds from Task 1):
```powershell
$env:MOCK_LLM="false"; .venv\Scripts\uvicorn.exe app.main:app --app-dir backend --port 8000
# second terminal:
curl -s -X POST localhost:8000/api/chat -H "content-type: application/json" -d '{"message":"What was profit before tax in FY25?"}'
```
Expected: reply contains `32,538` (or `32.5 trillion`) with `[p.13]`, route `metric`, model `claude-haiku-…`. Then ask `{"message":"why did CAR drop in Q4?","session_id":"<from first>"}` → mentions dividend, route `hybrid`, model sonnet.
- [ ] **Step 6: Commit**: `git add -A && git commit -m "feat(backend): answerer, chat pipeline, API with rate limiting"`

### Task 12: Dockerfile + compose + mock-mode boot check

**Files:** Create: `Dockerfile`, `.dockerignore`, `docker-compose.yml`

- [ ] **Step 1: Write the files**

`Dockerfile`:
```dockerfile
# ---- frontend build ----
FROM node:22-alpine AS fe
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- runtime ----
FROM python:3.12-slim
WORKDIR /srv
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY data/artifacts ./data/artifacts
COPY --from=fe /fe/dist ./static
ENV ARTIFACTS_DIR=/srv/data/artifacts STATIC_DIR=/srv/static
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`.dockerignore`:
```
.git
.venv
node_modules
frontend/node_modules
frontend/dist
infra
docs
tests
requirements
reports
**/__pycache__
.env*
```

`docker-compose.yml`:
```yaml
services:
  app:
    build: .
    ports:
      - "8080:8000"
    env_file: .env
    environment:
      SESSION_STORE: memory
```

- [ ] **Step 2: Build & boot in mock mode** (frontend doesn't exist yet — create a placeholder so the build passes: `frontend/` comes in Task 13; for now temporarily comment the three `COPY frontend`/`--from=fe` lines OR do Task 13 first if executing sequentially — **preferred: reorder is allowed, run this step after Task 13**). With frontend present:
```powershell
copy .env.example .env   # leave MOCK_LLM=true, no creds
docker compose up --build -d
curl -s localhost:8080/api/health
curl -s -X POST localhost:8080/api/chat -H "content-type: application/json" -d '{"message":"hello"}'
docker compose down
```
Expected: health `{"status":"ok",...,"mock":true}`; chat returns `[MOCK]…`.
- [ ] **Step 3: Commit**: `git add -A && git commit -m "feat: dockerfile and compose for one-command local run"`

---

## Phase 2 — Frontend (H12–24)

### Task 13: React chat UI (Vite + TS + Tailwind)

**Files:** Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`, `frontend/src/{main.tsx,index.css,types.ts,api.ts,App.tsx}`, `frontend/src/components/{Chat.tsx,Message.tsx,Composer.tsx}`

**Interfaces consumed:** `POST /api/chat` per Task 11 DTOs.

- [ ] **Step 1: Write the files**

`frontend/package.json`:
```json
{
  "name": "tcb-chatbot-ui",
  "private": true,
  "type": "module",
  "scripts": { "dev": "vite", "build": "tsc -b && vite build", "preview": "vite preview" },
  "dependencies": { "react": "^19.1.0", "react-dom": "^19.1.0" },
  "devDependencies": {
    "@types/react": "^19.1.0", "@types/react-dom": "^19.1.0",
    "@vitejs/plugin-react": "^4.5.0", "typescript": "~5.9.0",
    "vite": "^7.0.0", "tailwindcss": "^4.1.0", "@tailwindcss/vite": "^4.1.0"
  }
}
```

`frontend/vite.config.ts`:
```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { "/api": "http://localhost:8000" } },
});
```

`frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022", "lib": ["ES2022", "DOM", "DOM.Iterable"], "module": "ESNext",
    "moduleResolution": "bundler", "jsx": "react-jsx", "strict": true,
    "noEmit": true, "skipLibCheck": true, "isolatedModules": true, "types": ["vite/client"]
  },
  "include": ["src"]
}
```

`frontend/index.html`:
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>TCB FY25 Assistant</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`frontend/src/index.css`:
```css
@import "tailwindcss";
```

`frontend/src/types.ts`:
```ts
export interface Citation { page: number; snippet: string }
export interface ChatResponse {
  session_id: string; reply: string; citations: Citation[];
  route: string; model: string; latency_ms: number;
}
export interface UiMessage {
  role: "user" | "assistant"; content: string;
  citations?: Citation[]; route?: string; model?: string; error?: boolean;
}
```

`frontend/src/api.ts`:
```ts
import type { ChatResponse } from "./types";

export async function sendChat(message: string, sessionId: string | null): Promise<ChatResponse> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });
  if (!res.ok) {
    const detail = await res.json().then((b) => b.detail).catch(() => res.statusText);
    throw new Error(typeof detail === "string" ? detail : "Request failed");
  }
  return res.json();
}
```

`frontend/src/main.tsx`:
```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode><App /></StrictMode>
);
```

`frontend/src/App.tsx`:
```tsx
import Chat from "./components/Chat";

export default function App() {
  return (
    <div className="min-h-screen bg-slate-100 flex flex-col">
      <header className="bg-red-700 text-white px-6 py-4 shadow">
        <h1 className="text-lg font-semibold">Techcombank FY25 Results Assistant</h1>
        <p className="text-xs opacity-80">
          Grounded in the official FY25 press release (year ended 31 Dec 2025) — answers cite pages.
        </p>
      </header>
      <Chat />
    </div>
  );
}
```

`frontend/src/components/Chat.tsx`:
```tsx
import { useEffect, useRef, useState } from "react";
import { sendChat } from "../api";
import type { UiMessage } from "../types";
import Message from "./Message";
import Composer from "./Composer";

const STARTERS = [
  "What was profit before tax in FY25?",
  "How did the CASA ratio evolve during 2025?",
  "Why did CAR decrease in Q4 2025?",
  "Tell me about the TCBS IPO.",
];

export default function Chat() {
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(
    () => localStorage.getItem("tcb_session"));
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  async function ask(text: string) {
    if (!text.trim() || busy) return;
    setMessages((m) => [...m, { role: "user", content: text }]);
    setBusy(true);
    try {
      const res = await sendChat(text, sessionId);
      setSessionId(res.session_id);
      localStorage.setItem("tcb_session", res.session_id);
      setMessages((m) => [...m, { role: "assistant", content: res.reply,
        citations: res.citations, route: res.route, model: res.model }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", error: true,
        content: e instanceof Error ? e.message : "Something went wrong." }]);
    } finally {
      setBusy(false);
    }
  }

  function newChat() {
    localStorage.removeItem("tcb_session");
    setSessionId(null);
    setMessages([]);
  }

  return (
    <main className="flex-1 flex flex-col max-w-3xl w-full mx-auto p-4">
      <div className="flex justify-end mb-2">
        <button onClick={newChat} className="text-sm text-slate-500 hover:text-red-700">
          + New chat
        </button>
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto pb-4">
        {messages.length === 0 && (
          <div className="grid gap-2 sm:grid-cols-2 mt-8">
            {STARTERS.map((s) => (
              <button key={s} onClick={() => ask(s)}
                className="text-left text-sm bg-white border border-slate-200 rounded-xl p-3 hover:border-red-400 shadow-sm">
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.map((m, i) => <Message key={i} msg={m} />)}
        {busy && <div className="text-sm text-slate-400 animate-pulse">Thinking…</div>}
        <div ref={endRef} />
      </div>
      <Composer disabled={busy} onSend={ask} />
    </main>
  );
}
```

`frontend/src/components/Message.tsx`:
```tsx
import { useState } from "react";
import type { UiMessage } from "../types";

export default function Message({ msg }: { msg: UiMessage }) {
  const [open, setOpen] = useState(false);
  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="bg-red-700 text-white rounded-2xl rounded-br-sm px-4 py-2 max-w-[80%]">
          {msg.content}
        </div>
      </div>
    );
  }
  return (
    <div className="flex flex-col items-start gap-1 max-w-[85%]">
      <div className={`rounded-2xl rounded-bl-sm px-4 py-2 whitespace-pre-wrap shadow-sm ${
        msg.error ? "bg-amber-50 border border-amber-300 text-amber-900" : "bg-white border border-slate-200"}`}>
        {msg.content}
      </div>
      {(msg.route || msg.citations?.length) ? (
        <div className="flex flex-wrap items-center gap-1 pl-1">
          {msg.route && (
            <span className="text-[10px] uppercase tracking-wide bg-slate-200 text-slate-600 rounded px-1.5 py-0.5">
              {msg.route} · {msg.model}
            </span>
          )}
          {msg.citations?.map((c, i) => (
            <button key={i} onClick={() => setOpen(!open)}
              className="text-[10px] bg-blue-50 text-blue-700 border border-blue-200 rounded px-1.5 py-0.5 hover:bg-blue-100">
              p.{c.page}
            </button>
          ))}
        </div>
      ) : null}
      {open && msg.citations?.length ? (
        <div className="text-xs bg-slate-50 border border-slate-200 rounded-lg p-2 space-y-1">
          {msg.citations.map((c, i) => (
            <p key={i}><span className="font-semibold">p.{c.page}:</span> “{c.snippet}…”</p>
          ))}
        </div>
      ) : null}
    </div>
  );
}
```

`frontend/src/components/Composer.tsx`:
```tsx
import { useState } from "react";

export default function Composer({ disabled, onSend }:
  { disabled: boolean; onSend: (text: string) => void }) {
  const [text, setText] = useState("");
  function submit(e: React.FormEvent) {
    e.preventDefault();
    onSend(text);
    setText("");
  }
  return (
    <form onSubmit={submit} className="flex gap-2 pt-2 border-t border-slate-200">
      <input value={text} onChange={(e) => setText(e.target.value)} disabled={disabled}
        placeholder="Ask about Techcombank's FY25 results…"
        className="flex-1 rounded-xl border border-slate-300 px-4 py-2 focus:outline-none focus:border-red-500 bg-white" />
      <button disabled={disabled || !text.trim()}
        className="bg-red-700 text-white rounded-xl px-5 py-2 disabled:opacity-40">
        Send
      </button>
    </form>
  );
}
```

- [ ] **Step 2: Install & typecheck-build**:
```powershell
cd frontend; npm install; npm run build; cd ..
```
Expected: `tsc -b` clean, `vite build` emits `frontend/dist`.
- [ ] **Step 3: Manual verification (dev proxy)**: run backend (`uvicorn … --app-dir backend --port 8000`, MOCK_LLM ok) + `npm run dev --prefix frontend` → open http://localhost:5173 → starter question renders reply, citation chip expands, route badge visible, New chat resets.
- [ ] **Step 4: Now finish Task 12 Step 2** (full docker compose mock boot) if it was deferred.
- [ ] **Step 5: Commit**: `git add -A && git commit -m "feat(frontend): chat UI with citations, route badges, sessions"`

---

## Phase 3 — Infrastructure & CI/CD (H24–36)

### Task 14: Terraform bootstrap stack (state, OIDC, CI role, ECR)

**Files:** Create: `infra/bootstrap/main.tf`, `infra/bootstrap/variables.tf`, `infra/bootstrap/outputs.tf`

- [ ] **Step 1: Write the files**

`infra/bootstrap/variables.tf`:
```hcl
variable "github_repo" {
  description = "GitHub repo allowed to assume the CI role, e.g. yourname/tcb-fy25-chatbot"
  type        = string
}

variable "region" {
  type    = string
  default = "us-east-1"
}
```

`infra/bootstrap/main.tf`:
```hcl
terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

provider "aws" {
  region = var.region
  default_tags { tags = { project = "tcb-chatbot", stack = "bootstrap" } }
}

data "aws_caller_identity" "me" {}

resource "aws_s3_bucket" "tfstate" {
  bucket = "tcb-chatbot-tfstate-${data.aws_caller_identity.me.account_id}"
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket                  = aws_s3_bucket.tfstate.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_ecr_repository" "app" {
  name         = "tcb-chatbot"
  force_delete = true
}

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

data "aws_iam_policy_document" "ci_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:*"]
    }
  }
}

resource "aws_iam_role" "ci" {
  name               = "tcb-chatbot-github-actions"
  assume_role_policy = data.aws_iam_policy_document.ci_trust.json
}

# Take-home trade-off, stated in SOLUTION.md: AdministratorAccess keeps the 48h
# pipeline unblocked; production would scope to ECS/ECR/IAM-passrole/etc.
resource "aws_iam_role_policy_attachment" "ci_admin" {
  role       = aws_iam_role.ci.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}
```

`infra/bootstrap/outputs.tf`:
```hcl
output "ci_role_arn"   { value = aws_iam_role.ci.arn }
output "tfstate_bucket" { value = aws_s3_bucket.tfstate.bucket }
output "ecr_repo_url"  { value = aws_ecr_repository.app.repository_url }
```

- [ ] **Step 2: Validate**: `terraform -chdir=infra/bootstrap init && terraform -chdir=infra/bootstrap validate && terraform -chdir=infra/bootstrap fmt -check` → valid.
- [ ] **Step 3: ⚠️ USER ACTION — apply bootstrap** (local creds, state stays local & gitignored):
```powershell
terraform -chdir=infra/bootstrap apply -var "github_repo=<yourname>/tcb-fy25-chatbot"
```
Type `yes`. Record the three outputs.
- [ ] **Step 4: ⚠️ USER ACTION — set GitHub repo variables** (repo → Settings → Secrets and variables → Actions → **Variables**): `AWS_ROLE_ARN` = ci_role_arn output, `TFSTATE_BUCKET` = tfstate_bucket output, `ALERT_EMAIL` = your email.
- [ ] **Step 5: Commit**: `git add -A && git commit -m "feat(infra): bootstrap stack - state bucket, OIDC CI role, ECR"`

### Task 15: Terraform main stack (VPC, ALB, ECS, DynamoDB, S3, budget)

**Files:** Create: `infra/main/{backend.tf,providers.tf,variables.tf,vpc.tf,alb.tf,ecs.tf,iam.tf,dynamodb.tf,s3.tf,budget.tf,outputs.tf}`

- [ ] **Step 1: Write the files**

`infra/main/backend.tf`:
```hcl
terraform {
  required_version = ">= 1.10"
  backend "s3" {
    key          = "main/terraform.tfstate"
    use_lockfile = true
    # bucket + region supplied via -backend-config at init
  }
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}
```

`infra/main/providers.tf`:
```hcl
provider "aws" {
  region = var.region
  default_tags { tags = { project = "tcb-chatbot", stack = "main" } }
}

data "aws_caller_identity" "me" {}
```

`infra/main/variables.tf`:
```hcl
variable "region" {
  type    = string
  default = "us-east-1"
}

variable "image_tag" {
  description = "Docker image tag (git SHA) to deploy"
  type        = string
}

variable "alert_email" {
  description = "Email for the budget alert"
  type        = string
}

variable "budget_limit" {
  type    = string
  default = "10"
}

locals {
  name     = "tcb-chatbot"
  app_port = 8000
  image    = "${data.aws_caller_identity.me.account_id}.dkr.ecr.${var.region}.amazonaws.com/${local.name}:${var.image_tag}"
}
```

`infra/main/vpc.tf`:
```hcl
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  tags                 = { Name = local.name }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.${count.index + 1}.0/24"
  availability_zone       = "${var.region}${count.index == 0 ? "a" : "b"}"
  map_public_ip_on_launch = true
  tags                    = { Name = "${local.name}-public-${count.index}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}
```

`infra/main/alb.tf`:
```hcl
resource "aws_security_group" "alb" {
  name_prefix = "${local.name}-alb-"
  vpc_id      = aws_vpc.main.id
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_lb" "main" {
  name               = local.name
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id
}

resource "aws_lb_target_group" "app" {
  name        = local.name
  port        = local.app_port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"
  health_check {
    path                = "/api/health"
    matcher             = "200"
    interval            = 30
    healthy_threshold   = 2
    unhealthy_threshold = 5
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}
```

`infra/main/ecs.tf`:
```hcl
resource "aws_ecs_cluster" "main" {
  name = local.name
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${local.name}"
  retention_in_days = 7
}

resource "aws_security_group" "svc" {
  name_prefix = "${local.name}-svc-"
  vpc_id      = aws_vpc.main.id
  ingress {
    from_port       = local.app_port
    to_port         = local.app_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_ecs_task_definition" "app" {
  family                   = local.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  container_definitions = jsonencode([{
    name         = "app"
    image        = local.image
    essential    = true
    portMappings = [{ containerPort = local.app_port, protocol = "tcp" }]
    environment = [
      { name = "BEDROCK_REGION", value = var.region },
      { name = "SESSION_STORE", value = "dynamo" },
      { name = "SESSIONS_TABLE", value = aws_dynamodb_table.sessions.name },
      { name = "MOCK_LLM", value = "false" },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "app"
      }
    }
  }])
}

resource "aws_ecs_service" "app" {
  name            = local.name
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.svc.id]
    assign_public_ip = true
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "app"
    container_port   = local.app_port
  }
  depends_on = [aws_lb_listener.http]
}
```

`infra/main/iam.tf`:
```hcl
data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${local.name}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "task" {
  name               = "${local.name}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

data "aws_iam_policy_document" "task" {
  statement {
    sid       = "Bedrock"
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = ["*"] # inference profiles fan out to regional model ARNs
  }
  statement {
    sid       = "Sessions"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.sessions.arn]
  }
}

resource "aws_iam_role_policy" "task" {
  name   = "${local.name}-task"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}
```

`infra/main/dynamodb.tf`:
```hcl
resource "aws_dynamodb_table" "sessions" {
  name         = "${local.name}-sessions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "session_id"
  attribute {
    name = "session_id"
    type = "S"
  }
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}
```

`infra/main/s3.tf`:
```hcl
resource "aws_s3_bucket" "artifacts" {
  bucket = "${local.name}-artifacts-${data.aws_caller_identity.me.account_id}"
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
```

`infra/main/budget.tf`:
```hcl
resource "aws_budgets_budget" "monthly" {
  name         = "${local.name}-monthly"
  budget_type  = "COST"
  limit_amount = var.budget_limit
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}
```

`infra/main/outputs.tf`:
```hcl
output "alb_dns_name" { value = aws_lb.main.dns_name }
output "cluster_name" { value = aws_ecs_cluster.main.name }
output "service_name" { value = aws_ecs_service.app.name }
```

- [ ] **Step 2: Validate**: `terraform -chdir=infra/main init -backend=false && terraform -chdir=infra/main validate && terraform -chdir=infra fmt -check -recursive` → valid.
- [ ] **Step 3: Commit**: `git add -A && git commit -m "feat(infra): main stack - vpc, alb, ecs fargate, dynamodb, s3, budget"`

### Task 16: GitHub Actions workflows + ⚠️ first deploy

**Files:** Create: `.github/workflows/deploy.yml`, `.github/workflows/pr.yml`

- [ ] **Step 1: Write the files**

`.github/workflows/deploy.yml`:
```yaml
name: deploy
on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  id-token: write
  contents: read

env:
  AWS_REGION: us-east-1
  ECR_REPOSITORY: tcb-chatbot

jobs:
  test:
    name: Run Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: pip }
      - run: pip install -r requirements-dev.txt
      - run: pytest
      - uses: actions/setup-node@v4
        with: { node-version: "22", cache: npm, cache-dependency-path: frontend/package-lock.json }
      - run: npm ci --prefix frontend
      - run: npm run build --prefix frontend
      - uses: hashicorp/setup-terraform@v3
      - run: terraform -chdir=infra/main init -backend=false
      - run: terraform -chdir=infra/main validate
      - run: terraform fmt -check -recursive infra

  build-and-push:
    name: Build and Push Docker Image
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}
      - id: ecr
        uses: aws-actions/amazon-ecr-login@v2
      - run: |
          docker build -t ${{ steps.ecr.outputs.registry }}/$ECR_REPOSITORY:${{ github.sha }} .
          docker push ${{ steps.ecr.outputs.registry }}/$ECR_REPOSITORY:${{ github.sha }}

  terraform-apply:
    name: Deploy Infrastructure
    needs: build-and-push
    runs-on: ubuntu-latest
    env:
      TF_VAR_image_tag: ${{ github.sha }}
      TF_VAR_alert_email: ${{ vars.ALERT_EMAIL }}
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}
      - uses: hashicorp/setup-terraform@v3
      - run: >
          terraform -chdir=infra/main init
          -backend-config="bucket=${{ vars.TFSTATE_BUCKET }}"
          -backend-config="region=${{ env.AWS_REGION }}"
      - run: terraform -chdir=infra/main apply -auto-approve

  smoke-test:
    name: Smoke Test
    needs: terraform-apply
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}
      - uses: hashicorp/setup-terraform@v3
      - id: out
        run: |
          terraform -chdir=infra/main init \
            -backend-config="bucket=${{ vars.TFSTATE_BUCKET }}" \
            -backend-config="region=${{ env.AWS_REGION }}"
          echo "alb=$(terraform -chdir=infra/main output -raw alb_dns_name)" >> "$GITHUB_OUTPUT"
      - run: aws ecs wait services-stable --cluster tcb-chatbot --services tcb-chatbot --region $AWS_REGION
      - name: Health check
        run: |
          for i in $(seq 1 30); do
            code=$(curl -s -o /dev/null -w "%{http_code}" "http://${{ steps.out.outputs.alb }}/api/health") && \
            [ "$code" = "200" ] && exit 0
            sleep 10
          done
          exit 1
      - name: Grounded answer check
        run: |
          reply=$(curl -s -X POST "http://${{ steps.out.outputs.alb }}/api/chat" \
            -H "content-type: application/json" \
            -d '{"message":"What was Techcombank profit before tax in FY25?"}')
          echo "$reply"
          echo "$reply" | grep -Eq "32[.,]5" || (echo "expected PBT figure missing" && exit 1)

  deployment-status:
    name: Deployment Status
    needs: [smoke-test]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - run: |
          echo "smoke-test result: ${{ needs.smoke-test.result }}"
          [ "${{ needs.smoke-test.result }}" = "success" ]
```

`.github/workflows/pr.yml`:
```yaml
name: pr
on: pull_request

permissions:
  id-token: write
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: pip }
      - run: pip install -r requirements-dev.txt
      - run: pytest
      - uses: actions/setup-node@v4
        with: { node-version: "22", cache: npm, cache-dependency-path: frontend/package-lock.json }
      - run: npm ci --prefix frontend && npm run build --prefix frontend

  plan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars.AWS_ROLE_ARN }}
          aws-region: us-east-1
      - uses: hashicorp/setup-terraform@v3
      - run: >
          terraform -chdir=infra/main init
          -backend-config="bucket=${{ vars.TFSTATE_BUCKET }}"
          -backend-config="region=us-east-1"
      - run: terraform -chdir=infra/main plan -var image_tag=pr -var alert_email=${{ vars.ALERT_EMAIL }}
```

- [ ] **Step 2: ⚠️ USER ACTION — push to GitHub**:
```powershell
git remote add origin https://github.com/<yourname>/tcb-fy25-chatbot.git
git add -A; git commit -m "feat(ci): deploy and pr workflows"; git push -u origin main
```
- [ ] **Step 3: Watch the run** (Actions tab). Expected first-run flow: test ✓ → build ✓ → apply ✓ (creates ~25 resources, ALB takes ~3 min) → smoke ✓ → status ✓. Debug loop: read the failing job log, fix, push again. Common first-run issues: repo variables unset (assume-role error), Bedrock access not granted (smoke 503 → check Task 1 Step 4), service still stabilizing (health retries cover ~5 min).
- [ ] **Step 4: Open the app**: `terraform -chdir=infra/main output -raw alb_dns_name` (or from job log) → browse `http://<alb-dns>` → ask a question with real Bedrock. **Screenshot the green pipeline graph** (it mirrors their example) for the write-up.

---

## Phase 4 — Evals, docs, video, submission (H36–48)

### Task 17: Golden eval suite

**Files:** Create: `tests/evals/__init__.py` (empty), `tests/evals/golden.yaml`, `tests/evals/test_evals.py`

**Interfaces consumed:** live app pipeline via `create_app()` TestClient with real Bedrock (`MOCK_LLM=false`, creds required). Run: `pytest -m eval -s`.

- [ ] **Step 1: Write** `tests/evals/golden.yaml`:
```yaml
# expect_any: assertion passes if ANY listed string appears in the reply (case-insensitive).
# expect_all_any: list of groups; EVERY group must have at least one match.
# expect_refusal: reply must decline (judged by Haiku).
# turns: multi-turn conversations reuse one session.
cases:
  - id: pbt_fy25
    turns: ["What was Techcombank's profit before tax in FY25?"]
    expect_any: ["32,538", "32.5"]
  - id: casa_4q25
    turns: ["What was the CASA ratio at the end of 2025?"]
    expect_any: ["40.4"]
  - id: npl_4q25
    turns: ["What was the NPL ratio in 4Q25?"]
    expect_any: ["1.13"]
  - id: car_4q25
    turns: ["What was the Basel II CAR at the end of 2025?"]
    expect_any: ["14.6"]
  - id: toi_fy25_growth
    turns: ["What was total operating income in FY25 and how much did it grow?"]
    expect_all_any: [["53,391", "53.4"], ["13.6"]]
  - id: customers
    turns: ["How many customers did Techcombank have at the end of 2025?"]
    expect_any: ["18"]
  - id: deposits
    turns: ["What were customer deposits at end-2025?"]
    expect_any: ["665"]
  - id: car_why_drop
    turns: ["Why did CAR decrease in Q4 2025?"]
    expect_any: ["dividend"]
  - id: banca_story
    turns: ["What happened with bancassurance fees in 2025?"]
    expect_any: ["91.8", "termination"]
  - id: tcbs_ipo
    turns: ["Tell me about the TCBS listing."]
    expect_any: ["46,800", "October", "2.31 billion"]
  - id: fitch_rating
    turns: ["What rating did Fitch assign Techcombank?"]
    expect_all_any: [["BB-"], ["Positive"]]
  - id: followup_chain
    turns: ["What was the CASA ratio in FY25?", "What about Q3?"]
    expect_any: ["42.5"]
  - id: oos_fy23
    turns: ["What was Techcombank's profit in FY23?"]
    expect_refusal: true
  - id: oos_competitor
    turns: ["What is Vietcombank's CASA ratio?"]
    expect_refusal: true
  - id: oos_advice
    turns: ["Should I buy TCB stock right now?"]
    expect_refusal: true
```

- [ ] **Step 2: Write** `tests/evals/test_evals.py`:
```python
"""Golden evals against real Bedrock. Run: pytest -m eval -s"""
import os
import pathlib
import pytest
import yaml

os.environ.setdefault("SESSION_STORE", "memory")
pytestmark = pytest.mark.eval

from fastapi.testclient import TestClient  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.llm import LLMClient  # noqa: E402

CASES = yaml.safe_load(
    (pathlib.Path(__file__).parent / "golden.yaml").read_text(encoding="utf-8"))["cases"]
client = TestClient(create_app())
judge = LLMClient(Settings(mock_llm=False))

JUDGE_SYSTEM = ("You judge chatbot replies. Answer with exactly YES or NO. "
                "YES if the reply DECLINES to answer (says the information is not in the "
                "FY25 press release / out of scope / cannot help). NO otherwise.")

def ask(turns: list[str]) -> str:
    sid = None
    reply = ""
    for t in turns:
        r = client.post("/api/chat", json={"session_id": sid, "message": t})
        assert r.status_code == 200, r.text
        body = r.json()
        sid, reply = body["session_id"], body["reply"]
    return reply

@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_golden(case):
    reply = ask(case["turns"])
    low = reply.lower()
    print(f"\n[{case['id']}] {reply[:160]}")
    if case.get("expect_refusal"):
        verdict = judge.converse(
            "us.anthropic.claude-haiku-4-5-20251001-v1:0", JUDGE_SYSTEM,
            [{"role": "user", "content": f"Reply: {reply}"}], max_tokens=5)
        assert "YES" in verdict.upper(), f"expected refusal, got: {reply}"
    if "expect_any" in case:
        assert any(s.lower() in low for s in case["expect_any"]), reply
    if "expect_all_any" in case:
        for group in case["expect_all_any"]:
            assert any(s.lower() in low for s in group), f"missing {group}: {reply}"
```

- [ ] **Step 3: Run** (real creds, local): `pytest -m eval -s` → target **15/15**. For each failure: print shows the actual reply — fix the router prompt / metric aliases / answer prompt (not the test) unless the expectation itself is wrong vs the PDF.
- [ ] **Step 4: Record results** (copy the pass/fail table output) → save to `docs/eval-results.md` for SOLUTION.md.
- [ ] **Step 5: Commit**: `git add -A && git commit -m "test: golden eval suite with refusal judging - 15/15"`

### Task 18: README + SOLUTION.md

**Files:** Create: `README.md`, `SOLUTION.md`. Modify: none.

- [ ] **Step 1: Write `README.md`** with exactly these sections (fill the placeholders from your run):
  1. Title + one-line description + demo video link (add after Task 19) + live URL note ("deployed ALB URL available on request / shown in video — torn down to save cost" if you destroy it).
  2. **Quickstart (local, < 3 min):**
     ```
     git clone https://github.com/<you>/tcb-fy25-chatbot && cd tcb-fy25-chatbot
     cp .env.example .env        # paste AWS creds with Bedrock access (us-east-1)
     docker compose up --build   # ~2 min build
     # open http://localhost:8080     — no creds? set MOCK_LLM=true for canned answers
     ```
  3. Architecture diagram (copy the mermaid block from `docs/superpowers/specs/2026-07-08-tcb-rag-chatbot-design.md` §2).
  4. Repo map (one line per top-level dir).
  5. AWS deployment: bootstrap steps (Task 14 Steps 3–4 verbatim), then "push to main → pipeline deploys".
  6. Testing: `pytest` (unit), `pytest -m eval` (golden evals), CI smoke test.
- [ ] **Step 2: Write `SOLUTION.md`** with exactly these sections:
  1. **How I decomposed the problem** — the three-store insight (narrative/metrics/glossary); why one knowledge base is wrong for this document; the page-13 table failure mode with a concrete example.
  2. **Limitations of RAG and mitigations** — table: {numeric precision → structured store; follow-ups → query rewriting; acronyms → glossary expansion; retrieval misses → hybrid BM25+vector RRF; hallucination → grounding prompt + citations + refusals + evals}.
  3. **Model efficiency** — routing table: {router: Haiku ~300 tok; simple: Haiku; analytical: Sonnet; embeddings: Titan V2} with per-1K-token prices and an example cost per question (~$0.002 simple / ~$0.01 analytical).
  4. **Why not X** — Bedrock KB/OpenSearch (cost, table mangling, no local run, black box — right-sized instead; graduation trigger: multi-document corpus), fine-tuning (wrong tool for a single evolving document), agentic loops (latency/cost for no benefit here).
  5. **Evaluation** — paste `docs/eval-results.md` table; groundedness judging method; what 15/15 does and doesn't prove.
  6. **Infra & security decisions** — OIDC no-secrets CI, AdminAccess trade-off + prod scoping, public-subnet trade-off + prod path (private subnets, VPC endpoints, WAF, Cognito), budget alarm, rate limiting.
  7. **On Jarvis** — evaluated; borrowed conventions (native Terraform, OIDC, no lock-in); hand-rolled for defensibility at this scope.
  8. **What I'd do next** — streaming, Vietnamese support, conversation summarization, multi-doc corpus + KB, re-ranker, contextual-grounding guardrails.
- [ ] **Step 3: Commit**: `git add -A && git commit -m "docs: README quickstart + SOLUTION write-up"`

### Task 19: ⚠️ USER ACTION — clean-clone test, demo video, submit

- [ ] **Step 1: Clean-clone 3-minute test**:
```powershell
cd $env:TEMP; git clone https://github.com/<you>/tcb-fy25-chatbot demo-test; cd demo-test
copy .env.example .env   # paste real creds
Measure-Command { docker compose up --build -d }
start http://localhost:8080
```
Ask "What was PBT in FY25?" → expect 32,538 with [p.13]. Total time must be < 3 min (build is ~2). If over: check Docker layer caching, trim requirements.
- [ ] **Step 2: Record demo video (~4 min)** — script:
  1. (30s) Repo tour: README, the three artifacts in `data/artifacts/`, one sentence on the three-store design.
  2. (45s) Clean clone → `docker compose up` → app opens (can be pre-recorded/sped up).
  3. (90s) Chat demo in this order: "What was profit before tax in FY25?" (metric route, Haiku badge, [p.13] citation) → "What about 4Q25 alone?" (follow-up resolution) → "Why did CAR decrease in Q4?" (hybrid route, Sonnet badge, dividend answer) → "What was Techcombank's profit in FY23?" (refusal — the anti-hallucination money shot) → "Should I buy TCB stock?" (refusal).
  4. (45s) AWS console: ECS service running, DynamoDB sessions table with items, CloudWatch logs.
  5. (30s) GitHub Actions: the green `deploy` run graph (mirrors their example screenshot), point at smoke-test job asserting a grounded answer.
  Upload (YouTube unlisted / Drive), link in README.
- [ ] **Step 3: Final sweep**: `pytest` green; `pytest -m eval` rerun if any prompt changed; README video link committed; `git push`; Actions green; decide teardown (`terraform -chdir=infra/main destroy` after review — IaC redeploys in one push; state the choice in README).
- [ ] **Step 4: Submit** the repo link + video per the assignment instructions.

---

## Self-review notes (already applied)

- Spec §3.1→Tasks 3–5, §3.2→Tasks 6–11, §3.3→Task 13, §3.4→Tasks 14–15, §3.5→Task 16, §4→Tasks 7/10/11/17, §5 error handling→Tasks 9/11 (retries, fallback decision, metric-miss fallthrough, rate limit, 503), §6→Tasks 3–11/17 + CI smoke, §7 schedule→phase headers, §10→Tasks 18–19. Gap check: none.
- Task 12 has an explicit ordering note (frontend build dependency) — execute Step 2 after Task 13 if running strictly sequentially.
- Type consistency verified: `Turn`/`ChatResponse`/`Citation` defined Task 6, consumed Tasks 10–13; `RouteDecision` defined Task 10, consumed Task 11; `Retriever.search(query, query_vec, top_k)` defined Task 8, called Task 11; `LLMClient.converse/embed_query` defined Task 9, consumed Tasks 10/11/17; env var names in ecs.tf match `Settings` fields (pydantic-settings is case-insensitive).
