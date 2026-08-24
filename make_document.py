#!/usr/bin/env python3
"""Build the written rubric from the edit sheet.

    python3 make_document.py
    python3 make_document.py --video https://youtu.be/XXXX
    python3 make_document.py --sheet other.yaml

Writes two files into output/:

    rubric_online.md   linked contents, timecodes hyperlinked to the video
    rubric_print.md    no links, page breaks between chapters

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
import argparse, os, re, sys

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


def render(sheet, linked, video_url):
    durs = clip_durations()
    chap_at = video_chapter_starts()
    L = []
    add = L.append

    add("# Hierarchical Divine Liturgy")
    add("## A rubric for deacons")
    add("")
    add("Filmed 20 June 2026 · OCA, Diocese of New York and New Jersey")
    add("")
    add("Directions are numbered by their position in each clip, so a time here "
        "matches the same moment in the footage.")
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
                add(f"![{md_escape(c.get('chapter') or 'diagram')}]"
                    f"({os.path.relpath(img, OUT)})")
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


if __name__ == "__main__":
    main()
