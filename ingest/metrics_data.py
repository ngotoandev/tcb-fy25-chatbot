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
      {"4Q24": 4741, "4Q25": 4824, "FY24": 15370, "FY25": 16432},
      yoy="4Q +1.8%; FY +6.9%", note="Expense line (shown as VND 16,432 bn); driven by IT investment"),
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
