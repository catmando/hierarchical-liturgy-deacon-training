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
from build import parse_time            # one definition of a timecode, not two

# Singular and plural mean the same thing everywhere. Canonical name -> aliases.
CLIP_FIELDS = {
    "clip": (), "chapter": ("chapters",), "skip": (),
    "annotations": ("annotation",), "speed": ("speeds",), "cuts": ("cut",),
    "cards": ("card",), "rubrics": ("rubric",), "notes": ("note",),
}
ALIAS = {a: canon for canon, aliases in CLIP_FIELDS.items() for a in (canon,) + aliases}
LISTY = {"annotations", "speed", "cuts", "cards"}

ANN_KEYS   = {"at", "from", "for", "to", "role", "text"}
SPAN_KEYS  = {"at", "from", "for", "to", "role", "text"}
CARD_KEYS  = {"text", "image", "for", "to", "chapter", "after"}

errors, warnings = [], []
def err(where, msg):  errors.append(f"{where}: {msg}")
def warn(where, msg): warnings.append(f"{where}: {msg}")


def check_time(where, field, v):
    """Times may arrive as int/float (YAML base-60) or as a string."""
    if v is None:
        return
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


def check_entry(where, e, allowed, need_text=True):
    if not isinstance(e, dict):
        err(where, f"expected a mapping, got {type(e).__name__}: {e!r}")
        return
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


path = sys.argv[1] if len(sys.argv) > 1 else "annotations.yaml"
if not os.path.exists(path):
    sys.exit(f"ERROR: {path} not found")

try:
    doc = yaml.safe_load(open(path, encoding="utf-8"))
except yaml.YAMLError as e:
    m = getattr(e, "problem_mark", None)
    sys.exit(f"YAML SYNTAX ERROR in {path}"
             + (f", line {m.line + 1}, column {m.column + 1}" if m else "")
             + f"\n  {getattr(e, 'problem', e)}")

if not isinstance(doc, list):
    sys.exit(f"ERROR: {path} must be a list of clip blocks (each starting with '- clip:')")

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

    def items(field):
        """A listy field may be written as one entry or a list of them."""
        v = canon.get(field)
        if v is None: return []
        return v if isinstance(v, list) else [v]

    for j, e in enumerate(items("annotations"), 1):
        check_entry(f"{where} annotation {j}", e, ANN_KEYS)
    for j, e in enumerate(items("speed"), 1):
        check_entry(f"{where} speed {j}", e, SPAN_KEYS, need_text=False)
    for j, e in enumerate(items("cuts"), 1):
        check_entry(f"{where} cut {j}", e, {"at", "from", "to", "for"}, need_text=False)
    for j, e in enumerate(items("cards"), 1):
        check_entry(f"{where} card {j}", e, CARD_KEYS)

    # rubrics/notes may be a block of prose or a list of separate directives
    for field in ("rubrics", "notes"):
        v = canon.get(field)
        if v is None: continue
        if not isinstance(v, (str, list)):
            err(where, f"{field}: expected prose or a list, got {type(v).__name__}")
        elif isinstance(v, list) and not all(isinstance(x, str) for x in v):
            err(where, f"{field}: every item must be text")

def _n(b):
    v = b.get("annotations", b.get("annotation"))
    return len(v) if isinstance(v, list) else (1 if v else 0)
n_ann = sum(_n(b) for b in doc if isinstance(b, dict))
print(f"{path}: {len(doc)} clip blocks, {n_ann} annotations")
for w in warnings: print(f"  warning  {w}")
for e in errors:   print(f"  ERROR    {e}")
print()
if errors:
    print(f"{len(errors)} error(s).")
    sys.exit(1)
print("Syntax is valid." + (f" {len(warnings)} warning(s)." if warnings else ""))
