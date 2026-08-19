# Hierarchical Divine Liturgy — Deacon Training Video

> Rename this file to **`CLAUDE.md`** in the project root. Claude Code reads it
> automatically at the start of every session.

Last updated: 19 August 2026, ~01:00. Encode complete; annotation work in
progress; user is migrating the edit sheet from CSV to YAML.

---

## 1. The project

One training video for **deacons**, built from 37 short clips filmed at a
hierarchical Divine Liturgy, **20 June 2026**, OCA, Diocese of New York and
New Jersey (Archbishop MICHAEL; Metropolitan TIKHON). Each clip covers one
step of the service.

The video needs **explanatory text overlaid throughout** and **chapter
markers**. Annotations are rubric-level and choreographic: where to stand,
what to hold, which hand, what to say, and what cues trigger movement.

---

## 2. Where things stand

| | |
|---|---|
| Normalize encode | **DONE.** 37 clips → `_normalized/001.mp4`…`037.mp4` |
| `master.mp4` | built, 1:03:23 |
| Annotation timings | **clips 1–2 done; 35 to go** |
| Roles vocabulary | evolving by design (§6) |
| Roles chart | **still not uploaded** (§6) |
| Chapter titles in MKV | fix applied, **NOT VERIFIED** (§8) |
| Edit sheet format | CSV now; user wants to move to **YAML** (§9) |

---

## 3. One script does everything

`build.py`. It replaced the earlier `rebuild.sh`, `make_card.sh`,
`card_from_image.sh`, and `make_subs.py` — all obsolete, do not reintroduce.

```bash
python3 build.py                 # full build
python3 build.py --help          # flags AND the full sheet-format reference
python3 build.py --clip 3        # preview one clip (also 3-5 or 3,7,19)
python3 build.py --subs-only     # regenerate annotations only, fast
python3 build.py --speed 6       # global rate for every speed row
python3 build.py --no-mkv
python3 build.py --youtube       # burn subs into youtube.mp4, slow
```

**Outputs:** `master.mp4`, `liturgy_training.mkv` (chapters + annotations
embedded, subtitle track flagged default), `annotations.ass`, `chapters.txt`,
`youtube_chapters.txt`, `boundaries.tsv`. Preview mode writes `preview.*`
instead and leaves the real outputs alone.

`normalize_and_join.sh` already ran. Do not run it again unless the source
clips change.

**`--help` is authoritative for the sheet format** — it prints the module
docstring, which documents every row type. Read it before changing the parser.

---

## 4. The edit sheet

Columns: `type, clip, start, dur, role, text, image, notes`

| type | meaning |
|---|---|
| `annotation` (or blank) | text overlay. `start` = seconds from THAT CLIP's start; `dur` = how long it stays up (**a length, not an end time**; default 4). |
| `card` | title card inserted AFTER that clip; becomes **its own chapter**. `clip=0` = very front. `dur` = seconds (default 6). |
| `title` | same but **folds into the following chapter**. For section-title cards. |
| `chapter` | renames the chapter starting at that clip. |
| `skip` | omits that clip entirely. |
| `cut` | removes a span. **4th column is an END TIME.** `cut,19,1:00,2:00` |
| `speed` | speeds a span up. **4th column is an END TIME.** `text` = the on-screen label. |
| `#` | comment. |

**`start` accepts `C`** — continue 0.2s after the previous annotation on that
clip; `C+1.5` for a longer gap. Resolves in **CSV row order**.

**Times** accept plain seconds, `M:SS`, or `H:MM:SS`.
**Keywords are case-insensitive.** **Role codes are uppercased.**
**Line breaks:** a Return inside a cell, or `||`. Chapter titles collapse to
one line.

### Speed rows
Rate is global via `--speed` (default 4), deliberately **not per row** — the
user wants to tune overall feel, not vary it by section. Audio is **muted**
in sped spans. A label sits in the normal annotation position, italic, for
the whole span. Text goes in the `text` column, e.g.
`speed,3,1:10,3:40,,...Deacon 1 continues the entrance prayers...`
Blank → "skipping ahead". `-` → no label.

---

## 5. Everything is written against the ORIGINAL clip

Annotation times, cut times and speed times are all measured on the untouched
footage. The script maps them through the edits. So in a 3:00 clip:

```
cut,7,1:00,2:00
annotation,7,2:30,4,D1,text
cut,7,2:45,2:55
```

the annotation lands at 1:30 and the second cut at 1:45. **Nothing is ever
re-timed by hand.** Adding cards, changing card durations, skipping clips, or
resizing an edit shifts nothing in the sheet.

The one exception: **trimming the head of a clip** shifts that clip's own
offsets. Tail trims are harmless. Nothing outside the clip is affected.

> A user asked why an annotation typed as `46` appeared at `0:54` — because an
> 8-second title card sits ahead of clip 1. Correct behaviour, not a bug.
> **Do not "fix" this.**

---

## 6. Deacon roles

Two deacons, treated as the normal case.

> **D1 (protodeacon) takes everything touching the hierarch directly** — the
> dialogues, censing of the bishop, the Gospel, the great commemoration, the
> diskos. **Litanies alternate beginning with D2.**

Full table in Part Zero of `hierarchical_liturgy_cue_sheet.md`, inferred items
marked `[verify]`. Clip 24 confirms D2 is last in the shoulder-kissing.

**The vocabulary is deliberately unsettled** — the user is working out which
roles are worth highlighting. Seen so far: `D1`, `D2`, `AS1+2`, `AS3+4`,
`DEACONS`, `PRIEST`, `CHOIR`. Any code gets a colour automatically.
**Do not push to freeze this.** Two open questions, not resolved: whether
`DEACONS` should be `D1+D2` for consistency, and whether long codes should
render smaller, since the role is a bold prefix that eats width.

**⚠ The user has a diocesan roles chart** for one, two, three and four
deacons. **Still not uploaded.** It resolves every `[verify]` and is the one
outstanding item that could change annotation *text* rather than timings.

---

## 7. Environment and traps

- macOS, zsh, Apple Silicon. ffmpeg 9.0.1 from the **`homebrew-ffmpeg/ffmpeg`
  tap** — the default brew formula lacked `drawtext` and `libass`.
- **Numbers blanks the `clip` column on export.** Hit twice: first silently
  dropping 84 of 98 annotations, then blanking 34 of 38 **chapter** rows.
  `build.py` inherits blank clips on *annotation* rows only. **This is the
  single biggest reason to move to YAML.**
- **Numbers does not save as CSV** — File → Export To → CSV every time.
- **IINA bug:** opening the playlist/chapter panel and jumping chapters kills
  the subtitle track, and you cannot return to 0:00 without restarting. Use
  VLC, or `ffplay -ss N -vf "ass=annotations.ass" master.mp4`.
- **VLC needs the subtitle track switched on** (press `v`), even when flagged
  default.
- **YouTube silently drops ALL chapters** if any is under 10s, if the first is
  not 00:00, or if there are fewer than three. `build.py` warns.
- **Sparse annotations look like a bug.** Three times the user thought
  generation had failed when the cause was a long gap between timed
  annotations, or a preview containing only one chapter. **Check the actual
  event times before debugging anything.**

---

## 8. ⚠ Unfinished: chapter titles

Symptom: `liturgy_training.mkv` had 38 chapters with correct start times and
**no titles at all**.

Cause: `-map_metadata` copies *global* metadata; chapter titles are
per-chapter and need **`-map_chapters`**. The mux was missing it.

Fix applied to `build.py`, verified in a synthetic test, **but never confirmed
on the user's real footage.** First thing to check:

```bash
grep -c map_chapters build.py          # expect 1
python3 build.py
ffprobe -v error -show_chapters liturgy_training.mkv | grep -i title | head -5
```

Expect `TAG:title=Greeting of the Hierarch at the Doors`.

---

## 9. Planned: move the sheet to YAML

The user is switching to VS Code + Claude Code and wants YAML instead of CSV —
multi-line text without quoting, no spreadsheet export step, and immune to the
Numbers column-blanking bug.

Keep the same field names so the logic carries over. Suggested shape:

```yaml
- type: chapter
  clip: 1
  text: Greeting of the Hierarch at the Doors
  notes: |
    What is the order of greeting?
    Children - flowers; Council President - bread and salt.

- type: annotation
  clip: 1
  start: 0
  dur: 4
  role: AS1+2
  text: Subdeacons or altar servers place the mantiya
```

Ideally accept both formats, switching on file extension.

---

## 10. Known data issues in the current sheet

- **Clip 4 has two `chapter` rows** — the user's "Conclusion of the Entrance
  Prayers and the Vesting" and a leftover template row "Ton Despotin; Blessing
  of the Clergy". The second wins. Delete one.
- **Chapter 1's title contains the user's working notes**, which collapse into
  one very long chapter name. Move them to `notes`.
- The "Homily — not shown" card is **6s**; YouTube needs ≥10s.
- Clips 3–37 still carry template placeholder annotation timings, which now
  read as durations and overlap. They resolve as each clip is rewritten.

---

## 11. Coverage gaps

- **~18m after clip 20** — the homily. Deliberate. Card planned.
- **~27m after clip 33** — Lord's Prayer, elevation, fraction, communion of
  clergy and faithful. Neither notes nor footage cover it.

**The user has watched all the footage and asked not to keep raising these.
Respect that.**

---

## 12. Editorial cleanup, outstanding

- Source notes skip section 11 and use 20 twice.
- Transliterations vary: *Ton Des Postin / Ton Despotin*; *Eis Polla Eti Thes
  Posta* (= *Eis polla eti, despota*); *Kolbuk / Klobuk*; *Matiya / Mantiya*;
  *Trikiri / Trikirion*. "**Jezel**" is Slavonic *zhezl*, the same staff called
  "Staff" elsewhere. Normalize; consider a glossary card.
- **Check the hierarchs' names** in the long commemoration before publishing.
- Clip 02 is titled "Bishop moves to the cathedra" but precedes the entrance
  prayers, while the notes put the cathedra after. Confirm against the footage.

---

## 13. Notes for whoever picks this up

- **Claude cannot watch video** — only metadata and extracted stills. Never ask
  for the clips.
- **This is OCA / Russian recension.** Do not drift toward Greek or Antiochian
  usage.
- The user's priest and the footage are authoritative. Where this project
  infers, it says so. Keep that discipline.
- When something is broken, give commands **one at a time** and wait for
  output. Long multi-step blocks caused confusion more than once.
- Don't guess at causes. Twice tonight a confident diagnosis was wrong and the
  real cause only appeared after running the user's actual file. **Reproduce
  before explaining.**

---

## Files

| file | what |
|---|---|
| `build.py` | the entire toolchain |
| `annotations.csv` | the edit sheet (repaired; migrating to YAML) |
| `hierarchical_liturgy_cue_sheet.md` | 23 chapters from the priest's notes, D1/D2 role table, draft annotation text |
| `clip_to_chapter_map.md` | all 37 clips mapped to a 30-chapter structure |
| `normalize_and_join.sh` | reference only; already run |
| `notes_for_hierarchical_divine_liturgy.pdf` | the priest's original rubrics |
