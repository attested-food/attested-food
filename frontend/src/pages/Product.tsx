import { Link, useParams } from 'react-router';
import { buyUrl, dash, httpUrl, label, nameOf, nutritionRows, productName, verdictText, type Finding, type Product as P, type ProductCard, type Report, type Result } from '@/lib/api';
import { sourceGrade } from '@/lib/grade';
import { useApi } from '@/lib/useApi';
import { GradeChip, Photo, StateTag } from '@/components/bits';
import { Segments } from '@/components/Segments';
import './Product.css';

const GROUPS = ['nutrition', 'heavy_metal', 'toxin', 'pesticide', 'spiking', 'other'];
const num = (v: number | null) => (v === null ? '—' : Math.abs(v) >= 100 ? String(Math.round(v)) : String(Math.round(v * 100) / 100));
const pct = (v: number) => `${v >= 0 ? '+' : '−'}${Math.round(Math.abs(v))}%`;
const day = (d: string | null) => (d ? new Date(d).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—');
const month = (d: string | null) => (d ? new Date(d).toLocaleDateString('en-IN', { month: 'long', year: 'numeric' }) : null);

function grouped(results: Result[]) {
	const groupOf = (r: Result) => (GROUPS.includes(r.group) ? r.group : 'other');
	return GROUPS.map((g) => [g, results.filter((r) => groupOf(r) === g)] as const).filter(([, rs]) => rs.length);
}

// Tested value differs from the label claim by more than 10%.
function offClaim(r: Result) {
	if (r.value === null || r.label_claim === null) return false;
	if (r.label_claim === 0) return r.value !== 0;
	return Math.abs(r.value - r.label_claim) / Math.abs(r.label_claim) > 0.1;
}

function summary(r: Report | undefined) {
	if (!r) return 'Not tested yet. Request a test and others can chip in.';
	const when = month(r.tested_on ?? r.issued_on);
	if (r.kind === 'user') return `Bought by a member and tested at ${r.lab?.name ?? 'an accredited lab'}${r.lab?.accreditation ? ` (${r.lab.accreditation})` : ''}${when ? ` in ${when}` : ''}.`;
	return `Tested${r.lab?.name ? ` by ${r.lab.name}` : ''} for ${r.publisher?.name ?? 'a testing website'}${when ? ` in ${when}` : ''}.`;
}

function gradeLabel(r: Report | undefined) {
	if (!r) return 'Not tested yet';
	if (r.kind === 'user') return 'Lab results · OpenLabel grade coming soon';
	return sourceGrade(r) ? `Grade by ${r.publisher?.name ?? 'the source'}` : 'No grade from the source';
}

function Key({ f }: { f: Finding }) {
	const bad = f.kind === 'bad';
	return (
		<li className="p-key">
			<span className={`p-ico ${f.kind}`} aria-hidden="true">{bad ? '✕' : '✓'}</span>
			<span className="p-key-t"><span>{f.parameter}</span><span className="muted">Label says {num(f.label)} {f.unit ?? ''}</span></span>
			<span className={bad ? 'off' : 'ok'}>{f.text.replace(' vs label', '')}</span>
		</li>
	);
}

function LabelVsLab({ findings }: { findings: Finding[] }) {
	return (
		<div className="p-lvl-wrap">
			<div className="p-lvl">
				<div className="p-lvl-row head"><span>Nutrient</span><span className="r">Label</span><span className="r">Lab</span><span className="c">−30% · label · +30%</span><span className="r">Diff</span><span>Result</span></div>
				{findings.map((f) => {
					const dev = f.deviation_pct ?? 0;
					const left = Math.max(2, Math.min(98, 50 + (dev / 30) * 50));
					const cls = f.kind === 'bad' ? 'off' : f.kind === 'good' ? 'ok' : '';
					return (
						<div key={f.parameter} className="p-lvl-row">
							<span className="b">{f.parameter}</span>
							<span className="r">{num(f.label)} {f.unit ?? ''}</span>
							<span className={`r b ${cls}`}>{num(f.tested)} {f.unit ?? ''}</span>
							<span className="p-dot">
								<span className="axis" />
								<span className="band" />
								<span className="mid" />
								<span className={`dot ${f.kind}`} style={{ left: `${left}%` }} />
							</span>
							<span className={`r b ${cls}`}>{pct(dev)}</span>
							<span className={`res ${cls}`}>{f.kind === 'bad' ? '✕ Off label' : f.kind === 'good' ? '✓ Better than label' : 'Within 10%'}</span>
						</div>
					);
				})}
			</div>
		</div>
	);
}

function ReportBlock({ r }: { r: Report }) {
	return (
		<article className="p-report">
			<div className="p-report-head">
				<span className={`tag ${r.kind === 'user' ? 'tested' : 'requested'}`}>{r.kind === 'user' ? 'Lab report' : 'Published test'}</span>
				<h3>{r.lab?.name ?? r.publisher?.name ?? 'Report'}</h3>
				{r.lab?.accreditation && <span className="eyebrow">{r.lab.accreditation}</span>}
				{r.kind === 'user' && <span className="p-check">{r.verified ? `Verified · ${r.verification.replace(/_/g, ' ')}` : 'Source check pending'}</span>}
			</div>
			{r.kind === 'fallback' && (
				<p className="notice p-attrib">
					Data as published by {httpUrl(r.source_url) ? <a className="link" href={httpUrl(r.source_url)!} rel="noopener">{r.publisher?.name ?? 'the source'}</a> : r.publisher?.name ?? 'the source'}
					{r.lab?.name ? `, tested by ${r.lab.name}` : ''}. Not independently verified by OpenLabel.
				</p>
			)}
			<div className="p-report-body">
				<dl className="p-meta">
					{r.kind === 'user' && <><dt>Report no.</dt><dd className="mono">{dash(r.report_number)}</dd><dt>ULR</dt><dd className="mono">{dash(r.ulr_number)}</dd></>}
					<dt>Batch</dt><dd className="mono">{dash(r.batch_no)}</dd>
					<dt>Manufactured</dt><dd>{day(r.mfg_date)}</dd>
					<dt>Best before</dt><dd>{day(r.expiry_date)}</dd>
					<dt>Tested</dt><dd>{day(r.tested_on)}</dd>
					<dt>Issued</dt><dd>{day(r.issued_on)}</dd>
					{verdictText(r) && <><dt>Verdict</dt><dd>{verdictText(r)}</dd></>}
				</dl>
				<div className="p-results">
					{r.verdict === 'fail' && !r.results.some((x) => x.status === 'fail') && (
						<p className="notice">{r.publisher?.name ?? 'The source'} marks this product as failed but publishes the failing values only as images.</p>
					)}
					{r.results.length ? (
						<div className="p-table-wrap">
							<table className="p-table">
								<thead><tr><th>Parameter</th><th className="r">Label claim</th><th className="r">Result</th><th>Unit</th><th>Limit / LOQ</th><th>Method</th><th>Status</th></tr></thead>
								<tbody>
									{grouped(r.results).map(([group, rows]) => [
										<tr key={group} className="group"><th colSpan={7}>{label(group)}</th></tr>,
										...rows.map((row, i) => (
											<tr key={`${group}-${i}`}>
												<td>{row.parameter}</td>
												<td className="r">{dash(row.label_claim)}</td>
												<td className={`r b${offClaim(row) ? ' off' : ''}`} title={offClaim(row) ? 'Differs from the label claim by more than 10%' : undefined}>{dash(row.value_raw)}</td>
												<td className="muted">{dash(row.unit)}</td>
												<td className="muted">{row.limit !== null ? row.limit : row.detection_limit !== null ? `LOQ ${row.detection_limit}` : '—'}</td>
												<td className="mono muted">{dash(row.method)}</td>
												<td className={row.status === 'fail' ? 'off' : row.status === 'pass' ? 'ok' : 'muted'}>{row.status ? row.status.toUpperCase() : '—'}</td>
											</tr>
										))
									])}
								</tbody>
							</table>
						</div>
					) : (
						<p className="muted">No results recorded for this report.</p>
					)}
				</div>
			</div>
			{r.kind === 'user' && <p className="small muted">The buyer's name and contact details on the report are hidden. Only the findings are published.</p>}
		</article>
	);
}

function Others({ product }: { product: P }) {
	const others = useApi<{ items: ProductCard[] }>(product.category ? `/api/products?category=${encodeURIComponent(product.category)}&page_size=4` : null);
	const items = (others.data?.items ?? []).filter((x) => x.id !== product.id).slice(0, 3);
	if (!items.length) return null;
	return (
		<section className="p-section" aria-labelledby="alt">
			<h2 id="alt" className="section-title">Others on this shelf</h2>
			<div className="p-others">
				{items.map((x) => (
					<Link key={x.id} to={`/products/${x.id}`} className="p-other card hoverable">
						<Photo src={x.image_url} alt="" style={{ width: 88, flex: '0 0 88px' }} />
						<span className="p-other-t">
							<span className="muted small">{x.brand}</span>
							<span className="p-other-name">{productName(x)}</span>
							<span className="p-other-g"><GradeChip grade={sourceGrade(x.latest)} /> <span className="eyebrow">{x.latest?.kind === 'user' ? 'Lab-tested' : x.latest ? `by ${nameOf(x.latest.publisher)}` : 'Not tested'}</span></span>
						</span>
					</Link>
				))}
			</div>
		</section>
	);
}

export default function Product() {
	const { id = '' } = useParams();
	const { data: p, error, loading } = useApi<P>(`/api/products/${encodeURIComponent(id)}`);

	if (loading && !p) return <div className="page muted">Loading…</div>;
	if (error || !p) {
		return (
			<div className="page narrow">
				<p className="error">{error === 'Not found' ? 'Product not found.' : `Couldn't load the product: ${error}`}</p>
				<p><Link className="link" to="/products">Back to the marketplace</Link></p>
			</div>
		);
	}

	const first = p.reports[0];
	const a = p.annotations;
	const compared = a.findings.filter((f) => f.label !== null);
	const keys = compared.filter((f) => f.kind !== 'info').sort((x, y) => (x.kind === 'bad' ? -1 : 0) - (y.kind === 'bad' ? -1 : 0)).slice(0, 3);
	const nut = nutritionRows(p.label_nutrition);
	const name = productName(p);

	return (
		<div className="page">
			<title>{`${p.brand} ${name} · OpenLabel`}</title>
			<nav className="crumbs" aria-label="Breadcrumb">
				<Link to="/products">Marketplace</Link>
				{p.category && <><span aria-hidden="true">/</span><Link to={`/products?category=${p.category}`}>{label(p.category)}</Link></>}
			</nav>

			<div className="p-hero">
				<Photo src={p.image_url} alt={`${p.brand} ${name} pack`} className="p-photo" />
				<div className="p-summary">
					<div className="p-row">
						<span className="eyebrow">{label(p.category)}{p.net_quantity ? ` · ${p.net_quantity}` : ''}</span>
						<StateTag state={p.reports.length ? 'tested' : 'requested'} />
					</div>
					<Link className="p-brand" to={`/products?q=${encodeURIComponent(p.brand)}`}>{p.brand}</Link>
					<h1 className="p-name">{name}</h1>
					<p className="p-lede">{summary(first)}</p>
					<div className="p-verdict">
						<GradeChip grade={sourceGrade(first)} size={64} />
						<div>
							<div className="eyebrow">{gradeLabel(first)}</div>
							<div className="p-counts">
								<span className="ok">✓ {a.counts.pass} pass</span>
								<span className="off">✕ {a.counts.fail} fail</span>
								<span className="muted">? {a.counts.untested} not tested</span>
							</div>
						</div>
					</div>
					{keys.length > 0 && <ul className="p-keys">{keys.map((f) => <Key key={f.parameter} f={f} />)}</ul>}
					<div className="p-actions">
						<a className="btn lg" href={buyUrl(p)} target="_blank" rel="sponsored noopener">Buy on Amazon</a>
						<Link className="btn lg outline" to="/request">Request more tests</Link>
					</div>
				</div>
			</div>

			{compared.length > 0 && (
				<section className="p-section" aria-labelledby="lvl">
					<div className="p-lvl-title">
						<h2 id="lvl">Label vs lab</h2>
						<span className="muted">Per 100 g. Shaded band = within 10% of the label. Dot = what the lab found.</span>
					</div>
					<LabelVsLab findings={compared} />
				</section>
			)}

			<div className="p-two">
				<section aria-labelledby="ing" className="p-ing-col">
					<h2 id="ing" className="section-title">Ingredients{a.segments.some((s) => s.mark) ? ', marked up' : ''}</h2>
					{p.ingredients ? (
						<>
							<p className="p-ing">{a.segments.length ? <Segments segments={a.segments} /> : p.ingredients}</p>
							<p className="small muted">
								{a.segments.some((s) => s.mark) && 'Marks come from the lab results; notes are numbers only. '}
								{p.ingredients_source === 'open_food_facts' && <>Ingredient list from <a className="link" href="https://world.openfoodfacts.org" rel="noopener">Open Food Facts</a> (CC BY-SA).</>}
							</p>
						</>
					) : (
						<p className="muted">Not on file yet.</p>
					)}
				</section>
				<section aria-labelledby="pack" className="p-pack-col">
					<h2 id="pack" className="section-title">On the pack</h2>
					{nut.length ? (
						<div className="nut-rows">{nut.map((n) => <div key={n.key}><span>{n.name}</span><strong>{n.value}</strong></div>)}</div>
					) : (
						<p className="muted">Not on file yet.</p>
					)}
					<h2 className="section-title" style={{ marginTop: 36 }}>What's been tested</h2>
					<ul className="p-cov">
						{p.tests.map((t) => (
							<li key={t.name}>
								<span className={`p-ico ${t.tested ? 'good' : 'unk'}`} aria-hidden="true">{t.tested ? '✓' : '?'}</span>
								<span>{t.name}</span>
								<span className="eyebrow">{t.tested ? 'Tested' : 'Not tested'}</span>
							</li>
						))}
					</ul>
					<p className="small muted">Want more checked? <Link className="link" to="/request">Request a test</Link> and others can chip in.</p>
				</section>
			</div>

			<section className="p-section" aria-labelledby="rep">
				<h2 id="rep" className="section-title">{p.reports.length === 1 ? 'Lab report' : `Reports (${p.reports.length})`}</h2>
				{p.reports.length ? p.reports.map((r) => <ReportBlock key={r.id} r={r} />) : <p className="muted">No reports yet.</p>}
			</section>

			<section className="p-section" aria-labelledby="details">
				<h2 id="details" className="section-title">Product details</h2>
				<dl className="p-meta" style={{ marginTop: 18 }}>
					<dt>Manufacturer</dt><dd>{dash(p.manufacturer)}</dd>
					<dt>FSSAI licence</dt><dd className="mono">{dash(p.fssai_license)}</dd>
					<dt>Barcode</dt><dd className="mono">{dash(p.barcode)}</dd>
					<dt>Net quantity</dt><dd>{dash(p.net_quantity)}</dd>
				</dl>
			</section>

			<Others product={p} />
		</div>
	);
}
