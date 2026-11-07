import { useCallback, useState } from 'react';
import { Link, useParams } from 'react-router';
import { buyUrl, imgFallback, imgSrc, label, productName, type TestRequest } from '@/lib/api';
import { useApi } from '@/lib/useApi';
import { ResultIcon } from '@/components/bits';
import { Fund, type PostedReport } from '@/components/Fund';
import { ProvenReport } from '@/components/ProvenReport';
import './Product.css';

export default function RequestDetail() {
	const { id = '' } = useParams();
	const { data: r, error, loading } = useApi<TestRequest>(`/api/test-requests/${encodeURIComponent(id)}`);
	const [report, setReport] = useState<PostedReport | null>(null);
	const onReport = useCallback((p: PostedReport) => setReport((old) => old ?? p), []);

	if (loading && !r) return <div className="page muted">Loading…</div>;
	if (error || !r) {
		return (
			<div className="page narrow">
				<p className="error">{error === 'Not found' ? 'Request not found.' : `Couldn't load the request: ${error}`}</p>
				<p><Link className="link" to="/request">Request a test</Link></p>
			</div>
		);
	}
	const name = productName(r);
	const requested = new Date(r.requested_on).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
	const tests = r.standard_tests ?? (r.tests ?? []).map((t) => ({ name: t, why: '' }));
	const facts = [
		['Brand', r.brand],
		['Category', label(r.category)],
		['Net quantity', r.net_quantity],
		['Manufacturer', r.manufacturer],
		['FSSAI licence', r.fssai_license],
		['Barcode', r.barcode]
	].filter(([, v]) => v) as [string, string][];

	return (
		<div className="page">
			<title>{`${r.brand} ${name} · test request · OpenLabel`}</title>
			<nav className="crumbs" aria-label="Breadcrumb"><Link to="/tests">Tests</Link><span aria-hidden="true">/</span><span>Requested</span></nav>

			<div className="p-top">
				<div className="p-gallery">
					<span className="photo contain p-main-photo">
						<img src={imgSrc(r.image_url ?? null, 1000)} alt={`${r.brand} ${name} pack`} referrerPolicy="no-referrer" onError={imgFallback} />
					</span>
				</div>

				<div className="p-center">
					<Link className="p-store" to={`/products?q=${encodeURIComponent(r.brand)}`}>Brand: {r.brand}</Link>
					<h1 className="p-title">{name}</h1>
					<p className="p-req-line muted">Requested {requested}. {report ? <>Tested: the lab report is proven on-chain. <a className="link" href="#proven">See the results</a></> : 'Not tested yet.'}</p>
					<hr />
					<table className="p-facts">
						<tbody>
							{facts.map(([k, v]) => <tr key={k}><th>{k}</th><td className={k === 'FSSAI licence' || k === 'Barcode' ? 'mono' : undefined}>{v}</td></tr>)}
						</tbody>
					</table>
					<hr />
					<h2 className="p-about-h">{report ? 'Standard tests' : "Tests we'll run"}</h2>
					<p className="small muted p-cov-hint">The standard tests for {label(r.category).toLowerCase()}. Tap one to see why it matters.</p>
					<ul className="p-cov">
						{tests.map((t) => (
							<li key={t.name}>
								<details>
									<summary>
										<ResultIcon kind="unk" size={20} />
										<span className="p-cov-n">{t.name}</span>
									</summary>
									{t.why && <p>{t.why}</p>}
								</details>
							</li>
						))}
					</ul>
				</div>

				<aside className="p-side" aria-label="Fund or buy">
					<div id="fund"><Fund requestId={r.id} title={`${r.brand} ${name}`} onReport={onReport} /></div>
					<div className="p-buy card">
						<p className="p-buy-price">See today’s price on Amazon</p>
						<a className="btn lg p-buy-btn" href={buyUrl(r)} target="_blank" rel="sponsored noopener">Buy on Amazon</a>
						<p className="p-buy-note">We may earn a commission from Amazon. It never changes a grade or a result.</p>
					</div>
				</aside>
			</div>

			{report && (
				<section className="p-section" id="proven" aria-labelledby="proven-title">
					<h2 id="proven-title" className="section-title">Lab report</h2>
					<ProvenReport id={report.id} reportBlock={report.reportBlock} />
				</section>
			)}
		</div>
	);
}
