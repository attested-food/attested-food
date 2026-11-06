# attested.food: Verifiable Food Testing, with Privacy

## Summary

attested.food is a platform for sharing independently tested packaged-food reports without exposing the personal details of the person who commissioned the test. It also lets people pool funds to test products they want investigated.

A contributor uploads a lab report. attested.food checks its provenance using a lab’s digital signature or, where appropriate, a zero-knowledge proof of an email received from the lab. The contributor can then share verified findings while keeping details such as their name and address private. Reports and their verification status are linked to Ethereum, creating a public record that can be checked later.

## The problem

Food labels make claims about ingredients and nutrition, but consumers may want to check whether a product matches those claims—or test for substances that are not listed. Getting a product tested usually means paying a private lab and receiving a report that may contain personal information.

Sharing that report creates two problems: it can reveal the contributor’s identity or address, and other people may have no reliable way to tell whether the report really came from a lab or was altered.

There is also a cost barrier. One person may not want to pay for a test that would benefit many consumers.

## Two data layers

**Primary: user-commissioned lab reports (the core USP).** A user buys a product, gets it tested at a reputed lab (e.g. Equinox Labs, Eurofins), and uploads the report PDF. attested.food proves the PDF genuinely came from that lab and has not been altered, while hiding the user's personal details (name, address, phone, email, etc.). Only the test findings are published.

**Fallback: data from existing trusted testing websites (bootstrap).** Before enough user reports exist, the product is empty. To bootstrap, we import published test results from established third-party testing sites (e.g. [Trustified](https://www.trustified.in/passandfail/truebasicsplantprotein)). These are shown with clear attribution: *"If you trust <source>, this is what <source> reports for this product."* We do not claim to have verified this data ourselves; it is the source's word.

Display rule per product:

1. If a verified user lab report exists → show it (primary).
2. Otherwise → show fallback data from trusted sources, labelled with the source and a link back.
3. If neither exists → offer a community-funded test campaign.

Candidate fallback sources are tracked in [data-sources.md](data-sources.md).

Target market: **India**. Products, brands, labs and fallback sources are all India-focused.

## Reference report (first user-tested product)

Kellogg's Choco Millet Muesli, tested at **Equinox Labs** (Navi Mumbai, NABL accredited, lab code TC-6820). The PDF is kept out of the repo because it contains personal details.

| Section | Fields | Public? |
|---|---|---|
| Report identity | ULR number (NABL), report number `EQNX:001:NL:26:10:09217`, issue date, "Download Report" QR | Yes (proof of origin) |
| Customer info | Client name, address, contact person | **No, hidden** |
| Sample | Product name, sub group, batch no., mfg/expiry date, quantity and condition, collected by | Yes |
| Dates | Receipt, analysis start and end | Yes |
| Results | Parameter, unit, method (SOP / AOAC), value, RDA, %RDA. In this report: added sugars, total sugars, carbohydrate, dietary fibre, energy, protein, total/saturated/unsaturated/trans fat, MUFA, PUFA, cholesterol, sodium | Yes |
| Authorisation | Signatory name and role, lab stamp | Yes |

Verification notes: the PDF has **no embedded digital signature** (it was rendered by headless Chrome), so origin cannot be proved from the file alone. Options are a ZK proof of the lab email that delivered the report, or proving the copy fetched from the lab's "Download Report" QR URL matches (e.g. zkTLS). The NABL ULR number can also be cross-checked.

## The solution

attested.food gives contributors a way to submit lab reports, prove selected details about their source and contents, and share the results with others while keeping personal information private.

The platform also supports community-funded testing. People can contribute toward testing a particular brand or product. Once the target is reached, the funds can be used to commission the test, and the resulting report can be published for everyone to review.

## How it works

1. A contributor submits a lab report and chooses which findings to make public.
2. attested.food checks the report’s source using a supported lab signature or a zero-knowledge proof tied to a lab email.
3. Personal details are removed or kept private. The report file can be stored off-chain, while its cryptographic hash and verification status are recorded on Ethereum.
4. Visitors can inspect the published findings and verify that the report matches the one committed on-chain.
5. For a product without a report, visitors can contribute to a test fund. The campaign tracks its goal and contributions transparently.

## Why Ethereum and zero-knowledge proofs

Ethereum provides a shared, tamper-evident record of report commitments and crowdfunding activity. A report’s contents can remain off-chain, while its hash makes later changes detectable.

Zero-knowledge proofs can help a contributor show that a report came through a supported lab communication channel or disclose specific report details without revealing the full document or their identity. Where labs provide digital signatures, attested.food can verify those signatures directly.

These checks establish evidence about a report’s source and integrity. They do not independently prove that a lab used sound methods or that its conclusions are correct.

## Hackathon MVP

The prototype will focus on one product category and a small set of sample reports. It will include:

- A page to upload a report and redact personal details.
- Fallback product data imported from trusted testing websites, shown when no verified user report exists.
- A verification flow for a supported lab email or digitally signed report.
- A public report page with selected findings and an on-chain report hash.
- A smart contract for product-specific testing campaigns and transparent contributions.

## Impact

attested.food aims to make food-testing information easier to share, check, and fund collectively. Consumers can learn from reports without needing access to the original contributor’s private information, and communities can coordinate testing when a product raises questions.
