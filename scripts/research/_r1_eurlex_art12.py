"""R1.0 final item — fetch EU AI Act (Reg. 2024/1689) Articles 10 & 12
verbatim from EUR-Lex so the spec's mapping table cites exact clause
text, not memory."""
import re
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URL = ("https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/"
       "?uri=CELEX:32024R1689")

r = requests.get(URL, timeout=60,
                 headers={"User-Agent": "Mozilla/5.0 (research fetch)"})
r.raise_for_status()
html = r.text
# crude de-tag
text = re.sub(r"<[^>]+>", " ", html)
text = re.sub(r"&nbsp;?", " ", text)
text = re.sub(r"\s+", " ", text)

for art in ("Article 10", "Article 12", "Article 19"):
    # find the article heading followed by its body up to the next Article
    m = re.search(rf"{art}\s+([A-Z][a-zA-Z\- ]{{3,60}})\s", text)
    if not m:
        print(f"!! {art}: heading not found")
        continue
    start = m.start()
    nxt = re.search(r"Article \d+\s+[A-Z]", text[start + 20:])
    end = start + 20 + (nxt.start() if nxt else 4000)
    body = text[start:min(end, start + 4500)]
    print("=" * 80)
    print(body.strip()[:4200])
    print()
