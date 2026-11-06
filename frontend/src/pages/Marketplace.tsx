import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { buyUrl, label, nameOf, productName, type Brand, type Department, type ProductCard, type TestRequest } from '@/lib/api';
import { cardGrade, gradeColors } from '@/lib/grade';
import { useApi } from '@/lib/useApi';
import { GradeChip, GradeTag, Photo, StateTag } from '@/components/bits';
import './Marketplace.css';

type Page = { items: ProductCard[]; page: number; page_size: number; total: number };

const EVIDENCE = [
	['lab', 'OpenLabel lab report'],
	['published', 'Published tests']
] as const;
const ON_LABEL = [
	['no_added_sugar', 'No added sugar'],
	['high_fibre', 'High fibre (6 g+)'],
	['high_protein', 'High protein (20 g+)']
] as const;

/** Grade (if any), whose it is, and a short line naming who tested the product. */
export function gradeInfo(p: ProductCard) {
	const g = cardGrade(p);
	const l = p.latest;
	const who = l ? (l.kind === 'user' ? 'OpenLabel' : nameOf(l.publisher) ?? 'a testing website') : null;
	const text = !l ? 'Not tested yet' : g ? (g.ours ? '' : who!) : l.kind === 'user' ? 'Tested through OpenLabel' : `Tested for ${who}`;
	return { grade: g?.grade ?? null, ours: !!g?.ours, provisional: !!g?.provisional, hasGrade: !!g, text };
}

type GradeInfo = ReturnType<typeof gradeInfo>;

function Tile({ to, img, alt, state, brand, name, g, buy }: { to: string; img: string | null; alt: string; state: 'tested' | 'requested'; brand: string; name: string; g: GradeInfo; buy: string }) {
	return (
		<article className="m-tile card hoverable">
			<Link to={to} className="m-photo">
				<Photo src={img} alt={alt} />
				<StateTag state={state} style={{ position: 'absolute', left: 10, top: 10 }} />
			</Link>
			<Link to={to} className="m-text">
				<span className="m-brand">{brand}</span>
				<span className="m-name">{name}</span>
			</Link>
			<div className="m-grade">
				<GradeChip grade={g.grade} />
				{g.hasGrade && <GradeTag ours={g.ours} provisional={g.provisional} />}
				{g.text && <span>{g.text}</span>}
			</div>
			<a className="btn m-buy" href={buy} target="_blank" rel="sponsored noopener">Buy on Amazon</a>
		</article>
	);
}

export default function Marketplace() {
	const [params, setParams] = useSearchParams();
	const navigate = useNavigate();
	const q = params.get('q') ?? '';
	const category = params.get('category') ?? '';
	const dept = params.get('dept') ?? '';
	const evidence = params.getAll('evidence');
	const grades = params.getAll('grade');
	const brands = params.getAll('brand');
	const page = Number(params.get('page') ?? '1');
	const [query, setQuery] = useState(q);

	const results = useApi<Page>(`/api/products?${params}`);
	const depts = useApi<Department[]>('/api/departments');
	const brandScope = category ? `category=${encodeURIComponent(category)}` : dept ? `dept=${encodeURIComponent(dept)}` : '';
	const brandList = useApi<Brand[]>(`/api/brands?limit=12${brandScope ? `&${brandScope}` : ''}`);
	const filtered = evidence.length > 0 || grades.length > 0 || brands.length > 0 || !!dept || ON_LABEL.some(([k]) => params.get(k));
	const reqParams = new URLSearchParams();
	if (q) reqParams.set('q', q);
	if (category) reqParams.set('category', category);
	const requests = useApi<TestRequest[]>(page === 1 && !filtered ? `/api/test-requests?${reqParams}` : null);

	const change = (fn: (p: URLSearchParams) => void) => {
		const p = new URLSearchParams(params);
		fn(p);
		p.delete('page');
		setParams(p);
	};
	const hrefFor = (fn: (p: URLSearchParams) => void) => {
		const p = new URLSearchParams(params);
		fn(p);
		const s = p.toString();
		return s ? `/products?${s}` : '/products';
	};
	const search = (e: FormEvent) => {
		e.preventDefault();
		navigate(hrefFor((p) => {
			query.trim() ? p.set('q', query.trim()) : p.delete('q');
			p.delete('page');
		}));
	};

	const current = depts.data?.find((d) => d.key === dept);
	const r = results.data;
	const pages = r ? Math.max(1, Math.ceil(r.total / r.page_size)) : 1;
	const heading = category ? label(category) : current ? current.name : q ? `Results for “${q}”` : 'All products';
	const toggle = (key: string, value: string, on: boolean) =>
		change((p) => {
			const next = p.getAll(key).filter((x) => x !== value);
			p.delete(key);
			(on ? [...next, value] : next).forEach((x) => p.append(key, x));
		});

	return (
		<div className="page">
			<title>Browse Products · OpenLabel</title>
			<div className="page-head">
				<div style={{ flex: '1 1 420px', minWidth: 0 }}>
					<div className="eyebrow">{r ? `${r.total.toLocaleString('en-IN')} products` : ' '}</div>
					<h1 style={{ marginTop: 10 }}>Browse Products</h1>
					<p className="lede">What the label says, what the lab found, and where to buy it.</p>
				</div>
				<form role="search" className="search" onSubmit={search}>
					<label htmlFor="mq" className="sr-only">Search products or brands</label>
					<input id="mq" type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search products or brands" />
					<button type="submit">Search</button>
				</form>
			</div>

			<nav className="shelves" aria-label="Shelves">
				<Link to={hrefFor((p) => { p.delete('category'); p.delete('dept'); p.delete('brand'); p.delete('page'); })} aria-current={!category && !dept ? 'page' : undefined}>All</Link>
				{(depts.data ?? []).map((d) => (
					<Link key={d.key} to={hrefFor((p) => { p.set('dept', d.key); p.delete('category'); p.delete('brand'); p.delete('page'); })} aria-current={d.key === dept ? 'page' : undefined}>
						{d.name}
					</Link>
				))}
			</nav>

			<div className="m-body">
				<aside className="m-filters" aria-label="Filters">
					{current && (
						<fieldset>
							<legend>Category</legend>
							<nav className="m-cats" aria-label={`Categories in ${current.name}`}>
								<Link to={hrefFor((p) => { p.delete('category'); p.delete('page'); })} aria-current={!category ? 'page' : undefined}>
									<span>All {current.name.toLowerCase()}</span><span className="m-count">{current.product_count}</span>
								</Link>
								{current.categories.map((c) => (
									<Link key={c.category} to={hrefFor((p) => { p.set('category', c.category); p.delete('brand'); p.delete('page'); })} aria-current={c.category === category ? 'page' : undefined}>
										<span>{label(c.category)}</span><span className="m-count">{c.product_count}</span>
									</Link>
								))}
							</nav>
						</fieldset>
					)}
					<fieldset>
						<legend>Grade</legend>
						<div className="m-grades">
							{['A', 'B', 'C', 'D', 'E'].map((g) => {
								const c = gradeColors(g)!;
								const on = grades.includes(g);
								return (
									<label key={g} className={on ? 'on' : ''} style={on ? { background: c[0], color: c[1], borderColor: c[0] } : undefined}>
										<input className="sr-only" type="checkbox" checked={on} onChange={(e) => toggle('grade', g, e.target.checked)} />
										{g}
									</label>
								);
							})}
						</div>
						<p className="hint">Third-party grades. Scores like 86/100 count as A.</p>
					</fieldset>
					{(brandList.data?.length ?? 0) > 1 && (
						<fieldset>
							<legend>Brand</legend>
							{brandList.data!.map((b) => (
								<label key={b.brand}>
									<input type="checkbox" checked={brands.some((x) => x.toLowerCase() === b.brand.toLowerCase())} onChange={(e) => toggle('brand', b.brand, e.target.checked)} />
									<span>{b.brand}</span>
									<span className="m-count">{b.product_count}</span>
								</label>
							))}
						</fieldset>
					)}
					<fieldset>
						<legend>Evidence</legend>
						{EVIDENCE.map(([k, text]) => (
							<label key={k}>
								<input
									type="checkbox"
									checked={evidence.includes(k)}
									onChange={(e) => change((p) => {
										const next = p.getAll('evidence').filter((x) => x !== k);
										p.delete('evidence');
										(e.target.checked ? [...next, k] : next).forEach((x) => p.append('evidence', x));
									})}
								/>
								<span>{text}</span>
							</label>
						))}
					</fieldset>
					<fieldset>
						<legend>On the label</legend>
						{ON_LABEL.map(([k, text]) => (
							<label key={k}>
								<input type="checkbox" checked={params.get(k) === 'true'} onChange={(e) => change((p) => (e.target.checked ? p.set(k, 'true') : p.delete(k)))} />
								<span>{text}</span>
							</label>
						))}
						<p className="hint">Per 100 g, from the pack label.</p>
					</fieldset>
				</aside>

				<section className="m-results" aria-labelledby="m-h">
					<h2 id="m-h" className="m-heading">{heading}</h2>
					{results.error && <p className="error">Couldn't load products: {results.error}</p>}
					{results.loading && !r && <p className="muted">Loading…</p>}
					{r && !r.items.length && (
						<p>No products match. <Link className="link" to="/request">Request a test</Link> for one we don't have.</p>
					)}
					{r && r.items.length > 0 && (
						<div className="m-grid">
							{r.items.map((p) => (
								<Tile
									key={p.id}
									to={`/products/${p.id}`}
									img={p.image_url}
									alt={`${p.brand} ${productName(p)} pack`}
									state={p.latest ? 'tested' : 'requested'}
									brand={p.brand}
									name={productName(p)}
									g={gradeInfo(p)}
									buy={buyUrl(p)}
								/>
							))}
							{(requests.data ?? []).map((t) => (
								<Tile
									key={t.id}
									to={`/requests/${t.id}`}
									img={t.image_url ?? null}
									alt={`${t.brand} ${productName(t)} pack`}
									state="requested"
									brand={t.brand}
									name={productName(t)}
									g={{ grade: null, ours: false, provisional: false, hasGrade: false, text: 'Not tested · needs funding' }}
									buy={buyUrl(t)}
								/>
							))}
						</div>
					)}
					{r && pages > 1 && (
						<nav className="m-pager" aria-label="Pages">
							{page > 1 ? <Link className="link" to={hrefFor((p) => p.set('page', String(page - 1)))}>← Previous</Link> : <span />}
							<span className="muted">Page {page} of {pages}</span>
							{page < pages ? <Link className="link" to={hrefFor((p) => p.set('page', String(page + 1)))}>Next →</Link> : <span />}
						</nav>
					)}
					<section className="m-cta" aria-label="Request a test">
						<div>
							<div className="m-cta-title">Not on the shelf?</div>
							<p className="muted">Paste an Amazon link. Others can help fund it, and anyone can be the tester and take it to an accredited lab.</p>
						</div>
						<Link className="btn lg" to="/request">Request a test</Link>
					</section>
				</section>
			</div>
		</div>
	);
}
