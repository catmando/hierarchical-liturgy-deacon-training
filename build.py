#!/usr/bin/env python3
"""
build.py — build the whole video from one CSV.

Reads a single edit sheet and produces:
    master.mp4          the assembled video (cards inserted, clips skipped)
    annotations.ass     the annotation track
    chapters.txt        FFMETADATA chapter marks
    youtube_chapters.txt
    boundaries.tsv      for reference

USAGE
    python3 build.py                    # full build
    python3 build.py --subs-only        # only rebuild annotations.ass
                                        # (fast; use while timing text)
    python3 build.py --csv edit.csv
    python3 build.py --speed 6          # tune the speed-up rate
    python3 build.py --clip 3           # preview clip 3 on its own
    python3 build.py --clip 3-5         # preview a range

REQUIRES
    _normalized/001.mp4 ... from normalize_and_join.sh
    ffmpeg, ffprobe

------------------------------------------------------------------
THE CSV
------------------------------------------------------------------
Header row must include: type, clip, start, dur, role, text
(dur may also be called duration or length. A column named end is
accepted and treated as a duration.)
An optional  image  column may hold a path to a PNG for card rows.

  type          what the row does
  ------------  --------------------------------------------------
  annotation    text overlaid on the video. This is the default,
  (or blank)    so existing annotation rows keep working unchanged.
                start is seconds from THAT CLIP's beginning.
                dur    is how long it stays up, in seconds
                       (default 4). It is a LENGTH, not an end time.
                Put C in start to continue 0.2s after the previous
                annotation on that clip, or at the clip's start if
                it is the first. C+1.5 uses a 1.5s gap instead.
                A Return inside the cell makes a second line.

  card          a standalone card inserted AFTER the given clip
                number. It becomes its OWN chapter, titled with its
                first line. Use this for things like
                "Homily -- not shown".
                Use clip = 0 for a card before everything.
                dur   = card duration in seconds (default 6).
                text  = card text. Break lines either by typing a
                        Return inside the cell (Option-Return in
                        Numbers, Alt-Enter in Excel) or with ||.
                image = optional PNG to use instead of drawn text.
                Several cards after the same clip keep CSV order.

  title         same as card, but it LEADS INTO the next segment's
                chapter instead of forming its own. The chapter
                starts at the card, so a viewer jumping to that
                chapter sees the card first, then the footage.
                Use this for section-title cards.

  chapter       renames the chapter that starts at that clip.
                text = the chapter title.

  skip          leaves that clip out of the master entirely.

  cut           removes a section from inside a clip.
                For cut and speed rows the 4th column is an END TIME,
                not a duration -- you write "from X to Y".
                e.g.  cut,19,1:00,2:00   removes 1:00-2:00 of clip 19

  speed         speeds a section up instead of removing it.
                start / end as above.
                e.g.  speed,19,0:22,0:42,,Skipping the long censing
                      plays 22s-42s faster, and labels it

                The rate is set once for the whole video with --speed
                (default 4), not per row, so you can tune the overall
                feel without editing the sheet.

                Audio in a sped section is MUTED -- sped-up chant is
                unpleasant -- and a label sits in the usual annotation
                position for the whole span, in italics, so the viewer
                knows time is being skipped. Put your wording in the
                TEXT column, e.g.

                  speed,3,1:10,3:40,,...Deacon 1 continues the entrance
                  prayers...

                Leave the text blank for "skipping ahead", or write "-"
                for no label. Ordinary annotations inside a sped span
                are warned about, since they flash past and would sit
                on top of the skip label.

  IMPORTANT -- everything is written against the ORIGINAL clip.
  Annotation times, cut times and speed times are all measured on the
  untouched footage, and the script works out where they land after the
  edits. So in a 3:00 clip you can write:

        cut,7,1:00,2:00           remove the second minute
        annotation,7,2:30,4,D1,   text at the original 2:30
        cut,7,2:45,2:55           remove another ten seconds

  and the annotation ends up at 1:30 in the finished clip, with the
  second cut landing at 1:45. You never recalculate anything: add,
  remove or resize an edit and every other row follows automatically.

  Annotations that fall inside a cut are dropped, with a warning.
  Only clips carrying edits are re-encoded; the rest are untouched.

  #             ignored, use for comments.

EXAMPLE
  type,clip,start,dur,role,text
  title,0,,8,,Hierarchical Divine Liturgy||Deacon Training
  annotation,1,1,4,D1,Deacon greets last: censer and trikirion
  annotation,1,C,5,D1,Bless master the holy incense
  annotation,1,C+2,4,,Censer must already be lit
  chapter,7,,,,It is Time for the Lord to Act
  card,20,,6,,Homily||not shown
  skip,13,,,,
"""

import argparse, csv, hashlib, os, re, subprocess, sys
from collections import defaultdict

WORK = "_normalized"
MASTER = "master.mp4"
W, H, FPS, CRF, PRESET = 1920, 1080, 30, 18, "slow"

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


def split_lines(v):
    return [ln.strip() for ln in norm_lines(v).split("\n") if ln.strip()]


def get_dur(row):
    """Duration column. Accepts dur, duration, or legacy end."""
    for k in ("dur", "duration", "length", "end"):
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
    """Turn a clip duration + edit list into (start, end, factor) spans.
    factor 1.0 = untouched, >1 = sped up. Cut spans are omitted."""
    segs, prev = [], 0.0
    for st, d, factor in sorted(edits):
        st = max(st, 0.0); en = min(st + d, dur)
        if en <= prev: continue
        if st > prev: segs.append((prev, st, 1.0))
        if factor is not None: segs.append((st, en, float(factor)))
        prev = en
    if prev < dur: segs.append((prev, dur, 1.0))
    return [sg for sg in segs if sg[1] - sg[0] > 0.01]


def time_map(t, segs):
    """Map a time in the ORIGINAL clip to its position in the edited clip.
    Returns None if t falls inside a cut."""
    out = 0.0
    for a, b, f in segs:
        if t < a: return None          # inside a removed span
        if t <= b: return out + (t - a) / f
        out += (b - a) / f
    return out


def build_edited_clip(src, dst, segs):
    """Re-encode one clip with cuts and speed changes applied."""
    spec = hashlib.md5((src + repr([(round(a,3), round(b,3), round(f,4))
                                    for a, b, f in segs])).encode()).hexdigest()
    sidecar = dst + ".spec"
    if os.path.exists(dst) and os.path.exists(sidecar):
        if open(sidecar).read().strip() == spec:
            return False
    parts, labels = [], []
    for i, (a, b, f) in enumerate(segs):
        parts.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},"
                     f"setpts=(PTS-STARTPTS)/{f:.6f}[v{i}]")
        # atempo keeps audio the same length as the sped video, and
        # volume=0 silences it -- sped-up speech and chant is unpleasant.
        chain = ["asetpts=PTS-STARTPTS"] + atempo_chain(f)
        if abs(f - 1.0) > 1e-6:
            chain.append("volume=0")
        ach = ",".join(chain)
        parts.append(f"[0:a]atrim=start={a:.3f}:end={b:.3f},{ach}[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    fc = ";".join(parts) + ";" + "".join(labels) + \
         f"concat=n={len(segs)}:v=1:a=1[v][a]"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-nostdin",
         "-i", src, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
         "-r", str(FPS), "-fps_mode", "cfr",
         "-c:v", "libx264", "-preset", PRESET, "-crf", str(CRF),
         "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", dst])
    open(sidecar, "w").write(spec)
    return True


def clip_num(raw):
    raw = (raw or "").strip()
    if not raw: return None
    m = re.match(r"\s*(\d+)", raw)
    return int(m.group(1)) if m else None


# ----------------------------------------------------------------------

def make_card(path, text, dur, image=None):
    """Render a card, skipping if an identical one already exists."""
    spec = hashlib.md5(f"{text}|{dur}|{image}|{W}x{H}|{FPS}".encode()).hexdigest()
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
        font = find_font()
        if not font: die("no usable font found for card text")
        tmp = path + ".txt"
        with open(tmp, "w") as f:
            f.write("\n".join(split_lines(text)))
        vf = (f"drawtext=fontfile='{font}':textfile='{tmp}':fontcolor=white:"
              f"fontsize=64:line_spacing=28:x=(w-text_w)/2:y=(h-text_h)/2,"
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
    if not image and os.path.exists(path + ".txt"):
        os.remove(path + ".txt")
    return True


# ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        prog="build.py",
        description="Build the training video from one CSV edit sheet.",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default="annotations.csv", metavar="FILE",
                    help="the edit sheet to read (default annotations.csv)")
    ap.add_argument("--subs-only", action="store_true",
                    help="only regenerate the annotation track; skip "
                         "reassembling the video. Fast, for timing work.")
    ap.add_argument("--clip", metavar="N",
                    help="preview only these clips, e.g. 3, or 3,7, or 3-5. "
                         "Includes any title card that leads into the first "
                         "one. Writes preview.mkv and leaves master.mp4 and "
                         "the chapter files untouched.")
    ap.add_argument("--speed", type=float, default=4.0, metavar="N",
                    help="playback rate for every 'speed' row (default 4). "
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

    OUT_VIDEO = "preview.mp4" if only else MASTER
    OUT_ASS   = "preview.ass" if only else "annotations.ass"
    OUT_MKV   = "preview.mkv" if only else "liturgy_training.mkv"

    if not os.path.exists(a.csv): die(f"not found: {a.csv}")
    if not os.path.isdir(WORK): die(f"{WORK}/ not found — run normalize_and_join.sh first")

    clips = sorted(f for f in os.listdir(WORK)
                   if re.fullmatch(r"\d{3}\.mp4", f))
    if not clips: die(f"no normalized clips in {WORK}/")
    n_clips = len(clips)

    cards = defaultdict(list)      # after-clip -> [(dur, text, image)]
    edits = defaultdict(list)      # clip -> [(start, dur, factor|None)]
    labels_for = {}                # (clip, start) -> custom skip label
    skips = set()
    chapter_titles = {}
    anns = defaultdict(list)
    last_end = {}          # clip -> end of the most recent row, for "C"
    warnings = []
    seen_roles = []
    inherited = []

    last_clip_seen = None
    with open(a.csv, newline="", encoding="utf-8-sig") as f:
        for ln, raw in enumerate(csv.DictReader(f), start=2):
            row = {(k or "").strip().lower(): (v or "") for k, v in raw.items()}
            typ = row.get("type", "").strip().lower() or "annotation"
            if typ.startswith("#"): continue
            n = clip_num(row.get("clip", ""))
            text = row.get("text", "").strip()
            if n is not None:
                last_clip_seen = n
            elif typ == "annotation" and text and last_clip_seen is not None:
                # Spreadsheets sometimes blank a clip column on export.
                # Inherit from the last row that did carry a clip number.
                n = last_clip_seen
                inherited.append(ln)

            if typ == "skip":
                if n: skips.add(n)
                continue

            if typ in ("cut", "speed"):
                if n is None or not (1 <= n <= n_clips):
                    warnings.append(f"line {ln}: {typ} on unknown clip "
                                    f"{row.get('clip','')!r} — skipped")
                    continue
                try:
                    est = parse_time(row.get("start", ""))
                    een = parse_time(get_dur(row))
                except ValueError as e:
                    warnings.append(f"line {ln}: {e} — skipped"); continue
                if est is None or een is None:
                    warnings.append(f"line {ln}: {typ} needs a start and an "
                                    f"end time — skipped")
                    continue
                if een <= est:
                    warnings.append(f"line {ln}: {typ} end ({een:g}) must be "
                                    f"after start ({est:g}) — skipped")
                    continue
                edur = een - est
                if typ == "cut":
                    factor = None
                else:
                    factor = a.speed
                    if factor <= 0:
                        warnings.append(f"line {ln}: --speed must be positive "
                                        f"— skipped")
                        continue
                    if text: labels_for[(n, est)] = text
                edits[n].append((est, edur, factor))
                continue

            if typ == "chapter":
                if n and text:
                    chapter_titles[n] = " ".join(split_lines(text))
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
                    warnings.append(f"line {ln}: card with no text or image — skipped")
                    continue
                cards[n].append((dur, text, img, typ == "title"))
                continue

            # annotation
            if not text: continue
            if n is None or not (1 <= n <= n_clips):
                warnings.append(f"line {ln}: unknown clip {row.get('clip','')!r} — skipped")
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
                warnings.append(f"line {ln}: {e} — skipped"); continue
            if st is None:
                warnings.append(f"line {ln}: no start time — skipped ({text[:40]})")
                continue
            if dur is None: dur = DEFAULT_DUR
            if dur <= 0:
                warnings.append(f"line {ln}: duration must be positive — skipped"); continue
            en = st + dur
            last_end[n] = en
            role = row.get("role", "").strip().upper()
            if role and role not in seen_roles: seen_roles.append(role)
            anns[n].append((st, en, role, text))

    # ---------------- apply cuts and speed changes ----------------
    seg_map = {}          # clip -> segment list, for remapping annotations
    skip_spans = []       # (clip, orig_start, orig_end, label)
    edited_name = {}      # clip -> filename to use in the sequence
    for n, elist in sorted(edits.items()):
        src = os.path.join(WORK, f"{n:03d}.mp4")
        if not os.path.exists(src):
            warnings.append(f"clip {n:02d}: no normalized file, edits ignored")
            continue
        dur0 = probe_dur(src)
        elist = sorted(elist)
        # reject overlapping edits, which would corrupt the mapping
        clean, last_end = [], 0.0
        for st, d, f in elist:
            if st < last_end:
                warnings.append(f"clip {n:02d}: edit at {st:.1f}s overlaps the "
                                f"previous one — skipped")
                continue
            if st >= dur0:
                warnings.append(f"clip {n:02d}: edit at {st:.1f}s is past the "
                                f"end of the clip ({dur0:.1f}s) — skipped")
                continue
            clean.append((st, d, f)); last_end = st + d
        if not clean: continue
        segs = edit_segments(dur0, clean)
        seg_map[n] = segs
        for st, d, f in clean:
            if f is not None:
                lbl = (labels_for.get((n, st)) or SKIP_LABEL)
                if lbl.strip() not in ("-", "none", "None"):
                    skip_spans.append((n, st, st + d, lbl))
        dst = os.path.join(WORK, f"{n:03d}_edit.mp4")
        if not a.subs_only:
            build_edited_clip(src, dst, segs)
        edited_name[n] = f"{n:03d}_edit.mp4"
        newdur = sum((b - aa) / f for aa, b, f in segs)
        cuts = sum(1 for st, d, f in clean if f is None)
        sps = len(clean) - cuts
        bits = []
        if cuts: bits.append(f"{cuts} cut{'s' if cuts>1 else ''}")
        if sps: bits.append(f"{sps} speed change{'s' if sps>1 else ''}")
        print(f"  clip {n:02d}: {', '.join(bits)} — "
              f"{dur0:.1f}s becomes {newdur:.1f}s")

    # ---------------- assemble the sequence ----------------
    sequence = []          # (path_in_work, label, is_card, clip_no)
    if not a.subs_only:
        for dur, text, img, lead in cards.get(0, []):
            nm = f"000_card{len(sequence):02d}.mp4"
            make_card(os.path.join(WORK, nm), text, dur, img)
            lines = split_lines(text)
            sequence.append((nm, lines[0] if lines else "Card", True, 0, lead))

    for i in range(1, n_clips + 1):
        if i in skips: continue
        sequence.append((edited_name.get(i, f"{i:03d}.mp4"),
                         f"Clip {i:02d}", False, i, False))
        if not a.subs_only:
            for j, (dur, text, img, lead) in enumerate(cards.get(i, [])):
                nm = f"{i:03d}_card{j:02d}.mp4"
                make_card(os.path.join(WORK, nm), text, dur, img)
                lines = split_lines(text)
                sequence.append((nm, lines[0] if lines else "Card", True, i, lead))

    if only:
        kept = []
        for i, entry in enumerate(sequence):
            nm, label, is_card, cno, lead = entry
            if not is_card:
                if cno in only: kept.append(entry)
                continue
            # a leading title card comes along if the clip it introduces
            # is in the selection
            j = i + 1
            while j < len(sequence) and sequence[j][2]: j += 1
            if lead and j < len(sequence) and sequence[j][3] in only:
                kept.append(entry)
        if not kept:
            die(f"--clip {a.clip} matched no clips "
                f"(there are {n_clips}; check for a 'skip' row)")
        sequence = kept
        print(f"Preview: clips {', '.join(str(c) for c in sorted(only))} "
              f"({len(sequence)} segment(s))")

    if a.subs_only and os.path.exists("boundaries.tsv"):
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

    with open("preview_boundaries.tsv" if only else "boundaries.tsv", "w") as f:
        for st, nm, label, is_card, cno, d, lead in rows_out:
            f.write(f"{ass_time(st)}\t{nm}\t{label}\n")
        f.write(f"{ass_time(total)}\t[END]\t\n")

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
                for sa, sb, sf in segs:
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
            colour = ROLE_COLOURS.get(role)
            if role and colour is None:
                colour = FALLBACK[seen_roles.index(role) % len(FALLBACK)]
            body = text.replace("\\", "").replace("{", "(").replace("}", ")")
            body = "\\N".join(split_lines(body))
            if role:
                body = f"{{\\c{colour}\\b1}}{role}{{\\b0\\c{TEXT_COLOUR}}}  " + body
            events.append((base + st, base + en, body))
    # label each sped-up span, positioned at the top so it never collides
    # with the ordinary annotations along the bottom
    for n, o_st, o_en, lbl in skip_spans:
        base = starts.get(n)
        segs = seg_map.get(n)
        if base is None or not segs: continue
        m_st = time_map(o_st, segs)
        m_en = time_map(min(o_en, segs[-1][1]), segs)
        if m_st is None or m_en is None or m_en <= m_st: continue
        skip_events.append((base + m_st, base + m_en,
                            lbl.replace("{", "(").replace("}", ")")))

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
    meta = [";FFMETADATA1",
            "title=Hierarchical Divine Liturgy - Deacon Training",
            "date=2026-06-20", ""]
    yt = []
    chap_spans = []
    pending = None          # start time inherited from a leading title card
    for idx, (st, nm, label, is_card, cno, d, lead) in enumerate(rows_out):
        if is_card and lead and idx + 1 < len(rows_out):
            if pending is None: pending = st
            continue                       # folded into the next chapter
        title = chapter_titles.get(cno) if not is_card else (label or "Card")
        if title is None: title = label
        if pending is not None:
            st = pending; pending = None
        j = idx + 1
        while j < len(rows_out) and rows_out[j][3] and rows_out[j][6]:
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
        open("preview_chapters.txt", "w").write("\n".join(meta))
    else:
        open("chapters.txt", "w").write("\n".join(meta))
        open("youtube_chapters.txt", "w").write("\n".join(yt) + "\n")

    # ---------------- mux the review copy ----------------
    mkv = OUT_MKV
    if not a.no_mkv:
        print(f"Muxing {mkv} (subtitles + chapters, no re-encode)")
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-nostdin",
             "-i", OUT_VIDEO, "-i", OUT_ASS,
             "-i", "preview_chapters.txt" if only else "chapters.txt",
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
        yt_out = "youtube.mp4"
        print(f"Burning subtitles into {yt_out} — this re-encodes, "
              f"expect a long run")
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-nostdin",
             "-i", MASTER, "-vf", "ass=annotations.ass",
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
    if inherited:
        print(f"\nNote: {len(inherited)} annotation row(s) had a blank clip "
              f"column and inherited the clip above them.")
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


if __name__ == "__main__":
    main()
