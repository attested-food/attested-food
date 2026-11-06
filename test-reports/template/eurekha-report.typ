// Eurekha Labs test report. Compile with:
//   typst compile --root . --input data=/data/<id>.json --no-pdf-tags template/eurekha-report.typ out/<id>.typst.pdf
// then run scripts/build.mjs (or scripts/normalize.mjs) to get the raw PDF that goes to S3.
//
// Redaction contract (see README): every customer field is set in PII_FONT and nothing else is.
// The verifier only lets a redaction zero glyphs drawn with that font.

#import "@preview/tiaoma:0.3.0": qrcode

#let data = json(sys.inputs.at("data", default: "/data/choco-millet-muesli.json"))
// Prover-friendly variant (scripts/build-opt.mjs): QR as a raster image (path in input `qr`),
// no kerning, no bold face (one font fewer). Same text runs in the same order.
#let OPT = sys.inputs.at("opt", default: "0") == "1"
#let BOLD = if OPT { "regular" } else { "bold" }
#show strong: it => if OPT { it.body } else { it }

#let BODY_FONT = "Libertinus Serif"
#let PII_FONT = "DejaVu Sans Mono"
// Characters a PII value may use. Rendered invisibly once, before any PII, so the PII font
// subset, its glyph numbering (first use order) and its ToUnicode CMap are the same for every
// report and do not leak which letters, or in which order, the customer fields use.
#let PII_CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 &,.-/()#'@+:"
// Every PII line is padded to this many characters with U+00A0 so its glyph count, and so
// the redacted run's length, does not reveal the value's length.
#let PII_WIDTH = 34
#let PII_LINES = 3

#let accent = rgb("#0b5d6b")
#let muted = rgb("#5b6770")

#set document(title: "Eurekha Labs Test Report " + data.report.number, author: "Eurekha Labs Pvt. Ltd.")
#set text(font: BODY_FONT, size: 9.5pt, kerning: not OPT)
#set par(leading: 0.55em)

#let pii-line(s) = {
  assert(s.clusters().len() <= PII_WIDTH, message: "PII line longer than PII_WIDTH: " + s)
  for c in s.clusters() {
    assert(PII_CHARSET.contains(c), message: "PII char outside PII_CHARSET: " + c)
  }
  // box: a PII line must never wrap into a second run.
  box(s + "\u{00A0}" * (PII_WIDTH - s.clusters().len()))
}
// One PII field: fixed lines, each its own text run, kerning and ligatures off so a run
// is exactly one glyph per character.
#let pii(lines) = {
  let lines = if type(lines) == str { (lines,) } else { lines }
  assert(lines.len() <= PII_LINES, message: "too many PII lines")
  set text(font: PII_FONT, size: 8pt, kerning: false, ligatures: false)
  stack(spacing: 0.45em, ..lines.map(l => pii-line(l)))
}

#let report-url = "https://" + data.s3.bucket + ".s3.amazonaws.com/" + data.s3.key

#let header = {
  grid(
    columns: (1fr, auto),
    align: (left + horizon, right + horizon),
    [
      #text(size: 17pt, weight: BOLD, fill: accent)[EUREKHA LABS] \
      #text(size: 7.5pt, fill: muted)[Eurekha Labs Pvt. Ltd. · Food, Water & Environment Testing] \
      #text(size: 7.5pt, fill: muted)[Testing Lab Address : #data.lab.address]
    ],
    [
      #text(size: 13pt, weight: BOLD)[TEST REPORT] \
      #text(size: 7.5pt, fill: muted)[Accreditation No. #data.lab.accreditation]
    ],
  )
  v(4pt)
  line(length: 100%, stroke: 1.2pt + accent)
  v(2pt)
  grid(
    columns: (1fr, auto),
    [
      #data.report.ulr \
      Report Issue Date : #data.report.issue_date \
      Reference Number : #data.report.reference \
      Report Number : #data.report.number
    ],
    align(right + bottom, text(fill: muted)[Accredited Scope]),
  )
  v(6pt)
}

#set page(
  paper: "a4",
  margin: (x: 16mm, top: 46mm, bottom: 22mm),
  header-ascent: 6mm,
  header: header,
  footer: context {
    set text(size: 8pt, fill: muted)
    line(length: 100%, stroke: 0.4pt + muted)
    grid(
      columns: (1fr, auto),
      [Eurekha Labs Pvt. Ltd. · This is a computer generated report.],
      [Page #counter(page).display() of #counter(page).final().first()],
    )
  },
)

#let section(title) = block(
  width: 100%,
  inset: (x: 4pt, y: 3pt),
  fill: accent.lighten(85%),
  text(weight: BOLD, fill: accent, title),
)

#let kv(rows) = grid(
  columns: (auto, auto, 1fr),
  column-gutter: 6pt,
  row-gutter: 6pt,
  ..rows.map(((k, v)) => (k, ":", v)).flatten(),
)

// Invisible charset, must stay the first PII-font text in the document, see PII_CHARSET.
#place(top + left, text(font: PII_FONT, size: 1pt, fill: white, PII_CHARSET + "\u{00A0}"))

#section[Information Provided by Customer]
#grid(
  columns: (1.25fr, 1fr),
  column-gutter: 14pt,
  inset: (top: 4pt),
  kv((
    ("Client Name", pii(data.customer.name)),
    ("Address", pii(data.customer.address)),
    ("Contact Person", pii(data.customer.contact)),
  )),
  kv((
    ("Sampling Location", data.sample.location),
    ("Sample Sub Group", data.sample.sub_group),
    ("Sample Name", strong(data.sample.name)),
    ("Batch-No", data.sample.batch),
    ("Manufacturing Date", data.sample.mfg_date),
    ("Expiry Date", data.sample.expiry_date),
  )),
)

#v(6pt)
#section[Particulars of Sample Analysed]
#v(2pt)
#grid(
  columns: (1fr, 1fr),
  [Sampling Protocol : #data.sample.protocol],
  [Sample Collected by : #data.sample.collected_by],
)
#v(2pt)
Quantity & Condition : #data.sample.condition
#v(4pt)
#table(
  columns: (1fr,) * 4,
  align: center,
  stroke: 0.4pt + muted,
  table.header(..("Date of Sampling", "Date of Receipt", "Start Date of Analysis", "End Date of Analysis").map(strong)),
  data.dates.sampling, data.dates.receipt, data.dates.start, data.dates.end,
)

#v(4pt)
#align(center, text(weight: BOLD)[---------- Result of Analysis ----------])

#for group in data.results [
  #v(4pt)
  Discipline : #group.discipline #h(2em) Group : #group.group
  #v(2pt)
  #table(
    columns: (auto, 1.6fr, 1fr, 1.3fr, 1fr, 0.8fr, 0.8fr),
    align: (center, left, center, center, center, center, center),
    stroke: 0.4pt + muted,
    fill: (_, y) => if y == 0 { accent.lighten(85%) },
    // OPT: regular weight is narrower, so break "RDA Value*" by hand to keep the bold build's runs.
    table.header(..("No.", "Parameters", "Units", "Methods", "Results of Analysis", if OPT { [RDA \ Value\*] } else { "RDA Value*" }, "% RDA").map(strong)),
    ..group.rows.enumerate().map(((i, r)) => (
      str(i + 1), r.parameter, r.unit, r.method, strong(r.result), r.rda, r.rda_pct,
    )).flatten(),
  )
]

#text(size: 8pt)[
  \*Percentage contribution to Recommended Dietary Allowance calculated on basis of 2000 kcal energy \
  1 Serve = 100 g
]

#v(10pt)
#grid(
  columns: (1fr, auto),
  align: (left + bottom, center + bottom),
  [
    *Note:*
    #set text(size: 8pt)
    - This Report is valid for the tested sample only.
    - Test report shall not be reproduced except in full & with written approval of Eurekha Labs Pvt. Ltd.
    - The sample has been provided by the customer and results apply to the sample as received by the lab.
    - The information provided by the customer can affect the validity of results.
  ],
  [
    #let qr = qrcode(report-url, options: (scale: 1.6))
    // OPT: same QR as a raster image, sized like the vector one so page breaks do not move.
    #if OPT { context image(sys.inputs.qr, width: measure(qr).width, height: measure(qr).height) } else { qr } \
    #text(size: 7.5pt)[Download Report]
    #v(6pt)
    *#data.lab.signatory* \
    #text(size: 8pt)[#data.lab.signatory_title \ (Reviewed & Authorised By)]
  ],
)

#v(6pt)
#align(center, text(weight: BOLD)[---------- End Of Report ----------])

