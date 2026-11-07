import { useEffect, useState, useSyncExternalStore } from 'react';
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
// Every chain above is a testnet, so Sign in offers a paste-a-private-key option for testing.
// The key stays in memory for the session only. Set VITE_ALLOW_PRIVATE_KEY=false to hide it.
export const allowPrivateKey = env.VITE_ALLOW_PRIVATE_KEY !== 'false';

export const fundAbi = parseAbi([
	'function campaigns(bytes32) view returns (uint256 pool, address tester, uint64 deadline, uint8 status, uint256 shares, uint64 reportBlock)',
	'function registry() view returns (address)',
	'event ReportSubmitted(bytes32 indexed id, address indexed tester, uint256 payout, bytes publicValues)',
	'function contributed(bytes32, address) view returns (uint256)',
	'function contributors(bytes32) view returns (address[])',
	'function admin() view returns (address)',
	'function contribute(bytes32 id, uint256 amount)',
	'function commit(bytes32 id)',
	'function submitReport(bytes32 id, bytes32 backend, bytes publicValues, bytes proof, bytes notarySignature)',
	'function slash(bytes32 id)',
	'function distribute(bytes32 id, uint256 amount)'
]);

/** The app admin (TestFund.admin), who can distribute revenue to a tested pool's contributors. */
export const useIsAdmin = () => {
	const { address } = useWallet();
	const [admin, setAdmin] = useState<Address | null>(null);
	useEffect(() => {
		if (fundAddress) publicClient.readContract({ address: fundAddress, abi: fundAbi, functionName: 'admin' }).then(setAdmin, () => setAdmin(null));
	}, []);
	return !!address && !!admin && address.toLowerCase() === admin.toLowerCase();
};
/** EurekhaReportRegistry.decode: the report a proof's public values commit to. */
export const registryAbi = parseAbi([
	'struct Head { bytes header; uint64 sessionTime; string serverName; bytes32 keySha256; bytes32 bodyCommitment; uint32 pdfLen; bytes32 redactedSha256; uint256 spansAt; }',
	'struct KeyValue { string key; string value; }',
	'struct Row { string discipline; string group; string parameter; string unit; string method; string result; string rda; string rdaPct; }',
	'function decode(bytes publicValues) pure returns (Head h, uint32[2][] spans, KeyValue[] kv, Row[] rows)'
]);

export const txUrl = (hash: string) => (chain.blockExplorers?.default.url ? `${chain.blockExplorers.default.url}/tx/${hash}` : null);

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

async function attachProvider(provider: EIP1193Provider, silent = false) {
	const client = createWalletClient({ chain, transport: custom(provider) });
	const [address] = silent ? await client.getAddresses() : await client.requestAddresses();
	if (!address) throw new Error('Wallet is not connected to this site.');
	try {
		await client.switchChain({ id: chain.id });
	} catch {
		await client.addChain({ chain });
	}
	provider.on?.('accountsChanged', (accounts: string[]) => {
		const next = (accounts[0] as Address) ?? null;
		if (!next) forget();
		setWallet(next ? { ...wallet, address: next } : { address: null, client: null });
	});
	setWallet({ address, client });
}

type Announced = { info: { uuid: string; name: string; icon: string; rdns?: string }; provider: EIP1193Provider };

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

// Which wallet to reconnect after a reload: the browser wallet's EIP-6963 rdns (e.g. io.metamask) or
// WalletConnect. Never a key; private-key sign-in stays in memory only.
type Remembered = { kind: 'injected'; rdns: string | null } | { kind: 'walletconnect' };
const REMEMBER = 'wallet:last';
function remember(r: Remembered) {
	try { localStorage.setItem(REMEMBER, JSON.stringify(r)); } catch { /* storage unavailable: no reconnect after reload */ }
}
function forget() {
	try { localStorage.removeItem(REMEMBER); } catch { /* storage unavailable */ }
}

export async function connectInjected(provider?: EIP1193Provider) {
	const eth = provider ?? (window as { ethereum?: EIP1193Provider }).ethereum;
	if (!eth) throw new Error('No browser wallet found. Install MetaMask.');
	await attachProvider(eth);
	remember({ kind: 'injected', rdns: injected.find((w) => w.provider === eth)?.info.rdns ?? null });
}

async function walletConnectProvider() {
	// Loaded on demand: the WalletConnect SDK is large and most visitors never use it.
	const { default: EthereumProvider } = await import('@walletconnect/ethereum-provider');
	return EthereumProvider.init({
		projectId: wcProjectId!,
		optionalChains: [chain.id],
		rpcMap: { [chain.id]: rpc },
		showQrModal: true
	});
}

export async function connectWalletConnect() {
	const provider = await walletConnectProvider();
	await provider.connect();
	await attachProvider(provider as unknown as EIP1193Provider);
	remember({ kind: 'walletconnect' });
}

/** After a reload, quietly reconnect the wallet used last time if it still trusts this site. */
async function reconnect() {
	let r: Remembered | null = null;
	try { r = JSON.parse(localStorage.getItem(REMEMBER) ?? 'null'); } catch { return; }
	if (!r || wallet.address) return;
	try {
		if (r.kind === 'walletconnect') {
			if (!wcProjectId) return forget();
			const provider = await walletConnectProvider();
			if (!provider.session) return forget();
			await attachProvider(provider as unknown as EIP1193Provider, true);
		} else {
			const rdns = r.rdns;
			// Extensions announce themselves right after load; give them a moment.
			await new Promise((res) => setTimeout(res, 300));
			const eth = (rdns && injected.find((w) => w.info.rdns === rdns)?.provider) || (window as { ethereum?: EIP1193Provider }).ethereum;
			if (!eth) return;
			await attachProvider(eth, true);
		}
	} catch (e) {
		console.warn('[wallet] could not reconnect', e);
		forget();
	}
}

export function connectPrivateKey(key: string) {
	const account = privateKeyToAccount((key.startsWith('0x') ? key : `0x${key}`) as Hex);
	setWallet({ address: account.address, client: createWalletClient({ account, chain, transport: http(rpc) }) });
}

export function disconnect() {
	forget();
	setWallet({ address: null, client: null });
}

if (typeof window !== 'undefined') reconnect();

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
