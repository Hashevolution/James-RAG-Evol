"""R1.0 final item — fetch EU AI Act Articles 10/12/19 verbatim.

v2: EUR-Lex CELEX HTML defeated simple regex (heading not found), so
use the AI Act Explorer's per-article pages (artificialintelligenceact.eu)
which serve one clean article per URL. Cross-check the key phrases
against EUR-Lex manually before final spec citation.
"""
import re
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ARTICLES = {
    "10": "https://artificialintelligenceact.eu/article/10/",
    "12": "https://artificialintelligenceact.eu/article/12/",
    "19": "https://artificialintelligenceact.eu/article/19/",
}

HDRS = {"User-Agent": "Mozilla/5.0 (research fetch)"}


def clean(html: str) -> str:
    html = re.sub(r"<script[\s\S]*?</script>", " ", html)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;?", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\s+", " ", text)
    return text


def main() -> int:
    for art, url in ARTICLES.items():
        print("=" * 80)
        print(f"### Article {art}  ({url})")
        try:
            r = requests.get(url, timeout=60, headers=HDRS)
            print(f"HTTP {r.status_code}, {len(r.text)} chars")
            text = clean(r.text)
            # The article title appears in the nav/TOC first and again
            # at the body heading — take the LAST occurrence.
            matches = list(re.finditer(rf"Article {art}[: ]", text))
            start = matches[-1].start() if matches else 0
            body = text[start:start + 4500]
            print(body.strip())
        except Exception as e:
            print("  error:", e)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
