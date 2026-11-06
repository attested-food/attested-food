# ProofPlate: Verifiable Food Testing, with Privacy

## Summary

ProofPlate is a platform for sharing independently tested packaged-food reports without exposing the personal details of the person who commissioned the test. It also lets people pool funds to test products they want investigated.

A contributor uploads a lab report. ProofPlate checks its provenance using a lab’s digital signature or, where appropriate, a zero-knowledge proof of an email received from the lab. The contributor can then share verified findings while keeping details such as their name and address private. Reports and their verification status are linked to Ethereum, creating a public record that can be checked later.

## The problem

Food labels make claims about ingredients and nutrition, but consumers may want to check whether a product matches those claims—or test for substances that are not listed. Getting a product tested usually means paying a private lab and receiving a report that may contain personal information.

Sharing that report creates two problems: it can reveal the contributor’s identity or address, and other people may have no reliable way to tell whether the report really came from a lab or was altered.

There is also a cost barrier. One person may not want to pay for a test that would benefit many consumers.

## The solution

ProofPlate gives contributors a way to submit lab reports, prove selected details about their source and contents, and share the results with others while keeping personal information private.

The platform also supports community-funded testing. People can contribute toward testing a particular brand or product. Once the target is reached, the funds can be used to commission the test, and the resulting report can be published for everyone to review.

## How it works

1. A contributor submits a lab report and chooses which findings to make public.
2. ProofPlate checks the report’s source using a supported lab signature or a zero-knowledge proof tied to a lab email.
3. Personal details are removed or kept private. The report file can be stored off-chain, while its cryptographic hash and verification status are recorded on Ethereum.
4. Visitors can inspect the published findings and verify that the report matches the one committed on-chain.
5. For a product without a report, visitors can contribute to a test fund. The campaign tracks its goal and contributions transparently.

## Why Ethereum and zero-knowledge proofs

Ethereum provides a shared, tamper-evident record of report commitments and crowdfunding activity. A report’s contents can remain off-chain, while its hash makes later changes detectable.

Zero-knowledge proofs can help a contributor show that a report came through a supported lab communication channel or disclose specific report details without revealing the full document or their identity. Where labs provide digital signatures, ProofPlate can verify those signatures directly.

These checks establish evidence about a report’s source and integrity. They do not independently prove that a lab used sound methods or that its conclusions are correct.

## Hackathon MVP

The prototype will focus on one product category and a small set of sample reports. It will include:

- A page to upload a report and redact personal details.
- A verification flow for a supported lab email or digitally signed report.
- A public report page with selected findings and an on-chain report hash.
- A smart contract for product-specific testing campaigns and transparent contributions.

## Impact

ProofPlate aims to make food-testing information easier to share, check, and fund collectively. Consumers can learn from reports without needing access to the original contributor’s private information, and communities can coordinate testing when a product raises questions.
