import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { parseUnits, type Address } from 'viem';
import { productName, type TestRequest } from '@/lib/api';
import { useApi } from '@/lib/useApi';
import {
	campaignId, ensureAllowance, fundAbi, fundAddress, publicClient, send, short, usd, usdAbi, usdAddress, useIsAdmin, useWallet
} from '@/lib/wallet';

type Share = { address: Address; amount: bigint };

/** Admin only: pay revenue (e.g. affiliate income) to a tested pool's contributors, pro rata. */
export default function Distribute() {
	const isAdmin = useIsAdmin();
	const wallet = useWallet();
	const requests = useApi<TestRequest[]>('/api/test-requests');
	const [tested, setTested] = useState<TestRequest[] | null>(null);
	const [pick, setPick] = useState('');
	const [shares, setShares] = useState<{ list: Share[]; total: bigint } | null>(null);
	const [amount, setAmount] = useState('');
	const [balance, setBalance] = useState(0n);
	const [busy, setBusy] = useState(false);
	const [msg, setMsg] = useState('');
	const [error, setError] = useState('');

	useEffect(() => {
		if (!requests.data || !fundAddress) return;
		Promise.all(
			requests.data.map(async (r) => {
				const [, , , status] = await publicClient.readContract({ address: fundAddress!, abi: fundAbi, functionName: 'campaigns', args: [campaignId(r.id)] });
				return status === 2 ? r : null;
			})
		).then((rows) => setTested(rows.filter((r): r is TestRequest => !!r)), (e: Error) => setError(e.message.split('\n')[0]));
	}, [requests.data]);

	const loadShares = useCallback(async () => {
		if (!pick) return setShares(null);
		const id = campaignId(pick);
		const [list, campaign] = await Promise.all([
			publicClient.readContract({ address: fundAddress!, abi: fundAbi, functionName: 'contributors', args: [id] }),
			publicClient.readContract({ address: fundAddress!, abi: fundAbi, functionName: 'campaigns', args: [id] })
		]);
		const amounts = await Promise.all(
			list.map((a) => publicClient.readContract({ address: fundAddress!, abi: fundAbi, functionName: 'contributed', args: [id, a] }))
		);
		setShares({ list: list.map((a, i) => ({ address: a, amount: amounts[i] })), total: campaign[4] });
	}, [pick]);

	useEffect(() => {
		loadShares().catch((e: Error) => setError(e.message.split('\n')[0]));
	}, [loadShares]);

	useEffect(() => {
		if (wallet.address) publicClient.readContract({ address: usdAddress!, abi: usdAbi, functionName: 'balanceOf', args: [wallet.address] }).then(setBalance);
	}, [wallet.address, msg]);

	const value = /^\d+(\.\d{1,6})?$/.test(amount) ? parseUnits(amount, 6) : 0n;

	async function distribute(e: FormEvent) {
		e.preventDefault();
		setBusy(true);
		setError('');
		setMsg('');
		try {
			await ensureAllowance(value);
			await send({ address: fundAddress!, abi: fundAbi, functionName: 'distribute', args: [campaignId(pick), value] });
			setMsg(`Distributed ${usd(value)}.`);
		} catch (err) {
			setError(err instanceof Error ? (('shortMessage' in err && String(err.shortMessage)) || err.message.split('\n')[0]) : String(err));
		} finally {
			setBusy(false);
		}
	}

	if (!isAdmin) {
		return (
			<div className="page narrow">
				<title>Distribute · OpenLabel</title>
				<h1>Distribute</h1>
				<p className="notice">Only the admin can distribute funds. Sign in with the admin wallet.</p>
			</div>
		);
	}

	return (
		<div className="page narrow">
			<title>Distribute · OpenLabel</title>
			<div className="page-head">
				<div>
					<h1>Distribute to contributors</h1>
					<p className="lede">Pays an amount from your wallet to everyone who funded a tested product, in proportion to what each put in. A tester who covered a shortfall counts as a contributor for that part.</p>
				</div>
			</div>
			<form className="stack" onSubmit={distribute}>
				<label className="field">Product
					<select value={pick} onChange={(e) => setPick(e.target.value)} required>
						<option value="">{tested ? (tested.length ? 'Choose a tested product…' : 'No tested products yet') : 'Loading…'}</option>
						{tested?.map((r) => <option key={r.id} value={r.id}>{r.brand} · {productName(r)}</option>)}
					</select>
				</label>
				<label className="field">Amount (tUSD) · your balance {usd(balance)}
					<input inputMode="decimal" placeholder="e.g. 50" value={amount} onChange={(e) => setAmount(e.target.value)} required />
				</label>
				{shares && (
					<table>
						<thead><tr><th>Contributor</th><th>Put in</th><th>Share</th><th>Gets</th></tr></thead>
						<tbody>
							{shares.list.map((s) => (
								<tr key={s.address}>
									<td className="mono" title={s.address}>{short(s.address)}</td>
									<td>{usd(s.amount)}</td>
									<td>{shares.total ? `${(Number((s.amount * 10000n) / shares.total) / 100).toFixed(2)}%` : '—'}</td>
									<td>{shares.total ? usd((value * s.amount) / shares.total) : '—'}</td>
								</tr>
							))}
						</tbody>
					</table>
				)}
				<div>
					<button className="btn" disabled={busy || !pick || !value || value > balance}>{busy ? 'Distributing…' : `Distribute ${value ? usd(value) : ''}`}</button>
				</div>
				{busy && <p className="small muted">Confirm in your wallet, then wait for the transaction to be mined…</p>}
				{msg && <p className="notice">{msg}</p>}
				{error && <p className="error">{error}</p>}
			</form>
		</div>
	);
}
