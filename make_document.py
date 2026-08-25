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
import argparse, base64, datetime, html, mimetypes, os, re, shutil
import subprocess, sys

try:
    import yaml
except ModuleNotFoundError:
    sys.exit("ERROR: PyYAML missing — pip3 install --break-system-packages pyyaml")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_sheet import resolve, clip_durations, is_span, as_list, _first

OUT = "output"


def build_stamp():
    """When this was generated and from which commit, so it is obvious at
    a glance whether the page in front of you is the current one."""
    when = datetime.datetime.now().strftime("%d %b %Y, %H:%M")
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
    except Exception:
        sha = ""
    return f"generated {when}" + (f" \u00b7 {sha}" if sha else "")


def mmss(t):
    t = max(float(t), 0)
    h, m, s = int(t // 3600), int((t % 3600) // 60), int(t % 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def md_escape(t):
    """The sheet's own emphasis is markdown already, so only table-breaking
    pipes need dealing with."""
    return str(t).replace("|", "\\|")


def video_chapters(path=os.path.join(OUT, "chapters.txt")):
    """[(title, start, end)] from a full build's FFMETADATA chapters.

    A chapter's own END runs past the next chapter's START, because a leading
    card pulls the next chapter backwards to cover it. So a chapter really
    ends where the next one begins; only the last keeps its own END.
    """
    rows, start, end = [], None, None
    if not os.path.exists(path):
        return rows
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line.startswith("START="):
            start = int(line[6:]) / 1000.0
        elif line.startswith("END="):
            end = int(line[4:]) / 1000.0
        elif line.startswith("title=") and start is not None:
            rows.append([line[6:], start, end])
            start = end = None
    for i in range(len(rows) - 1):
        rows[i][2] = rows[i + 1][1]
    return [tuple(r) for r in rows]


def video_chapter_starts(path=os.path.join(OUT, "chapters.txt")):
    """title -> seconds."""
    out = {}
    for t, st, _en in video_chapters(path):
        out.setdefault(t, st)
    return out


POSTER_W    = 560      # poster width in px; the column is ~700 at most
POSTER_Q    = 6        # ffmpeg -q:v, 2 best .. 31 worst
AUTO_LEAD   = 14.0     # seconds into a section for an automatic grab
AUTO_FRAC   = 0.35     # ...or this far through it, whichever is sooner
MIN_RUN     = 1.0      # a stretch of footage shorter than this is not worth
                       # grabbing from, and absorbs cross-file rounding
MASTER      = os.path.join(OUT, "master.mp4")


def declared_thumbnails(path=os.path.join(OUT, "thumbnails.tsv")):
    """clip -> seconds into master.mp4, from a `thumbnail:` in the sheet.

    build.py writes this, because only it knows how the cuts and speed spans
    move a time written against the original clip. Absent file means nobody
    has declared one yet, which is the normal state early on.
    """
    out = {}
    if not os.path.exists(path):
        return out
    for i, line in enumerate(open(path, encoding="utf-8")):
        if i == 0 or not line.strip():
            continue
        bits = line.rstrip("\n").split("\t")
        if len(bits) < 2:
            continue
        try:
            out[int(bits[1])] = float(bits[0])
        except ValueError:
            pass
    return out


def poster_frames(jobs, outdir):
    """Grab one still per section out of master.mp4.

    jobs is [(name, seconds)]; returns name -> filename relative to outdir.
    Files are kept rather than inlined, so a regeneration that changes one
    thumbnail rewrites one small JPEG instead of the whole page — which is
    what keeps the git history of a 34-poster page reasonable.
    """
    if not os.path.exists(MASTER):
        print(f"  posters skipped — {MASTER} not found (run build.py)")
        return {}
    d = os.path.join(outdir, "posters")
    os.makedirs(d, exist_ok=True)

    idx_path = os.path.join(d, "index.tsv")
    have = {}
    if os.path.exists(idx_path):
        for line in open(idx_path, encoding="utf-8"):
            bits = line.rstrip("\n").split("\t")
            if len(bits) == 2:
                have[bits[0]] = bits[1]

    made, grabbed = {}, 0
    for name, secs in jobs:
        fn = f"{name}.jpg"
        made[name] = f"posters/{fn}"
        stamp = f"{secs:.3f}"
        full = os.path.join(d, fn)
        if have.get(name) == stamp and os.path.exists(full):
            continue          # same moment, already grabbed
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", stamp, "-i", MASTER,
             "-frames:v", "1", "-vf", f"scale={POSTER_W}:-2",
             "-q:v", str(POSTER_Q), full],
            capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(full):
            print(f"  poster {name} failed:", (r.stderr or "").strip()[:100])
            made.pop(name, None)
            continue
        have[name] = stamp
        grabbed += 1

    with open(idx_path, "w", encoding="utf-8") as f:
        for name in sorted(have):
            if name in made:
                f.write(f"{name}\t{have[name]}\n")

    kb = sum(os.path.getsize(os.path.join(d, f"{n}.jpg"))
             for n in made) / 1024
    print(f"  {d}/   {len(made)} posters, {kb:.0f} KB "
          f"({grabbed} freshly grabbed)")
    return made


def card_spans(path=os.path.join(OUT, "boundaries.tsv")):
    """[(start, end)] of the title cards inside master.mp4.

    A poster grabbed on a card is just the card's own words in small type,
    which is useless as a thumbnail and identical to every other card. The
    build already lists every segment here, cards included, so an automatic
    grab can step over them.
    """
    rows = []
    if not os.path.exists(path):
        return []
    for line in open(path, encoding="utf-8"):
        bits = line.rstrip("\n").split("\t")
        if len(bits) < 2:
            continue
        try:
            h, m, sec = bits[0].split(":")
            rows.append((int(h) * 3600 + int(m) * 60 + float(sec), bits[1]))
        except ValueError:
            continue
    out = []
    for i, (t, nm) in enumerate(rows):
        if re.search(r"_(?:end)?card\d+\.mp4$", nm):
            out.append((t, rows[i + 1][0] if i + 1 < len(rows) else t))
    return sorted(out)


def poster_plan(secs_titles, spans, thumbs, cards=()):
    """[(name, seconds)] — where each section's poster frame comes from.

    A `thumbnail:` on the clip wins. Failing that, one declared anywhere
    inside the section is used, which is how a joined clip can supply the
    poster for the chapter it continues. Failing that, a frame a little way
    in — far enough to clear a title card, not so far as to miss the point.
    """
    jobs = []
    for n, t in secs_titles:
        span = spans.get(t)
        if not span:
            continue
        st, en = span
        if n in thumbs:
            at = thumbs[n]
        else:
            inside = sorted(v for v in thumbs.values() if st <= v < en)
            if inside:
                at = inside[0]
            else:
                # What is left of the section once its cards are taken out.
                # Comparing times across two files needs slack: chapters.txt
                # is in milliseconds and boundaries.tsv in centiseconds, so a
                # chapter can begin a few thousandths before its own card.
                free, cur = [], st
                for cs, ce in cards:
                    if ce <= st or cs >= en:
                        continue
                    cs, ce = max(cs, st), min(ce, en)
                    if cs - cur > MIN_RUN:
                        free.append((cur, cs))
                    cur = max(cur, ce)
                if en - cur > MIN_RUN:
                    free.append((cur, en))
                if free:
                    fs, fe = max(free, key=lambda p: p[1] - p[0])
                else:
                    fs, fe = st, en     # a section that is nothing but a card
                at = fs + min(AUTO_LEAD, (fe - fs) * AUTO_FRAC)
        jobs.append((f"c{n}", max(0.0, min(at, en - 0.2))))
    return jobs


def video_id(url):
    """The bare id from a youtu.be/… or watch?v=… link."""
    m = re.search(r"(?:youtu\.be/|[?&]v=|/embed/)([A-Za-z0-9_-]{6,})", url or "")
    return m.group(1) if m else None


def blocks(sheet):
    with open(sheet, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    return [b for b in doc if isinstance(b, dict) and "clip" in b]


def front(sheet):
    """The intro block, if the sheet has one. Front matter belongs with the
    content it describes, not hardcoded in here."""
    with open(sheet, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    for b in doc:
        if isinstance(b, dict) and isinstance(b.get("intro"), dict):
            return b["intro"]
    return {}


def render(sheet, linked, video_url, base=OUT, dl=""):
    durs = clip_durations()
    chap_at = video_chapter_starts()
    L = []
    add = L.append

    fm = front(sheet)
    add("# " + str(fm.get("title", "Rubrics for a Hierarchical Liturgy")))
    add("")
    if fm.get("subtitle"):
        add("*" + str(fm["subtitle"]).strip() + "*")
        add("")
    if video_url:
        add(f"[Watch the whole video]({video_url}) · "
            f"[Download PDF]({dl}rubric.pdf) · "
            f"[Download Word]({dl}rubric.docx)")
        add("")
    for sec in fm.get("sections") or []:
        if sec.get("heading"):
            add("## " + str(sec["heading"]).strip())
            add("")
        add(str(sec.get("text", "")).strip())
        add("")
    add(f"`{build_stamp()}`")
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
                    sec = int(at + 0.5)
                    bits.append(
                        f"[open on YouTube at {stamp}]({video_url}&t={sec}s)"
                        if "?" in video_url else
                        f"[open on YouTube at {stamp}]({video_url}?t={sec}s)")
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


def chapter_sections(sheet):
    """[(clip, title)] for the clips that open a chapter — the sections that
    get a heading, and so a player and a poster."""
    out = []
    for b in blocks(sheet):
        if b.get("skip") is True or b.get("join") is True:
            continue
        t = _first(b, "chapter", "chapters")
        if t:
            out.append((b["clip"], str(t).strip()))
    return out


def render_html(sheet, video_url, posters=None, staging=False):
    posters = posters or {}
    up = "../" if staging else ""      # staging shares the live downloads
    durs, chap_at = clip_durations(), video_chapter_starts()
    spans = {t: (st, en) for t, st, en in video_chapters() if en and en > st}
    H = []
    add = H.append

    secs = chapter_sections(sheet)

    add('<title>Serving a Hierarchical Liturgy</title>')
    if staging:
        add('<meta name="robots" content="noindex">')
    add('<link rel="preconnect" href="https://fonts.googleapis.com">')
    add('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
    add('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
        'family=Cormorant+Garamond:wght@500;600&family=IBM+Plex+Mono:wght@400;500'
        '&display=swap">')
    add("<style>" + CSS + "</style>")

    if staging:
        add('<p class="staging">Staging &middot; not the published page</p>')
    add('<header class="masthead">')
    fm = front(sheet)
    if fm.get("subtitle"):
        add(f'  <p class="eyebrow">{html.escape(str(fm["subtitle"]).strip())}</p>')
    add("  <h1>" + html.escape(str(fm.get(
        "title", "Rubrics for a Hierarchical Liturgy"))) + "</h1>")
    if video_url:
        add('  <p class="actions">'
            f'<a href="{html.escape(video_url)}">Watch the whole video</a>'
            f'<a href="{up}rubric.pdf">Download PDF</a>'
            f'<a href="{up}rubric.docx">Download Word</a></p>')
    add(f'  <p class="build">{html.escape(build_stamp())}</p>')
    add('  <p class="colophon">OCA, Russian recension &middot; Diocese of New '
        'York and New Jersey &middot; Filmed 20 June 2026. Times are positions '
        'within each clip, so a direction here sits at the same moment in the '
        'footage.</p>')
    add("</header>")

    for sec in fm.get("sections") or []:
        add('<section class="intro">')
        if sec.get("heading"):
            add(f'  <h2>{html.escape(str(sec["heading"]).strip())}</h2>')
        for para in str(sec.get("text", "")).strip().split("\n\n"):
            if para.strip():
                add(f"  <p>{inline_md(para.strip())}</p>")
        add("</section>")

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
                meta.append(f"{stamp} in the video")
            add('  <p class="meta">' + " &middot; ".join(meta) + "</p>")

            vid = video_id(video_url)
            span = spans.get(t)
            if vid and span:
                st_i, en_i = int(span[0] + 0.5), int(span[1] + 0.5)
                # A placeholder, not an iframe: the IFrame API builds the
                # player here when it scrolls into view. Adopting an existing
                # lazy-loaded iframe is unreliable, and YouTube's own `end`
                # cannot be trusted — see END_GUARD.
                src = posters.get(f"c{n}")
                data = (f'data-vid="{vid}" data-start="{st_i}" '
                        f'data-end="{en_i}"')
                nos = (f'<noscript><a href="https://www.youtube.com/watch?v='
                       f'{vid}&amp;t={st_i}s">Watch this section</a></noscript>')
                if src:
                    # A still from this very moment, not an iframe: nothing is
                    # fetched from YouTube until the reader asks for it, and
                    # every section looks like itself rather than like the
                    # one thumbnail the whole video shares.
                    add(f'  <div class="player">'
                        f'<button type="button" class="poster" {data} '
                        f'aria-label="Play this section">'
                        f'<img src="{src}" alt="" loading="lazy" '
                        f'width="{POSTER_W}" height="{round(POSTER_W*9/16)}">'
                        f'<span class="play" aria-hidden="true"></span>'
                        f'</button>{nos}</div>')
                else:
                    add(f'  <div class="player"><div class="slot" {data}>'
                        f'</div>{nos}</div>')

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

    if video_id(video_url):
        add(END_GUARD)

    return "\n".join(H) + "\n"


END_GUARD = """
<script>
/* Posters are stills; the real player is built on click. Nothing is fetched
   from YouTube until then — not even the API — so a page of 34 sections costs
   34 small images instead of 34 embedded players.

   At the end of a section the player is destroyed and the poster put back,
   rather than left paused on its last frame. A paused player resumes where it
   stopped, which for a bounded section means it would run on into the next
   one; rebuilding from the poster always re-applies `start`.

   The callback has to exist before the API script is inserted, or the API
   fires it into nothing and no player is ever built. */
(function () {
  var pending = [], ready = false, asked = false;

  window.onYouTubeIframeAPIReady = function () {
    ready = true;
    pending.splice(0).forEach(function (j) { build(j[0], j[1], j[2]); });
  };

  function api() {
    if (asked) return;
    asked = true;
    var s = document.createElement("script");
    s.src = "https://www.youtube.com/iframe_api";
    document.head.appendChild(s);
  }

  /* Put the still back where the player was. The button is the very node that
     was taken out, so its click handler is still on it. */
  function restore(player, ctx) {
    if (!ctx) return;
    try { player.destroy(); } catch (e) {}
    if (!ctx.btn.parentNode) ctx.box.appendChild(ctx.btn);
  }

  function build(box, auto, ctx) {
    var end = parseFloat(box.getAttribute("data-end"));
    box.textContent = "";
    new YT.Player(box, {
      videoId: box.getAttribute("data-vid"),
      playerVars: {
        start: parseInt(box.getAttribute("data-start"), 10),
        end: parseInt(end, 10),
        autoplay: auto ? 1 : 0,
        rel: 0
      },
      events: {
        onStateChange: function (ev) {
          /* the whole video ran out — the last section can end this way */
          if (ev.data === YT.PlayerState.ENDED) {
            restore(ev.target, ctx);
            return;
          }
          if (ev.data !== YT.PlayerState.PLAYING) return;
          /* YouTube honours `end` erratically, so stop it here too. */
          var tick = setInterval(function () {
            var t = ev.target.getCurrentTime && ev.target.getCurrentTime();
            if (typeof t === "number" && t >= end) {
              clearInterval(tick);
              try { ev.target.pauseVideo(); } catch (e) {}
              /* a beat, so the picture stops before the still replaces it */
              setTimeout(function () { restore(ev.target, ctx); }, 180);
            }
          }, 200);
        }
      }
    });
  }

  function queue(box, auto, ctx) {
    if (ready) { build(box, auto, ctx); }
    else { pending.push([box, auto, ctx]); api(); }
  }

  /* YT.Player replaces the element it is handed, so give it a throwaway div
     rather than the button, whose parent carries the aspect ratio. */
  function swap(btn) {
    var box = btn.parentNode;
    var slot = document.createElement("div");
    slot.className = "slot";
    ["vid", "start", "end"].forEach(function (k) {
      slot.setAttribute("data-" + k, btn.getAttribute("data-" + k));
    });
    box.replaceChild(slot, btn);
    queue(slot, true, { box: box, btn: btn });
  }

  document.querySelectorAll(".player > .poster").forEach(function (btn) {
    btn.addEventListener("click", function () { swap(btn); });
  });

  /* No poster (no master.mp4 when the page was built): fall back to building
     those players outright, so the page still works. */
  document.querySelectorAll(".player > .slot[data-vid]").forEach(function (b) {
    queue(b, false, null);
  });
})();
</script>
"""

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
.build{
  margin:1.1rem 0 0; color:var(--gold);
  font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.72rem; letter-spacing:.1em; text-transform:uppercase;
}
.colophon{
  color:var(--muted); max-width:34rem; margin:1rem 0 0;
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.76rem;
  line-height:1.7; letter-spacing:.02em;
}
.actions{display:flex;flex-wrap:wrap;gap:.5rem;margin:1.4rem 0 0}
.actions a{
  display:inline-block; padding:.42rem .85rem; border:1px solid var(--rule);
  border-radius:2px; color:var(--ink); text-decoration:none;
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.74rem;
  letter-spacing:.06em;
}
.actions a:hover{border-color:var(--gold);color:var(--gold)}
.intro{max-width:44rem;margin:0 auto;padding:2.2rem 0 0}
.intro h2{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.74rem;
  letter-spacing:.18em; text-transform:uppercase; color:var(--gold);
  font-weight:500; margin:0 0 .7rem;
}
.intro p{margin:0 0 .9rem}
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
.player{
  position:relative; width:100%; aspect-ratio:16/9; margin:0 0 1.7rem;
  border:1px solid var(--rule); border-radius:3px; overflow:hidden;
  background:#000;
}
.player iframe{position:absolute;inset:0;width:100%;height:100%;border:0}
.player .slot{position:absolute;inset:0}
.player .poster{
  position:absolute;inset:0;display:block;width:100%;height:100%;
  padding:0;border:0;background:#000;cursor:pointer;
}
.player .poster img{
  width:100%;height:100%;object-fit:cover;display:block;opacity:.85;
  transition:opacity .18s ease;
}
.player .poster:hover img,.player .poster:focus-visible img{opacity:1}
.player .poster:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
.player .play{
  position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);
  width:4rem;height:4rem;border-radius:50%;display:grid;place-items:center;
  background:rgba(12,10,8,.6);border:1px solid rgba(255,255,255,.55);
  transition:background .18s ease,transform .18s ease;
}
.player .play::after{
  content:"";width:0;height:0;margin-left:.3rem;
  border-left:1rem solid #fff;
  border-top:.6rem solid transparent;border-bottom:.6rem solid transparent;
}
.player .poster:hover .play{
  background:var(--gold);transform:translate(-50%,-50%) scale(1.06);
}
@media (prefers-reduced-motion:reduce){
  .player .poster img,.player .play{transition:none}
}
.staging{
  background:var(--gold);color:#12100e;text-align:center;
  font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;
  padding:.55rem 1rem;margin:0;
}
.player noscript a{position:absolute;inset:0;display:grid;place-items:center;
  color:var(--gold);font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.8rem;letter-spacing:.05em}
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
  .actions{display:none}
  .intro{max-width:none;padding:1.4rem 0 0}
  .intro h2{color:#555}
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
  .player{display:none}
}
"""


def for_github(sheet, video_url, posters=None):
    """Copies meant to be committed: GitHub renders the markdown in the repo,
    and Pages serves the HTML from docs/."""
    md = render(sheet, True, video_url, base=".", dl="docs/")
    with open("RUBRIC.md", "w", encoding="utf-8") as f:
        f.write(md)
    print(f"  RUBRIC.md   {len(md.splitlines())} lines   (GitHub renders this)")

    os.makedirs("docs", exist_ok=True)
    doc = render_html(sheet, video_url, posters)
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

    # Pages serves docs/, so the download links only work if the files are
    # there — output/ is ignored by git and never reaches the site.
    for f in made:
        print(f"  {f}   {os.path.getsize(f) / 1024:.0f} KB")
        if os.path.isdir("docs"):
            shutil.copy2(f, os.path.join("docs", os.path.basename(f)))
            print(f"    -> docs/{os.path.basename(f)}")


def main():
    ap = argparse.ArgumentParser(description="Build the written rubric.")
    ap.add_argument("--sheet", default="annotations.yaml")
    ap.add_argument("--video", default="", metavar="URL",
                    help="video URL; chapter timecodes become links to it")
    ap.add_argument("--staging", action="store_true",
                    help="write only docs/staging/index.html, leaving the "
                         "published page and the downloads untouched")
    a = ap.parse_args()

    if not os.path.exists(a.sheet):
        sys.exit(f"ERROR: {a.sheet} not found")
    os.makedirs(OUT, exist_ok=True)

    # One poster plan, shared by every copy of the page.
    spans = {t: (st, en) for t, st, en in video_chapters() if en and en > st}
    jobs = poster_plan(chapter_sections(a.sheet), spans,
                       declared_thumbnails(), card_spans())

    if a.staging:
        d = os.path.join("docs", "staging")
        os.makedirs(d, exist_ok=True)
        doc = render_html(a.sheet, a.video, poster_frames(jobs, d),
                          staging=True)
        with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
            f.write(doc)
        print(f"  {d}/index.html   {len(doc) / 1024:.0f} KB   (staging)")
        print("  RUBRIC.md, docs/index.html and the downloads "
              "were not touched.")
        return

    for linked, name in ((True, "rubric_online.md"), (False, "rubric_print.md")):
        text = render(a.sheet, linked, a.video)
        path = os.path.join(OUT, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"  {path}   {len(text.splitlines())} lines, "
              f"{len(text.split())} words")

    docs_posters = poster_frames(jobs, "docs")
    for_github(a.sheet, a.video, docs_posters)

    # output/ sits beside docs/, so the print copy points at the same posters
    # rather than keeping a second set of them.
    doc = render_html(a.sheet, a.video,
                      {k: "../docs/" + v for k, v in docs_posters.items()})
    path = os.path.join(OUT, "rubric.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"  {path}   {len(doc) / 1024:.0f} KB (images embedded)")
    convert()


if __name__ == "__main__":
    main()
