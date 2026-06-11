"""R1.0 step 2 — fetch full abstracts of the candidate prior-art papers."""
import sys
import xml.etree.ElementTree as ET

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

IDS = [
    "2605.21997",  # The Log is the Agent (event-sourced auditable)
    "2606.04990",  # From Agent Traces to Trust (execution provenance)
    "2605.29253",  # OpenClawBench (process anomalies)
    "2605.15109",  # GraphRAG provenance
    "2606.04104",  # Proof-Carrying Agent Actions
]

NS = {"a": "http://www.w3.org/2005/Atom"}
url = ("http://export.arxiv.org/api/query?id_list="
       + ",".join(IDS) + "&max_results=20")
r = requests.get(url, timeout=30)
root = ET.fromstring(r.text)
for e in root.findall("a:entry", NS):
    title = (e.findtext("a:title", "", NS) or "").strip().replace("\n", " ")
    date = (e.findtext("a:published", "", NS) or "")[:10]
    link = e.findtext("a:id", "", NS) or ""
    summ = (e.findtext("a:summary", "", NS) or "").strip()
    print("=" * 80)
    print(f"[{date}] {title}")
    print(link)
    print()
    print(summ)
    print()
