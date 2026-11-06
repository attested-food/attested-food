import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { parseUnits, stringToHex, type Hex } from 'viem';
import { MOCK_PROVER, mockProof, pollJob, startProof, type Job } from '@/lib/prover';
import { ProvenReport } from './ProvenReport';
import {
	FUND_GOAL, FUND_STAKE, campaignId, ensureAllowance, fundAbi, fundAddress, publicClient, send, usd, usdAbi, usdAddress, useWallet
} from '@/lib/wallet';

const STATUS = ['Open', 'Pending', 'Submitted'] as const;
type Campaign = { pool: bigint; tester: Hex; deadline: Date; status: (typeof STATUS)[number]; reportBlock: bigint; mine: bigint; balance: bigint };

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
		const [pool, tester, deadline, status, , reportBlock] = await publicClient.readContract({ address: fundAddress!, abi: fundAbi, functionName: 'campaigns', args: [id] });
		const me = wallet.address;
		const [mine, balance] = me
			? await Promise.all([
					publicClient.readContract({ address: fundAddress!, abi: fundAbi, functionName: 'contributed', args: [id, me] }),
					publicClient.readContract({ address: usdAddress!, abi: usdAbi, functionName: 'balanceOf', args: [me] })
				])
			: [0n, 0n];
		setC({ pool, tester, deadline: new Date(Number(deadline) * 1000), status: STATUS[status], reportBlock, mine, balance });
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
	const slash = () => act('slash', () => send({ address: fundAddress!, abi: fundAbi, functionName: 'slash', args: [id] }));
	const faucet = () => act('faucet', () => send({ address: usdAddress!, abi: usdAbi, functionName: 'mint', args: [wallet.address!, parseUnits('200', 6)] }));

	const remaining = c && c.pool < FUND_GOAL ? FUND_GOAL - c.pool : 0n;
	const customAmount = /^\d+(\.\d{1,6})?$/.test(custom) ? parseUnits(custom, 6) : 0n;
	const isTester = !!c && !!wallet.address && c.tester.toLowerCase() === wallet.address.toLowerCase();
	const late = !!c && c.status === 'Pending' && c.deadline.getTime() < Date.now();
	const pct = c ? Math.min(100, Number((c.pool * 100n) / FUND_GOAL)) : 0;

	if (c?.status === 'Submitted') return <ProvenReport id={id} tester={c.tester} reportBlock={c.reportBlock} />;

	return (
		<section className="fund card" aria-labelledby="fund-h">
			<h2 id="fund-h" className="fund-title">Fund this test</h2>
			<p className="muted fund-lede">
				Anyone can contribute. Anyone can also be the tester by putting down a refundable stake; it comes back when the report is posted.
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
					</p>
					{c.status === 'Pending' && (
						<p className="small muted">Report due {c.deadline.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}{late && <strong className="late"> · overdue</strong>}</p>
					)}
					{!wallet.address ? (
						<p className="notice">Sign in (top right) to contribute or be the tester.</p>
					) : (
						<>
							<p className="small muted">
								You've put in {usd(c.mine)} · Balance {usd(c.balance)} tUSD
								<button type="button" className="fund-link" onClick={faucet} disabled={!!busy}>{busy === 'faucet' ? 'Minting…' : 'Get 200 test dollars'}</button>
							</p>
							{remaining > 0n && (
								<div className="fund-row">
									{[1, 2, 10, 20].map((d) => {
										const amount = parseUnits(String(d), 6);
										return <button key={d} type="button" className="btn sm" disabled={!!busy || amount > remaining} onClick={() => contribute(amount)}>${d}</button>;
									})}
									<form className="fund-row" onSubmit={(e: FormEvent) => { e.preventDefault(); contribute(customAmount); }}>
										<input className="fund-amount" inputMode="decimal" placeholder="Other $" aria-label="Other amount in dollars" value={custom} onChange={(e) => setCustom(e.target.value)} />
										<button className="btn sm outline" disabled={!!busy || !customAmount || customAmount > remaining}>Contribute</button>
									</form>
								</div>
							)}
							<div className="fund-row">
								{c.status === 'Open' && <button type="button" className="btn" disabled={!!busy} onClick={commit}>{busy === 'commit' ? 'Staking…' : 'Be the tester'}</button>}
								{late && <button type="button" className="btn outline" disabled={!!busy} onClick={slash}>{busy === 'slash' ? 'Working…' : 'Reopen the job'}</button>}
							</div>
							{c.status === 'Pending' && isTester && !late && <PostReport id={id} pool={c.pool} onPosted={load} />}
							{busy && busy !== 'faucet' && <p className="small muted">Confirm in your wallet, then wait for the transaction to be mined…</p>}
						</>
					)}
					{error && <p className="error">{error}</p>}
				</>
			)}
		</section>
	);
}

type Artifact = { publicValues: Hex; proof: Hex; notarySignature: Hex };
const hex = (v: unknown) => (String(v).startsWith('0x') ? String(v) : `0x${v}`) as Hex;
const saved = (id: string): Artifact | null => {
	try {
		return JSON.parse(localStorage.getItem(`proof:${id}`) ?? 'null');
	} catch {
		return null;
	}
};

/** Tester only: upload the lab report PDF, prove it with backend2-rs, post the proof to TestFund. */
function PostReport({ id, pool, onPosted }: { id: Hex; pool: bigint; onPosted: () => Promise<void> }) {
	const [pdf, setPdf] = useState<File | null>(null);
	const [job, setJob] = useState<Job | null>(null);
	const [artifact, setArtifact] = useState<Artifact | null>(() => saved(id));
	const [busy, setBusy] = useState('');
	const [error, setError] = useState('');
	const payout = usd(pool + FUND_STAKE);

	async function post(a: Artifact) {
		setBusy('post');
		setError('');
		try {
			await send({
				address: fundAddress!, abi: fundAbi, functionName: 'submitReport',
				args: [id, stringToHex('sp1', { size: 32 }), a.publicValues, a.proof, a.notarySignature]
			});
			try { localStorage.removeItem(`proof:${id}`); } catch { /* storage unavailable */ }
			await onPosted();
		} catch (e) {
			setError(firstLine(e));
		} finally {
			setBusy('');
		}
	}

	async function prove(e: FormEvent) {
		e.preventDefault();
		if (!pdf) return;
		setBusy('prove');
		setError('');
		setJob(null);
		try {
			const done = MOCK_PROVER ? await mockProof(setJob) : await pollJob(await startProof(pdf), setJob);
			const raw = done.result?.artifact as Record<string, unknown> | undefined;
			if (done.status === 'failed' || !raw) throw new Error(done.error ?? 'The prover returned no proof.');
			const a = { publicValues: hex(raw.publicValues), proof: hex(raw.proof), notarySignature: hex(raw.notarySignature) };
			setArtifact(a);
			try { localStorage.setItem(`proof:${id}`, JSON.stringify(a)); } catch { /* storage unavailable */ }
			await post(a);
		} catch (err) {
			setError(firstLine(err));
			setBusy('');
		}
	}

	return (
		<div className="post-report">
			<h3 className="fund-title">Post the lab report</h3>
			<p className="small muted">
				Upload the lab's PDF. We prove it came from the lab and publish only the test results, never your name or address.
				A valid proof pays you <strong>{payout}</strong> (your stake plus the pool){pool < FUND_GOAL && <>, and the {usd(FUND_GOAL - pool)} the pool was short counts as your contribution</>}.
			</p>
			{artifact && busy !== 'prove' ? (
				<div className="fund-row">
					<button type="button" className="btn" disabled={!!busy} onClick={() => post(artifact)}>{busy === 'post' ? 'Posting…' : 'Post the proof'}</button>
					<span className="small muted">Proof ready.</span>
				</div>
			) : (
				<form className="fund-row" onSubmit={prove}>
					<input type="file" accept="application/pdf" aria-label="Lab report PDF" onChange={(e) => setPdf(e.target.files?.[0] ?? null)} disabled={!!busy} />
					<button className="btn" disabled={!pdf || !!busy}>{busy === 'prove' ? 'Proving…' : 'Prove and post'}</button>
				</form>
			)}
			{job && busy === 'prove' && (
				<p className="small muted">
					Proving: {job.stage ?? job.status}, {Math.round(job.elapsedMs / 1000)} s
					{job.progress?.fraction != null && <> · ~{Math.round(job.progress.fraction * 100)}%</>}. This takes a few minutes; keep this tab open.
				</p>
			)}
			{error && <p className="error">{error}</p>}
		</div>
	);
}
