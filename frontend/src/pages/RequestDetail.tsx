import { Link, useParams } from 'react-router';
import { buyUrl, dash, httpUrl, label, productName, type TestRequest } from '@/lib/api';
import { useApi } from '@/lib/useApi';
import { Photo, ResultIcon, StateTag } from '@/components/bits';
import { Fund } from '@/components/Fund';
import './Product.css';

export default function RequestDetail() {
	const { id = '' } = useParams();
	const { data: r, error, loading } = useApi<TestRequest>(`/api/test-requests/${encodeURIComponent(id)}`);

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

	return (
		<div className="page">
			<title>{`${r.brand} ${name} · test request · OpenLabel`}</title>
			<nav className="crumbs" aria-label="Breadcrumb"><Link to="/tests">Tests</Link><span aria-hidden="true">/</span><span>Requested</span></nav>
			<div className="p-hero">
				<Photo src={r.image_url} alt={`${r.brand} ${name} pack`} className="p-photo" />
				<div className="p-summary">
					<div className="p-row">
						<span className="eyebrow">{label(r.category)}{r.net_quantity ? ` · ${r.net_quantity}` : ''}</span>
						<StateTag state="requested" />
					</div>
					<div className="p-brand">{r.brand}</div>
					<h1 className="p-name">{name}</h1>
					<p className="p-lede">Requested on {requested}. <a className="link" href={buyUrl(r)} target="_blank" rel="sponsored noopener">Buy it on Amazon</a></p>
					<div id="fund"><Fund requestId={r.id} /></div>

					<h2 className="section-title" style={{ marginTop: 40 }}>Tests we'll run</h2>
					<ul className="p-cov">
						{(r.tests ?? []).map((t) => (
							<li key={t}><ResultIcon kind="unk" size={20} /><span>{t}</span><span className="eyebrow">Not tested</span></li>
						))}
					</ul>

					<h2 className="section-title" style={{ marginTop: 40 }}>Details</h2>
					<dl className="p-meta" style={{ marginTop: 18 }}>
						<dt>Net quantity</dt><dd>{dash(r.net_quantity)}</dd>
						<dt>Manufacturer</dt><dd>{dash(r.manufacturer)}</dd>
						<dt>FSSAI licence</dt><dd className="mono">{dash(r.fssai_license)}</dd>
						<dt>Barcode</dt><dd className="mono">{dash(r.barcode)}</dd>
						<dt>Where to buy</dt><dd>{httpUrl(r.buy_url ?? null) ? <a className="link" href={httpUrl(r.buy_url ?? null)!} rel="noopener">{r.buy_url}</a> : '—'}</dd>
					</dl>
				</div>
			</div>
		</div>
	);
}
