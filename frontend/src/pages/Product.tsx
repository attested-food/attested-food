import { Link, useParams } from 'react-router';
import { buyUrl, dash, httpUrl, imgFallback, imgSrc, label, nutritionRows, productName, verdictText, type Finding, type Product as P, type ProductCard, type Report, type Result } from '@/lib/api';
import { sourceGrade } from '@/lib/grade';
import { useApi } from '@/lib/useApi';
import { GradeChip, GradeTag, Photo, ResultCounts, ResultIcon, StateTag } from '@/components/bits';
import { gradeInfo } from './Marketplace';
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
	if (!r) return 'Not tested yet. Request a test and others can help fund it.';
	const when = month(r.tested_on ?? r.issued_on);
	if (r.kind === 'user') return `Bought by a member and tested at ${r.lab?.name ?? 'an accredited lab'}${r.lab?.accreditation ? ` (${r.lab.accreditation})` : ''}${when ? ` in ${when}` : ''}.`;
	return `Tested${r.lab?.name ? ` by ${r.lab.name}` : ''} for ${r.publisher?.name ?? 'a testing website'}${when ? ` in ${when}` : ''}.`;
}

function gradeLabel(r: Report | undefined, ours: P['openlabel_grade']) {
	if (!r) return 'Not tested yet';
	if (ours) return ours.provisional ? 'OpenLabel grade · provisional until all standard tests are done' : 'OpenLabel grade';
	if (r.kind === 'user') return 'Tested through OpenLabel';
	return sourceGrade(r) ? `Graded by ${r.publisher?.name ?? 'the source'}` : `Tested for ${r.publisher?.name ?? 'a testing website'}`;
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
							<span className={`res ${cls}`}><ResultIcon kind={f.kind} size={16} />{f.kind === 'bad' ? 'Off label' : f.kind === 'good' ? 'Better than label' : 'Within 10%'}</span>
						</div>
					);
				})}
			</div>
		</div>
	);
}

function ReportBlock({ r, findings }: { r: Report; findings: Finding[] }) {
	const pdf = httpUrl(r.pdf_url);
	const source = httpUrl(r.source_url);
	const off = Math.max(findings.filter((f) => f.kind === 'bad').length, r.results.filter(offClaim).length);
	const failed = r.results.filter((x) => x.status === 'fail').length;
	const passed = r.results.filter((x) => x.status === 'pass').length;
	// The few things worth reading first: label mismatches, then failed/passed limits.
	const highlights = [
		...findings.filter((f) => f.kind !== 'info').map((f) => ({ kind: f.kind, t: f.parameter, r: f.text })),
		...r.results.filter((x) => x.status === 'fail').map((x) => ({ kind: 'bad' as const, t: x.parameter, r: `${x.value_raw}${x.unit ? ` ${x.unit}` : ''}, over the limit` }))
	]
		.sort((x, y) => (x.kind === 'bad' ? 0 : 1) - (y.kind === 'bad' ? 0 : 1))
		.slice(0, 4);
	const keyFacts = [
		r.tested_on ? ['Tested', day(r.tested_on)] : r.issued_on ? ['Issued', day(r.issued_on)] : null,
		r.batch_no ? ['Batch', r.batch_no] : null,
		r.kind === 'user' && r.report_number ? ['Report no.', r.report_number] : null
	].filter(Boolean) as [string, string][];
	const moreFacts = [
		r.kind === 'user' && r.ulr_number ? ['ULR', r.ulr_number] : null,
		r.mfg_date ? ['Manufactured', day(r.mfg_date)] : null,
		r.expiry_date ? ['Best before', day(r.expiry_date)] : null,
		r.tested_on && r.issued_on ? ['Issued', day(r.issued_on)] : null,
		verdictText(r) ? ['Verdict', verdictText(r)] : null
	].filter(Boolean) as [string, string][];
	const summary = [`${r.results.length} ${r.results.length === 1 ? 'result' : 'results'}`, off ? `${off} off the label` : null, failed ? `${failed} over the limit` : passed ? `${passed} within limits` : null].filter(Boolean).join(' · ');

	return (
		<article className="rp card">
			<header className="rp-head">
				<div className="rp-title">
					<span className="rp-kind">{r.kind === 'user' ? 'OpenLabel lab report' : 'Third-party test'}</span>
					<h3>{r.lab?.name ?? r.publisher?.name ?? 'Report'}{r.lab?.accreditation && <span className="rp-acc">{r.lab.accreditation}</span>}</h3>
					<span className="rp-sub">{r.kind === 'fallback' ? `Published by ${r.publisher?.name ?? 'a testing website'}. OpenLabel hasn't verified it independently.` : summary}</span>
				</div>
				<div className="rp-actions">
					{r.kind === 'user' && <span className={`rp-pill ${r.verified ? 'ok' : 'wait'}`}>{r.verified ? 'Verified' : 'Source check pending'}</span>}
					{pdf && <a className="link" href={pdf} rel="noopener">Download PDF</a>}
					{source && r.kind === 'fallback' && <a className="link" href={source} rel="noopener">View on {r.publisher?.name ?? 'source'} ↗</a>}
				</div>
			</header>

			{highlights.length > 0 && (
				<ul className="rp-highlights">
					{highlights.map((h, i) => (
						<li key={i}><ResultIcon kind={h.kind} size={18} /><span className="rp-h-t">{h.t}</span><span className={h.kind === 'bad' ? 'off' : 'ok'}>{h.r}</span></li>
					))}
				</ul>
			)}

			{keyFacts.length > 0 && (
				<dl className="rp-key">
					{keyFacts.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
				</dl>
			)}

			<details className="rp-more">
				<summary>
					<span>Show all {r.results.length} results{moreFacts.length ? ' and report details' : ''}</span>
					<svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M3 4.5l3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
				</summary>
				{moreFacts.length > 0 && (
					<dl className="rp-key rp-key-more">
						{moreFacts.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
					</dl>
				)}
				<div className="rp-results">
					{r.verdict === 'fail' && !r.results.some((x) => x.status === 'fail') && (
						<p className="notice">{r.publisher?.name ?? 'The source'} marks this product as failed but publishes the failing values only as images.</p>
					)}
					{r.results.length ? (
						grouped(r.results).map(([group, rows]) => (
							<div key={group} className="rp-group">
								<h4>{label(group)}</h4>
								<table className="rp-table">
									<tbody>
										{rows.map((row, i) => (
											<tr key={i}>
												<td className="rp-param">{row.parameter}{row.method && <span className="rp-method">{row.method}</span>}</td>
												<td className={`r rp-val${offClaim(row) ? ' off' : ''}`} title={offClaim(row) ? 'More than 10% away from the label claim' : undefined}>
													{dash(row.value_raw)}<span className="rp-unit">{row.unit ? ` ${row.unit}` : ''}</span>
													{row.label_claim !== null && <span className="rp-claim">label {row.label_claim}</span>}
												</td>
												<td className="rp-status">{row.status ? <span className={`rp-pill ${row.status === 'pass' ? 'ok' : 'bad'}`}>{row.status === 'pass' ? 'Pass' : 'Fail'}</span> : null}</td>
											</tr>
										))}
									</tbody>
								</table>
							</div>
						))
					) : (
						<p className="muted">No results recorded for this report.</p>
					)}
				</div>
			</details>
			{r.kind === 'user' && <p className="rp-foot">The buyer's name and contact details on the report are hidden. Only the findings are published.</p>}
		</article>
	);
}

function Breakdown({ g }: { g: NonNullable<P['openlabel_grade']> }) {
	const part = (name: string, v: number | null) => (
		<span className="p-part"><span>{name}</span><b>{v === null ? 'not tested' : v}</b></span>
	);
	return (
		<div className="p-breakdown">
			{part('Label honesty', g.parts.honesty)}
			{part('Safety', g.parts.safety)}
			{part('Nutrition', g.parts.nutrition)}
			<Link className="link small" to="/about#grading">How we grade</Link>
			{g.safety_failed && <p className="off small">A safety test failed, so the grade can't be higher than D.</p>}
		</div>
	);
}

function ShelfGrade({ x }: { x: ProductCard }) {
	const g = gradeInfo(x);
	return (
		<>
			<GradeChip grade={g.grade} />
			{g.hasGrade && <GradeTag ours={g.ours} provisional={g.provisional} />}
			{g.text && <span>{g.text}</span>}
		</>
	);
}

function Others({ product }: { product: P }) {
	const others = useApi<{ items: ProductCard[] }>(product.category ? `/api/products?category=${encodeURIComponent(product.category)}&page_size=9` : null);
	const items = (others.data?.items ?? []).filter((x) => x.id !== product.id).slice(0, 8);
	if (!items.length) return null;
	return (
		<section className="p-section" aria-labelledby="alt">
			<h2 id="alt" className="section-title">Others on this shelf</h2>
			<div className="p-shelf">
				{items.map((x) => (
					<Link key={x.id} to={`/products/${x.id}`} className="p-shelf-item card hoverable">
						<Photo src={x.image_url} alt="" />
						<span className="muted small p-shelf-brand">{x.brand}</span>
						<span className="p-shelf-name">{productName(x)}</span>
						<span className="p-shelf-g">
							<ShelfGrade x={x} />
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
				<p><Link className="link" to="/products">Back to Browse Products</Link></p>
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
				<Link to="/products">Browse Products</Link>
				{p.category && <><span aria-hidden="true">/</span><Link to={`/products?category=${p.category}`}>{label(p.category)}</Link></>}
			</nav>

			<div className="p-top">
				<div className="p-gallery">
					<span className="photo contain p-main-photo">
						<img src={imgSrc(p.image_url, 1000)} alt={`${p.brand} ${name} pack`} referrerPolicy="no-referrer" onError={imgFallback} />
					</span>
				</div>

				<div className="p-center">
					<Link className="p-store" to={`/products?q=${encodeURIComponent(p.brand)}`}>Brand: {p.brand}</Link>
					<h1 className="p-title">{name}{p.net_quantity ? `, ${p.net_quantity}` : ''}</h1>
					<a className="p-rating" href={compared.length ? '#results' : '#rep'}>
						<GradeChip grade={p.openlabel_grade?.letter ?? sourceGrade(first)} size={26} />
						{(p.openlabel_grade || sourceGrade(first)) && <GradeTag ours={!!p.openlabel_grade} provisional={p.openlabel_grade?.provisional} />}
						<span className="p-rating-src">{gradeLabel(first, p.openlabel_grade)}</span>
						<ResultCounts counts={a.counts} size="sm" />
					</a>
					{p.openlabel_grade && <Breakdown g={p.openlabel_grade} />}
					<hr />
					<table className="p-facts">
						<tbody>
							<tr><th>Brand</th><td>{p.brand}</td></tr>
							<tr><th>Category</th><td>{label(p.category)}</td></tr>
							{p.net_quantity && <tr><th>Net quantity</th><td>{p.net_quantity}</td></tr>}
							<tr><th>Evidence</th><td>{first ? (first.kind === 'user' ? `OpenLabel lab report · ${first.lab?.name ?? 'accredited lab'}` : `Published test · ${first.publisher?.name ?? 'testing website'}`) : 'Not tested yet'}</td></tr>
							{first?.tested_on && <tr><th>Tested</th><td>{day(first.tested_on)}</td></tr>}
						</tbody>
					</table>
					<hr />
					<h2 className="p-about-h">About this item</h2>
					<ul className="p-about">
						<li>{summary(first)}</li>
						{keys.map((f) => (
							<li key={f.parameter} className={f.kind}>
								<strong>{f.parameter}:</strong> lab found {num(f.tested)} {f.unit ?? ''} against {num(f.label)} {f.unit ?? ''} on the label ({pct(f.deviation_pct ?? 0)}), {f.kind === 'bad' ? 'off label' : 'better than the label'}.
							</li>
						))}
						{compared.length > keys.length && <li>{compared.length - keys.length} more nutrients are within 10% of what the pack says.</li>}
						{p.tests.some((t) => t.tested) && <li>Covered by the results on file: {p.tests.filter((t) => t.tested).map((t) => t.name).join(', ')}.</li>}
						{p.tests.some((t) => !t.tested) && <li>Standard tests not covered yet: {p.tests.filter((t) => !t.tested).map((t) => t.name).join(', ')}.</li>}
					</ul>
				</div>

				<aside className="p-buy card" aria-label="Buy">
					<div className="p-buy-state"><StateTag state={p.reports.length ? 'tested' : 'requested'} /></div>
					<p className="p-buy-price">See today’s price on Amazon</p>
					<a className="btn lg p-buy-btn" href={buyUrl(p)} target="_blank" rel="sponsored noopener">Buy on Amazon</a>
					<Link className="btn lg outline p-buy-btn" to="/request">Request more tests</Link>
					<dl className="p-buy-meta">
						{first && <><dt>Tested by</dt><dd>{first.lab?.name ?? first.publisher?.name ?? '—'}</dd></>}
						{first?.kind === 'fallback' && <><dt>Published by</dt><dd>{first.publisher?.name ?? '—'}</dd></>}
						{compared.length > 0 && <><dt>Results</dt><dd><a className="link" href="#results">Label vs lab ↓</a></dd></>}
					</dl>
					<p className="p-buy-note">We may earn a commission from Amazon. It never changes a grade or a result.</p>
				</aside>
			</div>

			{compared.length > 0 && (
				<section className="p-section" id="results" aria-labelledby="lvl">
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
								<ResultIcon kind={t.tested ? 'good' : 'unk'} size={20} />
								<span>{t.name}</span>
								<span className="eyebrow">{t.tested ? 'Tested' : 'Not tested'}</span>
							</li>
						))}
					</ul>
					<p className="small muted">Want more checked? <Link className="link" to="/request">Request a test</Link> and others can help fund it.</p>
				</section>
			</div>

			<section className="p-section" aria-labelledby="rep">
				<h2 id="rep" className="section-title">{p.reports.length === 1 ? 'Lab report' : `Reports (${p.reports.length})`}</h2>
				{p.reports.length ? p.reports.map((r, i) => <ReportBlock key={r.id} r={r} findings={i === 0 ? compared : []} />) : <p className="muted">No reports yet.</p>}
			</section>

			<Others product={p} />
		</div>
	);
}
