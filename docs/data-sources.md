# Fallback data sources (India)

Third-party sites that publish lab test results for products sold in India. Used only as **fallback** data when no verified user lab report exists (see [idea.md](idea.md#two-data-layers)). Always shown with source attribution and a link back.

Status: candidate list, checked Nov 2026. Not yet approved for scraping; check each site's terms first.

## Recommended

| Source | Coverage | What a product page shows | Sample |
|---|---|---|---|
| Unbox Health | Broad Indian packaged food plus supplements: cereals and muesli, snacks, biscuits, ghee, oils, honey, noodles, protein and more | Grade A+ to D, labs used (Eurofins, ALS), batch no., **label claim vs tested value** with an accuracy score per parameter, toxins (aflatoxin, lead, mercury). Report PDFs require login. | https://www.unboxhealth.in/explore/product/patanjali-cow-ghee/0ecbe039-9606-4e5d-8df9-b7b4e2299fa3 |
| Trustified | Mostly Indian protein and supplement brands (MuscleBlaze, Avvatar, AS-IT-IS, Nutrabox, Nakpro, The Whole Truth, Mille...), a few foods (protein bar, protein flour) | Pass/fail per batch, tested by Eurofins, published date; label accuracy, amino and melamine spiking, heavy metals, aflatoxins, pesticides (some values only as images) | https://www.trustified.in/passandfail/truebasicsplantprotein |

## Maybe

| Source | Why maybe | Sample |
|---|---|---|
| Labdoor | US site, but has graded a few Indian protein products (MuscleBlaze, Bal Bharat, MyProtein India) | https://labdoor.com/review/muscleblaze-biozyme-performance-whey |
| Consumer Voice (VOICE magazine) | Indian comparative lab tests of named brands, including breakfast cereals, but old and published as PDFs, not per-product pages | https://consumeraffairs.nic.in/sites/default/files/file-uploads/ctocpas/corn%20flakes-12.pdf |
| Citizens Protein Project | One-off peer-reviewed study of about 36 Indian protein powders with brand-wise results; static paper, not a feed | https://pmc.ncbi.nlm.nih.gov/articles/PMC10994440/ (behind a captcha, not verified) |

## Dropped

- **Food Pharmer**: "label reviewed" only, no lab values on product pages.
- **Clean Label Project, ConsumerLab, Informed Sport, NSF**: US/global brands; little or no Indian coverage.
