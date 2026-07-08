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
        return f"VND {value:,.0f} bn"
    if isinstance(value, (int, float)) and unit == "%":
        return f"{value}%"
    return f"{value} {unit}".strip()

class MetricsStore:
    def __init__(self, path: str | Path) -> None:
        self._metrics: list[dict] = json.loads(Path(path).read_text(encoding="utf-8"))

    def lookup(self, query: str) -> list[dict]:
        qtokens = _norm(query)
        qlower = query.lower()
        scored: list[tuple[float, int, dict]] = []
        for met in self._metrics:
            names = [met["name"], met["metric_id"].replace("_", " "), *met["aliases"]]
            best = 0.0
            best_len = 0
            for name in names:
                ntokens = _norm(name)
                if not ntokens:
                    continue
                overlap = len(ntokens & qtokens) / len(ntokens)
                # exact alias/id phrase match is a strong signal, but only as a whole
                # word/phrase -- a plain substring check would let a short alias like
                # "car" spuriously match inside an unrelated word like "card".
                if re.search(rf"\b{re.escape(name.lower())}s?\b", qlower):
                    overlap = max(overlap, 1.0)
                # on a tie, prefer whichever name/alias is more specific (more tokens)
                # so e.g. "casa balance" (2 tokens) outranks the generic "casa" alias
                # (1 token) shared with casa_ratio when both hit the same score.
                if overlap > best or (overlap == best and len(ntokens) > best_len):
                    best = overlap
                    best_len = len(ntokens)
            if best >= 0.6:
                scored.append((best, best_len, met))
        scored.sort(key=lambda x: (-x[0], -x[1]))
        return [met for _, _, met in scored[:3]]

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
