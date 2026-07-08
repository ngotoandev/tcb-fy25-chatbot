# Solution write-up: TCB FY25 results chatbot

This is the "how I thought through the problem" write-up the assignment asks for. It's organized
around the assignment's own hints, in the order they're most useful to explain: how the document
got decomposed, where plain RAG breaks on it and what I did about it, how model routing keeps cost
down, why I didn't reach for heavier tools, what the evals show, the infra/security trade-offs I
made under a short build window, my read on the recommended tooling, and what I'd build next given
more time.

The companion [`README.md`](./README.md) has the architecture diagram and run instructions. The
design reasoning was captured up front, before writing code, in
[`docs/superpowers/specs/2026-07-08-tcb-rag-chatbot-design.md`](./docs/superpowers/specs/2026-07-08-tcb-rag-chatbot-design.md)
— this write-up expands on that with what actually happened during the build, including the
places the design changed once I hit real constraints.

---

## 1. How I decomposed the problem

The source document is Techcombank's FY25 press release — 14 pages, in three genuinely different
shapes:

- **Pages 1–11**: narrative prose — highlights, income-statement commentary, balance-sheet
  commentary, subsidiary write-ups (TCBS, Techcom Life, TCGI), customer/awards sections.
- **Page 12**: a two-column acronym glossary (CASA, CAR, NIM, …).
- **Page 13**: a dense financial summary table — three sub-blocks (Balance Sheet, Capital &
  Liquidity, Profitability), ~24 rows, each a metric name against either five quarterly columns or
  a mix of quarterly-plus-FY columns, holding most of the numbers a reader would actually ask
  about.
- Page 14 is blank.

The assignment's hint — "should the whole doc be in one knowledge base? What's the limitation of
RAG?" — is really asking whether it's safe to treat all of that as one undifferentiated blob of
text to chunk and embed. It isn't, and page 13 is the clearest reason why.

**The three-store design.** I split the document into three separate stores by *shape*, not by
page:

1. **Narrative store** (`ingest/chunker.py` → `data/artifacts/chunks.json`) — the prose sections,
   split on the document's own headings and packed to ~300 tokens with `{chunk_id, section,
   page}` metadata. 25 chunks in the current build. Embedded with Titan Text Embeddings V2 and
   retrieved with hybrid BM25 + cosine similarity (`backend/app/services/retrieval.py`).
2. **Structured metrics store** (`ingest/metrics_data.py` → `data/artifacts/metrics.json`) —
   every number on page 13, plus supplementary in-text figures scattered across pages 2–6 (fee
   breakdowns, subsidiary PBT, customer counts, the October dividend). 38 records, each
   `{metric_id, name, aliases[], unit, values: {period: number}, qoq, yoy, note, source_page}`.
   Looked up by exact alias/period match (`backend/app/services/metrics_store.py`), never
   embedded, never paraphrased by an LLM.
3. **Glossary store** (`ingest/glossary_data.py` → `data/artifacts/glossary.json`) — the 26
   acronym definitions from page 12, used purely for **query expansion** before
   retrieval/routing (`expand_query()` in `retrieval.py`), not as retrievable content competing
   for a slot in the narrative store.

**Why one knowledge base is wrong here, concretely.** Naive chunk-and-embed treats page 13 as more
prose: split it into ~300-token windows, embed each, and answer numeric questions via cosine
similarity like everything else. Two things break:

- *Chunk boundaries would split structure that matters.* The table has three sub-blocks with
  **different column schemes** — the Balance Sheet and Capital & Liquidity blocks are five
  quarterly columns (4Q24…4Q25); the Profitability block is 4Q24, 4Q25, a YoY delta, then FY24,
  FY25, an annual YoY delta. A chunker that doesn't know this is a table (`pdfplumber`'s own table
  detector mangles page 12's two-column glossary into one garbled cell for exactly this kind of
  reason — I checked the parsed output directly) would happily split mid-block and lose which
  header row a number belongs to.
- *Cosine similarity can't tell adjacent rows apart.* "Basel II CAR" and "Basel II Tier 1 ratio"
  are consecutive rows on page 13, both in the low-to-mid teens, both trending down over the
  year: CAR is `15.4 / 15.3 / 15.0 / 15.8 / 14.6`, Tier 1 is `14.7 / 14.7 / 14.3 / 14.2 / 13.7`. A
  financially-dense chunk spanning both rows would embed close to *any* capital-ratio question.
  Handed a wall of numbers like that with a truncated header, a model asked "what was CAR in
  4Q25?" has every incentive to eyeball-guess the wrong row rather than admit it can't tell —
  that's the hallucination mode the assignment is warning about, not a hypothetical one.

In this system, that same question never reaches an LLM's judgment at all: `MetricsStore.lookup()`
does whole-word/plural-tolerant matching against each metric's `name`/`metric_id`/`aliases` (with
a specificity tie-break so, e.g., `casa_balance`'s full-phrase alias beats `casa_ratio`'s generic
`"casa"` alias on a tie), returns the single `car_basel2` record with period-keyed values `{4Q24:
15.4, ..., 4Q25: 14.6}`, and the answer model is only allowed to format and cite what's already in
that record — it never has weights-recall as an option for the number itself.

One more case is worth naming because it shows the three stores working *together*, not just the
metrics store in isolation: **"Why did CAR decrease in Q4 2025?"** is literally the router's own
worked example for the `hybrid` intent (see `ROUTER_SYSTEM` in `router_svc.py`) — it needs the CAR
numbers *and* the reason. The `car_basel2` record actually carries a hand-curated `note` field —
`"Q4 decline reflects >VND 7tn cash dividend paid October 2025"` — captured during metric
extraction from the surrounding narrative on page 4 (the same page the `dividend` metric record
itself cites), so the structured store alone can answer it; if the router still classifies the
question `hybrid`, the narrative-retrieval leg adds that page-4 chunk describing the October
dividend payment as a second, independent citation. Either path lands on the same grounded answer
— it's never invented.

---

## 2. Limitations of RAG and mitigations

| RAG limitation | Mitigation | Where |
|---|---|---|
| **Numeric precision** — embeddings/cosine similarity have no notion of "the exact right number"; a model asked to read numbers off a retrieved chunk will paraphrase or misread them | Structured metrics store: exact JSON lookup by alias/period, the LLM only formats and cites — never recalls a figure from its own weights | `metrics_store.py`, `data/artifacts/metrics.json` |
| **Multi-turn follow-ups** — "what about Q3?" is meaningless without conversation context, and embedding it as-is retrieves garbage | Router produces a `standalone_query` rewrite that resolves pronouns/ellipsis using the last 6 turns before anything is retrieved | `router_svc.py::route()` |
| **Acronyms don't match retrieval or embeddings** — a user typing "CASA" and a chunk saying "current account savings account" may not be semantically close enough | Query expansion against the 26-entry glossary appends the spelled-out form to the query before embedding / BM25 / routing | `retrieval.py::expand_query()` |
| **Retrieval misses** — pure keyword search misses paraphrases; pure vector search misses exact terms and out-of-vocabulary queries | Hybrid BM25 + cosine similarity fused with Reciprocal Rank Fusion, top 6 | `retrieval.py::Retriever.search()` |
| **Hallucination** — the model fills gaps with plausible-sounding invented content | Grounded system prompt (context-only, explicit refusal instruction, `[p.N]` citations, temp ≤ 0.2) + router `out_of_scope` guard + golden eval suite | `answerer.py::ANSWER_SYSTEM`, `router_svc.py`, §5 below |

A few of these are worth a sentence more:

- **Numeric precision** is the assignment's central hint made concrete — see §1. It's also why
  metric records carry a hand-curated `note` field (e.g. the CAR/dividend link above) and
  per-metric `qoq`/`yoy` deltas lifted straight from the table's own delta columns, rather than
  asking the LLM to compute a change between two numbers itself.
- **Retrieval misses** got one real fix during implementation, not just a design decision on
  paper. The first cut of Reciprocal Rank Fusion awarded rank-based points to *every* chunk for
  the BM25 leg, even ones the keyword ranker never actually matched — BM25 returns an all-zero
  score array for out-of-vocabulary queries, but `argsort` still hands back a full ranking over
  zeros, so those degenerate "matches" were silently biasing results toward whatever the cosine
  leg's own ordering happened to favor at each rank position. Fixed by only awarding BM25 rank
  points when the underlying BM25 score is actually nonzero, so an out-of-vocabulary query falls
  through cleanly to pure cosine ranking instead of a position-biased blend — verified with a
  25/25 self-embed sweep (every chunk's own text, embedded and searched, correctly ranks itself
  first).
- **Hallucination** mitigations are layered on purpose: even if the grounding prompt failed on
  some question, the router's scope guard independently refuses anything about other fiscal
  years, other companies, or investment advice *before* it reaches an answer call at all —
  routing does content-scope filtering, prompting does context filtering, and the two don't share
  a failure mode.

---

## 3. Model efficiency

The assignment's hint is explicit: route cheap requests to a cheap model, and don't pay
Sonnet-tier latency/cost for a lookup a Haiku-tier model can do correctly. There is exactly one
router decision per turn, and everything downstream of it is gated by that decision:

| Stage | Model | Typical tokens (estimated) | Input $ / 1M tok | Output $ / 1M tok |
|---|---|---|---|---|
| Router (classify + rewrite) | Claude Haiku 4.5 | ~300–600 in / ~80 out | $1.00 | $5.00 |
| Simple fact answers | Claude Haiku 4.5 | ~600–900 in / ~150 out | $1.00 | $5.00 |
| Analytical / hybrid answers | Claude Sonnet 4.5 | ~2,000–3,000 in / ~300–500 out | $3.00 | $15.00 |
| Golden-eval refusal judge | Claude Haiku 4.5 | ~50 in / ~5 out | $1.00 | $5.00 |
| Query embeddings | Titan Text Embeddings V2 | ~10–30 in (query only) | $0.02 | — (no output tokens) |

(Bedrock on-demand pricing, `us-east-1`, current as of this write-up. Token counts are estimates
from this codebase's actual prompt sizes, not yet measured against live traffic — golden evals
against real Bedrock are still pending; see §5.)

**Example cost per question**, using the estimates above:

- *Simple fact* ("What was profit before tax in FY25?") — one router call plus one Haiku answer
  call, both over the ~500–900-token context a metric-store lookup produces. **≈ $0.002–0.003**
  per question.
- *Analytical / hybrid* ("Why did CAR decrease in Q4 2025?") — one router call (Haiku) plus one
  Sonnet answer call over a larger context (metric block plus up to 6 retrieved narrative chunks,
  ~2,500 tokens). **≈ $0.012–0.015** per question.

Both numbers are dominated by the answer call, not the router — which is the point: the router
itself is cheap enough (Haiku, ~300-token system prompt, JSON-only output) that adding a
classification step ahead of *every* request is close to free, and it's what keeps every
`metric`, `chitchat`, or simple `narrative` question off Sonnet entirely. Retrieval itself (BM25 +
cosine over 25 in-memory chunks) costs nothing beyond the one Titan query embedding, which at
$0.02 per 1M input tokens is functionally free per question.

The router also does double duty for cost: `chitchat` and `out_of_scope` turns skip retrieval
*and* the answer-model call entirely (`pipeline.py::handle()` returns a canned reply directly), so
a greeting or an out-of-scope question costs exactly one Haiku call, not two.

---

## 4. Why not X

**Bedrock Knowledge Bases / a managed vector DB (OpenSearch Serverless, etc.).** Three reasons,
not one:

- *Cost* — OpenSearch Serverless has an always-on minimum (OCU-hours billed whether or not it's
  queried), which doesn't make sense for a corpus that's 25 chunks and a few hundred KB.
- *Table mangling* — a managed KB's ingestion pipeline chunks by token count over extracted text,
  which is exactly the failure mode described in §1. It doesn't know page 13 is a table with three
  different column schemes; the structured-metrics-store design would still be necessary on top
  of it, so the KB wouldn't remove the hard part of this problem, only add infrastructure around
  the easy part.
- *No local run / black box* — a managed KB can't be part of a `docker compose up` clone-to-run
  flow, and its retrieval ranking isn't something I can unit-test or reason about precisely
  (chunking heuristics, index-time scoring, etc. are opaque). The in-process retriever here is
  about 50 lines, has a unit-test suite covering the out-of-vocabulary fallback and the RRF math
  directly, and runs identically in CI, locally, and in prod.

Right-sized instead: in-process numpy cosine similarity plus `rank_bm25` BM25, fused with
Reciprocal Rank Fusion. Exact, sub-5ms, zero additional infrastructure. **Graduation trigger**
(named explicitly, not just implied): this stops being the right call once the corpus becomes
multi-document — multiple fiscal years, multiple companies — or large enough that in-memory
brute-force cosine search is the bottleneck. At that point a managed KB's ingestion, incremental
indexing, and cross-document retrieval start earning their infrastructure cost. One document, one
snapshot in time, doesn't clear that bar.

**Fine-tuning.** Wrong tool for a single, evolving document. Fine-tuning bakes a snapshot of facts
into model weights that (a) still isn't queryable with exact-lookup guarantees — a fine-tuned
model still *recalls* rather than *looks up*, which is the same numeric-precision problem from §1
wearing a different hat — and (b) goes stale the moment the next quarterly press release ships, at
which point it's a re-training cycle instead of an `ingest/run.py` re-run. Retrieval generalizes to
a new source document with a data-pipeline change, not a training run.

**Agentic loops** (a ReAct-style agent deciding at each step whether to search, re-search, or call
more tools). No benefit at this scope, and a real cost: the entire retrieval need for a 14-page
document is one router decision away from being fully specified — there's no exploratory
"figure out what to look for" step that an agent loop would add value on. What it would add is
multiple extra round-trip LLM calls (each with its own retry/backoff overhead against a
new-account Bedrock quota that was already the tightest constraint in this build) to arrive at the
same answer the fixed three-step pipeline (route → retrieve → answer) already gets deterministically.
This is also a direct answer to the assignment's "if you simply put the doc into ChatGPT API, it's
the wrong solution" hint from the other direction: the failure mode of *too little* structure
(whole-document stuffing) and the failure mode of *unnecessary* structure (an agent loop searching
a document that doesn't need searching) are both wrong for the same underlying reason — neither is
sized to what a single, small, static document actually requires.

---

## 5. Evaluation

**Design.** A golden suite of 15 cases exercises the live pipeline end to end through
`/api/chat`, specified in the implementation plan
(`docs/superpowers/plans/2026-07-08-tcb-rag-chatbot.md`, Task 17) as `tests/evals/golden.yaml` +
`tests/evals/test_evals.py`, run via `pytest -m eval -s` against real Bedrock (`MOCK_LLM=false`):

- **7 exact-metric cases** — PBT, CASA ratio, NPL ratio, Basel II CAR, TOI (with its YoY growth
  figure), customer count, customer deposits — each asserting the reply contains the correct
  figure(s) from the source table.
- **1 hybrid case** — "Why did CAR decrease in Q4 2025?" — asserting the reply mentions the
  dividend payment, not just the number.
- **3 narrative cases** — the bancassurance fee story (either the 91.8% YoY growth figure or the
  word "termination" — banca fees grew strongly in FY25 on new propositions introduced after the
  prior partnership terminated in 4Q24), the TCBS listing (any of three independent facts), and
  the Fitch rating (both the letter rating and the outlook — this one requires both).
- **1 multi-turn follow-up chain** — "What was the CASA ratio in FY25?" then "What about Q3?" —
  asserting the second, context-dependent answer resolves to the right quarter.
- **3 out-of-scope refusal traps** — FY23 profit (wrong fiscal year), a competitor's CASA ratio
  (wrong company), "should I buy TCB stock right now?" (investment advice) — each asserting the
  reply declines.

Grounded cases are designed to be judged by case-insensitive substring match against the
known-correct figure(s) pulled from the source PDF. Refusal cases are designed to be judged by a
second, independent Haiku call that asks a fresh model instance "does this reply decline to
answer?" and expects `YES` — rather than string-matching the refusal text itself, since a refusal
can be phrased many ways, and the interesting failure mode (a refusal that leaks a fabricated
number anyway) wouldn't be caught by keyword matching alone.

> **TODO (pending):** the eval suite above is fully specified but not yet implemented as runnable
> test files, and has not been run. Both wait on AWS Bedrock model access being granted for this
> account — the same environmental gate that has `data/artifacts/embeddings.npz` still running on
> deterministic placeholder vectors rather than real Titan embeddings (see the ledger note in the
> design spec's risk table). Once access lands: implement `tests/evals/golden.yaml` /
> `tests/evals/test_evals.py` per the design above, regenerate real embeddings via `python -m
> ingest.run`, run `pytest -m eval -s`, target 15/15, and paste the pass/fail table here (also
> saved to `docs/eval-results.md`).

**What 15/15 would and wouldn't prove.** If every case passes, that's real evidence the live
pipeline — router, both retrieval paths, both answer models, the refusal guard — produces correct
or on-policy output for these 15 specific, hand-picked scenarios against real Bedrock, not mocks.
It would not be evidence of general robustness: the suite doesn't cover adversarial phrasings or
prompt-injection attempts; it doesn't exercise anywhere near all 38 metric records or the full
narrative surface (7 of 15 cases are single-metric spot-checks, and most numeric questions resolve
via exact lookup rather than retrieval, so hybrid BM25+cosine ranking quality is only indirectly
touched by the 4 narrative/hybrid cases); it doesn't grade the *quality* of analytical reasoning
beyond substring presence (a hybrid answer could contain the right number wrapped in bad reasoning
and still pass); and it says nothing about how the same pipeline generalizes to a different source
document — it's a fixed snapshot against one specific press release.

---

## 6. Infra & security decisions

**OIDC, no long-lived secrets in CI.** GitHub Actions authenticates to AWS by assuming an IAM role
via OpenID Connect (`infra/bootstrap/main.tf`'s `aws_iam_openid_connect_provider` plus a trust
policy scoped to `repo:ngotoandev/tcb-fy25-chatbot:*` — any other repo, or a fork, cannot assume
this role). No AWS access keys are stored as GitHub secrets at all; both `deploy.yml` and `pr.yml`
authenticate via `aws-actions/configure-aws-credentials` against that role.

**The CI role has `AdministratorAccess` — a deliberate, documented trade-off, not an oversight.**
It's called out directly in the Terraform source itself, right next to the policy attachment
(`infra/bootstrap/main.tf`): for a short build spanning two Terraform stacks (VPC, ALB, ECS, IAM,
ECR, DynamoDB, S3, Budgets), hand-enumerating the exact IAM action set across every resource type
up front would have cost real build time for a role that only a couple of people ever exercise,
for a few days, against a throwaway AWS account. Production scoping: a customer-managed policy
limited to the specific actions the two stacks actually call (`ecs:*`, `ecr:*`, `iam:PassRole`
restricted to just the two task roles, `dynamodb:*`, `elasticloadbalancing:*`, `budgets:*`,
scoped `s3:*` on the tfstate bucket, `logs:*`) — and in a real team setting, splitting the CI
role in two: a plan-only role for PRs (already effectively true today, since `pr.yml` only plans)
and an apply role gated by a GitHub environment protection rule requiring approval.

**Public subnets, no NAT gateway — another scope trade-off, with a named production path.** The
ECS task and the ALB both sit in public subnets; there's no NAT gateway. This was a direct cost
call: NAT is a fixed monthly charge regardless of traffic that alone would exceed this exercise's
entire estimated AWS bill. The task's security group only accepts inbound traffic from the ALB's
security group (`infra/main/ecs.tf`), and the ALB only exposes port 80 — there's no broader public
attack surface than "anyone can hit the chat endpoint," which is inherent to a public demo, not a
consequence of the subnet choice. Production path: move the ECS tasks into private subnets with
VPC endpoints for the services they need (`ecr.api`, `ecr.dkr`, `logs`, `dynamodb`,
`bedrock-runtime`) so tasks never carry a public IP at all — there's no runtime S3 dependency since
build artifacts are baked into the image; put the ALB behind AWS WAF
(rate-based rule plus a managed rule group) and an authentication layer — Cognito, or at minimum
an API-key/JWT check in front of `/api/chat` — since the current endpoint is intentionally
unauthenticated for reviewer access. The ALB is also HTTP-only right now, with no ACM certificate
or 443 listener; production adds both plus an HTTP→HTTPS redirect.

**Budget alarm.** An AWS Budget (`infra/main/budget.tf`) set to $10/month, alerting by email at
80% of actual spend and 100% of forecasted spend. Sized to the exercise, not to a real deployment
— the whole point is a tripwire that fires well before the estimated $5–10 total cost for the
review window becomes a surprise.

**Rate limiting.** A per-client-IP sliding-window limiter (`backend/app/api/chat.py`, default 20
requests/minute) sits in front of the pipeline, specifically to protect the one thing on this
stack that costs real money per call once it's publicly reachable: the Bedrock endpoint, behind an
unauthenticated ALB. Two details only surfaced under review, not in the first draft: it's keyed on
`request.client.host`, not the client-supplied `session_id` — `session_id` is unauthenticated and
client-rotatable, so keying on it would let anyone bypass the limit by generating a new session
per request — and the check-evict-record sequence is wrapped in a single lock, because FastAPI
runs sync endpoints on a thread pool, and the original read-then-write had a race where two
concurrent requests for the same IP could both read "under the limit" before either wrote its own
hit, letting both through.

---

## 7. On Jarvis

The assignment recommends [Jarvis](https://github.com/andrewuta99-coder/jarvis) as development
tooling. I looked at what it offers before starting and made a scoping call rather than adopting
it wholesale: for a single 14-page document served by one container, the value a scaffolding tool
adds — reusable project structure, opinionated defaults, conventions I don't have to invent — is
smaller than the cost of taking on a dependency whose internals I'd have to learn well enough to
defend in an interview without having written them myself. Everything in this repo, I can point to
a specific reason for.

That said, I kept the parts of its general direction that are just good practice independent of
tooling choice, because they *are* good practice: plain, native Terraform rather than a wrapped or
opinionated IaC DSL, so `terraform plan`/`apply` behave exactly as documented and anyone reviewing
this doesn't need to learn a second layer on top of Terraform itself; GitHub OIDC for CI
authentication rather than long-lived access keys; and no framework lock-in — every piece
(FastAPI, Terraform, React, boto3) is a direct, replaceable dependency, not something routed
through a wrapper that would need to be unwound to swap out later.

---

## 8. What I'd do next

Roughly in the order I'd tackle them:

- **SSE streaming.** The current `/api/chat` is request/response, not streamed — noted as out of
  scope for this 48h build in the design spec. For a chat product this is the first thing a
  user would notice; it's a moderate backend change (stream tokens from the Bedrock Converse
  stream API instead of the blocking call) and a frontend change to render incrementally.
- **Vietnamese-language support.** The source press release and the UI are both English, but the
  audience for a Techcombank product is predominantly Vietnamese-speaking. Doing this well means
  more than translating the system prompt — the metrics store's period extraction
  (`extract_periods()` in `metrics_store.py`) and the metric alias lists would both need
  Vietnamese variants, not just a translated final answer.
- **Conversation summarization for long sessions.** History is currently just truncated to the
  last 6 turns fed into both the router and the answer call (`router_svc.py::build_router_user_msg`,
  `answerer.py::answer`). That's fine for the kind of short exploratory sessions this is built
  for, but a long session would silently lose earlier context rather than summarizing it forward.
- **Multi-document corpus + Bedrock Knowledge Bases graduation.** The moment there's more than one
  fiscal year's press release, or a competitor's for genuine comparison questions, the in-process
  retrieval right-sizing argument from §4 flips, and a managed KB starts earning its
  infrastructure cost.
- **A re-ranking step.** Right now hybrid retrieval returns the top-6 RRF-fused chunks directly
  into the answer context. A cross-encoder re-rank pass over a larger candidate set (say top-20
  RRF → re-rank → top-6) would matter more as the corpus grows past the point where BM25+cosine
  alone reliably surfaces the single best chunk.
- **Runtime contextual-grounding guardrails.** The current anti-hallucination strategy (§2) is
  prompt + citations + refusal + offline evals. Bedrock Guardrails' contextual grounding check —
  or an inline groundedness-scoring pass at answer time, not just in the eval suite — would catch
  a hallucination *before* it reaches the user, as a runtime safety net layered on top of what's
  here rather than something that only shows up in a nightly eval run.
