import { useSyncExternalStore } from 'react';
import {
	createPublicClient,
	createWalletClient,
	custom,
	formatUnits,
	http,
	pad,
	parseAbi,
	type Address,
	type EIP1193Provider,
	type Hex,
	type WalletClient
} from 'viem';
import { privateKeyToAccount } from 'viem/accounts';
import { anvil, baseSepolia, sepolia } from 'viem/chains';

const env = import.meta.env;
export const chain = [anvil, sepolia, baseSepolia].find((c) => c.id === Number(env.VITE_CHAIN_ID)) ?? anvil;
const rpc: string = env.VITE_RPC_URL || chain.rpcUrls.default.http[0];
export const fundAddress = env.VITE_FUND_ADDRESS as Address | undefined;
export const usdAddress = env.VITE_USD_ADDRESS as Address | undefined;
const wcProjectId: string | undefined = env.VITE_WC_PROJECT_ID;
export const hasWalletConnect = !!wcProjectId;
// Only for local testnets (anvil): set VITE_ALLOW_PRIVATE_KEY=true in .env to show it in Sign in.
export const allowPrivateKey = env.VITE_ALLOW_PRIVATE_KEY === 'true';

export const fundAbi = parseAbi([
	'function campaigns(bytes32) view returns (uint256 pool, address tester, uint64 deadline, uint8 status)',
	'function contributed(bytes32, address) view returns (uint256)',
	'function contribute(bytes32 id, uint256 amount)',
	'function commit(bytes32 id)',
	'function submitReport(bytes32 id)',
	'function slash(bytes32 id)'
]);
export const usdAbi = parseAbi([
	'function balanceOf(address) view returns (uint256)',
	'function allowance(address, address) view returns (uint256)',
	'function approve(address, uint256) returns (bool)',
	'function mint(address, uint256)'
]);

export const publicClient = createPublicClient({ chain, transport: http(rpc) });

type WalletState = { address: Address | null; client: WalletClient | null };

/** Current wallet. Read it in components with useWallet(); it is replaced (never mutated) on change. */
export let wallet: WalletState = { address: null, client: null };
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());
const subscribe = (l: () => void) => {
	listeners.add(l);
	return () => listeners.delete(l);
};
function setWallet(next: WalletState) {
	wallet = next;
	notify();
}
export const useWallet = () => useSyncExternalStore(subscribe, () => wallet);

/** Test-request uuid → bytes32 campaign id (uuid bytes, right-padded). */
export const campaignId = (uuid: string) => pad(`0x${uuid.replaceAll('-', '')}` as Hex, { dir: 'right', size: 32 });

export const usd = (v: bigint) => `$${formatUnits(v, 6)}`;

/** Cost of one test, in tUSD (6 decimals). */
export const FUND_GOAL = 100_000_000n;

/** Refundable stake to take a test, in tUSD (6 decimals). Mirrors TestFund.STAKE. */
export const FUND_STAKE = 110_000_000n;

export const short = (a: string) => `${a.slice(0, 6)}…${a.slice(-4)}`;

async function attachProvider(provider: EIP1193Provider) {
	const client = createWalletClient({ chain, transport: custom(provider) });
	const [address] = await client.requestAddresses();
	try {
		await client.switchChain({ id: chain.id });
	} catch {
		await client.addChain({ chain });
	}
	provider.on?.('accountsChanged', (accounts: string[]) => {
		const next = (accounts[0] as Address) ?? null;
		setWallet(next ? { ...wallet, address: next } : { address: null, client: null });
	});
	setWallet({ address, client });
}

type Announced = { info: { uuid: string; name: string; icon: string }; provider: EIP1193Provider };

/** Browser wallets that announced themselves via EIP-6963, so MetaMask isn't confused with other extensions. */
export let injected: Announced[] = [];
export const useInjected = () => useSyncExternalStore(subscribe, () => injected);

if (typeof window !== 'undefined') {
	window.addEventListener('eip6963:announceProvider', (e) => {
		const d = (e as CustomEvent<Announced>).detail;
		if (!injected.some((w) => w.info.uuid === d.info.uuid)) {
			injected = [...injected, d];
			notify();
		}
	});
	window.dispatchEvent(new Event('eip6963:requestProvider'));
}

/** Use any EIP-1193 provider as the signed-in wallet (e.g. Privy's embedded wallet). */
export const connectProvider = (provider: EIP1193Provider) => attachProvider(provider);

export async function connectInjected(provider?: EIP1193Provider) {
	const eth = provider ?? (window as { ethereum?: EIP1193Provider }).ethereum;
	if (!eth) throw new Error('No browser wallet found. Install MetaMask.');
	await attachProvider(eth);
}

export async function connectWalletConnect() {
	// Loaded on demand: the WalletConnect SDK is large and most visitors never use it.
	const { default: EthereumProvider } = await import('@walletconnect/ethereum-provider');
	const provider = await EthereumProvider.init({
		projectId: wcProjectId!,
		optionalChains: [chain.id],
		rpcMap: { [chain.id]: rpc },
		showQrModal: true
	});
	await provider.connect();
	await attachProvider(provider as unknown as EIP1193Provider);
}

export function connectPrivateKey(key: string) {
	const account = privateKeyToAccount((key.startsWith('0x') ? key : `0x${key}`) as Hex);
	setWallet({ address: account.address, client: createWalletClient({ account, chain, transport: http(rpc) }) });
}

export function disconnect() {
	setWallet({ address: null, client: null });
}

type Call = { address: Address; abi: typeof fundAbi | typeof usdAbi; functionName: string; args: readonly unknown[] };

/** Send a contract call from the connected wallet and wait until it is mined. */
export async function send(call: Call) {
	const { client, address } = wallet;
	if (!client || !address) throw new Error('Connect your wallet first.');
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	const hash = await client.writeContract({ ...call, account: client.account ?? address, chain } as any);
	const receipt = await publicClient.waitForTransactionReceipt({ hash });
	if (receipt.status !== 'success') throw new Error('Transaction reverted');
}

/** Approve the fund to pull `amount` tUSD if the current allowance is short. */
export async function ensureAllowance(amount: bigint) {
	const allowance = await publicClient.readContract({
		address: usdAddress!, abi: usdAbi, functionName: 'allowance', args: [wallet.address!, fundAddress!]
	});
	if (allowance < amount) await send({ address: usdAddress!, abi: usdAbi, functionName: 'approve', args: [fundAddress!, amount] });
}
