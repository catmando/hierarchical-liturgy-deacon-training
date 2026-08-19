# Hierarchical Divine Liturgy — Deacon Training Video

Claude Code reads this file automatically at the start of every session.

Last updated: 19 August 2026. Encode complete. Now in git, with the raw
footage archived off-machine; directories reorganized; annotation work in
progress; the edit sheet is still CSV and migrating to YAML.

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
| Version control | **DONE.** github.com/catmando/hierarchical-liturgy-deacon-training (public) |
| Raw footage backup | **DONE.** 37 clips on the `raw-footage-v1` release; restore verified (§14) |
| Directory layout | **DONE.** `raw/` → `normalized/` → `output/` (§14) |
| Normalize encode | **DONE.** 37 clips → `normalized/001.mp4`…`037.mp4` |
| `master.mp4` | built, 1:03:23, now at `output/master.mp4` |
| Annotation timings | **clips 1–2 done; 35 to go** |
| Roles vocabulary | evolving by design (§6) |
| Roles chart | **still not uploaded** (§6) |
| Chapter titles in MKV | **VERIFIED WORKING** on real footage (§8) |
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

**Outputs, all into `output/`:** `master.mp4`, `liturgy_training.mkv`
(chapters + annotations embedded, subtitle track flagged default),
`annotations.ass`, `chapters.txt`, `youtube_chapters.txt`, `boundaries.tsv`.
Preview mode writes `output/preview.*` instead and leaves the real outputs
alone.

Three supporting scripts, none of which touch the video:
`check_environment.sh` (verify a machine can build — run it before committing
hours to a normalize pass), `restore_raw_clips.sh` (fetch and SHA-256 verify
the footage), `make_manifest.sh` (regenerate `raw_clips.tsv`).

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

Clip 24 confirms D2 is last in the shoulder-kissing. (An earlier
`hierarchical_liturgy_cue_sheet.md` held a fuller table, but it was written
before the 37 clips were in hand and the user has confirmed it is no longer
needed — the footage supersedes it. Do not go looking for it.)

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

## 8. ✅ Resolved: chapter titles

Symptom: `liturgy_training.mkv` had 38 chapters with correct start times and
**no titles at all**.

Cause: `-map_metadata` copies *global* metadata; chapter titles are
per-chapter and need **`-map_chapters`**. The mux was missing it.

Fix applied to `build.py` and **now confirmed on the real footage** — a
`build.py --clip 3` preview mux produced `TAG:title=Entrance Prayers`, with
the subtitle track present and flagged default. Nothing further to do.

To re-check after any change to the mux:

```bash
python3 build.py --clip 3
ffprobe -v error -show_chapters output/preview.mkv | grep -i title
```

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
- **State the plan before executing it.** The user asked for this explicitly.
  Say what you intend to do and wait for a go, especially for anything slow,
  outward-facing, or hard to undo. Read-only inspection to inform the plan is
  fine and expected.
- **Verify, don't assume.** Every claim in this file that says DONE was
  actually run. Follow that: prove the round trip, diff the output, check the
  real file.
- The user works on a **Mac laptop** (Apple Silicon, macOS). Cross-machine
  continuity means another Mac or a fresh clone after a disk failure — see §14.

---

## Files

| file | what |
|---|---|
| `build.py` | the entire toolchain |
| `annotations.csv` | the edit sheet (repaired; migrating to YAML) |
| `raw_clips.tsv` | manifest: size, SHA-256, duration, codec of all 37 clips |
| `normalize_and_join.sh` | raw → normalized → master; already run, don't re-run |
| `restore_raw_clips.sh` | download the footage from the release and verify it |
| `check_environment.sh` | verify a machine can build before committing hours |
| `make_manifest.sh` | regenerate `raw_clips.tsv` |
| `README.md` | recovery runbook: bare Mac → finished video |
| `CLAUDE.md` | this file |

Three files this document used to list —
`hierarchical_liturgy_cue_sheet.md`, `clip_to_chapter_map.md`, and
`notes_for_hierarchical_divine_liturgy.pdf` — **no longer exist and are not
needed.** They were scaffolding from before the 37 clips were in hand. The
user has confirmed the footage supersedes them. Don't hunt for them, and
don't ask the user to re-supply them.

---

## 14. The repository and disaster recovery

**github.com/catmando/hierarchical-liturgy-deacon-training** — public, owned
by `catmando` (not the `catprintlabs` org, to keep it off company billing).

### Layout

Directories are named for the order the pipeline runs them. Nothing tracked
by git lives in a subdirectory, so ffmpeg can write freely without ever
showing up in `git status`.

```
build.py, *.sh, annotations.csv, raw_clips.tsv, README.md, CLAUDE.md
raw/          37 source clips · 6.8 GB   — not in git; on the release
normalized/   build.py working files     — not in git; rebuildable
output/       master, mkv, subs, chapters — not in git; rebuildable
junk/         parked, deliberately not deleted
```

`junk/` exists because the user asked that nothing be deleted. Park things
there rather than removing them. It currently holds `test.mkv` and
`check.mkv`, 7.1 GB each.

### Why the footage isn't in git

6.8 GB, with 27 clips over GitHub's 100 MB per-file hard limit. Git LFS was
rejected deliberately: **LFS bandwidth is billed to the repo owner and
downloads by strangers count**, which on a public repo is an uncapped bill.
Release assets have no bandwidth metering and a 2 GB per-file ceiling, which
every clip clears comfortably.

### Recovery

Full runbook in `README.md`. The short version:

```bash
git clone https://github.com/catmando/hierarchical-liturgy-deacon-training.git
cd hierarchical-liturgy-deacon-training
./check_environment.sh          # tools, ffmpeg filters, font, disk, auth
./restore_raw_clips.sh          # 6.8 GB into raw/, SHA-256 verified
./normalize_and_join.sh         # hours; overnight; resumable
python3 build.py
```

**This path is tested, not theoretical.** Clip 01 was moved aside, recovered
from the release, and confirmed byte-identical; `make_manifest.sh` was
confirmed to reproduce the committed manifest exactly.

### Two traps worth knowing

- **GitHub rewrites release asset names**, turning spaces into dots:
  `01 - Greeting….mp4` is stored as `01.-.Greeting….mp4`.
  `restore_raw_clips.sh` maps them back via the manifest. Verified against
  the live API, not assumed.
- **ffmpeg must come from the `homebrew-ffmpeg/ffmpeg` tap.** The stock
  formula has shipped without `drawtext` and `libass`, which the title cards
  and the annotation overlay respectively depend on. `check_environment.sh`
  probes for exactly these.

### The source clips are not uniformly 30 fps

25 are 30 fps, six are 179/6 (≈29.83), five are 119/4 (≈29.75), and one is
120 fps. All 1920×1080 h264/aac, 63.4 minutes total. This is precisely why
`normalize_and_join.sh` exists — concatenating them raw produces broken
timing.
