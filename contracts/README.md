# Contracts

`TestFund` — one campaign per test request (id = request uuid, right-padded to bytes32).
Contributors pool tUSD up to $100. Anyone can take the job at any time by staking $110
(`commit`); `submitReport` within 30 days returns the stake. After the deadline anyone
can `slash`: the stake joins the pool and the job reopens. `MockUSD` is a 6-decimal test dollar with an open `mint`.

```sh
forge test
anvil &
forge script script/Deploy.s.sol --rpc-url http://127.0.0.1:8545 --broadcast \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
# copy the printed VITE_* lines into the root .env
```

Local test wallets (anvil defaults, pasteable into "Private key (testing only)"):
`0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d`,
`0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a`.
