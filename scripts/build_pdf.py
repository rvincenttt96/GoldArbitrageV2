#!/usr/bin/env python3
"""Renders a Markdown document to a print-ready PDF.

Written for the Persian change report, so it handles the two things a generic
converter gets wrong here: right-to-left text needs a font that actually has
Persian glyphs, and the Mermaid diagrams have to be executed rather than printed
as code. Headless Chrome does both, which is why it is the engine.

    python3 -m scripts.build_pdf docs/CHANGES.md --out docs/CHANGES.pdf
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

CHROME = "google-chrome"

#: Chrome renders, then prints. Mermaid needs a moment to lay the diagrams out,
#: and virtual time lets that happen without a real wall-clock wait.
VIRTUAL_TIME_MS = 20000

CSS = """
@page { size: A4; margin: 14mm 13mm; }

body {
  font-family: "Noto Sans Arabic", "Noto Naskh Arabic", "DejaVu Sans", sans-serif;
  direction: rtl;
  text-align: right;
  line-height: 1.6;
  font-size: 9.5pt;
  color: #1a1a1a;
}

h1 {
  font-size: 17pt;
  color: #1F3864;
  border-bottom: 2.5px solid #1F3864;
  padding-bottom: 8px;
  margin-top: 0;
}
h2 {
  font-size: 12.5pt;
  color: #1F3864;
  margin-top: 16px;
  border-right: 4px solid #C9A227;
  padding-right: 10px;
}
h3 { font-size: 10.5pt; color: #2b4a7d; margin-top: 13px; }

/* Each "page" heading in the source starts a real page. */
h2:has(+ *) { break-after: avoid; }
hr { border: none; border-top: 1px solid #d8d8d8; margin: 14px 0; }

table {
  border-collapse: collapse;
  width: 100%;
  margin: 9px 0;
  font-size: 8.5pt;
  break-inside: avoid;
}
th {
  background: #1F3864;
  color: #fff;
  padding: 7px 9px;
  text-align: right;
  font-weight: 600;
}
td { border: 1px solid #d5d5d5; padding: 6px 9px; }
tr:nth-child(even) td { background: #f6f7fa; }

code {
  font-family: "DejaVu Sans Mono", monospace;
  direction: ltr;
  unicode-bidi: embed;
  background: #f0f2f6;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 9pt;
}
pre {
  background: #f6f7fa;
  border: 1px solid #dfe3ea;
  border-right: 4px solid #1F3864;
  padding: 11px 13px;
  border-radius: 4px;
  direction: ltr;
  text-align: left;
  overflow-x: auto;
  font-size: 8.5pt;
  line-height: 1.5;
  break-inside: avoid;
}
pre code { background: none; padding: 0; }

blockquote {
  border-right: 3px solid #C9A227;
  margin: 12px 0;
  padding: 4px 14px;
  color: #444;
  background: #fdfaf2;
}

ul, ol { padding-right: 22px; }
li { margin: 2px 0; }

.mermaid {
  direction: ltr;
  text-align: center;
  margin: 10px 0;
  break-inside: avoid;
}
.mermaid svg { max-height: 235mm; }
.page-break { break-before: page; }
"""

MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"

TEMPLATE = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
{body}
<script src="{cdn}"></script>
<script>
  mermaid.initialize({{ startOnLoad: true, theme: "neutral",
                        flowchart: {{ useMaxWidth: true, htmlLabels: true }} }});
</script>
</body>
</html>
"""


def extract_mermaid(text: str) -> tuple[str, list[str]]:
    """Pull Mermaid blocks out before Markdown turns them into code listings."""
    diagrams: list[str] = []

    def take(match: re.Match) -> str:
        diagrams.append(match.group(1).strip())
        return f"\n\nMERMAIDPLACEHOLDER{len(diagrams) - 1}\n\n"

    return re.sub(r"```mermaid\n(.*?)```", take, text, flags=re.S), diagrams


def build_html(source: Path) -> str:
    text = source.read_text(encoding="utf-8")
    text, diagrams = extract_mermaid(text)

    # Only the numbered section headings start a new page, and not the first
    # one: breaking there would leave the title alone on a near-empty sheet.
    breaks = [0]

    def section_break(match: re.Match) -> str:
        breaks[0] += 1
        if breaks[0] == 1:
            return "\n\n<hr/>\n\n"
        return '\n\n<div class="page-break"></div>\n\n'

    text = re.sub(r"\n---\n+(?=## صفحهٔ)", section_break, text)
    text = text.replace("\n---\n", "\n\n<hr/>\n\n")

    body = markdown.markdown(
        text, extensions=["tables", "fenced_code", "sane_lists", "md_in_html"]
    )

    for index, diagram in enumerate(diagrams):
        body = body.replace(
            f"<p>MERMAIDPLACEHOLDER{index}</p>",
            f'<div class="mermaid">{diagram}</div>',
        )

    title = next(
        (line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("# ")),
        source.stem,
    )
    return TEMPLATE.format(title=title, css=CSS, body=body, cdn=MERMAID_CDN)


def to_pdf(html: str, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "doc.html"
        page.write_text(html, encoding="utf-8")

        command = [
                CHROME,
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                "--allow-file-access-from-files",
                f"--virtual-time-budget={VIRTUAL_TIME_MS}",
                "--no-pdf-header-footer",
                f"--print-to-pdf={out}",
                page.as_uri(),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=90)  # noqa: S603
        except subprocess.TimeoutExpired:
            # Chrome occasionally writes the PDF and then declines to exit. The
            # file is what we came for, so a timeout with output on disk is a
            # success, not a failure.
            if not out.exists() or out.stat().st_size == 0:
                raise
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--html", type=Path, help="also write the intermediate HTML")
    args = parser.parse_args()

    html = build_html(args.source)
    if args.html:
        args.html.write_text(html, encoding="utf-8")

    out = args.out or args.source.with_suffix(".pdf")
    to_pdf(html, out)
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
