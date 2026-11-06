import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { label, nameOf, productName, type Category, type ProductCard, type TestRequest } from '@/lib/api';
import { useApi } from '@/lib/useApi';
import { FUND_GOAL, campaignId, fundAbi, fundAddress, publicClient, usd } from '@/lib/wallet';
import { Photo, StateTag, type TestState } from '@/components/bits';
import './Tests.css';

type Item = {
	key: string;
	to: string;
	img: string | null;
	cat: string | null;
	brand: string;
	name: string;
	tests: string;
	state: TestState;
	tag: string;
	pct?: number;
	raised?: string;
	status?: { t: string; c?: 'ok' | 'off' }[];
	action: string;
	alt?: string;
};

type Campaign = { pool: bigint; status: number };

/** Read each request's campaign from the TestFund contract, when this deployment has one. */
function useCampaigns(requests: TestRequest[] | null) {
	const [map, setMap] = useState<Record<string, Campaign> | null>(null);
	const [error, setError] = useState('');
	useEffect(() => {
		if (!fundAddress || !requests) return;
		let live = true;
		Promise.all(
			requests.map(async (r) => {
				const [pool, , , status] = await publicClient.readContract({ address: fundAddress!, abi: fundAbi, functionName: 'campaigns', args: [campaignId(r.id)] });
				return [r.id, { pool, status }] as const;
			})
		)
			.then((rows) => live && setMap(Object.fromEntries(rows)))
			.catch((e: Error) => live && setError(e.message.split('\n')[0]));
		return () => {
			live = false;
		};
	}, [requests]);
	return { map, error };
}

function Card({ it }: { it: Item }) {
	return (
		<li className="t-card card">
			<div className="t-top">
				<Photo src={it.img} alt="" className="t-photo" />
				<div className="t-text">
					<div className="t-meta"><span className="eyebrow">{label(it.cat)}</span><StateTag state={it.state} text={it.tag} /></div>
					<span className="muted small">{it.brand}</span>
					<Link to={it.to} className="t-name">{it.name}</Link>
				</div>
			</div>
			{it.tests && <div className="t-tests">Tests: <span>{it.tests}</span></div>}
			{it.pct !== undefined && (
				<div className="t-fund">
					<span className="bar"><span style={{ width: `${it.pct}%` }} /></span>
					<span className="small muted"><strong>{it.raised}</strong> of {usd(FUND_GOAL)}</span>
				</div>
			)}
			{it.status && (
				<div className="t-status">{it.status.map((s, i) => <span key={i} className={s.c ?? 'muted'}>{s.t}</span>)}</div>
			)}
			<div className="t-actions">
				<Link className="btn sm" to={it.to}>{it.action}</Link>
				{it.alt && <Link className="link small" to={`${it.to}#fund`}>{it.alt}</Link>}
			</div>
		</li>
	);
}

export default function Tests() {
	const requests = useApi<TestRequest[]>('/api/test-requests');
	const cats = useApi<Category[]>('/api/categories');
	const tested = useApi<{ items: ProductCard[] }>('/api/products?evidence=lab&page_size=24');
	const { map, error } = useCampaigns(requests.data);

	const testsFor = (c: string | null) => (cats.data?.find((x) => x.category === c)?.tests ?? []).join(', ');
	const cols: Record<'requested' | 'funding' | 'funded' | 'tested', Item[]> = { requested: [], funding: [], funded: [], tested: [] };

	for (const r of requests.data ?? []) {
		const base = { key: r.id, to: `/requests/${r.id}`, img: r.image_url ?? null, cat: r.category, brand: r.brand, name: productName(r), tests: testsFor(r.category) };
		const c = map?.[r.id];
		const pct = c ? Math.min(100, Number((c.pool * 100n) / FUND_GOAL)) : 0;
		if (!c || (c.status === 0 && c.pool === 0n)) {
			cols.requested.push({ ...base, state: 'requested', tag: 'Requested', pct: fundAddress ? 0 : undefined, raised: usd(0n), action: 'Fund this test', alt: 'Be the tester' });
		} else if (c.status === 0 && c.pool < FUND_GOAL) {
			cols.funding.push({ ...base, state: 'funding', tag: `Funding · ${pct}%`, pct, raised: usd(c.pool), action: 'Fund this test', alt: 'Be the tester' });
		} else if (c.status === 2) {
			cols.tested.push({ ...base, state: 'tested', tag: 'Report posted', status: [{ t: 'Report posted by the tester' }], action: 'See the test' });
		} else {
			const pending = c.status === 1;
			cols.funded.push({ ...base, state: 'funded', tag: pending ? 'At the lab' : 'Fully funded', status: [pending ? { t: 'Tester assigned' } : { t: 'Fully funded', c: 'ok' }, { t: pending ? 'Report on its way' : 'Needs a tester' }], action: pending ? 'Follow this test' : 'Be the tester' });
		}
	}
	for (const p of tested.data?.items ?? []) {
		cols.tested.push({ key: p.id, to: `/products/${p.id}`, img: p.image_url, cat: p.category, brand: p.brand, name: productName(p), tests: testsFor(p.category), state: 'tested', tag: 'Tested', status: [{ t: nameOf(p.latest?.lab ?? null) ?? 'Lab report' }], action: 'See results' });
	}

	const COLS = [
		['requested', '1', 'Requested', 'Waiting for the first backer.'],
		['funding', '2', 'Funding', 'People are chipping in toward the lab’s quote.'],
		['funded', '3', 'Funded', 'Fully funded, or a tester has taken it to a lab.'],
		['tested', '4', 'Tested', 'Report published.']
	] as const;
	const loading = requests.loading || tested.loading;

	return (
		<div className="page">
			<title>Requested & Funded Tests · OpenLabel</title>
			<div className="page-head">
				<div style={{ flex: '1 1 520px', minWidth: 0 }}>
					<h1>Requested &amp; Funded Tests</h1>
					<p className="lede">Ask for a product to be tested, chip in, or be the tester yourself. Every finished report is published in full.</p>
				</div>
				<Link className="btn lg" to="/request">Request a test</Link>
			</div>

			<ol className="t-rules" aria-label="How a test gets paid for">
				<li><b>1</b><span><strong>Chip in</strong><span className="muted">Each test is priced from the lab’s quote. Anyone can put in any amount.</span></span></li>
				<li><b>2</b><span><strong>Be the tester</strong><span className="muted">Put down a refundable stake and take the product to an accredited lab. The stake comes back when the report is posted.</span></span></li>
				<li><b>3</b><span><strong>Deliver in time</strong><span className="muted">Miss the deadline and the stake goes to the pool. The job reopens for someone else.</span></span></li>
			</ol>

			{!fundAddress && <p className="notice t-note">On-chain funding isn't configured for this deployment, so every request shows as Requested.</p>}
			{error && <p className="error t-note">Couldn't read campaigns: {error}</p>}
			{(requests.error || tested.error) && <p className="error t-note">Couldn't load tests: {requests.error ?? tested.error}</p>}

			<div className="t-cols">
				{COLS.map(([key, n, title, sub]) => (
					<section key={key} aria-label={title} className="t-col">
						<div className="t-col-head">
							<h2><span>{n}</span>{title}</h2>
							<span className="eyebrow">{cols[key].length} {cols[key].length === 1 ? 'test' : 'tests'}</span>
						</div>
						<p className="t-col-sub muted">{sub}</p>
						{loading && !cols[key].length ? (
							<p className="muted small">Loading…</p>
						) : cols[key].length ? (
							<ul className="t-list">{cols[key].map((it) => <Card key={it.key} it={it} />)}</ul>
						) : (
							<p className="muted small t-empty">Nothing here yet.</p>
						)}
					</section>
				))}
			</div>
		</div>
	);
}
