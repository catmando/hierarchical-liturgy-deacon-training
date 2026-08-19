#!/usr/bin/env python3
"""
Build an .ass annotation track from annotations.csv + boundaries.tsv.

USAGE
    python3 make_subs.py

    python3 make_subs.py --csv annotations.csv \
                        --boundaries boundaries.tsv \
                        --out annotations.ass

WHAT IT EXPECTS

annotations.csv, with a header row containing at least:
    clip, start, end, role, text

  clip   the clip number (1, 01, or the full filename — all work)
  start  time RELATIVE TO THAT CLIP's beginning
  end    likewise. Leave blank for a default 4 seconds.
  role   D1 D2 SD AS B P R CH ... or blank. Unknown codes get a colour.
  text   the annotation. Keep to roughly 5-12 words.

  Times accept  M:SS  /  M:SS.s  /  H:MM:SS  /  plain seconds.

boundaries.tsv comes from normalize_and_join.sh or rebuild.sh.
Rerun this script after any rebuild and the timings follow automatically.
"""

import argparse, csv, os, re, sys
from collections import defaultdict

# Role label -> colour. Add freely; unknown roles fall through to a palette.
ROLE_COLOURS = {
    "D1": "&H00A5FF&",   # amber
    "D2": "&H80D0A0&",   # sage
    "SD": "&HD0C070&",   # teal
    "AS": "&HC0C0C0&",   # grey
    "B":  "&H80B0FF&",   # warm
    "P":  "&HB0A0E0&",   # mauve
    "R":  "&HA0D0D0&",
    "CH": "&HD0B0D0&",
}
FALLBACK = ["&H90E0E0&", "&HE0C090&", "&HA0E0A0&", "&HE0A0C0&"]

TEXT_COLOUR = "&HFFFFFF&"
FONT = "Georgia"
FONTSIZE = 44
DEFAULT_DUR = 4.0


def parse_time(v):
    v = (v or "").strip()
    if not v:
        return None
    if re.fullmatch(r"\d+(\.\d+)?", v):
        return float(v)
    parts = v.split(":")
    try:
        parts = [float(p) for p in parts]
    except ValueError:
        raise ValueError(f"cannot parse time: {v!r}")
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    raise ValueError(f"cannot parse time: {v!r}")


def ass_time(t):
    if t < 0:
        t = 0
    h = int(t // 3600); t -= h * 3600
    m = int(t // 60);   t -= m * 60
    return f"{h}:{m:02d}:{t:05.2f}"


def load_boundaries(path):
    starts, names, order = {}, {}, []
    with open(path) as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 2 or p[1] == "[END]":
                continue
            order.append((parse_time(p[0]), p[1]))
    for i, (t, name) in enumerate(order, start=1):
        starts[i] = t
        names[i] = name
    return starts, names


def clip_number(raw, names):
    raw = (raw or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"\d+", raw):
        return int(raw)
    for n, name in names.items():
        if raw == name or name.startswith(raw):
            return n
    m = re.match(r"\s*(\d+)", raw)
    return int(m.group(1)) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="annotations.csv")
    ap.add_argument("--boundaries", default="boundaries.tsv")
    ap.add_argument("--out", default="annotations.ass")
    a = ap.parse_args()

    for p in (a.csv, a.boundaries):
        if not os.path.exists(p):
            sys.exit(f"Not found: {p}")

    starts, names = load_boundaries(a.boundaries)
    if not starts:
        sys.exit("No clips found in boundaries file.")

    events, skipped, warnings = [], 0, []
    per_clip = defaultdict(list)
    seen_roles = []

    with open(a.csv, newline="", encoding="utf-8-sig") as f:
        for lineno, row in enumerate(csv.DictReader(f), start=2):
            row = { (k or "").strip().lower(): (v or "") for k, v in row.items() }
            text = row.get("text", "").strip()
            if not text:
                continue
            n = clip_number(row.get("clip", ""), names)
            if n is None or n not in starts:
                warnings.append(f"line {lineno}: unknown clip {row.get('clip','')!r} — skipped")
                skipped += 1
                continue
            try:
                st = parse_time(row.get("start", ""))
                en = parse_time(row.get("end", ""))
            except ValueError as e:
                warnings.append(f"line {lineno}: {e} — skipped")
                skipped += 1
                continue
            if st is None:
                warnings.append(f"line {lineno}: no start time — skipped ({text[:40]})")
                skipped += 1
                continue
            if en is None:
                en = st + DEFAULT_DUR
            if en <= st:
                warnings.append(f"line {lineno}: end <= start — skipped")
                skipped += 1
                continue

            role = row.get("role", "").strip().upper()
            if role and role not in seen_roles:
                seen_roles.append(role)

            per_clip[n].append((st, en, role, text, lineno))

    for n, items in per_clip.items():
        items.sort()
        base = starts[n]
        for i, (st, en, role, text, lineno) in enumerate(items):
            if i + 1 < len(items) and items[i + 1][0] < en:
                warnings.append(
                    f"clip {n:02d}: annotations overlap around {st:.0f}s "
                    f"— they will render on top of each other")
            colour = ROLE_COLOURS.get(role)
            if role and colour is None:
                colour = FALLBACK[(len(ROLE_COLOURS) + seen_roles.index(role)) % len(FALLBACK)]
            body = text.replace("\\", "").replace("{", "(").replace("}", ")")
            if role:
                body = (f"{{\\c{colour}\\b1}}{role}{{\\b0\\c{TEXT_COLOUR}}}  " + body)
            events.append((base + st, base + en, body))

    events.sort()

    header = f"""[Script Info]
Title: Hierarchical Divine Liturgy - Deacon Training
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Ann,{FONT},{FONTSIZE},{TEXT_COLOUR},{TEXT_COLOUR},&H00000000,&HB4000000,0,0,0,0,100,100,0,0,3,14,0,2,90,90,54,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    with open(a.out, "w", encoding="utf-8") as f:
        f.write(header)
        for st, en, body in events:
            f.write(f"Dialogue: 0,{ass_time(st)},{ass_time(en)},Ann,,0,0,0,,{body}\n")

    print(f"Wrote {a.out}: {len(events)} annotations across {len(per_clip)} clips")
    if seen_roles:
        print("Roles seen: " + ", ".join(seen_roles))
    if skipped:
        print(f"\n{skipped} row(s) skipped:")
    for w in warnings[:40]:
        print("  " + w)
    if len(warnings) > 40:
        print(f"  ... and {len(warnings)-40} more")
    print("\nNext:")
    print("  ffmpeg -i master.mp4 -i chapters.txt -i annotations.ass \\")
    print("    -map 0 -map 2 -map_metadata 1 -c copy -c:s mov_text out.mp4")


if __name__ == "__main__":
    main()
