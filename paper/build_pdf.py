"""
Builds paper/approvalloop.pdf from paper/approvalloop.tex without a LaTeX installation.

It converts the small LaTeX subset used by the paper into IEEE-styled HTML (two columns, Times,
US Letter) and prints it with headless Microsoft Edge or Chrome. For a submission-grade PDF,
compile approvalloop.tex with IEEEtran instead (e.g. on Overleaf: pdflatex approvalloop.tex).

    python paper/build_pdf.py
"""
from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEX = (HERE / "approvalloop.tex").read_text(encoding="utf-8")


def roman(n: int) -> str:
    vals = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for v, s in vals:
        while n >= v:
            out += s
            n -= v
    return out


def env(name: str, src: str) -> str:
    m = re.search(r"\\begin\{%s\}(.*?)\\end\{%s\}" % (name, name), src, re.S)
    return m.group(1) if m else ""


def braced(src: str, start: int) -> tuple[str, int]:
    """Returns the content of the {...} group starting at src[start] == '{' and the index after it."""
    depth, i = 0, start
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start + 1:i], i + 1
        i += 1
    raise ValueError("unbalanced braces")


def cmd_arg(name: str, src: str) -> str:
    i = src.find("\\" + name + "{")
    return braced(src, i + len(name) + 1)[0] if i >= 0 else ""


# ---- numbering: citations, figures, tables
bib_keys = re.findall(r"\\bibitem\{([^}]+)\}", TEX)
cite_no = {k: i + 1 for i, k in enumerate(bib_keys)}
labels: dict[str, str] = {}
fig_n = tab_n = 0
for m in re.finditer(r"\\begin\{(figure\*?|table)\}(.*?)\\end\{\1\}", TEX, re.S):
    lab = re.search(r"\\label\{([^}]+)\}", m.group(2))
    if m.group(1).startswith("figure"):
        fig_n += 1
        if lab:
            labels[lab.group(1)] = str(fig_n)
    else:
        tab_n += 1
        if lab:
            labels[lab.group(1)] = roman(tab_n)


def math(s: str) -> str:
    s = s.replace("{,}", ",").replace("\\le", "\u2264").replace("\\ge", "\u2265").replace("\\pm", "\u00b1")
    s = s.replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"(?<![A-Za-z])([a-zA-Z])(?![A-Za-z])", r"<i>\1</i>", s)
    return s.replace("-", "\u2212") if s.strip() == "-" else s


def inline(s: str) -> str:
    s = re.sub(r"(?<!\\)%.*", "", s)  # comments
    # protect math first
    maths: list[str] = []
    s = re.sub(r"\$(.+?)\$", lambda m: maths.append(math(m.group(1))) or f"\x00{len(maths) - 1}\x00", s)
    s = s.replace("\\&", "\x01amp").replace("\\%", "%").replace("\\_", "_").replace("\\#", "#")
    s = html.escape(s, quote=False).replace("\x01amp", "&amp;")
    s = s.replace("-{}-", "\x02")  # LaTeX idiom for a literal double hyphen (e.g. --tag), protected from dash conversion
    s = s.replace("``", "\u201c").replace("''", "\u201d").replace("---", "\u2014").replace("--", "\u2013")
    s = s.replace("\x02", "--")
    s = s.replace("\\,", "\u2009").replace("{,}", ",").replace("~", "\u00a0").replace("\\\\", "<br>")
    s = s.replace("\\`{i}", "\u00ec").replace("\\`{e}", "\u00e8").replace("\\'{c}", "\u0107")
    s = re.sub(r"\\cite\{([^}]+)\}", lambda m: "[" + ", ".join(str(cite_no[k.strip()]) for k in m.group(1).split(",")) + "]", s)
    s = re.sub(r"\\ref\{([^}]+)\}", lambda m: labels.get(m.group(1), "??"), s)
    s = re.sub(r"\\url\{([^}]+)\}", r'<span class="url">\1</span>', s)
    for tag, cls in [("emph", "em"), ("textbf", "strong"), ("texttt", "code")]:
        while "\\" + tag + "{" in s:
            i = s.find("\\" + tag + "{")
            body, j = braced(s, i + len(tag) + 1)
            s = s[:i] + f"<{cls}>{body}</{cls}>" + s[j:]
    while "\\textsc{" in s:
        i = s.find("\\textsc{")
        body, j = braced(s, i + 7)
        s = s[:i] + f'<span class="sc">{body}</span>' + s[j:]
    s = re.sub(r"\x00(\d+)\x00", lambda m: maths[int(m.group(1))], s)
    return s.strip()


def tabular(src: str) -> str:
    start = src.find("\\begin{tabular}") + len("\\begin{tabular}")
    _spec, after = braced(src, start)  # the column spec may itself contain braces, e.g. p{4.6cm}
    body = src[after:src.find("\\end{tabular}")]
    rows = [r.replace("\\hline", "").strip() for r in body.split("\\\\")]
    rows = [r for r in rows if r]
    out = ["<table>"]
    for i, r in enumerate(rows):
        cells = [inline(c) for c in r.split("&")]
        t = "th" if i == 0 else "td"
        out.append("<tr>" + "".join(f"<{t}>{c}</{t}>" for c in cells) + "</tr>")
    out.append("</table>")
    return "\n".join(out)


def blocks(src: str) -> str:
    out: list[str] = []
    pos = 0
    pattern = re.compile(r"\\section\{|\\subsection\{|\\begin\{(itemize|enumerate|figure\*?|table)\}")
    sec = sub = 0
    first_para_after_heading = False

    def paras(text: str):
        nonlocal first_para_after_heading
        for p in re.split(r"\n\s*\n", text):
            p = p.strip()
            if not p:
                continue
            cls = ' class="noindent"' if first_para_after_heading else ""
            out.append(f"<p{cls}>{inline(p)}</p>")
            first_para_after_heading = False

    while True:
        m = pattern.search(src, pos)
        if not m:
            paras(src[pos:])
            break
        paras(src[pos:m.start()])
        tok = m.group(0)
        if tok.startswith("\\section"):
            title, pos = braced(src, m.end() - 1)
            sec += 1
            sub = 0
            out.append(f'<h2><span class="secno">{roman(sec)}.</span> {inline(title)}</h2>')
            first_para_after_heading = True
        elif tok.startswith("\\subsection"):
            title, pos = braced(src, m.end() - 1)
            sub += 1
            out.append(f'<h3>{chr(64 + sub)}. {inline(title)}</h3>')
            first_para_after_heading = True
        else:
            name = m.group(1)
            end = src.find("\\end{%s}" % name, m.end())
            body = src[m.end():end]
            pos = end + len("\\end{%s}" % name)
            if name in ("itemize", "enumerate"):
                tag = "ul" if name == "itemize" else "ol"
                items = [i.strip() for i in body.split("\\item") if i.strip()]
                out.append(f"<{tag}>" + "".join(f"<li>{inline(i)}</li>" for i in items) + f"</{tag}>")
            elif name.startswith("figure"):
                img = re.search(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", body).group(1)
                cap = cmd_arg("caption", body)
                lab = re.search(r"\\label\{([^}]+)\}", body).group(1)
                wide = " wide" if name == "figure*" else ""
                out.append(f'<figure class="fig{wide}"><img src="{img}.svg" alt=""><figcaption>'
                           f'<span class="figno">Fig.\u00a0{labels[lab]}.</span> {inline(cap)}</figcaption></figure>')
            else:
                cap = cmd_arg("caption", body)
                lab = re.search(r"\\label\{([^}]+)\}", body).group(1)
                out.append(f'<div class="tbl"><div class="tblno">TABLE {labels[lab]}</div>'
                           f'<div class="tblcap">{inline(cap)}</div>{tabular(body)}</div>')
    return "\n".join(out)


# ---- assemble
title = inline(cmd_arg("title", TEX))
author = TEX[TEX.find("\\author{"):]
author_name = inline(cmd_arg("IEEEauthorblockN", author))
author_aff = inline(cmd_arg("IEEEauthorblockA", author))
abstract = inline(env("abstract", TEX))
keywords = inline(env("IEEEkeywords", TEX))
body_src = TEX[TEX.find("\\end{IEEEkeywords}") + len("\\end{IEEEkeywords}"):TEX.find("\\begin{thebibliography}")]
bib = env("thebibliography", TEX)
bib = bib[bib.find("}") + 1:]
refs = [inline(re.sub(r"^\{[^}]+\}", "", b.strip())) for b in bib.split("\\bibitem") if b.strip()]
appendix_src = TEX[TEX.find("\\appendix"):TEX.find("\\end{document}")]
app_title = re.search(r"\\appendix\[([^\]]+)\]", appendix_src).group(1)
app_body = inline(appendix_src[appendix_src.find("]") + 1:])

CSS = """
@page { size: 8.5in 11in; margin: 0.75in 0.625in 1in 0.625in; }
* { box-sizing: border-box; }
html { font-family: "Times New Roman", Times, serif; font-size: 10pt; color: #000; background: #fff; }
body { margin: 0; }
.head { text-align: center; margin-bottom: 14pt; }
.title { font-size: 22pt; line-height: 1.15; margin: 0 0.3in 10pt; font-weight: normal; }
.author { font-size: 11pt; margin-bottom: 2pt; }
.aff { font-size: 10pt; font-style: italic; line-height: 1.25; }
.cols { column-count: 2; column-gap: 0.25in; text-align: justify; hyphens: auto; line-height: 1.17; }
.abstract, .keywords { font-weight: bold; font-size: 9pt; margin: 0 0 7pt; line-height: 1.2; }
.abstract em.lbl, .keywords em.lbl { font-style: italic; }
p { margin: 0; text-indent: 1em; }
p.noindent { text-indent: 0; }
h2 { font-size: 10pt; font-weight: normal; font-variant: small-caps; text-align: center; margin: 10pt 0 5pt; break-after: avoid; letter-spacing: 0.02em; }
h3 { font-size: 10pt; font-weight: normal; font-style: italic; margin: 7pt 0 3pt; break-after: avoid; }
ul, ol { margin: 3pt 0 3pt 1.2em; padding-left: 0.6em; }
li { margin-bottom: 2pt; }
code { font-family: "Courier New", monospace; font-size: 8.6pt; }
.sc { font-variant: small-caps; }
.url { font-family: "Courier New", monospace; font-size: 7.6pt; word-break: break-all; }
figure.fig { margin: 8pt 0; break-inside: avoid; text-align: center; }
figure.fig img { width: 100%; }
figure.wide { column-span: all; margin: 4pt 0 12pt; }
figcaption { font-size: 8pt; text-align: justify; margin-top: 3pt; line-height: 1.2; }
.tbl { break-inside: avoid; margin: 8pt 0; text-align: center; }
.tblno { font-size: 8pt; letter-spacing: 0.05em; }
.tblcap { font-size: 8pt; font-variant: small-caps; margin-bottom: 4pt; }
table { border-collapse: collapse; margin: 0 auto; font-size: 8pt; text-align: left; }
th, td { border: 0.6pt solid #000; padding: 1.5pt 4pt; vertical-align: top; line-height: 1.15; }
th { font-weight: bold; }
.refs { font-size: 8pt; line-height: 1.2; }
.refs ol { list-style: none; margin: 0; padding: 0; counter-reset: r; }
.refs li { position: relative; padding-left: 2.2em; margin-bottom: 2.5pt; text-align: left; }
.refs li::before { counter-increment: r; content: "[" counter(r) "]"; position: absolute; left: 0; }
.appendix p { text-indent: 0; text-align: left; }
.appendix code { display: inline-block; margin: 1pt 0; }
"""

doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>ApprovalLoop</title><style>{CSS}</style></head>
<body>
<div class="head">
  <h1 class="title">{title}</h1>
  <div class="author">{author_name}</div>
  <div class="aff">{author_aff}</div>
</div>
<div class="cols">
  <p class="abstract noindent"><em class="lbl">Abstract</em>\u2014{abstract}</p>
  <p class="keywords noindent"><em class="lbl">Index Terms</em>\u2014{keywords}</p>
  {blocks(body_src)}
  <h2>References</h2>
  <div class="refs"><ol>{''.join(f'<li>{r}</li>' for r in refs)}</ol></div>
  <div class="appendix"><h2>Appendix: {inline(app_title)}</h2><p>{app_body}</p></div>
</div>
</body></html>"""

out_html = HERE / "approvalloop.html"
out_html.write_text(doc, encoding="utf-8")

browser = next((p for p in [
    shutil.which("msedge"), shutil.which("chrome"), shutil.which("google-chrome"), shutil.which("chromium"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
] if p and os.path.exists(p)), None)
if not browser:
    sys.exit(f"Wrote {out_html}; no Edge/Chrome found to print the PDF.")
pdf = HERE / "approvalloop.pdf"
subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                f"--print-to-pdf={pdf}", out_html.as_uri()], check=True, capture_output=True, timeout=120)
print(f"Wrote {pdf}")
