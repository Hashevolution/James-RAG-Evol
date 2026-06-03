"""Ad-hoc markdown -> PDF (tables-aware) via markdown + xhtml2pdf.

Usage: python scripts/research/_md_to_pdf.py <input.md> <output.pdf>
"""
import sys
import markdown
from xhtml2pdf import pisa

CSS = """
@page { size: A4; margin: 1.6cm 1.5cm; }
body { font-family: "Helvetica","Arial",sans-serif; font-size: 9pt;
       line-height: 1.35; color: #1a1a1a; }
h1 { font-size: 16pt; border-bottom: 2px solid #333; padding-bottom: 4px; }
h2 { font-size: 12.5pt; margin-top: 14px; border-bottom: 1px solid #bbb;
     padding-bottom: 2px; }
h3 { font-size: 10.5pt; margin-top: 10px; color: #222; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 7.6pt; }
th, td { border: 0.5px solid #999; padding: 3px 5px; text-align: left;
         vertical-align: top; }
th { background: #ececec; font-weight: bold; }
code { font-family: "Courier New",monospace; font-size: 8pt;
       background: #f2f2f2; padding: 0 2px; }
blockquote { border-left: 3px solid #ccc; margin: 6px 0; padding: 2px 10px;
             color: #444; font-style: italic; }
strong { color: #000; }
hr { border: none; border-top: 0.5px solid #ccc; margin: 10px 0; }
"""


def main():
    src, out = sys.argv[1], sys.argv[2]
    with open(src, encoding="utf-8") as f:
        text = f.read()
    html_body = markdown.markdown(
        text, extensions=["tables", "fenced_code", "sane_lists"]
    )
    html = f"<html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{html_body}</body></html>"
    with open(out, "wb") as f:
        result = pisa.CreatePDF(html, dest=f, encoding="utf-8")
    if result.err:
        print(f"[error] {result.err} errors during PDF generation")
        return 1
    print(f"[ok] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
