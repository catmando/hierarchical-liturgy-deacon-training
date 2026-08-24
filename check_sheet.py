#!/usr/bin/env python3
"""Validate a YAML edit sheet without building anything.

    python3 check_sheet.py                     # checks annotations.yaml
    python3 check_sheet.py annotations.draft.yaml

Reports YAML syntax errors with line numbers, unknown or misspelled keys, bad
times, and the silent flow-mapping comma trap — where `{text: a, b}` quietly
turns the rest of your sentence into a key instead of failing.

Exits non-zero if anything is wrong, so it can gate a build.
"""
import sys, os

try:
    import yaml
except ModuleNotFoundError:
    sys.exit("ERROR: PyYAML missing — run: pip3 install --break-system-packages pyyaml")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import parse_time, CONT_GAP, DEFAULT_DUR   # one definition, not two


def clip_durations():
    """Length of each clip, keyed by clip number.

    Prefers the normalized clips the build actually concatenates; falls back to
    raw_clips.tsv so the sheet can be checked on a machine with no footage.
    """
    import csv as _csv, subprocess, glob
    durs = {}
    for path in sorted(glob.glob("normalized/[0-9][0-9][0-9].mp4")):
        n = int(os.path.basename(path)[:3])
        try:
            durs[n] = float(subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", path],
                capture_output=True, text=True, check=True).stdout.strip())
        except Exception:
            pass
    if durs:
        return durs
    try:
        with open("raw_clips.tsv", encoding="utf-8") as f:
            for i, row in enumerate(_csv.DictReader(f, delimiter="\t"), start=1):
                durs[i] = float(row["duration_s"])
    except Exception:
        pass
    return durs


def _first(d, *names):
    for n in names:
        if n in d and d[n] is not None:
            return d[n]
    return None


def resolve(entries, dur=None):
    """Resolve each annotation to (start, end), mirroring build.py exactly:
    an explicit time wins, otherwise continue CONT_GAP after the previous end,
    and with no length given the annotation holds until the next one starts.
    """
    def stated_start(e):
        v = e.get("at", e.get("from")) if isinstance(e, dict) else None
        if v is None:
            return None
        if isinstance(v, str) and v.strip().lower().startswith(("next", "c")):
            return None
        try:
            return parse_time(str(v))
        except Exception:
            return None

    out, prev_end = [], None
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            out.append((None, None)); continue
        raw = e.get("at", e.get("from"))
        try:
            if raw is None:
                st = 0.0 if prev_end is None else prev_end + CONT_GAP
            elif isinstance(raw, str) and raw.strip().lower().startswith(("next", "c")):
                tail = raw.strip().lstrip("nextNEXTcC").strip().lstrip("+").strip()
                gap = float(tail) if tail else CONT_GAP
                st = 0.0 if prev_end is None else prev_end + gap
            else:
                st = parse_time(str(raw))
            if "for" in e:
                en = st + parse_time(str(e["for"]))
            elif "to" in e:
                t = e["to"]
                if isinstance(t, str) and t.strip().lower() == "end":
                    if dur is None:
                        out.append((None, None)); continue
                    en = dur
                else:
                    en = parse_time(str(t))
            else:
                nxt = entries[i + 1] if i + 1 < len(entries) else None
                ns = stated_start(nxt) if nxt is not None else None
                en = ns if (ns is not None and ns > st) else st + DEFAULT_DUR
        except Exception:
            out.append((None, None)); continue
        out.append((st, en))
        prev_end = en
    return out


def fmt(t):
    return f"{int(t // 60)}:{t % 60:05.2f}" if t >= 60 else f"{t:.2f}s"

# Singular and plural mean the same thing everywhere. Canonical name -> aliases.
CLIP_FIELDS = {
    "clip": (), "chapter": ("chapters",), "skip": (), "join": (),
    "annotations": ("annotation",), "speed": ("speeds",), "cuts": ("cut",),
    "cards": ("card",), "notes": ("note",), "todos": ("todo",),
}
# notes: is published prose; todos: is private. Both may hang off a clip, a
# card or a single annotation, and both take prose or a list of points.
PROSE = {"notes": "note", "todos": "todo"}
ALIAS = {a: canon for canon, aliases in CLIP_FIELDS.items() for a in (canon,) + aliases}
LISTY = {"annotations", "speed", "cuts", "cards"}


def as_list(v):
    """A field that holds entries, however it was written. Anything that is
    not a list or a single mapping yields nothing, so a malformed value is
    reported once by the type check rather than crashing every later loop."""
    if v is None: return []
    if isinstance(v, dict): return [v]
    return v if isinstance(v, list) else []

# An entry in the annotations list is a span if it says so; spans may also be
# written in their own speed:/cuts: blocks.
ANN_KEYS   = {"at", "from", "for", "to", "role", "text", "speed", "cut",
              "mute", "audio", "hold", "notes", "note", "todos", "todo"}
AUDIO_MODES = ("mute", "fast", "normal")
LONG_HOLD = 30.0    # an INFERRED length past this is probably not intended


def is_span(e):
    """A span is marked `cut: true`, or `speed:` with a rate or true."""
    if not isinstance(e, dict):
        return False
    return e.get("cut") is True or ("speed" in e and e["speed"] is not False)


def parse_rate(v):
    """speed: true → the global --speed rate. 4, 4x and 2.5x → that rate."""
    if v is True:
        return None                     # defer to --speed
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    if isinstance(v, str):
        t = v.strip().lower().rstrip("x").strip()
        try: return float(t)
        except ValueError: pass
    raise ValueError(f"{v!r} — use true, or a rate like 4 or 4x")
SPAN_KEYS  = {"at", "from", "for", "to", "role", "text", "speed", "mute",
              "audio", "hold", "notes", "note", "todos", "todo"}
CARD_KEYS  = {"text", "image", "for", "to", "chapter", "after",
              "notes", "note", "todos", "todo"}

errors, warnings = [], []
def err(where, msg):  errors.append(f"{where}: {msg}")
def warn(where, msg): warnings.append(f"{where}: {msg}")


def check_time(where, field, v):
    """Times may arrive as int/float (YAML base-60) or as a string."""
    if v is None:
        return
    if field == "to" and isinstance(v, str) and v.strip().lower() == "end":
        return                      # runs to the end of the clip
    if isinstance(v, (int, float)):
        return
    s = str(v).strip()
    if s.lower().startswith(("next", "c")) and field in ("at", "from"):
        tail = s.lstrip("nextNEXTcC").strip().lstrip("+").strip()
        if tail:
            try: float(tail)
            except ValueError: err(where, f"{field}: {v!r} — expected next+SECONDS")
        return
    try: parse_time(s)
    except Exception: err(where, f"{field}: {v!r} is not a time")


def check_prose(where, field, v):
    """notes:/todos: — a block of prose, or a list of separate points."""
    if isinstance(v, str) or v is None:
        return
    if isinstance(v, list):
        if not all(isinstance(x, str) for x in v):
            err(where, f"{field}: every item must be text")
    else:
        err(where, f"{field}: expected prose or a list, got {type(v).__name__}")


def check_entry(where, e, allowed, need_text=True):
    if not isinstance(e, dict):
        err(where, f"expected a mapping, got {type(e).__name__}: {e!r}")
        return
    for canon, alias in PROSE.items():
        if canon in e and alias in e:
            err(where, f"{canon!r} and {alias!r} both given — keep one")
        for k in (canon, alias):
            if k in e: check_prose(where, k, e[k])
    for k in e:
        if k not in allowed:
            hint = ""
            if isinstance(e.get(k), type(None)):
                hint = ("  ← looks like the flow-mapping comma trap: prose inside "
                        "{ } is cut at the first comma. Use block style with 'text: >'.")
            err(where, f"unknown key {k!r} (allowed: {', '.join(sorted(allowed))}){hint}")
    if "at" in e and "from" in e:
        warn(where, "both 'at' and 'from' given; they mean the same thing")
    if "for" in e and "to" in e:
        err(where, "give either 'for' (duration) or 'to' (absolute end), not both")
    for f in ("at", "from", "for", "to"):
        if f in e: check_time(where, f, e[f])
    if need_text and not str(e.get("text", "")).strip() and not e.get("image"):
        err(where, "no text")


def validate(path):
    """Check a sheet without building. Returns (errors, warnings, summary)."""
    global errors, warnings
    errors, warnings = [], []

    if not os.path.exists(path):
        return [f"{path}: not found"], [], ""
    try:
        with open(path, encoding="utf-8") as f:
            doc = yaml.safe_load(f)
    except yaml.YAMLError as e:
        m = getattr(e, "problem_mark", None)
        where = (f"{path}, line {m.line + 1}, column {m.column + 1}"
                 if m else path)
        return [f"YAML syntax error in {where}: "
                f"{getattr(e, 'problem', e)}"], [], ""
    if not isinstance(doc, list):
        return [f"{path}: must be a list of clip blocks, "
                f"each starting with '- clip:'"], [], ""

    seen = {}
    for i, b in enumerate(doc):
        where = f"block {i + 1}"
        if not isinstance(b, dict):
            err(where, f"expected a clip block, got {type(b).__name__}"); continue
        if "clip" not in b:
            err(where, "no 'clip:' key"); continue
        n = b["clip"]
        where = f"clip {n}"
        if not isinstance(n, int):
            err(where, f"clip must be a whole number, got {n!r}")
        if n in seen and n != 0:
            warn(where, f"clip {n} also appears at block {seen[n]}")
        seen.setdefault(n, i + 1)

        canon = {}
        for k, v in b.items():
            c = ALIAS.get(k)
            if c is None:
                err(where, f"unknown key {k!r} (allowed: {', '.join(sorted(ALIAS))})")
                continue
            if c in canon:
                err(where, f"{k!r} and its synonym both given — keep one")
                continue
            canon[c] = v

        if canon.get("join") is True:
            if canon.get("cards"):
                err(where, "join: true with a card — a joined clip continues "
                           "the one before it, so a card between them would "
                           "break the join. Remove one.")
            if canon.get("chapter"):
                warn(where, "join: true with chapter: — the chapter title is "
                            "ignored, since the clip continues the previous "
                            "chapter")

        for field in LISTY:
            v = canon.get(field)
            if v is None or isinstance(v, (list, dict)):
                continue
            hint = ""
            if field == "cuts" and v is True:
                hint = ("  — `cut:` marks a span inside annotations and needs "
                        "from:/to:. To drop a whole clip use `skip: true`.")
            err(where, f"{field}: expected a list of entries, got "
                       f"{type(v).__name__} {v!r}{hint}")
            canon[field] = None

        def items(field):
            """A listy field may be written as one entry or a list of them."""
            return as_list(canon.get(field))

        for j, e in enumerate(items("annotations"), 1):
            w = f"{where} {'span' if is_span(e) else 'annotation'} {j}"
            check_entry(w, e, ANN_KEYS, need_text=not is_span(e))
            if is_span(e):
                if "speed" in e and e.get("cut") is True:
                    err(w, "marked both speed and cut — pick one")
                if "speed" in e:
                    try:
                        rate = parse_rate(e["speed"])
                        if rate is not None and rate <= 0:
                            err(w, f"speed: {e['speed']!r} — rate must be positive")
                    except ValueError as ex:
                        err(w, f"speed: {ex}")
                if "mute" in e and not isinstance(e["mute"], bool):
                    err(w, f"mute: {e['mute']!r} — use true or false")
                if "audio" in e:
                    if str(e["audio"]).strip().lower() not in AUDIO_MODES:
                        err(w, f"audio: {e['audio']!r} — use "
                               + ", ".join(AUDIO_MODES))
                    if "mute" in e:
                        warn(w, "audio: and mute: both given — audio: wins")
                if "hold" in e:
                    try:
                        if float(e["hold"]) < 0: raise ValueError
                    except (TypeError, ValueError):
                        err(w, f"hold: {e['hold']!r} — seconds at full volume "
                               f"before the fade, e.g. 4")
                    if str(e.get("audio", "")).strip().lower() != "normal":
                        warn(w, "hold: only applies to audio: normal")
                if e.get("cut") is True and any(k in e for k in
                                                ("mute", "audio", "hold")):
                    warn(w, "audio settings have no effect on a cut")
                if "at" not in e and "from" not in e: err(w, "no start — a span needs from:")
                if "to" not in e and "for" not in e:  err(w, "no end — a span needs to: or for:")
        # A span is a region of the original clip, so unlike an annotation it
        # cannot inherit its start from whatever came before.
        for j, e in enumerate(items("speed"), 1):
            w = f"{where} speed {j}"
            check_entry(w, e, SPAN_KEYS, need_text=False)
            if isinstance(e, dict):
                if "at" not in e and "from" not in e: err(w, "no start — a span needs from:")
                if "to" not in e and "for" not in e:  err(w, "no end — a span needs to: or for:")
        for j, e in enumerate(items("cuts"), 1):
            w = f"{where} cut {j}"
            check_entry(w, e, {"at", "from", "to", "for"}, need_text=False)
            if isinstance(e, dict):
                if "at" not in e and "from" not in e: err(w, "no start — a cut needs from:")
                if "to" not in e and "for" not in e:  err(w, "no end — a cut needs to: or for:")
        for j, e in enumerate(items("cards"), 1):
            check_entry(f"{where} card {j}", e, CARD_KEYS)

        for field in PROSE:
            if field in canon: check_prose(where, field, canon[field])

    # ---------------- timing: past the end of a clip, and overlaps -------------
    DURS = clip_durations()
    if not DURS:
        warnings.append("could not read clip durations "
                        "(no normalized/ and no raw_clips.tsv) — skipped end-of-clip checks")

    for b in doc:
        if not isinstance(b, dict) or "clip" not in b: continue
        n = b["clip"]
        if not isinstance(n, int) or n == 0: continue
        where = f"clip {n}"
        entries = as_list(b.get("annotations", b.get("annotation")))
        anns   = [e for e in entries if not is_span(e)]
        inline = [e for e in entries if is_span(e)]
        dur    = DURS.get(n)
        spans  = resolve(anns, dur)

        # cuts remove footage, so an annotation over one has nothing to sit on
        cuts = []
        for c in list(inline) + as_list(b.get("cuts", b.get("cut"))):
            if not isinstance(c, dict) or c.get("cut") is not True: continue
            try:
                cst = parse_time(str(_first(c, "at", "from")))
                t = c.get("to")
                if isinstance(t, str) and t.strip().lower() == "end":
                    cen = dur
                elif t is not None:
                    cen = parse_time(str(t))
                else:
                    cen = cst + parse_time(str(c["for"]))
                if cst is not None and cen is not None:
                    cuts.append((cst, cen))
            except Exception:
                pass

        for i, ((st, en), e) in enumerate(zip(spans, anns), 1):
            if st is None: continue
            label = str(e.get("text", ""))[:40].replace("\n", " ") if isinstance(e, dict) else ""
            if en is not None and en <= st:
                err(f"{where} annotation {i}",
                    f"ends at {fmt(en)} but starts at {fmt(st)} — a 'to:' "
                    f"earlier than the start. Did you mean 'for:'?  ({label})")
                continue
            hidden = next(((cs, ce) for cs, ce in cuts if cs <= st < ce), None)
            if hidden:
                # A warning, not an error: mid-edit this is often transient,
                # and the build still succeeds without the annotation.
                warn(f"{where} annotation {i}",
                     f"starts at {fmt(st)}, inside the cut "
                     f"{fmt(hidden[0])}-{fmt(hidden[1])} — that footage is "
                     f"removed, so it will not appear  ({label})")
                continue

            # Only when the length was inferred from the next annotation. An
            # explicit `for:` or `to:` is a decision, however long it runs.
            if ("for" not in e and "to" not in e
                    and en is not None and en - st > LONG_HOLD):
                warn(f"{where} annotation {i}",
                     f"holds {en - st:.0f}s — no `for:` or `to:`, so it stays "
                     f"up until the next annotation at {fmt(en)}. Add a "
                     f"`for:` if it should clear sooner  ({label})")

            if dur is not None:
                if st >= dur:
                    how = ("starts exactly at the clip's end"
                           if abs(st - dur) < 0.05 else
                           f"starts at {fmt(st)}, past the clip's end")
                    err(f"{where} annotation {i}",
                        f"{how} ({st:.3f}s vs {dur:.3f}s) — nothing of this clip is "
                        f"left to show it over, so it will caption the following "
                        f"clip  ({label})")
                elif en > dur:
                    warn(f"{where} annotation {i}",
                         f"runs to {fmt(en)}, past the clip's {fmt(dur)} end "
                         f"— it will spill into the next clip  ({label})")

        # annotations sharing screen time land on top of each other
        for i in range(len(spans)):
            for j in range(i + 1, len(spans)):
                a, bb = spans[i], spans[j]
                if None in a or None in bb: continue
                lo, hi = max(a[0], bb[0]), min(a[1], bb[1])
                if hi - lo > 0.01:
                    warn(f"{where} annotations {i+1} and {j+1}",
                         f"overlap {fmt(lo)}–{fmt(hi)} — they share the same screen position")

        # a speed label sits in the annotation position for its whole span
        sp = as_list(b.get("speed", b.get("speeds")))
        sp = list(sp) + [e for e in inline if e.get("speed") is True]
        for k, e in enumerate(sp, 1):
            if not isinstance(e, dict): continue
            try:
                sst = parse_time(str(e.get("at", e.get("from"))))
                if "to" in e:
                    t = e["to"]
                    sen = (dur if isinstance(t, str)
                                  and t.strip().lower() == "end"
                           else parse_time(str(t)))
                else:
                    sen = sst + parse_time(str(e["for"]))
                if sen is None:
                    continue
            except Exception:
                continue
            for i, (st, en) in enumerate(spans, 1):
                if st is None: continue
                lo, hi = max(st, sst), min(en, sen)
                if hi - lo > 0.01:
                    warn(f"{where} annotation {i} and speed {k}",
                         f"overlap {fmt(lo)}–{fmt(hi)} — the speed label shares that position")



    def _entries(b):
        return as_list(b.get("annotations", b.get("annotation")))

    def _spans(b):
        return (as_list(b.get("speed", b.get("speeds")))
                + as_list(b.get("cuts", b.get("cut"))))

    blocks = [b for b in doc if isinstance(b, dict)]
    n_ann  = sum(len([e for e in _entries(b) if not is_span(e)]) for b in blocks)
    n_span = sum(len([e for e in _entries(b) if is_span(e)]) + len(_spans(b))
                 for b in blocks)
    summary = (f"{path}: {len(doc)} clip blocks, {n_ann} annotations"
               + (f", {n_span} span(s)" if n_span else ""))
    return errors, warnings, summary


def report(errors, warnings, summary, stream=sys.stdout):
    """Print a validation result the same way wherever it is run from."""
    if summary: print(summary, file=stream)
    for w in warnings: print(f"  warning  {w}", file=stream)
    for e in errors:   print(f"  ERROR    {e}", file=stream)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "annotations.yaml"
    errors, warnings, summary = validate(path)
    report(errors, warnings, summary)
    print()
    if errors:
        print(f"{len(errors)} error(s).")
        return 1
    print("Syntax is valid." + (f" {len(warnings)} warning(s)." if warnings else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())