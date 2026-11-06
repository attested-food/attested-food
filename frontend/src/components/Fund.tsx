import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { parseUnits } from 'viem';
import {
	FUND_GOAL, FUND_STAKE, campaignId, ensureAllowance, fundAbi, fundAddress, publicClient, send, usd, usdAbi, usdAddress, useWallet
} from '@/lib/wallet';

const STATUS = ['Open', 'Pending', 'Submitted'] as const;
type Campaign = { pool: bigint; tester: string; deadline: Date; status: (typeof STATUS)[number]; mine: bigint; balance: bigint };

const firstLine = (e: unknown) =>
	e instanceof Error ? ('shortMessage' in e && String(e.shortMessage)) || e.message.split('\n')[0] : String(e);

/** On-chain funding for one test request (TestFund contract). The tester stays anonymous. */
export function Fund({ requestId }: { requestId: string }) {
	const wallet = useWallet();
	const id = campaignId(requestId);
	const [c, setC] = useState<Campaign | null>(null);
	const [busy, setBusy] = useState('');
	const [error, setError] = useState('');
	const [custom, setCustom] = useState('');

	const load = useCallback(async () => {
		const [pool, tester, deadline, status] = await publicClient.readContract({ address: fundAddress!, abi: fundAbi, functionName: 'campaigns', args: [id] });
		const me = wallet.address;
		const [mine, balance] = me
			? await Promise.all([
					publicClient.readContract({ address: fundAddress!, abi: fundAbi, functionName: 'contributed', args: [id, me] }),
					publicClient.readContract({ address: usdAddress!, abi: usdAbi, functionName: 'balanceOf', args: [me] })
				])
			: [0n, 0n];
		setC({ pool, tester, deadline: new Date(Number(deadline) * 1000), status: STATUS[status], mine, balance });
	}, [id, wallet.address]);

	useEffect(() => {
		if (fundAddress) load().catch((e) => setError(`Could not read the campaign: ${firstLine(e)}`));
	}, [load]);

	async function act(name: string, fn: () => Promise<unknown>) {
		setBusy(name);
		setError('');
		try {
			await fn();
			await load();
		} catch (e) {
			setError(firstLine(e));
		} finally {
			setBusy('');
		}
	}

	const contribute = (amount: bigint) =>
		act('contribute', async () => {
			await ensureAllowance(amount);
			await send({ address: fundAddress!, abi: fundAbi, functionName: 'contribute', args: [id, amount] });
		});
	const commit = () =>
		act('commit', async () => {
			await ensureAllowance(FUND_STAKE);
			await send({ address: fundAddress!, abi: fundAbi, functionName: 'commit', args: [id] });
		});
	const call = (fn: 'submitReport' | 'slash') => act(fn, () => send({ address: fundAddress!, abi: fundAbi, functionName: fn, args: [id] }));
	const faucet = () => act('faucet', () => send({ address: usdAddress!, abi: usdAbi, functionName: 'mint', args: [wallet.address!, parseUnits('200', 6)] }));

	const remaining = c && c.pool < FUND_GOAL ? FUND_GOAL - c.pool : 0n;
	const customAmount = /^\d+(\.\d{1,6})?$/.test(custom) ? parseUnits(custom, 6) : 0n;
	const isTester = !!c && !!wallet.address && c.tester.toLowerCase() === wallet.address.toLowerCase();
	const late = !!c && c.status === 'Pending' && c.deadline.getTime() < Date.now();
	const pct = c ? Math.min(100, Number((c.pool * 100n) / FUND_GOAL)) : 0;

	return (
		<section className="fund card" aria-labelledby="fund-h">
			<h2 id="fund-h" className="fund-title">Fund this test</h2>
			<p className="muted fund-lede">
				Anyone can chip in. Anyone can also be the tester by putting down a refundable stake; it comes back when the report is posted.
				If the report isn't posted in time, the stake goes to the pool and the job reopens.
			</p>
			{!fundAddress ? (
				<p className="notice">On-chain funding isn't configured for this deployment.</p>
			) : !c ? (
				<p className="muted">{error || 'Loading the campaign…'}</p>
			) : (
				<>
					<span className="bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}><span style={{ width: `${pct}%` }} /></span>
					<p className="fund-raised">
						<span><strong>{usd(c.pool)}</strong> of {usd(FUND_GOAL)} raised</span>
						{c.status === 'Open' && remaining === 0n && <span className="tag tested">Fully funded · needs a tester</span>}
						{c.status === 'Pending' && <span className="tag funded">Tester assigned</span>}
						{c.status === 'Submitted' && <span className="tag tested">Report posted</span>}
					</p>
					{c.status === 'Pending' && (
						<p className="small muted">Report due {c.deadline.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}{late && <strong className="late"> · overdue</strong>}</p>
					)}
					{!wallet.address ? (
						<p className="notice">Sign in (top right) to chip in or be the tester.</p>
					) : (
						<>
							<p className="small muted">
								You've put in {usd(c.mine)} · Balance {usd(c.balance)} tUSD
								<button type="button" className="fund-link" onClick={faucet} disabled={!!busy}>{busy === 'faucet' ? 'Minting…' : 'Get 200 test dollars'}</button>
							</p>
							{c.status !== 'Submitted' && remaining > 0n && (
								<div className="fund-row">
									{[1, 2, 10, 20].map((d) => {
										const amount = parseUnits(String(d), 6);
										return <button key={d} type="button" className="btn sm" disabled={!!busy || amount > remaining} onClick={() => contribute(amount)}>${d}</button>;
									})}
									<form className="fund-row" onSubmit={(e: FormEvent) => { e.preventDefault(); contribute(customAmount); }}>
										<input className="fund-amount" inputMode="decimal" placeholder="Other $" aria-label="Other amount in dollars" value={custom} onChange={(e) => setCustom(e.target.value)} />
										<button className="btn sm outline" disabled={!!busy || !customAmount || customAmount > remaining}>Chip in</button>
									</form>
								</div>
							)}
							<div className="fund-row">
								{c.status === 'Open' && <button type="button" className="btn" disabled={!!busy} onClick={commit}>{busy === 'commit' ? 'Staking…' : 'Be the tester'}</button>}
								{c.status === 'Pending' && isTester && !late && <button type="button" className="btn" disabled={!!busy} onClick={() => call('submitReport')}>{busy === 'submitReport' ? 'Posting…' : 'Post the report'}</button>}
								{late && <button type="button" className="btn outline" disabled={!!busy} onClick={() => call('slash')}>{busy === 'slash' ? 'Working…' : 'Reopen the job'}</button>}
							</div>
							{busy && busy !== 'faucet' && <p className="small muted">Confirm in your wallet, then wait for the transaction to be mined…</p>}
						</>
					)}
					{error && <p className="error">{error}</p>}
				</>
			)}
		</section>
	);
}
