import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { parseUnits, type Hex } from 'viem';
import { dismissReportTask, isActive, prove, savedProof, submit, useReportTask } from '@/lib/reportTask';
import { SubmitProof, TaskProgress } from './ReportTaskWindow';
import { ProvenReport } from './ProvenReport';
import {
	FUND_GOAL, FUND_STAKE, campaignId, ensureAllowance, fundAbi, fundAddress, publicClient, send, usd, usdAbi, usdAddress, useWallet
} from '@/lib/wallet';

const STATUS = ['Open', 'Pending', 'Submitted'] as const;
type Campaign = { pool: bigint; tester: Hex; deadline: Date; status: (typeof STATUS)[number]; reportBlock: bigint; mine: bigint; balance: bigint };

const firstLine = (e: unknown) =>
	e instanceof Error ? ('shortMessage' in e && String(e.shortMessage)) || e.message.split('\n')[0] : String(e);

export type PostedReport = { id: Hex; tester: Hex; reportBlock: bigint };

/** On-chain funding for one test request. With `onReport`, a posted report is handed to the page to show in full. */
export function Fund({ requestId, title, onReport }: { requestId: string; title: string; onReport?: (r: PostedReport) => void }) {
	const wallet = useWallet();
	const task = useReportTask();
	const id = campaignId(requestId);
	const [c, setC] = useState<Campaign | null>(null);
	const [busy, setBusy] = useState('');
	const [error, setError] = useState('');
	const [custom, setCustom] = useState('');
	const [pick, setPick] = useState<bigint>(parseUnits('10', 6));

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

	// A background prove-and-post for this pool finished while the page is open: show the result here.
	const posted = task?.id === id && task.phase === 'done';
	useEffect(() => {
		if (!posted) return;
		dismissReportTask();
		load().catch((e) => setError(firstLine(e)));
	}, [posted, load]);

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

	const submitted = c?.status === 'Submitted';
	useEffect(() => {
		if (submitted && onReport && c) onReport({ id, tester: c.tester, reportBlock: c.reportBlock });
	}, [submitted, onReport, c, id]);
	if (submitted && onReport) {
		return (
			<section className="fund card" aria-labelledby="fund-h">
				<h2 id="fund-h" className="fund-title">Tested</h2>
				<span className="tag tested" style={{ justifySelf: 'start' }}>Report posted</span>
				<p className="small muted">The tester's lab report is proven on-chain. <a className="link" href="#proven">See the results ↓</a></p>
			</section>
		);
	}
	if (submitted) return <ProvenReport id={id} reportBlock={c!.reportBlock} />;

	const chosen = custom ? customAmount : pick;
	const canGive = !!busy || !chosen || chosen > remaining;

	return (
		<section className="fund card" aria-labelledby="fund-h">
			<h2 id="fund-h" className="fund-title">Fund this test</h2>
			{!fundAddress ? (
				<p className="notice">On-chain funding isn't configured for this deployment.</p>
			) : !c ? (
				<p className="muted small">{error || 'Loading the campaign…'}</p>
			) : (
				<>
					<div className="fund-progress">
						<span className="bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}><span style={{ width: `${pct}%` }} /></span>
						<p className="fund-raised"><span><strong>{usd(c.pool)}</strong> raised of {usd(FUND_GOAL)}</span><span className="muted">{pct}%</span></p>
						{c.status === 'Open' && remaining === 0n && <span className="tag tested">Fully funded · needs a tester</span>}
						{c.status === 'Pending' && <p className="small muted"><span className="tag funded">Tester assigned</span> Report due {c.deadline.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}{late && <strong className="late"> · overdue</strong>}</p>}
					</div>

					{!wallet.address ? (
						<p className="fund-signin">Sign in (top right) to contribute or be the tester.</p>
					) : (
						<>
							{remaining > 0n && (
								<div className="fund-give">
									<div className="fund-chips" role="radiogroup" aria-label="Amount">
										{[1, 2, 10, 20].map((d) => {
											const amount = parseUnits(String(d), 6);
											const on = !custom && pick === amount;
											return (
												<button key={d} type="button" role="radio" aria-checked={on} className={`fund-chip${on ? ' on' : ''}`} disabled={!!busy || amount > remaining} onClick={() => { setPick(amount); setCustom(''); }}>
													${d}
												</button>
											);
										})}
										<input className={`fund-chip fund-other${custom ? ' on' : ''}`} inputMode="decimal" placeholder="Other amount, in $" aria-label="Other amount in dollars" value={custom} onChange={(e) => setCustom(e.target.value)} />
									</div>
									<button type="button" className="btn lg fund-btn" disabled={canGive} onClick={() => contribute(chosen)}>
										{busy === 'contribute' ? 'Contributing…' : chosen ? `Contribute ${usd(chosen)}` : 'Contribute'}
									</button>
								</div>
							)}
							{c.status === 'Open' && (
								<div className="fund-tester">
									<button type="button" className="btn lg outline fund-btn" disabled={!!busy} onClick={commit}>{busy === 'commit' ? 'Staking…' : 'Be the tester'}</button>
									<p className="small muted">Stake {usd(FUND_STAKE)} and take it to an accredited lab. You get the stake back, plus the pool, when you post the report.</p>
								</div>
							)}
							{late && <button type="button" className="btn outline fund-btn" disabled={!!busy} onClick={slash}>{busy === 'slash' ? 'Working…' : 'Reopen the job'}</button>}
							{c.status === 'Pending' && isTester && !late && <PostReport requestId={requestId} id={id} title={title} pool={c.pool} />}
							{busy && busy !== 'faucet' && <p className="small muted">Confirm in your wallet, then wait for the transaction to be mined…</p>}
							<p className="fund-wallet small muted">
								You've put in {usd(c.mine)} · Balance {usd(c.balance)}
								<button type="button" className="fund-link" onClick={faucet} disabled={!!busy}>{busy === 'faucet' ? 'Minting…' : 'Get 200 test dollars'}</button>
							</p>
						</>
					)}
					{error && <p className="error">{error}</p>}
				</>
			)}
			<p className="fund-lede small muted">
				Anyone can contribute any amount. If the tester misses the deadline, their stake goes to the pool and the job reopens.
			</p>
		</section>
	);
}

/** Tester only: upload the lab report PDF, prove it in the background (lib/reportTask), then Submit. */
function PostReport({ requestId, id, title, pool }: { requestId: string; id: Hex; title: string; pool: bigint }) {
	const task = useReportTask();
	const [pdf, setPdf] = useState<File | null>(null);
	const [error, setError] = useState('');
	const mine = task?.id === id ? task : null;
	const payout = usd(pool + FUND_STAKE);

	function start(e: FormEvent) {
		e.preventDefault();
		setError('');
		prove(requestId, id, title, pdf).catch((err: Error) => setError(err.message));
	}
	/** A proof saved before a reload: load it into the task and submit. */
	function submitSaved() {
		setError('');
		prove(requestId, id, title, null).then(submit, (err: Error) => setError(err.message));
	}

	return (
		<div className="post-report">
			<h3 className="fund-title">Post the lab report</h3>
			<p className="small muted">
				Upload the lab's PDF. We prove it came from the lab and publish only the test results, never your name or address.
				Submitting a valid proof pays you <strong>{payout}</strong> (your stake plus the pool){pool < FUND_GOAL && <>, and the {usd(FUND_GOAL - pool)} the pool was short counts as your contribution</>}.
			</p>
			{mine && (mine.phase === 'proving' || mine.phase === 'posting') && <TaskProgress task={mine} />}
			{mine && (mine.phase === 'ready' || mine.phase === 'posting') ? (
				<SubmitProof task={mine} />
			) : mine?.phase === 'proving' ? (
				<p className="small muted">You can leave this page; proving keeps going in the background.</p>
			) : savedProof(id) ? (
				<div className="task-submit">
					<button type="button" className="btn" disabled={isActive(task)} onClick={submitSaved}>Submit</button>
					<span className="small muted">Proof ready. Submit it to post the report and get paid.</span>
				</div>
			) : (
				<form className="fund-row" onSubmit={start}>
					<input type="file" accept="application/pdf" aria-label="Lab report PDF" onChange={(e) => setPdf(e.target.files?.[0] ?? null)} />
					<button className="btn" disabled={!pdf || isActive(task)}>Generate proof</button>
				</form>
			)}
			{(error || mine?.error) && <p className="error">{error || mine?.error}</p>}
		</div>
	);
}
