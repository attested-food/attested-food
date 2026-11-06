import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router';
import { api, ApiError, label, post, type Category, type Prefill, type TestRequest } from '@/lib/api';
import './Request.css';

const MAX_IMAGE = 5 * 1024 * 1024;
const empty = () => ({ brand: '', name: '', variant: '', category: '', net_quantity: '', manufacturer: '', fssai_license: '', barcode: '', buy_url: '' });
type Form = ReturnType<typeof empty>;
type Match = { kind: 'product' | 'request'; id: string; brand: string; name: string; variant: string | null; category?: string | null; requested_on?: string | null };

const asRequest = (r: TestRequest): Match => ({ kind: 'request', ...r });
const fullName = (p: Match) => `${p.brand} ${p.name}${p.variant ? ` · ${p.variant}` : ''}`;

export default function Request() {
	const navigate = useNavigate();
	const [mode, setMode] = useState<'link' | 'manual'>('link');
	const [link, setLink] = useState('');
	const [fetching, setFetching] = useState(false);
	const [fetched, setFetched] = useState(false);
	const [linkNote, setLinkNote] = useState('');
	const [form, setForm] = useState<Form>(empty());
	const [imageMode, setImageMode] = useState<'url' | 'file'>('url');
	const [imageUrl, setImageUrl] = useState('');
	const [imageData, setImageData] = useState<string | null>(null);
	const [imageError, setImageError] = useState('');
	const [categories, setCategories] = useState<Category[]>([]);
	const [suggestions, setSuggestions] = useState<Match[]>([]);
	const [existing, setExisting] = useState<Match | null>(null);
	const [error, setError] = useState('');
	const [submitting, setSubmitting] = useState(false);
	const [done, setDone] = useState<{ id: string; tests: string[] } | null>(null);
	const fileInput = useRef<HTMLInputElement>(null);
	const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
	const latestQuery = useRef('');

	const tests = categories.find((c) => c.category === form.category)?.tests ?? [];
	const preview = imageMode === 'file' ? imageData : /^https?:\/\//i.test(imageUrl) ? imageUrl : null;
	const showForm = mode === 'manual' || fetched;
	const set = (k: keyof Form) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));

	useEffect(() => {
		api<Category[]>('/api/categories').then(setCategories).catch((e: Error) => setError(`Couldn't load categories: ${e.message}`));
	}, []);

	function search(q: string) {
		clearTimeout(timer.current);
		latestQuery.current = q;
		if (q.length < 2) return setSuggestions([]);
		timer.current = setTimeout(async () => {
			try {
				const found = await api<Match[]>(`/api/duplicates?q=${encodeURIComponent(q)}`);
				if (q === latestQuery.current) setSuggestions(found);
			} catch (e) {
				console.error('duplicate search failed', e);
			}
		}, 250);
	}

	function choose(m: Match) {
		setForm({ ...empty(), brand: m.brand, name: m.name, variant: m.variant ?? '', category: m.category ?? '' });
		setExisting(m);
		setSuggestions([]);
	}

	function reset() {
		setForm(empty());
		setLink('');
		setFetched(false);
		setLinkNote('');
		setImageMode('url');
		setImageUrl('');
		setImageData(null);
		setImageError('');
		if (fileInput.current) fileInput.current.value = '';
		setExisting(null);
		setSuggestions([]);
		setError('');
		setDone(null);
	}

	function switchMode(m: 'link' | 'manual') {
		reset();
		setMode(m);
	}

	async function fetchLink(e: FormEvent) {
		e.preventDefault();
		setExisting(null);
		setError('');
		setFetching(true);
		try {
			const p = await api<Prefill>(`/api/prefill?url=${encodeURIComponent(link.trim())}`);
			setForm({ ...empty(), brand: p.brand ?? '', name: p.name ?? '', category: p.category ?? '', net_quantity: p.net_quantity ?? '', manufacturer: p.manufacturer ?? '', buy_url: p.buy_url });
			setImageMode('url');
			setImageUrl(p.image_url ?? '');
			setFetched(true);
			setLinkNote('Filled in from Amazon. Check it against the pack before sending.');
			if (p.existing_request) setExisting(asRequest(p.existing_request));
			else search(`${p.brand ?? ''} ${p.name ?? ''}`.trim());
		} catch (err) {
			const msg = err instanceof Error ? err.message : String(err);
			if (msg.includes('(422)')) {
				setLinkNote('');
				setError("That doesn't look like an amazon.in product link.");
			} else {
				setForm({ ...empty(), buy_url: /^https?:\/\//i.test(link.trim()) ? link.trim() : '' });
				setFetched(true);
				setLinkNote("We couldn't read that Amazon page. Please fill in the details below.");
			}
		} finally {
			setFetching(false);
		}
	}

	function pickFile(e: ChangeEvent<HTMLInputElement>) {
		const file = e.currentTarget.files?.[0];
		setImageData(null);
		setImageError('');
		if (!file) return;
		if (file.size > MAX_IMAGE) return setImageError('Image must be 5 MB or smaller.');
		const reader = new FileReader();
		reader.onload = () => setImageData(reader.result as string);
		reader.onerror = () => setImageError("Couldn't read that file.");
		reader.readAsDataURL(file);
	}

	async function submit(e: FormEvent) {
		e.preventDefault();
		setError('');
		if (imageMode === 'file' && !imageData) return setError(imageError || 'Choose an image file.');
		const body = {
			...Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v.trim() || null])),
			image_url: imageMode === 'url' ? imageUrl.trim() : null,
			image_data: imageMode === 'file' ? imageData : null
		};
		setSubmitting(true);
		try {
			setDone(await post<{ id: string; tests: string[] }>('/api/test-requests', body));
		} catch (err) {
			if (err instanceof ApiError && err.status === 409) {
				const d = err.detail as { product_id?: string; request?: TestRequest };
				setExisting(d.request ? asRequest(d.request) : { kind: 'product', id: d.product_id ?? '', brand: form.brand, name: form.name, variant: form.variant || null });
			} else if (err instanceof ApiError && Array.isArray(err.detail)) {
				setError(err.detail.map((d: { loc: string[]; msg: string }) => `${label(String(d.loc.at(-1)))}: ${d.msg}`).join('; '));
			} else {
				setError(err instanceof Error ? err.message : String(err));
			}
		} finally {
			setSubmitting(false);
		}
	}

	return (
		<div className="page">
			<title>Request a test · OpenLabel</title>
			<nav className="crumbs" aria-label="Breadcrumb"><Link to="/tests">Tests</Link><span aria-hidden="true">/</span><span>Request a test</span></nav>
			<div className="page-head" style={{ marginTop: 12 }}>
				<div>
					<h1>Request a test</h1>
					<p className="lede">Paste an Amazon link and we fill in the details. If the product is already here, we take you to it.</p>
				</div>
			</div>

			{done ? (
				<div className="rq-done">
					<p className="notice">Request received for <strong>{form.brand} {form.name}</strong>. Once others contribute and someone takes it on as the tester, it goes to an accredited lab.</p>
					<h2 className="section-title" style={{ marginTop: 28 }}>Tests we'll run</h2>
					<ul className="rq-tests">{done.tests.map((t) => <li key={t}><span>{t}</span></li>)}</ul>
					<div className="rq-row" style={{ marginTop: 20 }}>
						<Link className="btn lg" to={`/requests/${done.id}`}>View your request</Link>
						<button type="button" className="btn lg outline" onClick={() => switchMode(mode)}>Request another product</button>
					</div>
				</div>
			) : (
				<div className="rq-body">
					<div className="rq-main">
						<div className="rq-modes" role="radiogroup" aria-label="How to add the product">
							<label className={mode === 'link' ? 'on' : ''}><input className="sr-only" type="radio" name="mode" checked={mode === 'link'} onChange={() => switchMode('link')} />Paste an Amazon link</label>
							<label className={mode === 'manual' ? 'on' : ''}><input className="sr-only" type="radio" name="mode" checked={mode === 'manual'} onChange={() => switchMode('manual')} />Enter details yourself</label>
						</div>

						{existing && (
							<div className="notice rq-existing" role="alert">
								<p>
									<strong>{fullName(existing)}</strong>
									{existing.kind === 'product' ? ' is already on OpenLabel.' : ` was already requested on ${existing.requested_on}.`} Go to its page?
								</p>
								<div className="rq-row">
									<button type="button" className="btn sm" onClick={() => navigate(existing.kind === 'product' ? `/products/${existing.id}` : `/requests/${existing.id}`)}>Yes, open it</button>
									<button type="button" className="btn sm outline" onClick={() => switchMode(mode)}>No, start over</button>
								</div>
							</div>
						)}

						{mode === 'link' && (
							<form onSubmit={fetchLink} className="rq-link">
								<label htmlFor="link" className="field"><span>Amazon product link</span></label>
								<div className="search rq-link-box">
									<input id="link" type="url" required maxLength={2000} value={link} onChange={(e) => setLink(e.target.value)} disabled={!!existing || fetching} placeholder="https://www.amazon.in/…/dp/B08R3CLJ8H" />
									<button type="submit" disabled={!!existing || fetching}>{fetching ? 'Fetching…' : fetched ? 'Fetch again' : 'Fetch details'}</button>
								</div>
								{linkNote && <p className="rq-note">{linkNote}</p>}
							</form>
						)}

						{error && !showForm && <p className="error">{error}</p>}

						{showForm && (
							<form onSubmit={submit}>
								<fieldset disabled={!!existing} className="rq-fields">
									<h2 className="section-title">The product</h2>
									<div
										className="rq-suggest"
										onBlur={(e) => {
											if (!e.currentTarget.contains(e.relatedTarget as Node)) setSuggestions([]);
										}}
									>
										<div className="rq-grid">
											<label className="field">Brand *<input required maxLength={100} value={form.brand} onChange={(e) => { set('brand')(e); search(`${e.target.value} ${form.name}`.trim()); }} placeholder="e.g. Pintola" autoComplete="off" /></label>
											<label className="field">Product name *<input required maxLength={200} value={form.name} onChange={(e) => { set('name')(e); search(`${form.brand} ${e.target.value}`.trim()); }} placeholder="e.g. Peanut Butter" autoComplete="off" /></label>
										</div>
										{suggestions.length > 0 && (
											<ul aria-label="Products already on OpenLabel">
												{suggestions.map((s) => (
													<li key={s.kind + s.id}><button type="button" onClick={() => choose(s)}>{fullName(s)}<span>{s.kind === 'product' ? 'Already listed' : 'Already requested'}</span></button></li>
												))}
											</ul>
										)}
									</div>
									<div className="rq-grid">
										<label className="field">Variant / flavour<input maxLength={100} value={form.variant} onChange={set('variant')} placeholder="e.g. Creamy, Dark Chocolate" /></label>
										<label className="field">Category *
											<select required value={form.category} onChange={set('category')}>
												<option value="" disabled>Choose a category</option>
												{categories.map((c) => <option key={c.category} value={c.category}>{label(c.category)}</option>)}
											</select>
										</label>
									</div>

									<div className="field">
										<span>Product image *</span>
										<div className="rq-modes small" role="radiogroup" aria-label="Image source">
											<label className={imageMode === 'url' ? 'on' : ''}><input className="sr-only" type="radio" checked={imageMode === 'url'} onChange={() => setImageMode('url')} />Image URL</label>
											<label className={imageMode === 'file' ? 'on' : ''}><input className="sr-only" type="radio" checked={imageMode === 'file'} onChange={() => setImageMode('file')} />Upload file</label>
										</div>
									</div>
									<div className="rq-image">
										{preview && <span className="photo rq-preview"><img src={preview} alt="Product preview" /></span>}
										<div style={{ flex: 1, minWidth: 0 }}>
											{imageMode === 'url' ? (
												<label className="field">Image URL<input type="url" required maxLength={2000} value={imageUrl} onChange={(e) => setImageUrl(e.target.value)} placeholder="https://…" /></label>
											) : (
												<label className="field">Image file<input type="file" required accept="image/png,image/jpeg,image/webp" ref={fileInput} onChange={pickFile} /><span className="hint">JPG, PNG or WebP, up to 5 MB</span></label>
											)}
											{imageError && <p className="error">{imageError}</p>}
										</div>
									</div>

									<div className="rq-grid">
										<label className="field">Net quantity<input maxLength={50} value={form.net_quantity} onChange={set('net_quantity')} placeholder="e.g. 1 kg" /></label>
										<label className="field">Where to buy<input type="url" maxLength={2000} value={form.buy_url} onChange={set('buy_url')} placeholder="Amazon, BigBasket or brand site link" /></label>
										<label className="field">Barcode<input inputMode="numeric" pattern="\d{8,14}" title="8 to 14 digits" value={form.barcode} onChange={set('barcode')} placeholder="From the pack" /></label>
										<label className="field">FSSAI licence no.<input inputMode="numeric" pattern="\d{14}" title="14 digits" value={form.fssai_license} onChange={set('fssai_license')} placeholder="14 digits, from the pack" /></label>
									</div>
									<label className="field">Manufacturer<input maxLength={200} value={form.manufacturer} onChange={set('manufacturer')} placeholder="From the pack" /></label>

									{error && <p className="error">{error}</p>}
									<div className="rq-submit">
										<button className="btn lg" type="submit" disabled={submitting}>{submitting ? 'Sending…' : 'Request this test'}</button>
										<span className="muted small">Next you can contribute, or put down a refundable stake and be the tester yourself.</span>
									</div>
								</fieldset>
							</form>
						)}
					</div>

					<aside className="rq-aside" aria-label="About this test">
						<section>
							<div className="rq-aside-head">
								<h2 className="section-title">Tests we'll run</h2>
								{form.category && <span className="eyebrow">{label(form.category)}</span>}
							</div>
							{tests.length ? (
								<ul className="rq-tests">{tests.map((t) => <li key={t}><span>{t}</span></li>)}</ul>
							) : (
								<p className="muted small" style={{ marginTop: 12 }}>Choose a category to see the tests.</p>
							)}
							<p className="small muted">Set by category. The price comes from the lab’s quote.</p>
						</section>
						<section>
							<h2 className="section-title">After you send it</h2>
							<ol className="rq-next">
								<li><b>1</b><span>It shows up on the Tests board as Requested.</span></li>
								<li><b>2</b><span>Anyone can contribute toward the lab’s quote. You can too.</span></li>
								<li><b>3</b><span>Whoever puts down the stake becomes the tester, takes it to an accredited lab and posts the report before the deadline.</span></li>
							</ol>
						</section>
					</aside>
				</div>
			)}
		</div>
	);
}
