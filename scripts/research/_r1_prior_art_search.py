"""R1.0 — prior-art search via the official arXiv API.

The duckduckgo-search library is broken (deprecated backend returns
region-ignored noise), so we query arXiv's public Atom API directly —
the right source for "does an academic benchmark already exist".

Read-only HTTP GETs; prints title / date / link / first 200 chars of
abstract for manual review.
"""
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API = "http://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom"}

QUERIES = [
    # benchmark for audit/replay of AI systems?
    'all:"audit" AND all:"benchmark" AND (all:"LLM" OR all:"agent") AND all:"log"',
    # provenance evaluation for RAG
    'all:"provenance" AND (all:"retrieval-augmented" OR all:"RAG") AND all:"evaluation"',
    # replayability / reconstruction metrics
    'all:"replay" AND all:"reconstruction" AND all:"audit"',
    # traceability benchmarks for AI systems
    'all:"traceability" AND all:"benchmark" AND all:"AI"',
    # EU AI Act logging operationalisation
    'all:"AI Act" AND (all:"record-keeping" OR all:"logging") AND all:"Article 12"',
    # observability / tracing evaluation for agents
    'all:"observability" AND all:"agent" AND all:"evaluation" AND all:"trace"',
]


def search(q: str, max_results: int = 8):
    url = (f"{API}?search_query={urllib.parse.quote(q)}"
           f"&sortBy=submittedDate&sortOrder=descending"
           f"&max_results={max_results}")
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    root = ET.fromstring(r.text)
    out = []
    for e in root.findall("a:entry", NS):
        title = (e.findtext("a:title", "", NS) or "").strip().replace("\n", " ")
        date = (e.findtext("a:published", "", NS) or "")[:10]
        link = e.findtext("a:id", "", NS) or ""
        summ = (e.findtext("a:summary", "", NS) or "").strip().replace("\n", " ")
        out.append((date, title, link, summ[:220]))
    return out


def main() -> int:
    for q in QUERIES:
        print(f"=== Q: {q} ===")
        try:
            for date, title, link, summ in search(q):
                print(f" [{date}] {title[:95]}")
                print(f"    {link}")
                print(f"    {summ}")
        except Exception as ex:
            print("  error:", ex)
        print()
        time.sleep(3)  # arXiv API politeness
    return 0


if __name__ == "__main__":
    sys.exit(main())
