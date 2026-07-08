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
