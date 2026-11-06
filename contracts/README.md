# Contracts

`TestFund`: one pool per test request (id = request uuid, right-padded to bytes32).

- `contribute`: anyone chips in tUSD, up to the $100 goal.
- `commit`: anyone takes the job at any time by staking $110.
- `submitReport(id, backend, publicValues, proof, notarySignature)`: the tester posts a backend2-rs
  `sp1-groth16` proof of the lab report (checked by `EurekhaReportRegistry.check` from
  `../backend2-rs/contracts`) within 30 days. Pays the tester the stake plus the pool; whatever the pool
  was short of $100 is recorded as the tester's contribution. Each report can close one pool only.
- `slash`: after the deadline anyone forfeits the stake into the pool and the job reopens.
- `distribute(id, amount)`: admin only, on a tested pool. Pulls `amount` from the admin and pays each
  contributor their share (`contributed / total`).

`MockUSD` is a 6-decimal test dollar with an open `mint`.

```sh
forge test
anvil &
forge script script/Deploy.s.sol --rpc-url http://127.0.0.1:8545 --broadcast \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
# copy the printed VITE_* lines into the root .env
```

Deploy env (optional): `USD` reuses a token, `REGISTRY` reuses a registry (else one is deployed with
`NOTARY`, default the backend2-rs dev notary, and `VKEY`, default the live prover's SP1 program),
`ADMIN` (default the deployer).

Base Sepolia: TestFund `0x62b89329c709b008cC366FD22E8934931125c88E`, registry
`0x7b99B87c980E08Ee490B8F93EdC625c241697be4`, tUSD `0xbf73cf388CDcB0842E0eE8623E3836F8078Fb685`.

Local test wallets (anvil defaults, pasteable into "Private key (testing only)"):
`0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d`,
`0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a`.
