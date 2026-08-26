#!/usr/bin/env python3
"""
build.py — build the whole video from one edit sheet.

Reads a single YAML edit sheet and writes into output/:
    master.mp4          the assembled video (cards inserted, clips skipped)
    liturgy_training.mkv  the same, with annotations and chapters embedded
    annotations.ass     the annotation track
    chapters.txt        FFMETADATA chapter marks
    youtube_chapters.txt
    boundaries.tsv      for reference
    thumbnails.tsv      poster moments, mapped into master.mp4 time, for
                        make_document.py

USAGE
    python3 build.py                    # full build
    python3 build.py --subs-only        # only rebuild annotations.ass
                                        # (fast; use while timing text)
    python3 build.py --sheet edit.yaml  # a different sheet
    python3 build.py --speed 6          # default rate for spans saying speed: true
    python3 build.py --clip 3           # preview clip 3 on its own
    python3 build.py --clip 3-5         # preview a range
    python3 build.py --clip 3 --cards none    # preview times = clip times
    python3 build.py --clip 3 --draft         # fast, blocky re-encode
    python3 build.py --clip 3 --play          # open it in VLC when it works
    python3 build.py --clip 3 --timecode --draft   # show ORIGINAL clip times
    python3 build.py --fade 0           # no audio fade at clip ends
    python3 build.py --cut-fade 0       # no audio fade leading into cuts

    The sheet defaults to the annotations/ directory, whose .yaml files are
    read in name order. It is validated before anything
    is built, and errors stop the build; --no-check overrides that.
    To check without building: python3 check_sheet.py

REQUIRES
    normalized/001.mp4 ... from normalize_and_join.sh
    ffmpeg, ffprobe, PyYAML

------------------------------------------------------------------
THE SHEET
------------------------------------------------------------------
A list of clip blocks, in order. The clip number IS the block, so it
cannot go missing.

  - clip: 5
    chapter: Vesting of the Hierarch
    cards:        played BEFORE this clip
    annotations:  on-screen text, and speed/cut spans, in time order
    notes:        published — goes into the written document
    todos:        yours alone; never on screen, never printed
    thumbnail:    the moment to use as this section's poster frame on the
                  written-rubric web page. Original clip time, like every
                  other time here, so --timecode shows you what to type.
                  Leave it out and a frame is picked automatically.
    skip: true    leave this clip out of the build entirely
    join: true    this clip continues the one before it: no chapter of its
                  own, and the previous clip does not fade out at its end.
                  It must carry no cards, or one would sit in the join.

Singular and plural key names mean the same thing everywhere:
annotation/annotations, card/cards, cut/cuts, note/notes, todo/todos,
thumbnail/thumb.

The sheet may also carry `intro:` and `appendix:` blocks. Those are prose for
the written rubric, they sit at no moment in the video, and this build steps
over them — see make_document.py. A block with neither `clip:` nor one of
those keys is still an error, so a misspelling is not silently ignored.

TIMES
  Write them bare — 1:27, 1:03:23, 0:04, 87 and 4.5 all work.

  On an annotation:
    at: (or from:)  when it appears. LEAVE IT OUT and it picks up 0.2s
                    after the previous annotation ends, or at 0 if it is
                    the first in the clip.
    for:            how long it stays up. Leave it out and the annotation
                    holds until the next one starts, so a run of cues needs
                    only the moments they happen:

                        - at: 1:16
                          text: do thing 1
                        - at: 1:20
                          text: do thing 2

                    Falls back to 4s when there is no next annotation, or
                    when the next one's start is itself relative.
    to:             an absolute end instead of a duration. `to: end` runs
                    to the end of the clip — on spans too, so `cut: true`
                    with `to: end` trims a clip's tail.
    at: next+1.5    continue, but wait 1.5s. "C" and "C+1.5" also work.

TEXT
  Put prose under `text: >` (folds to one line) or `text: |` (keeps your
  line breaks). Neither needs quoting or escaping. Never put prose inside
  { } — a comma there ends the value and silently swallows the rest.

  Blank lines are kept, and render as a real gap. Leading and trailing ones
  are dropped, so a block scalar's trailing newline adds nothing.

  A little markdown works:

    **bold**      *italic*      _underline_        anywhere
    # Heading     ## Smaller    ### Smaller still  on cards

  Headings only mean anything on a card, which has room for more than one
  size. Chapter names take the text with the markers stripped, so a card
  headed `# Entrance Prayers` is still called "Entrance Prayers".

CHAPTERS
  chapter: always means "a chapter starts here, titled this". Present, a
  chapter starts; absent, it does not.
    on a clip  names the chapter beginning at that clip
    on a card  the card becomes its own chapter with that title, which
               need not match the words on screen

CARDS
  Played before the clip they are listed under, so they introduce it.
  `after: true` puts one after instead. A `clip: 0` block means "before
  everything".
    for:     card duration in seconds (default 6)
    text:    card text
    image:   optional PNG shown instead of drawn text
  A card with no chapter: folds into the chapter that follows — that
  chapter simply starts earlier, at the card.

SPEED AND CUT SPANS
  Written inline in the annotations list so a clip reads in time order:

    - from: 38
      to: 1:18
      speed: 4x        4 and 2.5x also parse; true = the --speed rate
      audio: normal    what a sped span sounds like:
                         mute    silence (the default)
                         fast    time-stretched to fit. Pitch is intact but
                                 speech and chant sound hurried.
                         normal  natural speed: the opening of the span plays
                                 untouched for exactly as long as the sped
                                 video lasts. Right for background singing —
                                 the chant sounds normal while the picture
                                 races. It fades out rather than stopping
                                 dead, after `hold:` seconds at full volume
                                 (default 4).
      hold: 2          seconds before the fade begins; only for audio: normal
                       mute: true/false is the older spelling of mute/fast.
      role: PRIEST
      text: Greets the bishop

    - from: 1:00
      to: 2:00
      cut: true        removes the span entirely

  Both ends must be given: a span marks a region of the original clip and
  cannot continue from whatever preceded it. A span never advances the
  point where the next annotation picks up.

  A span's text is its label, in the usual annotation position but
  italic. Blank gives "skipping ahead"; "-" gives no label. Ordinary
  annotations inside a sped span are warned about, since they flash past
  and would sit on top of the label.

  Separate speed: and cuts: blocks also work. A key cannot repeat in one
  block, though — writing annotations: twice silently discards the first.

IMPORTANT — everything is written against the ORIGINAL clip.
  Annotation, cut and speed times are all measured on the untouched
  footage; the script works out where they land after the edits. In a
  3:00 clip you can write a cut at 1:00-2:00, an annotation at 2:30 and
  another cut at 2:45, and the annotation ends up at 1:30 with the second
  cut at 1:45. You never recalculate anything: add, remove or resize an
  edit and everything else follows.

  Annotations falling inside a cut are dropped, with a warning. Only
  clips carrying edits are re-encoded.

EXAMPLE
  - clip: 0
    cards:
      - text: |
          Hierarchical Divine Liturgy
          Deacon Training
        for: 8

  - clip: 1
    chapter: Greeting of the Hierarch at the Doors
    annotations:
      - for: 4
        role: D1
        text: Deacon greets last: censer and trikirion
      - for: 5
        role: D1
        text: Bless master, the holy incense
      - at: next+2
        text: Censer must already be lit
    todos: Check the transliteration here.

  - clip: 13
    skip: true
"""

import argparse, hashlib, os, re, subprocess, sys
from collections import defaultdict

WORK = "normalized"          # build.py working files, from normalize_and_join.sh
RAW  = "raw"                 # the 37 source clips (see raw_clips.tsv)
OUT  = "output"              # every build product lands here

def out(name):
    """Path to a build product. Everything build.py writes goes to OUT/."""
    return os.path.join(OUT, name)

MASTER = os.path.join(OUT, "master.mp4")
W, H, FPS, CRF, PRESET = 1920, 1080, 30, 18, "slow"
DRAFT_CRF, DRAFT_PRESET = 30, "ultrafast"
AUDIO_HOLD = 4.0    # seconds at full volume before `audio: normal` fades out
CLIP_FADE = 3.0     # default audio fade at the end of every clip
CUT_FADE  = 1.5     # default audio fade leading into a cut

ROLE_COLOURS = {
    "D1": "&H00A5FF&", "D2": "&H80D0A0&", "SD": "&HD0C070&",
    "AS": "&HC0C0C0&", "B": "&H80B0FF&", "P": "&HB0A0E0&",
    "R": "&HA0D0D0&", "CH": "&HD0B0D0&",
}
FALLBACK = ["&H90E0E0&", "&HE0C090&", "&HA0E0A0&", "&HE0A0C0&"]
TEXT_COLOUR, FONT, FONTSIZE, DEFAULT_DUR = "&HFFFFFF&", "Georgia", 44, 4.0
CONT_GAP = 0.2      # default gap used by a "C" start time
CARD_DUR = 6.0
SKIP_LABEL = "· · ·   skipping ahead   · · ·"

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
]


def die(m): sys.exit("ERROR: " + m)


def role_prefix(role, seen_roles):
    """The bold coloured role tag that opens an annotation. Empty when there
    is no role. Used by ordinary annotations and by sped-span labels alike."""
    if not role:
        return ""
    colour = ROLE_COLOURS.get(role)
    if colour is None:
        colour = FALLBACK[seen_roles.index(role) % len(FALLBACK)]
    return f"{{\\c{colour}\\b1}}{role}{{\\b0\\c{TEXT_COLOUR}}}  "


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-2000:] + "\n")
        die("ffmpeg failed: " + " ".join(cmd[:6]) + " ...")


def probe_dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "csv=p=0", p],
                       capture_output=True, text=True)
    return float(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None


def parse_time(v):
    v = (v or "").strip()
    if not v: return None
    if re.fullmatch(r"\d+(\.\d+)?", v): return float(v)
    parts = [float(p) for p in v.split(":")]
    if len(parts) == 2: return parts[0]*60 + parts[1]
    if len(parts) == 3: return parts[0]*3600 + parts[1]*60 + parts[2]
    raise ValueError(f"cannot parse time {v!r}")


def ass_time(t):
    t = max(t, 0)
    h = int(t//3600); t -= h*3600
    m = int(t//60);   t -= m*60
    return f"{h}:{m:02d}:{t:05.2f}"


def find_font():
    for c in FONT_CANDIDATES:
        if os.path.exists(c): return c
    return None


def norm_lines(v):
    """Normalise line breaks. A Return typed inside a spreadsheet cell
    exports as an embedded newline; || also works as an explicit break."""
    return (v or "").replace("\r\n", "\n").replace("\r", "\n").replace("||", "\n")


def split_lines(v, keep_blanks=False):
    """Text as a list of lines.

    keep_blanks preserves interior blank lines, which both drawtext and libass
    render as a real gap — leading and trailing ones are dropped, so a YAML
    block scalar's trailing newline never adds space. Chapter titles use the
    default and collapse, since a chapter name has to be one line.
    """
    lines = [ln.strip() for ln in norm_lines(v).split("\n")]
    if not keep_blanks:
        return [ln for ln in lines if ln]
    while lines and not lines[0]:  lines.pop(0)
    while lines and not lines[-1]: lines.pop()
    return lines


HEADING_SCALE = {1: 1.55, 2: 1.30, 3: 1.15}
CARD_FONTSIZE = 64


def card_ass(body):
    """A card's text as a standalone ASS file.

    libass rather than drawtext, because drawtext has one font and one size
    for the whole block — no bold, no italic, no headings. Alignment 5 centres
    the block in the frame; every line carries its own size tag.
    """
    text = "\\N".join(md_line(ln, CARD_FONTSIZE) if ln.strip() else ""
                      for ln in body.split("\n"))
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Card,{FONT},{CARD_FONTSIZE},{TEXT_COLOUR},{TEXT_COLOUR},&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,140,140,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,9:59:59.99,Card,,0,0,0,,{text}
"""


def md_inline(t):
    """A small markdown subset as libass override tags.

    **bold**, *italic*, _underline_. Braces and backslashes are neutralised
    first, so nothing in the sheet can inject an override tag of its own.
    """
    t = t.replace("\\", "").replace("{", "(").replace("}", ")")
    t = re.sub(r"\*\*(.+?)\*\*", r"{\\b1}\1{\\b0}", t)
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"{\\i1}\1{\\i0}", t)
    t = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"{\\u1}\1{\\u0}", t)
    return t


def md_line(ln, base):
    """One line as ASS. `#`, `##`, `###` set the size for that line; every
    line carries an explicit size so nothing leaks across the break."""
    m = re.match(r"^(#{1,3})\s+(.*)$", ln)
    if m:
        size = int(base * HEADING_SCALE[len(m.group(1))])
        ln = m.group(2).strip()
    else:
        size = base
    return "{\\fs%d}%s" % (size, md_inline(ln))


def md_plain(t):
    """The same text with the markers removed — for chapter names."""
    t = re.sub(r"^#{1,3}\s+", "", t.strip())
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", t)
    t = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", t)
    return t


def get_dur(row):
    """A row's length or end time. Annotations and cards carry dur; spans
    carry end, which the span branch reads as an absolute position."""
    for k in ("dur", "end"):
        if row.get(k, "").strip():
            return row[k]
    return ""


def atempo_chain(f):
    """atempo only accepts 0.5-2.0 per stage, so chain them."""
    parts, x = [], float(f)
    while x > 2.0:
        parts.append("atempo=2.0"); x /= 2.0
    while x < 0.5:
        parts.append("atempo=0.5"); x /= 0.5
    if abs(x - 1.0) > 1e-6:
        parts.append(f"atempo={x:.6f}")
    return parts


def edit_segments(dur, edits):
    """Turn a clip duration + edit list into (start, end, factor, audio) spans.
    factor 1.0 = untouched, >1 = sped up. Cut spans are omitted.
    audio is (mode, hold): mode is mute / fast / normal, hold is the seconds
    at full volume before `normal` fades out. Only matters where factor != 1."""
    segs, prev = [], 0.0
    for st, d, factor, amode in sorted(edits):
        st = max(st, 0.0); en = min(st + d, dur)
        if en <= prev: continue
        if st > prev: segs.append((prev, st, 1.0, ("", 0.0)))
        if factor is not None: segs.append((st, en, float(factor), amode))
        prev = en
    if prev < dur: segs.append((prev, dur, 1.0, ("", 0.0)))
    return [sg for sg in segs if sg[1] - sg[0] > 0.01]


def time_map(t, segs):
    """Map a time in the ORIGINAL clip to its position in the edited clip.
    Returns None if t falls inside a cut."""
    out = 0.0
    for a, b, f, _ in segs:
        if t < a: return None          # inside a removed span
        if t <= b: return out + (t - a) / f
        out += (b - a) / f
    return out


def build_edited_clip(src, dst, segs, fade=0.0, cut_fade=0.0):
    """Re-encode one clip with cuts and speed changes applied.

    fade is an audio fade at the very end of the finished clip, so the sound
    settles rather than cutting dead into whatever follows. cut_fade does the
    same immediately before a cut, where the sound would otherwise jump. Both
    happen inside existing footage — nothing is made longer — and neither
    touches the picture.
    """
    spec = hashlib.md5((src + f"|v2|{PRESET}|{CRF}|{fade:.3f}|{cut_fade:.3f}|" +
                        repr([(round(a,3), round(b,3), round(f,4), m)
                              for a, b, f, m in segs])).encode()).hexdigest()
    sidecar = dst + ".spec"
    if os.path.exists(dst) and os.path.exists(sidecar):
        if open(sidecar).read().strip() == spec:
            return False
    # The picture is already right only if one segment runs at normal speed
    # from the very start to the very end. A tail cut also leaves a single
    # segment starting at 0 — it just stops early — so the end must be checked
    # too, or the trim is silently discarded along with the re-encode.
    srcdur = probe_dur(src) or 0.0
    if (len(segs) == 1 and abs(segs[0][2] - 1.0) < 1e-6
            and segs[0][0] < 0.01 and segs[0][1] >= srcdur - 0.05):
        af = (f"afade=t=out:st={max(segs[0][1] - fade, 0):.3f}:d={fade:.3f}"
              if fade > 0.05 and segs[0][1] > fade else "anull")
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-nostdin",
             "-i", src, "-af", af, "-c:v", "copy",
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", dst])
        open(sidecar, "w").write(spec)
        return True

    parts, labels = [], []
    for i, (a, b, f, audio) in enumerate(segs):
        amode, hold_s = audio
        parts.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},"
                     f"setpts=(PTS-STARTPTS)/{f:.6f}[v{i}]")
        sped = abs(f - 1.0) > 1e-6
        aa, ab = a, b
        if not sped:
            chain = ["asetpts=PTS-STARTPTS"]
        elif amode == "fast":
            # atempo compresses the audio to match the video, pitch intact.
            # Hurried speech and chant, but continuous.
            chain = ["asetpts=PTS-STARTPTS"] + atempo_chain(f)
        elif amode == "normal":
            # Play the opening of the span at natural speed for exactly as
            # long as the sped video lasts. Right for background singing:
            # the chant sounds untouched while the picture races. Fade it
            # out rather than cutting, which lands as harshly as a mute.
            outdur = (b - a) / f
            ab = a + outdur
            chain = ["asetpts=PTS-STARTPTS"]
            hold = min(hold_s, max(0.0, outdur - 0.5))
            fade = outdur - hold
            if fade > 0.05:
                chain.append(f"afade=t=out:st={hold:.3f}:d={fade:.3f}")
        else:                                   # "mute", the default
            chain = ["asetpts=PTS-STARTPTS"] + atempo_chain(f) + ["volume=0"]
        # Removed footage next? Then the sound is about to jump, so ease it
        # down first. Skipped where the segment already fades of its own
        # accord, to avoid attenuating twice.
        nxt = segs[i + 1][0] if i + 1 < len(segs) else None
        if (cut_fade > 0.05 and nxt is not None and nxt > b + 0.01
                and amode != "normal"):
            seg_out = (b - a) / f
            st = max(seg_out - cut_fade, 0.0)
            if seg_out - st > 0.05:
                chain.append(f"afade=t=out:st={st:.3f}:d={seg_out - st:.3f}")

        ach = ",".join(chain)
        parts.append(f"[0:a]atrim=start={aa:.3f}:end={ab:.3f},{ach}[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    fc = ";".join(parts) + ";" + "".join(labels) + \
         f"concat=n={len(segs)}:v=1:a=1[vc][ac]"
    outdur = sum((b - a) / f for a, b, f, _ in segs)
    fc += ";[vc]null[v]"
    if fade > 0.05 and outdur > fade:
        st = outdur - fade
        fc += f";[ac]afade=t=out:st={st:.3f}:d={fade:.3f}[a]"
    else:
        fc += ";[ac]anull[a]"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-nostdin",
         "-i", src, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
         "-r", str(FPS), "-fps_mode", "cfr",
         "-c:v", "libx264", "-preset", PRESET, "-crf", str(CRF),
         "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", dst])
    open(sidecar, "w").write(spec)
    return True


def _as_list(v):
    """Entries however they were written. A scalar where a list belongs yields
    nothing here; check_sheet reports it properly rather than crashing."""
    if v is None: return []
    if isinstance(v, dict): return [v]
    return v if isinstance(v, list) else []


def _first(d, *names):
    for n in names:
        if n in d and d[n] is not None:
            return d[n]
    return None


def _text(v):
    """A YAML scalar, or a list of points, as one string."""
    if v is None: return ""
    if isinstance(v, (list, tuple)):
        return "\n".join(str(x).strip() for x in v if str(x).strip())
    return str(v)


MATTER_KEYS = ("intro", "appendix")
"""Blocks that carry prose for the written rubric and never reach the video."""

SHEET_DIR = "annotations"


def default_sheet():
    """The sheet to use when none is named: the annotations/ directory if it
    is there, else the older single file."""
    if os.path.isdir(SHEET_DIR):
        return SHEET_DIR
    for cand in ("annotations.yaml", "annotations.yml"):
        if os.path.exists(cand):
            return cand
    return SHEET_DIR


def sheet_files(path):
    """The YAML files a sheet is made of, in order.

    A directory is every .yaml/.yml inside it, sorted by name — which is why
    they carry number prefixes: 01_intro, 02_clips, 03_appendices. Splitting
    the clips further is just a matter of adding 02b_… and so on. A plain
    file is itself, so an older single-file sheet still builds.
    """
    if os.path.isdir(path):
        fs = sorted(f for f in os.listdir(path)
                    if f.endswith((".yaml", ".yml")) and not f.startswith("."))
        if not fs:
            die(f"{path}/ holds no .yaml files")
        return [os.path.join(path, f) for f in fs]
    return [path]


def load_sheet(path):
    """(blocks, origins) — every block across the sheet in order, with the
    file and position each came from so an error can name them."""
    try:
        import yaml
    except ModuleNotFoundError:
        die("PyYAML is needed to read the sheet — "
            "pip3 install --break-system-packages pyyaml")
    blocks, origins = [], []
    for f in sheet_files(path):
        with open(f, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        if doc is None:
            continue                     # a file of nothing but comments
        if not isinstance(doc, list):
            die(f"{f}: expected a list of blocks, each starting with '- '")
        for i, b in enumerate(doc, 1):
            blocks.append(b)
            origins.append((os.path.basename(f), i))
    return blocks, origins


def read_sheet(path):
    """Flatten the YAML sheet into rows.

    Cards listed under a clip play BEFORE it, so a card in block N is emitted
    against clip N-1 -- and for clip 1 that is clip 0, which build.py already
    treats as the very front. `after: true` keeps it on clip N.

    Annotation start times are resolved here rather than downstream: an
    explicit time wins, otherwise the annotation picks up CONT_GAP after the
    previous one ended, or at 0 if it is the first in its clip.
    """
    doc, _origins = load_sheet(path)

    def is_span(e):
        return isinstance(e, dict) and (
            e.get("cut") is True or ("speed" in e and e["speed"] is not False))

    _lens = {}

    def clip_len(n):
        if n not in _lens:
            _lens[n] = probe_dur(os.path.join(WORK, f"{n:03d}.mp4"))
        return _lens[n]

    def end_of(v, n):
        """A time, or the word `end` for the end of clip n."""
        if v is None:
            die(f"clip {n}: a `to:` was left empty. Give it a time, or `end`, "
                f"or remove the line.")
        if isinstance(v, str) and v.strip().lower() == "end":
            d = clip_len(n)
            if d is None:
                die(f"clip {n}: 'to: end' needs {WORK}/{n:03d}.mp4 to measure")
            return d
        return parse_time(str(v))

    def audio_of(e):
        """(mode, hold). audio: mute | fast | normal; mute: true/false is the
        older spelling. hold: seconds at full volume before normal fades."""
        v = e.get("audio")
        if v is None:
            v = "mute" if e.get("mute", True) else "fast"
        hold = e.get("hold", AUDIO_HOLD)
        try: hold = float(hold)
        except (TypeError, ValueError): hold = AUDIO_HOLD
        return (str(v).strip().lower(), hold)

    def rate_of(v):
        if v is True: return None
        if isinstance(v, str): return float(v.strip().lower().rstrip("x").strip())
        return float(v)

    rows = []
    for bi, b in enumerate(doc, 1):
        if not isinstance(b, dict): die(f"{path}: block {bi} is not a clip block")
        # Prose blocks — intro: and appendix: are written for the rubric and
        # never reach the video, so the build steps over them. check_sheet.py
        # and make_document.py skip the same set. A block with no clip: and
        # none of these keys is still an error, so a typo is not swallowed.
        if "clip" not in b and any(k in b for k in MATTER_KEYS):
            continue
        n = b.get("clip")
        if not isinstance(n, int): die(f"{path}: block {bi} has no whole-number clip:")
        where = f"clip {n}"

        if b.get("skip") is True:
            rows.append((where, {"type": "skip", "clip": str(n)}))
            continue

        if b.get("join") is True:
            rows.append((where, {"type": "join", "clip": str(n)}))

        title = _first(b, "chapter", "chapters")
        if title:
            rows.append((where, {"type": "chapter", "clip": str(n),
                                 "text": _text(title)}))

        thumb = _first(b, "thumbnail", "thumb")
        if thumb is not None:
            rows.append((where, {"type": "thumbnail", "clip": str(n),
                                 "start": str(thumb)}))

        cards = _as_list(_first(b, "cards", "card"))
        for ci, c in enumerate(cards, 1):
            ctitle = _first(c, "chapter", "chapters")
            dur = _first(c, "for", "to")
            rows.append((f"{where} card {ci}", {
                "type":  "card" if ctitle else "title",
                "clip":  str(n),
                "_after": c.get("after") is True,
                "end":   "" if dur is None else str(dur),
                "text":  _text(c.get("text")),
                "image": _text(c.get("image")),
                "_chapter": _text(ctitle) if ctitle else "",
            }))

        entries = _as_list(_first(b, "annotations", "annotation"))
        spans = (_as_list(_first(b, "speed", "speeds"))
                 + _as_list(_first(b, "cuts", "cut")))
        spans = [e for e in spans if isinstance(e, dict)]

        # Annotations only, in order — so one can see when the next begins.
        anns = [x for x in entries if isinstance(x, dict) and not is_span(x)]

        def stated_start(e):
            """The start an annotation gives outright, or None when it depends
            on what came before — those cannot end the one before them."""
            v = _first(e, "at", "from")
            if v is None:
                return None
            if isinstance(v, str) and v.strip().lower().startswith(("next", "c")):
                return None
            try:
                return parse_time(str(v))
            except Exception:
                return None

        prev_end, ai, si = None, 0, 0
        for e in entries:
            if not isinstance(e, dict): continue
            if is_span(e):
                si += 1
                spans.append(e)
                continue
            ai += 1
            raw_at = _first(e, "at", "from")
            if raw_at is None:
                st = 0.0 if prev_end is None else prev_end + CONT_GAP
            elif isinstance(raw_at, str) and raw_at.strip().lower().startswith(("next", "c")):
                tail = raw_at.strip().lstrip("nextNEXTcC").strip().lstrip("+").strip()
                gap = float(tail) if tail else CONT_GAP
                st = 0.0 if prev_end is None else prev_end + gap
            else:
                st = parse_time(str(raw_at))
            if "for" in e:
                dur = parse_time(str(e["for"]))
            elif "to" in e:
                dur = end_of(e["to"], n) - st
            else:
                # No length given: hold until the next annotation starts, so a
                # run of cues needs only the moments they happen. Falls back to
                # the default when there is no next one, or when its start is
                # itself relative and would make this circular.
                nxt = anns[ai] if ai < len(anns) else None
                ns = stated_start(nxt) if nxt is not None else None
                dur = (ns - st) if (ns is not None and ns > st) else DEFAULT_DUR
            prev_end = st + dur
            rows.append((f"{where} annotation {ai}", {
                "type": "annotation", "clip": str(n),
                "start": f"{st:.6f}", "dur": f"{dur:.6f}",
                "role": _text(e.get("role")), "text": _text(e.get("text")),
            }))

        for k, e in enumerate(spans, 1):
            st = parse_time(str(_first(e, "at", "from")))
            en = (end_of(e["to"], n) if "to" in e
                  else st + parse_time(str(e["for"])))
            cut = e.get("cut") is True
            rows.append((f"{where} {'cut' if cut else 'speed'} {k}", {
                "type": "cut" if cut else "speed", "clip": str(n),
                "start": f"{st:.6f}", "end": f"{en:.6f}",
                "role": _text(e.get("role")), "text": _text(e.get("text")),
                "_rate": None if cut else rate_of(e.get("speed", True)),
                "_audio": audio_of(e),
            }))
    return rows


def burn_timecode(video, rows_out, seg_map):
    """Overlay each frame with its position in the ORIGINAL clip.

    The edit pipeline maps original time forward; this inverts it. A clip is
    laid down as pieces (a, b, factor): the piece occupies (b-a)/factor of
    output time, and output time T inside it corresponds to original time
    a + (T - S) * factor, where S is where the piece starts in the output.
    One drawtext per piece, switched on for exactly that span, so the number
    stays true across cuts, speed changes and inserted cards alike.
    """
    font = find_font()
    if not font:
        print("--timecode: no usable font found, skipped."); return

    draws = []
    for t0, nm, label, is_card, cno, d, lead in rows_out:
        if is_card:
            continue                      # a card has no place in the original
        segs = seg_map.get(cno) or [(0.0, d, 1.0, ("", 0.0))]
        cum = 0.0
        for seg in segs:
            aa, bb, ff = seg[0], seg[1], seg[2]
            piece = (bb - aa) / ff
            st, en = t0 + cum, t0 + cum + piece
            cum += piece
            # seconds in the original clip, as an ffmpeg expression
            e = f"(({{t}}-{st:.3f})*{ff:.6f}+{aa:.3f})".replace("{t}", "t")
            mins = f"%{{eif\\:floor(({e})/60)\\:d}}"
            secs = f"%{{eif\\:mod(floor({e})\\,60)\\:d\\:2}}"
            draws.append(
                f"drawtext=fontfile='{font}'"
                f":text='clip {cno:02d}   {mins}\\:{secs}'"
                f":fontcolor=white:fontsize=40:box=1:boxcolor=black@0.65"
                f":boxborderw=12:x=w-tw-32:y=32"
                f":enable='between(t\\,{st:.3f}\\,{en:.3f})'")

    if not draws:
        print("--timecode: nothing to label, skipped."); return

    tmp = video + ".tc.mp4"
    print(f"Burning original-clip timecode into {video} ({len(draws)} spans)")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-nostdin",
         "-i", video, "-vf", ",".join(draws),
         "-c:v", "libx264", "-preset", PRESET, "-crf", str(CRF),
         "-pix_fmt", "yuv420p", "-c:a", "copy", tmp])
    os.replace(tmp, video)


def clip_num(raw):
    raw = (raw or "").strip()
    if not raw: return None
    m = re.match(r"\s*(\d+)", raw)
    return int(m.group(1)) if m else None


# ----------------------------------------------------------------------

def make_card(path, text, dur, image=None):
    """Render a card, skipping if an identical one already exists."""
    # Key on the laid-out lines rather than the raw text, so a change in how
    # text is broken up invalidates the cache by itself.
    body = "\n".join(split_lines(text, keep_blanks=True))
    spec = hashlib.md5(
        f"{body}|{dur}|{image}|{W}x{H}|{FPS}|{PRESET}|{CRF}".encode()).hexdigest()
    sidecar = path + ".spec"
    if os.path.exists(path) and os.path.exists(sidecar):
        if open(sidecar).read().strip() == spec:
            return False

    fade = 0.4
    out_st = max(dur - fade, 0)

    if image:
        if not os.path.exists(image): die(f"card image not found: {image}")
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
              f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,format=yuv420p,"
              f"fade=t=in:st=0:d={fade},fade=t=out:st={out_st}:d={fade}")
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-nostdin",
               "-loop", "1", "-framerate", str(FPS), "-i", image,
               "-f", "lavfi", "-i",
               "anullsrc=channel_layout=stereo:sample_rate=48000",
               "-vf", vf]
    else:
        tmp = path + ".ass"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(card_ass(body))
        vf = (f"ass={tmp},"
              f"fade=t=in:st=0:d={fade},fade=t=out:st={out_st}:d={fade},setsar=1")
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-nostdin",
               "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={FPS}:d={dur}",
               "-f", "lavfi", "-i",
               "anullsrc=channel_layout=stereo:sample_rate=48000",
               "-vf", vf]

    cmd += ["-t", str(dur), "-r", str(FPS), "-fps_mode", "cfr",
            "-c:v", "libx264", "-preset", PRESET, "-crf", str(CRF),
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-shortest", path]
    run(cmd)
    open(sidecar, "w").write(spec)
    if not image and os.path.exists(path + ".ass"):
        os.remove(path + ".ass")
    return True


# ----------------------------------------------------------------------

def main():
    global CRF, PRESET
    ap = argparse.ArgumentParser(
        prog="build.py",
        description="Build the training video from one edit sheet.",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheet", dest="sheet", metavar="FILE",
                    help="the edit sheet: a directory of .yaml files, or one file (default: the annotations/ directory)")
    ap.add_argument("--fade", type=float, default=CLIP_FADE, metavar="SEC",
                    help=f"fade the AUDIO out over SEC seconds at the end of "
                         f"each clip, so the sound settles instead of cutting "
                         f"dead (default {CLIP_FADE:g}; 0 turns it off). The "
                         f"picture is untouched and no clip gets longer — the "
                         f"fade happens inside the clip's existing length.")
    ap.add_argument("--cut-fade", type=float, default=CUT_FADE, metavar="SEC",
                    dest="cut_fade",
                    help=f"fade the AUDIO out over SEC seconds leading into a "
                         f"cut, so the sound eases down instead of jumping "
                         f"(default {CUT_FADE:g}; 0 turns it off). Inside the "
                         f"footage that survives — nothing gets longer.")
    ap.add_argument("--timecode", action="store_true",
                    help="burn the ORIGINAL clip time into the corner of a "
                         "preview. The number on screen is the number to type "
                         "into the sheet, so scrubbing a preview never needs "
                         "converting back through cuts and speed spans. "
                         "Costs one re-encode — pair it with --draft.")
    ap.add_argument("--play", action="store_true",
                    help="open the finished file in VLC when the build "
                         "succeeds — the preview for --clip, otherwise the "
                         "review copy. Nothing opens if the build fails.")
    ap.add_argument("--draft", action="store_true",
                    help="re-encode edited clips fast and ugly "
                         f"(-preset {DRAFT_PRESET} -crf {DRAFT_CRF} instead of "
                         f"-preset {PRESET} -crf {CRF}). Several times quicker "
                         "while you are checking timings; the picture is "
                         "blocky and it is not for anything you keep. Draft "
                         "and final clips are cached separately, so switching "
                         "back re-encodes properly.")
    ap.add_argument("--no-check", action="store_true",
                    help="build even if the sheet fails validation. The check "
                         "runs first by default and stops the build on errors.")
    ap.add_argument("--cards", choices=("none", "leading", "all"),
                    default="leading",
                    help="which cards a --clip preview includes. 'leading' "
                         "(default) keeps only a folding title card running "
                         "into a selected clip; 'all' keeps standalone cards "
                         "too, matching the finished video; 'none' drops them "
                         "so preview times equal the clip's own times. "
                         "Ignored for a full build, which always has them.")
    ap.add_argument("--subs-only", action="store_true",
                    help="only regenerate the annotation track; skip "
                         "reassembling the video. Fast, for timing work.")
    ap.add_argument("--clip", metavar="N",
                    help="preview only these clips, e.g. 3, or 3,7, or 3-5. "
                         "Includes any title card that leads into the first "
                         "one. Writes preview.mkv and leaves master.mp4 and "
                         "the chapter files untouched.")
    ap.add_argument("--speed", type=float, default=4.0, metavar="N",
                    help="default rate for spans that say speed: true "
                         "(default 4). A span may state its own, e.g. 4x. "
                         "Changing this re-encodes only the affected clips.")
    ap.add_argument("--no-mkv", action="store_true",
                    help="skip building the .mkv review copy")
    ap.add_argument("--youtube", action="store_true",
                    help="also burn subtitles into a .mp4 for upload "
                         "(full re-encode, slow)")
    a = ap.parse_args()

    only = None
    if a.clip:
        only = set()
        for part in a.clip.replace(" ", "").split(","):
            if not part: continue
            if "-" in part:
                lo, _, hi = part.partition("-")
                try: only.update(range(int(lo), int(hi) + 1))
                except ValueError: die(f"bad --clip range: {part!r}")
            else:
                try: only.add(int(part))
                except ValueError: die(f"bad --clip value: {part!r}")
        if not only: die("--clip selected nothing")

    OUT_VIDEO = out("preview.mp4") if only else MASTER
    OUT_ASS   = out("preview.ass" if only else "annotations.ass")
    OUT_MKV   = out("preview.mkv" if only else "liturgy_training.mkv")

    os.makedirs(OUT, exist_ok=True)

    if a.sheet is None:
        a.sheet = default_sheet()
    if not os.path.exists(a.sheet):
        die(f"not found: {a.sheet} — expected the {SHEET_DIR}/ directory")

    if a.draft:
        CRF, PRESET = DRAFT_CRF, DRAFT_PRESET
        print(f"Draft mode: -preset {PRESET} -crf {CRF}. "
              f"Fast and blocky — not for anything you keep.")

    # Validate before spending anything on ffmpeg.
    import check_sheet
    sheet_errors, sheet_warnings, sheet_summary = check_sheet.validate(a.sheet)
    if sheet_errors or sheet_warnings:
        check_sheet.report(sheet_errors, sheet_warnings, sheet_summary)
        print()
    if sheet_errors:
        if a.no_check:
            print(f"{len(sheet_errors)} error(s) in {a.sheet} — "
                  f"building anyway because --no-check was given.\n")
        else:
            die(f"{len(sheet_errors)} error(s) in {a.sheet} — nothing built. "
                f"Fix them, or pass --no-check to build regardless.")
    if not os.path.isdir(WORK): die(f"{WORK}/ not found — run normalize_and_join.sh first")

    clips = sorted(f for f in os.listdir(WORK)
                   if re.fullmatch(r"\d{3}\.mp4", f))
    if not clips: die(f"no normalized clips in {WORK}/")
    n_clips = len(clips)

    cards = defaultdict(list)       # clip -> cards played BEFORE it
    cards_after = defaultdict(list)  # clip -> cards played AFTER it
    edits = defaultdict(list)      # clip -> [(start, dur, factor|None)]
    labels_for = {}                # (clip, start) -> custom skip label
    skips = set()
    joined = set()          # clips that continue the previous one
    chapter_titles = {}
    thumbs = {}            # clip -> poster moment, in ORIGINAL clip time
    anns = defaultdict(list)
    last_end = {}          # clip -> end of the most recent row, for "C"
    warnings = []
    seen_roles = []
    for ln, row in read_sheet(a.sheet):
        typ = row.get("type", "").strip().lower() or "annotation"
        n = clip_num(row.get("clip", ""))
        text = row.get("text", "").strip()
        if typ == "join":
            if n: joined.add(n)
            continue

        if typ == "skip":
            if n: skips.add(n)
            continue

        if typ in ("cut", "speed"):
            if n is None or not (1 <= n <= n_clips):
                warnings.append(f"{ln}: {typ} on unknown clip "
                                f"{row.get('clip','')!r} — skipped")
                continue
            try:
                est = parse_time(row.get("start", ""))
                een = parse_time(get_dur(row))
            except ValueError as e:
                warnings.append(f"{ln}: {e} — skipped"); continue
            if est is None or een is None:
                warnings.append(f"{ln}: {typ} needs a start and an "
                                f"end time — skipped")
                continue
            if een <= est:
                warnings.append(f"{ln}: {typ} end ({een:g}) must be "
                                f"after start ({est:g}) — skipped")
                continue
            edur = een - est
            if typ == "cut":
                factor = None
            else:
                factor = row.get("_rate") or a.speed
                if factor <= 0:
                    warnings.append(f"{ln}: --speed must be positive "
                                    f"— skipped")
                    continue
                srole = row.get("role", "").strip().upper()
                if srole and srole not in seen_roles: seen_roles.append(srole)
                if text: labels_for[(n, est)] = (srole, text)
            edits[n].append((est, edur, factor,
                             row.get("_audio") or ("mute", AUDIO_HOLD)))
            continue

        if typ == "chapter":
            if n and text:
                chapter_titles[n] = md_plain(" ".join(split_lines(text)))
            continue

        if typ == "thumbnail":
            if n:
                try:
                    thumbs[n] = parse_time(row.get("start", ""))
                except ValueError as e:
                    warnings.append(f"{ln}: thumbnail — {e} — ignored")
            continue

        if typ in ("card", "title"):
            if n is None: n = 0
            raw_cd = ""
            for key in ("dur", "duration", "length", "end"):
                if row.get(key, "").strip():
                    raw_cd = row[key].strip(); break
            try: dur = parse_time(raw_cd) or CARD_DUR
            except ValueError: dur = CARD_DUR
            img = (row.get("image", "") or "").strip() or None
            if not text and not img:
                warnings.append(f"{ln}: card with no text or image — skipped")
                continue
            bucket = cards_after if row.get("_after") else cards
            bucket[n].append((dur, text, img, typ == "title",
                              (row.get("_chapter") or "").strip()))
            continue

        # annotation
        if not text: continue
        if n is None or not (1 <= n <= n_clips):
            warnings.append(f"{ln}: unknown clip {row.get('clip','')!r} — skipped")
            continue
        raw_start = (row.get("start", "") or "").strip()
        raw_dur = ""
        for key in ("dur", "duration", "length", "end"):
            if row.get(key, "").strip():
                raw_dur = row[key].strip(); break

        try:
            if raw_start[:1].upper() == "C":
                # continue from the previous annotation in this clip
                gap = CONT_GAP
                tail = raw_start[1:].strip().lstrip("+").strip()
                if tail:
                    gap = float(tail)
                prev = last_end.get(n)
                st = 0.0 if prev is None else prev + gap
            else:
                st = parse_time(raw_start)
            dur = parse_time(raw_dur)
        except ValueError as e:
            warnings.append(f"{ln}: {e} — skipped"); continue
        if st is None:
            warnings.append(f"{ln}: no start time — skipped ({text[:40]})")
            continue
        if dur is None: dur = DEFAULT_DUR
        if dur <= 0:
            warnings.append(f"{ln}: duration must be positive — skipped"); continue
        en = st + dur
        last_end[n] = en
        role = row.get("role", "").strip().upper()
        if role and role not in seen_roles: seen_roles.append(role)
        anns[n].append((st, en, role, text))

    # ---------------- apply cuts and speed changes ----------------
    seg_map = {}          # clip -> segment list, for remapping annotations
    skip_spans = []       # (clip, orig_start, orig_end, label)
    edited_name = {}      # clip -> filename to use in the sequence
    order = [i for i in range(1, n_clips + 1) if i not in skips]
    no_fade = set()
    for k, i in enumerate(order):
        if i in joined and k > 0:
            no_fade.add(order[k - 1])

    wanted = sorted(set(edits) | (set(only) if (a.fade > 0.05 and only)
                                  else set(range(1, n_clips + 1))
                                  if a.fade > 0.05 else set()))
    for n in wanted:
        elist = edits.get(n, [])
        if only and n not in only:
            continue          # a preview must not pay to edit clips it drops
        if n in skips:
            continue
        src = os.path.join(WORK, f"{n:03d}.mp4")
        if not os.path.exists(src):
            warnings.append(f"clip {n:02d}: no normalized file, edits ignored")
            continue
        dur0 = probe_dur(src)
        elist = sorted(elist)
        # reject overlapping edits, which would corrupt the mapping
        clean, last_end = [], 0.0
        for st, d, f, mu in elist:
            if st < last_end:
                warnings.append(f"clip {n:02d}: edit at {st:.1f}s overlaps the "
                                f"previous one — skipped")
                continue
            if st >= dur0:
                warnings.append(f"clip {n:02d}: edit at {st:.1f}s is past the "
                                f"end of the clip ({dur0:.1f}s) — skipped")
                continue
            clean.append((st, d, f, mu)); last_end = st + d
        if not clean and a.fade <= 0.05:
            continue
        segs = edit_segments(dur0, clean)
        seg_map[n] = segs
        for st, d, f, mu in clean:
            if f is not None:
                srole, lbl = labels_for.get((n, st), ("", SKIP_LABEL))
                if lbl.strip() not in ("-", "none", "None"):
                    skip_spans.append((n, st, st + d, srole, lbl))
        dst = os.path.join(WORK, f"{n:03d}_edit.mp4")
        if not a.subs_only:
            build_edited_clip(src, dst, segs,
                              fade=0.0 if n in no_fade else a.fade,
                              cut_fade=a.cut_fade)
        edited_name[n] = f"{n:03d}_edit.mp4"
        newdur = sum((b - aa) / f for aa, b, f, _ in segs)
        cuts = sum(1 for st, d, f, _ in clean if f is None)
        sps = len(clean) - cuts
        bits = []
        if cuts: bits.append(f"{cuts} cut{'s' if cuts>1 else ''}")
        if sps: bits.append(f"{sps} speed change{'s' if sps>1 else ''}")
        if bits:
            print(f"  clip {n:02d}: {', '.join(bits)} — "
                  f"{dur0:.1f}s becomes {newdur:.1f}s")

    # ---------------- assemble the sequence ----------------
    sequence = []          # (path_in_work, label, is_card, clip_no, lead)

    def add_cards(bucket, i, tag):
        """Cards belong to the clip they are written under, so a skipped clip
        takes only its own cards with it — never the one introducing the clip
        after it.

        --subs-only must still put cards in the sequence: they occupy real
        time in the finished video, so leaving them out drifts every later
        annotation, chapter mark and boundary earlier by the total card
        length. make_card() already skips an unchanged card, so this costs
        nothing when only the text has moved."""
        for j, (dur, text, img, lead, ctitle) in enumerate(bucket.get(i, [])):
            nm = f"{i:03d}_{tag}{j:02d}.mp4"
            make_card(os.path.join(WORK, nm), text, dur, img)
            lines = [md_plain(l) for l in split_lines(text)]
            sequence.append((nm, ctitle or (lines[0] if lines else "Card"),
                             True, i, lead))

    add_cards(cards, 0, "card")          # a `clip: 0` block means the very front

    for i in range(1, n_clips + 1):
        if i in skips: continue
        add_cards(cards, i, "card")
        sequence.append((edited_name.get(i, f"{i:03d}.mp4"),
                         f"Clip {i:02d}", False, i, False))
        add_cards(cards_after, i, "endcard")

    if only:
        kept = []
        for i, entry in enumerate(sequence):
            nm, label, is_card, cno, lead = entry
            if not is_card:
                if cno in only: kept.append(entry)
                continue
            if a.cards == "none":
                continue          # preview times then equal the clip's own
            # the clip this card runs into; cno is the one it follows
            j = i + 1
            while j < len(sequence) and sequence[j][2]: j += 1
            nxt = sequence[j][3] if j < len(sequence) else None
            if a.cards == "all":
                if nxt in only or cno in only: kept.append(entry)
            elif lead and nxt in only:
                kept.append(entry)
        if not kept:
            die(f"--clip {a.clip} matched no clips "
                f"(there are {n_clips}; check for a 'skip' row)")
        sequence = kept
        print(f"Preview: clips {', '.join(str(c) for c in sorted(only))} "
              f"({len(sequence)} segment(s))")

    if a.subs_only and os.path.exists(out("boundaries.tsv")):
        pass  # reuse existing boundaries below
    else:
        listfile = os.path.join(WORK, "concat.txt")
        with open(listfile, "w") as f:
            for nm, *_ in sequence:
                f.write(f"file '{nm}'\n")
        print(f"Assembling {len(sequence)} segments -> {OUT_VIDEO}")
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-nostdin",
             "-f", "concat", "-safe", "0", "-i", listfile,
             "-c", "copy", "-movflags", "+faststart", OUT_VIDEO])

    # ---------------- boundaries ----------------
    starts, t = {}, 0.0
    rows_out = []
    for nm, label, is_card, cno, lead in sequence:
        d = probe_dur(os.path.join(WORK, nm))
        if d is None: die(f"cannot probe {nm}")
        if not is_card: starts[cno] = t
        rows_out.append((t, nm, label, is_card, cno, d, lead))
        t += d
    total = t

    if a.timecode and not a.subs_only:
        burn_timecode(OUT_VIDEO, rows_out, seg_map)

    with open(out("preview_boundaries.tsv" if only else "boundaries.tsv"), "w") as f:
        for st, nm, label, is_card, cno, d, lead in rows_out:
            f.write(f"{ass_time(st)}\t{nm}\t{label}\n")
        f.write(f"{ass_time(total)}\t[END]\t\n")

    # ---------------- thumbnails ----------------
    # `thumbnail:` names a moment in the ORIGINAL clip, like every other time in
    # the sheet, but the poster is grabbed from master.mp4 — so map it through
    # this clip's own edits and add the clip's offset in the finished video.
    # make_document.py cannot work this out for itself: all it ever sees is
    # chapters.txt, which knows nothing about cuts.
    thumb_rows = []
    for cn in sorted(thumbs):
        if cn not in starts:
            if not only:
                warnings.append(f"clip {cn:02d}: thumbnail on a clip that is "
                                f"not in the video — ignored")
            continue
        t0 = thumbs[cn]
        segs = seg_map.get(cn)
        mapped = time_map(t0, segs) if segs else t0
        if mapped is None:
            warnings.append(f"clip {cn:02d}: thumbnail at {t0:g}s falls inside "
                            f"a cut, so that frame is not in the video "
                            f"— ignored")
            continue
        thumb_rows.append((starts[cn] + mapped, cn, t0))

    with open(out("preview_thumbnails.tsv" if only else "thumbnails.tsv"), "w") as f:
        f.write("master_s\tclip\torig_s\n")
        for ms, cn, t0 in thumb_rows:
            f.write(f"{ms:.3f}\t{cn}\t{t0:.3f}\n")

    # ---------------- annotations ----------------
    events = []
    skip_events = []
    for n, items in anns.items():
        if n in skips:
            warnings.append(f"clip {n:02d}: skipped, so its annotations were dropped")
            continue
        base = starts.get(n)
        if base is None: continue
        segs = seg_map.get(n)
        if segs:
            remapped = []
            for st, en, role, text in items:
                m_st = time_map(st, segs)
                if m_st is None:
                    warnings.append(f"clip {n:02d}: annotation at {st:.1f}s "
                                    f"falls inside a cut — dropped "
                                    f"({text[:32]})")
                    continue
                for sa, sb, sf, _ in segs:
                    if sa <= st < sb and abs(sf - 1.0) > 1e-6:
                        warnings.append(
                            f"clip {n:02d}: annotation at {st:.1f}s is inside "
                            f"a {sf:g}x section, so it will flash by and may "
                            f"collide with the skip label ({text[:28]})")
                        break
                m_en = time_map(en, segs)
                if m_en is None or m_en <= m_st:
                    m_en = m_st + 1.0
                remapped.append((m_st, m_en, role, text))
            items = remapped
        items.sort()
        for i, (st, en, role, text) in enumerate(items):
            if i + 1 < len(items) and items[i+1][0] < en:
                warnings.append(f"clip {n:02d}: annotations overlap near {st:.0f}s")
            body = "\\N".join(md_inline(ln) if ln else ""
                              for ln in split_lines(text, keep_blanks=True))
            events.append((base + st, base + en,
                           role_prefix(role, seen_roles) + body))
    # label each sped-up span. Same screen position as the ordinary
    # annotations, distinguished by the italic Skip style.
    for n, o_st, o_en, srole, lbl in skip_spans:
        base = starts.get(n)
        segs = seg_map.get(n)
        if base is None or not segs: continue
        m_st = time_map(o_st, segs)
        m_en = time_map(min(o_en, segs[-1][1]), segs)
        if m_st is None or m_en is None or m_en <= m_st: continue
        skip_events.append((base + m_st, base + m_en,
                            role_prefix(srole, seen_roles)
                            + lbl.replace("{", "(").replace("}", ")")))

    events.sort()
    skip_events.sort()

    with open(OUT_ASS, "w", encoding="utf-8") as f:
        f.write(f"""[Script Info]
Title: Hierarchical Divine Liturgy - Deacon Training
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Ann,{FONT},{FONTSIZE},{TEXT_COLOUR},{TEXT_COLOUR},&H00000000,&HB4000000,0,0,0,0,100,100,0,0,3,14,0,2,90,90,54,1
Style: Skip,{FONT},{FONTSIZE},{TEXT_COLOUR},{TEXT_COLOUR},&H00000000,&HB4000000,0,1,0,0,100,100,0,0,3,14,0,2,90,90,54,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""")
        for st, en, body in events:
            f.write(f"Dialogue: 0,{ass_time(st)},{ass_time(en)},Ann,,0,0,0,,{body}\n")
        for st, en, body in skip_events:
            f.write(f"Dialogue: 1,{ass_time(st)},{ass_time(en)},Skip,,0,0,0,,{body}\n")

    # ---------------- chapters ----------------
    # A preview gets no media title. VLC paints that tag over the picture at
    # playback start and after every seek, landing on top of the annotations
    # you are trying to read. The finished file keeps it — it belongs there,
    # and VLC can be told not to draw it (Preferences -> Video -> uncheck
    # "Show media title on video start", or --no-video-title-show).
    meta = [";FFMETADATA1"]
    if not only:
        meta.append("title=Hierarchical Divine Liturgy - Deacon Training")
    meta += ["date=2026-06-20", ""]
    yt = []
    chap_spans = []
    pending = None          # start time inherited from a leading title card
    for idx, (st, nm, label, is_card, cno, d, lead) in enumerate(rows_out):
        if is_card and lead and idx + 1 < len(rows_out):
            if pending is None: pending = st
            continue                       # folded into the next chapter
        if not is_card and cno in joined:
            continue                      # continues the previous chapter
        title = chapter_titles.get(cno) if not is_card else (label or "Card")
        if title is None: title = label
        if pending is not None:
            st = pending; pending = None
        j = idx + 1
        while j < len(rows_out) and ((rows_out[j][3] and rows_out[j][6])
                                     or (not rows_out[j][3]
                                         and rows_out[j][4] in joined)):
            j += 1
        en = rows_out[j][0] if j < len(rows_out) else total
        meta += ["[CHAPTER]", "TIMEBASE=1/1000",
                 f"START={int(st*1000)}", f"END={int(en*1000)}",
                 f"title={title}", ""]
        h, m, s = int(st//3600), int((st % 3600)//60), int(st % 60)
        yt.append((f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}") + " " + title)
        chap_spans.append((st, en, title))
    # YouTube rejects a whole chapter list if any chapter is under 10s,
    # if the first is not 00:00, or if there are fewer than three.
    yt_problems = []
    if yt and not yt[0].startswith("00:00"):
        yt_problems.append("first chapter must start at 00:00")
    if not only and len(yt) < 3:
        yt_problems.append(f"YouTube needs at least 3 chapters, this has {len(yt)}")
    for k in (range(len(chap_spans)) if not only else []):
        st_k, en_k, title_k = chap_spans[k]
        if en_k - st_k < 10:
            yt_problems.append(
                f"{ass_time(st_k)} \"{title_k[:40]}\" is only {en_k-st_k:.0f}s "
                f"(YouTube needs 10s)")

    if only:
        open(out("preview_chapters.txt"), "w").write("\n".join(meta))
    else:
        open(out("chapters.txt"), "w").write("\n".join(meta))
        open(out("youtube_chapters.txt"), "w").write("\n".join(yt) + "\n")

    # ---------------- mux the review copy ----------------
    mkv = OUT_MKV
    if not a.no_mkv:
        print(f"Muxing {mkv} (subtitles + chapters, no re-encode)")
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-nostdin",
             "-i", OUT_VIDEO, "-i", OUT_ASS,
             "-i", out("preview_chapters.txt" if only else "chapters.txt"),
             "-map", "0:v", "-map", "0:a", "-map", "1",
             "-map_metadata", "2", "-map_chapters", "2",
             "-c", "copy",
             "-disposition:s:0", "default",
             "-metadata:s:s:0", "language=eng",
             "-metadata:s:s:0", "title=Annotations",
             mkv])

    if a.youtube and only:
        print("(--youtube ignored while previewing)")
    elif a.youtube:
        yt_out = out("youtube.mp4")
        print(f"Burning subtitles into {yt_out} — this re-encodes, "
              f"expect a long run")
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-nostdin",
             "-i", MASTER, "-vf", f"ass={OUT_ASS}",
             "-c:v", "libx264", "-preset", PRESET, "-crf", str(CRF),
             "-pix_fmt", "yuv420p", "-c:a", "copy",
             "-movflags", "+faststart", yt_out])

    # ---------------- report ----------------
    n_cards = sum(1 for r in rows_out if r[3])
    print(f"\nSegments: {len(rows_out)}  ({len(rows_out)-n_cards} clips, {n_cards} cards)")
    if skips: print(f"Skipped clips: {', '.join(f'{s:02d}' for s in sorted(skips))}")
    print(f"Annotations: {len(events)}"
          + (f"  (+{len(skip_events)} skip labels)" if skip_events else ""))
    if seen_roles: print("Roles: " + ", ".join(seen_roles))
    print(f"Total length: {ass_time(total)}")
    if warnings:
        print(f"\n{len(warnings)} warning(s):")
        for w in warnings[:40]: print("  " + w)
        if len(warnings) > 40: print(f"  ... and {len(warnings)-40} more")
    if yt_problems:
        print(f"\nYouTube chapter warnings ({len(yt_problems)}):")
        for p in yt_problems[:12]: print("  " + p)
        if len(yt_problems) > 12: print(f"  ... and {len(yt_problems)-12} more")
        print("  (YouTube silently drops ALL chapters if any rule is broken.)")
    print()
    if only:
        print(f"Preview:      {mkv}")
        print(f"  open -a VLC {mkv}")
        print("  master.mp4 and the chapter files were not touched.")
    elif not a.no_mkv:
        print(f"Review copy:  {mkv}   (chapters + annotations built in)")
        print(f"  open -a VLC {mkv}")
        print("  If the text does not show, turn on the subtitle track (press v).")
    if a.youtube:
        print("YouTube file: youtube.mp4   (subtitles burned in)")
        print("  Paste youtube_chapters.txt into the video description.")
    elif not only:
        print("For YouTube, re-run with --youtube to burn the text in.")

    if a.play:
        # Whatever this run actually produced, so an old file is never opened
        # by mistake. VLC because IINA drops the subtitle track when you use
        # its chapter panel.
        target = mkv if not a.no_mkv else OUT_VIDEO
        if not os.path.exists(target):
            print(f"\n--play: nothing to open, {target} was not built.")
        else:
            print(f"\nOpening {target} in VLC. "
                  f"Press v if the text does not show.")
            subprocess.run(["open", "-a", "VLC", target], check=False)


if __name__ == "__main__":
    main()
