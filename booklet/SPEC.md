# The service-book page, measured

Everything here was measured off `source/scan-000.jpg`, a ~450 ppi scan of
page 136 of the parish Divine Liturgy book, not guessed. The numbers drive
`booklet.css`; change them there.

| | measured | in `booklet.css` |
|---|---|---|
| Page | 3.625 × 5.875 in (261 × 423 pt) | `@page size` |
| Measure | 203.5 pt (2.83 in) | margins 0.40 in |
| Body x-height | 4.55 pt | → 11.7 pt Junicode-Cond |
| Body leading | 14.2 pt | `line-height` |
| Paragraph indent | 15 pt (~1.4 em) | `text-indent` |
| Choir / small text | x-height 3.49 pt, leading 11.0 pt | 9 pt / 11 pt |
| Footnote | as the small text | 9 pt |
| Running head | caps, letterspaced, cap height 5.24 pt | 8.6 pt, `.09em` |
| Rule under the head | 0.64 pt, full measure, 6.8 pt below / 6.7 pt above | `border-bottom` |
| Page number | centred at the foot, italic | 9 pt italic |
| Red | `#d80c18` | `--red` |
| Black | `#000000` | |

## The typeface

The original is in the **Jenson/Centaur** family — humanist, a calligraphic
`e`, an `ff` ligature, and an Arrighi-style chancery italic. Most likely Adobe
Jenson. Nothing in that family was on the machine, so the build uses
**Junicode**, which is free (OFL, licence in `fonts/`) and modelled on Jenson.

Two things had to be corrected, and both were measured rather than eyeballed:

- **Junicode's x-height is smaller** for a given nominal size, so 10.5 pt set
  visibly small. The body is therefore **11.7 pt**, which puts the x-height at
  4.56 pt against the measured 4.55.
- **At that size the regular cut sets about 11% wide**, so a page held fewer
  words than the book's. The **condensed** cut restores it: the opening
  paragraph sets in 6 lines, exactly as the book does.

Nothing here needs to be exact — the user's words — but matching the x-height
and the density is what makes an insert sit convincingly next to a real page.

## Building

    cd booklet && weasyprint --encoding utf-8 test_p136.html test_p136.pdf

`test_p136.html` reproduces the scanned page for comparison only; it is the
yardstick, not the deliverable. Compare with:

    pdftoppm -png -r 300 test_p136.pdf /tmp/mine   # then look beside the scan

**Hyphenation needs `pyphen`** (`pip3 install --break-system-packages pyphen`).
Without it weasyprint silently sets justified text with no hyphens, and the
word spacing goes to pieces — which looks like a font problem and is not.

---

## The insert — `insert.html` + `insert.css`

Pages 136 and 137 sit on **different leaves** and face each other across the
gutter when the book is open. So the replacement is **one sheet, printed on
one side only**, carrying 136 on the left and 137 on the right. It folds down
the middle into the gutter, and its blank back is glued over the two existing
pages: printed side to the reader, blank side to the book.

That means there is **no duplex and no imposition to get wrong** — the thing
that makes the roles card fiddly does not arise here.

    cd booklet && python3 make_insert.py        # pages/136.txt + 137.txt
    cd booklet && python3 make_insert.py 140 141

`insert.html` is generated — edit `pages/*.txt`, not it.

Output is a US Letter sheet with the 7¼ × 5⅞ spread centred, a dashed cut
border, a dashed fold line down the centre, and a caption outside the cut so
it goes with the offcut. **Print at 100%**, not "fit to page".

Each leaf is a `.leaf`, which carries the book's own furniture: running head
at 0.115 in, the red rule at 0.29 in, first body line at 0.386 in, folio
centred at the foot. The rule is a separate absolutely-placed element rather
than a border on the running head, so it sits where it was measured instead of
drifting with the head's line box — as a border it landed on the first line of
text.

Content classes, all matching the book's own devices:

| class | what it is |
|---|---|
| `p` | body paragraph, indented 15 pt |
| `p.flush` | body paragraph, no indent |
| `p.rubric` | a whole paragraph in red |
| `p.label` | centred red italic — *The priest prays:* |
| `span.lead` | red italic opening a black paragraph — *Exclamation:* |
| `span.red` | red inside black text — the `N.` of a name |
| `p.small` | the choir's text, 9/11 |
| `p.note` | footnote, 9/11 |
| `sup` | red superior figure |

**Why this exists.** Pasting corrections into a service book is ordinary
practice in the parish — for personal notes and for the way the local priest
has things said. It is usually done by hand on paper; this only makes a
printed one instead. So the fitting, the paper and the glue are the user's
own well-trodden ground: **don't offer advice about them.** The job here is
the typography and the words.

The current page 137 is invented placeholder text and must be replaced.

## Writing the pages — `pages/136.txt`

The text lives in a plain file per page, one paragraph per block, wrapped over
as many lines as you like. **A blank line starts a new paragraph.** Lines
beginning `#` are comments.

| written | comes out as |
|---|---|
| `head:` | the running head |
| `folio:` | the page number |
| *(no prefix)* | body paragraph, first line indented |
| `flush:` | body paragraph, no indent |
| `rubric:` | the whole paragraph in red |
| `label:` | centred red italic — *The priest prays:* |
| `small:` | the choir's smaller type |
| `note:` | a footnote |
| `{red}` | red inside black text — `{N.}` for a name |
| `{*red italic*}` | an opening like *Exclamation:* |
| `*italic*`, `**bold**` | as everywhere else in this project |
| `[1]` | a red superior figure |

That is the whole of it. It is deliberately the same `**bold**` / `*italic*`
the annotations sheet uses, so there is one set of conventions to remember.

**Why not a word processor.** Styled text exports badly, every edit is a
manual round trip, and none of it versions with the repo — a diff would show
"the file changed" and nothing more. A plain file diffs line by line, travels
with the clone, and cannot lose a rubric's colour in an export.

**Page 136 is transcribed from the scan and checked against `tesseract` OCR**,
which agreed word for word. Proofread it anyway before it is glued into a
book.
