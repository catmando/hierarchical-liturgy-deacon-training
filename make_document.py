#!/usr/bin/env python3
"""Build the written rubric from the edit sheet.

    python3 make_document.py
    python3 make_document.py --video https://youtu.be/XXXX
    python3 make_document.py --sheet other.yaml

Writes two files into output/:

    rubric_online.md   linked contents, timecodes hyperlinked to the video
    rubric_print.md    no links, page breaks between chapters
    rubric.html        the same, styled and self-contained
    rubric.pdf         for printing        (needs weasyprint)
    rubric.docx        for editing in Word (needs pandoc)

Two more are written outside output/, because they are meant to be committed
and read on GitHub:

    RUBRIC.md          rendered by GitHub in the repository itself
    docs/index.html    served by GitHub Pages, styled, diagrams and all

The last two are written only if those tools are installed:

    brew install weasyprint pandoc

Both carry the same words. The online one is for reading beside the video;
the printed one is for the ambo, the vestry, or a pocket.

What goes in, and what does not:

    chapter:      becomes the section heading
    cards:        the words on screen, shown as a quotation
    image:        diagrams are embedded
    annotations:  the timed directions, with role and timecode
    notes:        published prose, printed under the directions
    todos:        NEVER — those are the user's own

Timecodes are positions in the ORIGINAL clip, matching the sheet. Chapter
headings additionally carry their position in the finished video when
output/chapters.txt is present from a full build.
"""
import argparse, base64, html, mimetypes, os, re, shutil, subprocess, sys

try:
    import yaml
except ModuleNotFoundError:
    sys.exit("ERROR: PyYAML missing — pip3 install --break-system-packages pyyaml")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_sheet import resolve, clip_durations, is_span, as_list, _first

OUT = "output"


def mmss(t):
    t = max(float(t), 0)
    h, m, s = int(t // 3600), int((t % 3600) // 60), int(t % 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def md_escape(t):
    """The sheet's own emphasis is markdown already, so only table-breaking
    pipes need dealing with."""
    return str(t).replace("|", "\\|")


def video_chapter_starts(path=os.path.join(OUT, "chapters.txt")):
    """title -> seconds, from a full build's FFMETADATA chapters."""
    out = {}
    if not os.path.exists(path):
        return out
    start = None
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line.startswith("START="):
            start = int(line[6:]) / 1000.0
        elif line.startswith("title=") and start is not None:
            out.setdefault(line[6:], start)
            start = None
    return out


def blocks(sheet):
    with open(sheet, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    return [b for b in doc if isinstance(b, dict) and "clip" in b]


def render(sheet, linked, video_url, base=OUT):
    durs = clip_durations()
    chap_at = video_chapter_starts()
    L = []
    add = L.append

    add("# Rubrics for Serving at a Hierarchical Liturgy")
    add("")
    add("*For deacons, subdeacons and altar servers*")
    add("")
    add("This assumes the parish Liturgy is already second nature — in the "
        "Russian recension a deacon serves it regularly. What follows focuses "
        "on what changes when the bishop serves.")
    add("")
    add("OCA, Russian recension · Diocese of New York and New Jersey · "
        "Filmed 20 June 2026. "
        "Times are positions within each clip, so a direction here sits at the "
        "same moment in the footage.")
    add("")
    if not linked:
        add("<!-- printed form: convert to HTML and print from a browser, or "
            "run it through pandoc -->")
        add("")
    add("---")
    add("")

    # ── contents ──────────────────────────────────────────────────────
    sections = []
    for b in blocks(sheet):
        if b.get("skip") is True or b.get("join") is True:
            continue
        title = _first(b, "chapter", "chapters")
        if title:
            sections.append((b["clip"], str(title).strip()))

    add("## Contents")
    add("")
    for n, title in sections:
        at = chap_at.get(title)
        stamp = f" · {mmss(at)}" if at is not None else ""
        if linked:
            anchor = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            add(f"{n}. [{title}](#{anchor}){stamp}")
        else:
            add(f"{n}. {title}{stamp}")
    add("")
    add("---")
    add("")

    # ── the body ──────────────────────────────────────────────────────
    for b in blocks(sheet):
        n = b["clip"]
        if b.get("skip") is True:
            continue
        title = _first(b, "chapter", "chapters")
        joined = b.get("join") is True

        if title and not joined:
            at = chap_at.get(str(title).strip())
            head = str(title).strip()
            if linked and video_url and at is not None:
                head = f"{head}"
            add(f"## {head}")
            add("")
            bits = [f"clip {n}"]
            if durs.get(n): bits.append(mmss(durs[n]))
            if at is not None:
                stamp = mmss(at)
                if linked and video_url:
                    bits.append(f"[{stamp} in the video]({video_url}&t={int(at)}s)"
                                if "?" in video_url else
                                f"[{stamp} in the video]({video_url}?t={int(at)}s)")
                else:
                    bits.append(f"{stamp} in the video")
            add(f"*{' · '.join(bits)}*")
            add("")

        # cards: the words on screen
        for c in as_list(_first(b, "cards", "card")):
            if not isinstance(c, dict):
                continue
            img = str(c.get("image", "")).strip()
            if img:
                alt = (str(c["chapter"]) if c.get("chapter")
                       else f"{title or f'clip {n}'} — plan")
                add(f"![{md_escape(alt)}]({os.path.relpath(img, base)})")
                add("")
            txt = str(c.get("text", "")).strip()
            if txt:
                for line in txt.split("\n"):
                    add(f"> {line}" if line.strip() else ">")
                add("")

        # published prose
        for note in as_list(_first(b, "notes", "note")) or (
                [_first(b, "notes", "note")] if _first(b, "notes", "note") else []):
            if isinstance(note, str) and note.strip():
                add(note.strip())
                add("")

        # the timed directions
        entries = as_list(_first(b, "annotations", "annotation"))
        anns = [e for e in entries if isinstance(e, dict) and not is_span(e)]
        if anns:
            spans = resolve(anns, durs.get(n))
            for (st, _en), e in zip(spans, anns):
                text = str(e.get("text", "")).strip()
                if not text:
                    continue
                role = str(e.get("role", "")).strip()
                stamp = mmss(st) if st is not None else "—"
                lead = f"**{stamp}**"
                if role:
                    lead += f" · **{role}**"
                add(lead)
                add("")
                for line in text.split("\n"):
                    add(f"  {line}" if line.strip() else "")
                add("")

        if not joined:
            add("---" if linked else
                '<div style="page-break-after: always"></div>')
            add("")

    return "\n".join(L).rstrip() + "\n"


ROLE_TINT = {
    "FIRST DEACON":  "#e0912c",
    "SECOND DEACON": "#7aa84b",
    "DEACONS":       "#4f9d90",
    "SUBDEACONS":    "#9b74b8",
    "SUBDEACON":     "#9b74b8",
    "SERVERS":       "#7d8598",
    "SERVER":        "#7d8598",
    "PRIEST":        "#c25f63",
    "CHOIR":         "#b3893c",
}


def tint(role):
    return ROLE_TINT.get(role.split(",")[0].strip().upper(), "#8b8378")


def data_uri(path):
    """Images must travel inside the file — an artifact cannot fetch them."""
    if not os.path.exists(path):
        return None
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def inline_md(t):
    """The sheet's **bold**, *italic* and _underline_, as HTML."""
    t = html.escape(str(t))
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", t)
    t = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<u>\1</u>", t)
    return t.replace("\n", "<br>")


def render_html(sheet, video_url):
    durs, chap_at = clip_durations(), video_chapter_starts()
    H = []
    add = H.append

    secs = []
    for b in blocks(sheet):
        if b.get("skip") is True or b.get("join") is True:
            continue
        t = _first(b, "chapter", "chapters")
        if t:
            secs.append((b["clip"], str(t).strip()))

    add('<title>Serving a Hierarchical Liturgy</title>')
    add('<link rel="preconnect" href="https://fonts.googleapis.com">')
    add('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
    add('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
        'family=Cormorant+Garamond:wght@500;600&family=IBM+Plex+Mono:wght@400;500'
        '&display=swap">')
    add("<style>" + CSS + "</style>")

    add('<header class="masthead">')
    add('  <p class="eyebrow">Deacons &middot; Subdeacons &middot; Altar servers</p>')
    add('  <h1>Rubrics for Serving at a Hierarchical Liturgy</h1>')
    add('  <p class="standfirst">This assumes the parish Liturgy is already '
        'second nature &mdash; in the Russian recension a deacon serves it '
        'regularly. What follows focuses on what changes when the bishop '
        'serves.</p>')
    add('  <p class="colophon">OCA, Russian recension &middot; Diocese of New '
        'York and New Jersey &middot; Filmed 20 June 2026. Times are positions '
        'within each clip, so a direction here sits at the same moment in the '
        'footage.</p>')
    add("</header>")

    add('<nav class="toc" aria-label="Contents"><h2>Contents</h2><ol>')
    for n, t in secs:
        at = chap_at.get(t)
        stamp = (f'<span class="tc">{mmss(at)}</span>' if at is not None else "")
        add(f'  <li><span class="num">{n}</span>'
            f'<a href="#c{n}">{html.escape(t)}</a>{stamp}</li>')
    add("</ol></nav>")

    open_sec = False
    for b in blocks(sheet):
        n = b["clip"]
        if b.get("skip") is True:
            continue
        title = _first(b, "chapter", "chapters")
        joined = b.get("join") is True

        if title and not joined:
            t = str(title).strip()
            at = chap_at.get(t)
            if open_sec:
                add("</section>")
            add(f'<section class="chapter" id="c{n}">')
            open_sec = True
            add(f'  <h2>{html.escape(t)}</h2>')
            meta = [f"clip {n}"]
            if durs.get(n):
                meta.append(mmss(durs[n]))
            if at is not None:
                stamp = mmss(at)
                meta.append(
                    f'<a href="{html.escape(video_url)}'
                    f'{"&" if "?" in video_url else "?"}t={int(at)}s">{stamp} in the video</a>'
                    if video_url else f"{stamp} in the video")
            add('  <p class="meta">' + " &middot; ".join(meta) + "</p>")

        if not open_sec:
            add('<section class="preamble">')
            open_sec = True

        for c in as_list(_first(b, "cards", "card")):
            if not isinstance(c, dict):
                continue
            img = str(c.get("image", "")).strip()
            if img:
                uri = data_uri(img)
                if uri:
                    alt = (str(c["chapter"]) if c.get("chapter")
                           else f"{title or f'clip {n}'} — plan")
                    add(f'  <figure><img src="{uri}" alt="{html.escape(alt)}">'
                        f'</figure>')
            txt = str(c.get("text", "")).strip()
            if txt:
                add('  <blockquote class="card"><p class="onscreen">on screen</p>'
                    + f"<p>{inline_md(txt)}</p></blockquote>")

        note = _first(b, "notes", "note")
        for item in (note if isinstance(note, list) else [note] if note else []):
            if str(item).strip():
                add(f'  <p class="note">{inline_md(str(item).strip())}</p>')

        entries = as_list(_first(b, "annotations", "annotation"))
        anns = [e for e in entries if isinstance(e, dict) and not is_span(e)]
        if anns:
            add('  <ol class="cues">')
            for (st, _e), e in zip(resolve(anns, durs.get(n)), anns):
                text = str(e.get("text", "")).strip()
                if not text:
                    continue
                role = str(e.get("role", "")).strip()
                add('    <li>')
                add(f'      <span class="tc">{mmss(st) if st is not None else "&mdash;"}</span>')
                add('      <div class="cue">')
                if role:
                    add(f'        <span class="role" style="--tint:{tint(role)}">'
                        f'{html.escape(role)}</span>')
                add(f'        <p>{inline_md(text)}</p>')
                add("      </div>")
                add("    </li>")
            add("  </ol>")

    if open_sec:
        add("</section>")

    return "\n".join(H) + "\n"


CSS = """
:root{
  --ground:#faf7f0; --panel:#f4efe4; --ink:#23201a; --muted:#6f6a5f;
  --gold:#9c7518; --rule:#e0d7c6; --quote:#efe8d9;
}
:root:not([data-theme="light"]){ }
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --ground:#12100e; --panel:#1a1713; --ink:#e8e2d6; --muted:#968d7e;
    --gold:#d9b45b; --rule:#2f2a23; --quote:#1e1a15;
  }
}
:root[data-theme="dark"]{
  --ground:#12100e; --panel:#1a1713; --ink:#e8e2d6; --muted:#968d7e;
  --gold:#d9b45b; --rule:#2f2a23; --quote:#1e1a15;
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font:400 17px/1.62 Georgia,"Times New Roman",serif;
  padding:0 1.5rem 6rem;
}
.masthead,.toc,.chapter{max-width:44rem;margin:0 auto}
.masthead{padding:4.5rem 0 2rem;border-bottom:1px solid var(--rule)}
.eyebrow{
  margin:0 0 .6rem; font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.74rem; letter-spacing:.18em; text-transform:uppercase;
  color:var(--gold);
}
h1{
  margin:0; font-family:"Cormorant Garamond",Georgia,serif; font-weight:600;
  font-size:clamp(2.6rem,6vw,3.9rem); line-height:1.04; text-wrap:balance;
  letter-spacing:-.01em;
}
.standfirst{color:var(--ink);max-width:34rem;margin:1.2rem 0 0;font-size:1.12rem}
.colophon{
  color:var(--muted); max-width:34rem; margin:1rem 0 0;
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.76rem;
  line-height:1.7; letter-spacing:.02em;
}
.toc{padding:2.5rem 0 1rem}
.toc h2{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.74rem;
  letter-spacing:.18em; text-transform:uppercase; color:var(--muted);
  font-weight:500; margin:0 0 1rem;
}
.toc ol{list-style:none;margin:0;padding:0;display:grid;gap:.1rem}
.toc li{display:grid;grid-template-columns:2.2rem 1fr auto;align-items:baseline;
  gap:.5rem;padding:.3rem 0;border-bottom:1px solid transparent}
.toc li:hover{border-bottom-color:var(--rule)}
.num{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.8rem;
  color:var(--muted); font-variant-numeric:tabular-nums;
}
.toc a{color:var(--ink);text-decoration:none}
.toc a:hover{color:var(--gold)}
.preamble{max-width:44rem;margin:0 auto;padding:1.5rem 0 0}
.chapter{padding:3.2rem 0 1rem;border-top:1px solid var(--rule);margin-top:2.6rem}
.chapter h2{
  font-family:"Cormorant Garamond",Georgia,serif; font-weight:600;
  font-size:clamp(1.9rem,4vw,2.5rem); line-height:1.12; margin:0;
  text-wrap:balance;
}
.meta{
  margin:.55rem 0 1.6rem; color:var(--muted);
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.76rem;
  letter-spacing:.05em; font-variant-numeric:tabular-nums;
}
.meta a{color:var(--gold)}
blockquote.card{
  margin:0 0 1.6rem; padding:1.15rem 1.35rem; background:var(--quote);
  border-left:3px solid var(--gold); border-radius:2px;
}
blockquote.card p{margin:0}
.onscreen{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.66rem;
  letter-spacing:.16em; text-transform:uppercase; color:var(--muted);
  margin:0 0 .5rem !important;
}
.note{color:var(--muted);margin:0 0 1.5rem}
figure{margin:0 0 1.6rem;overflow-x:auto}
figure img{width:100%;height:auto;display:block;border:1px solid var(--rule);border-radius:3px}
ol.cues{list-style:none;margin:0;padding:0;display:grid;gap:1.35rem}
ol.cues li{display:grid;grid-template-columns:4.2rem 1fr;gap:1rem;align-items:baseline}
.tc{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.82rem;
  color:var(--muted); font-variant-numeric:tabular-nums; letter-spacing:.02em;
}
.cue p{margin:.15rem 0 0}
.role{
  display:inline-block; font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.66rem; letter-spacing:.14em; text-transform:uppercase;
  color:var(--tint); border:1px solid var(--tint); border-radius:2px;
  padding:.1rem .42rem; opacity:.95;
}
u{text-decoration:underline;text-underline-offset:.18em}
a:focus-visible,li:focus-visible{outline:2px solid var(--gold);outline-offset:3px}
@media (max-width:640px){
  ol.cues li{grid-template-columns:1fr;gap:.2rem}
  .toc li{grid-template-columns:2rem 1fr;}
  .toc li .tc{grid-column:2}
}
@media print{
  @page{ margin:16mm 15mm; }
  body{background:#fff;color:#000;font-size:10.5pt;line-height:1.5;padding:0}
  .masthead{padding:0 0 1.2rem;border-bottom:1px solid #bbb}
  .masthead,.toc,.chapter{max-width:none}
  h1{font-size:26pt}
  .eyebrow,.onscreen{color:#555}
  .standfirst,.colophon,.note,.meta{color:#222}
  .toc{page-break-after:always;padding-top:1.2rem}
  .toc li:hover{border-bottom-color:transparent}
  .preamble{max-width:none;padding:0 0 1rem}
  /* the opening card should not strand itself on a page of its own */
  .preamble + .chapter{page-break-before:avoid}
  .chapter{page-break-before:always;border-top:0;margin-top:0;padding:0 0 1rem}
  .chapter h2{font-size:16pt;break-after:avoid}
  .meta{break-after:avoid}
  a{color:#000;text-decoration:none}
  /* never split a direction, a card or a plan across a page */
  ol.cues li,blockquote.card,figure{break-inside:avoid;page-break-inside:avoid}
  blockquote.card{background:#f1f1f1;border-left-color:#777}
  .role{color:#000;border-color:#777}
  .tc{color:#333}
  figure img{border:1px solid #999}
}
"""


def for_github(sheet, video_url):
    """Copies meant to be committed: GitHub renders the markdown in the repo,
    and Pages serves the HTML from docs/."""
    md = render(sheet, True, video_url, base=".")
    with open("RUBRIC.md", "w", encoding="utf-8") as f:
        f.write(md)
    print(f"  RUBRIC.md   {len(md.splitlines())} lines   (GitHub renders this)")

    os.makedirs("docs", exist_ok=True)
    doc = render_html(sheet, video_url)
    with open(os.path.join("docs", "index.html"), "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"  docs/index.html   {len(doc) / 1024:.0f} KB   (GitHub Pages)")


def convert():
    """PDF and Word, when the tools for them are on the machine."""
    made = []

    if shutil.which("weasyprint"):
        pdf = os.path.join(OUT, "rubric.pdf")
        # --encoding matters: without it the em dashes come out as mojibake
        r = subprocess.run(["weasyprint", "--encoding", "utf-8",
                            os.path.join(OUT, "rubric.html"), pdf],
                           capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(pdf):
            made.append(pdf)
        else:
            print("  weasyprint failed:", (r.stderr or "").strip()[:120])
    else:
        print("  rubric.pdf skipped — brew install weasyprint")

    if shutil.which("pandoc"):
        # run from output/ so the ../art/ image paths resolve
        r = subprocess.run(["pandoc", "rubric_print.md", "-o", "rubric.docx"],
                           cwd=OUT, capture_output=True, text=True)
        docx = os.path.join(OUT, "rubric.docx")
        if r.returncode == 0 and os.path.exists(docx):
            made.append(docx)
        else:
            print("  pandoc failed:", (r.stderr or "").strip()[:120])
    else:
        print("  rubric.docx skipped — brew install pandoc")

    for f in made:
        print(f"  {f}   {os.path.getsize(f) / 1024:.0f} KB")


def main():
    ap = argparse.ArgumentParser(description="Build the written rubric.")
    ap.add_argument("--sheet", default="annotations.yaml")
    ap.add_argument("--video", default="", metavar="URL",
                    help="video URL; chapter timecodes become links to it")
    a = ap.parse_args()

    if not os.path.exists(a.sheet):
        sys.exit(f"ERROR: {a.sheet} not found")
    os.makedirs(OUT, exist_ok=True)

    for linked, name in ((True, "rubric_online.md"), (False, "rubric_print.md")):
        text = render(a.sheet, linked, a.video)
        path = os.path.join(OUT, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"  {path}   {len(text.splitlines())} lines, "
              f"{len(text.split())} words")

    for_github(a.sheet, a.video)

    doc = render_html(a.sheet, a.video)
    path = os.path.join(OUT, "rubric.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"  {path}   {len(doc) / 1024:.0f} KB (images embedded)")
    convert()


if __name__ == "__main__":
    main()
