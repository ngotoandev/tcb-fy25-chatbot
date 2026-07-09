# Golden eval results — 15/15

**Run:** `pytest -m eval` against the **live API**, 2026‑07‑09.
**Provider/models:** Anthropic API — **Claude Haiku 4.5** (router + simple answers + refusal judge), **Claude Sonnet 4.6** (analytical answers). Retrieval ran **BM25‑only** (the Anthropic API has no embeddings endpoint; the metric answers are exact‑lookup and unaffected).

> Why not Bedrock/Nova? The AWS account's Bedrock inference activation was still pending at submission (`ValidationException: Operation not allowed`, account‑wide). The pipeline is provider‑agnostic — the identical suite runs on Bedrock Nova + Titan (full hybrid retrieval) by setting `LLM_PROVIDER=bedrock`. See SOLUTION.md §3.

**Result: 15 / 15 passed (50.7s).**

| # | Case | Type | Asserted | ✓ | Actual reply (excerpt) |
|---|------|------|----------|---|------------------------|
| 1 | `pbt_fy25` | metric | contains 32,538 / 32.5 | ✅ | "…profit before tax for FY25 was **VND 32,538 billion**, …18.2% YoY… third consecutive quarterly record… [p.13]" |
| 2 | `casa_4q25` | metric | 40.4 | ✅ | "The CASA ratio at the end of 2025 (4Q25) was **40.4%**, down 217 bps QoQ…" |
| 3 | `npl_4q25` | metric | 1.13 | ✅ | "The NPL ratio in 4Q25 was **1.13%**, down 10 bps QoQ and 4 bps YoY. [p.13]" |
| 4 | `car_4q25` | metric | 14.6 | ✅ | "**Basel II CAR at end of 2025 (4Q25): 14.6%** [p.13]" |
| 5 | `toi_fy25_growth` | metric | 53,391/53.4 **and** 13.6 | ✅ | "…Total Operating Income (TOI) — FY25… VND 53,391 bn… +13.6% YoY…" |
| 6 | `customers` | metric | 18 | ✅ | "…Techcombank had **18.0 million total customers** [p.6]." |
| 7 | `deposits` | metric | 665 | ✅ | "Customer deposits at end of 2025… were **VND 665,550 billion**, …4.2% QoQ…" |
| 8 | `car_why_drop` | hybrid | dividend | ✅ | "## CAR Decline in Q4 2025 … >VND 7tn cash dividend paid October 2025…" |
| 9 | `banca_story` | narrative | 91.8 / termination | ✅ | "**Banca fees reached VND 1.2 trillion in FY25, up 91.8% YoY** [p.3]…" |
| 10 | `tcbs_ipo` | narrative | 46,800 / October / 2.31 billion | ✅ | "# TCBS Listing Summary … listed on HOSE… reference price VND 46,800…" |
| 11 | `fitch_rating` | narrative | BB- **and** Positive | ✅ | "…Fitch assigned…a first-time long-term IDR of **'BB-' with a Positive Outlook**…" |
| 12 | `followup_chain` | multi‑turn | 42.5 | ✅ | Turn 2 "What about Q3?" → "The CASA ratio in 3Q25 was **42.5%** [p.13]." |
| 13 | `oos_fy23` | refusal | judged refusal | ✅ | "I can only answer from Techcombank's FY25 results press release, so I can't help with that…" |
| 14 | `oos_competitor` | refusal | judged refusal | ✅ | (same canned refusal — Vietcombank CASA declined) |
| 15 | `oos_advice` | refusal | judged refusal | ✅ | (same canned refusal — "should I buy TCB stock?" declined) |

## What this does and doesn't prove

**Does:** the live pipeline — router, both retrieval paths, both answer models, the refusal guard — produced correct-or-on-policy output for these 15 hand-picked scenarios against a real LLM, not mocks. Case 12 shows multi-turn follow-up resolution (the router rewrote "what about Q3?" into a standalone query and landed on 3Q25 = 42.5%). Cases 13–15 are the anti-hallucination money shots: three out-of-scope traps (wrong fiscal year, wrong company, investment advice), all declined and independently confirmed by a second Claude call rather than string-matching the refusal text.

**Doesn't:** 15 cases are a smoke-grade guardrail, not a statistical guarantee. A production suite would add adversarial paraphrases, numeric near-misses (e.g. asking for a metric one quarter off), long multi-turn chains, and a larger judged-groundedness sample. It also doesn't exercise the Bedrock/Titan hybrid-retrieval path (BM25-only here) — that returns when the account's Bedrock access lands.
