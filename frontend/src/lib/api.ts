export type Source = {
	id: string;
	type?: 'lab' | 'website';
	name: string;
	url: string | null;
	accreditation: string | null;
	description?: string | null;
	report_count?: number;
};

export type Result = {
	parameter: string;
	group: string;
	unit: string | null;
	value: number | null;
	value_raw: string;
	label_claim: number | null;
	limit: number | null;
	detection_limit: number | null;
	method: string | null;
	status: 'pass' | 'fail' | null;
};

export type Report = {
	id: string;
	kind: 'user' | 'fallback';
	lab: Source | null;
	publisher: Source | null;
	source_url: string | null;
	report_number: string | null;
	ulr_number: string | null;
	batch_no: string | null;
	mfg_date: string | null;
	expiry_date: string | null;
	tested_on: string | null;
	issued_on: string | null;
	verdict: 'pass' | 'fail' | 'grade' | null;
	grade: string | null;
	pdf_url: string | null;
	verification: string;
	verified: boolean;
	results: Result[];
};

export type Product = {
	id: string;
	brand: string;
	name: string;
	variant: string | null;
	category: string | null;
	manufacturer: string | null;
	fssai_license: string | null;
	barcode: string | null;
	net_quantity: string | null;
	image_url: string | null;
	ingredients: string | null;
	ingredients_source: string | null;
	label_nutrition: LabelNutrition | null;
	reports: Report[];
	tests: { name: string; why?: string; tested: boolean; status?: 'pass' | 'fail' | 'measured' | 'untested' }[];
	annotations: Annotations;
	openlabel_grade: OpenLabelGrade | null;
};

/** Per 100 g, from the pack label. Any subset. */
export type LabelNutrition = Partial<{
	energy_kcal: number;
	protein_g: number;
	sugars_g: number;
	added_sugars_g: number;
	fiber_g: number;
	fat_g: number;
	saturated_fat_g: number;
	sodium_mg: number;
}>;

export type OpenLabelGrade = {
	letter: string;
	score: number;
	provisional: boolean;
	safety_failed: boolean;
	safety_tier?: 'critical' | 'serious' | 'minor' | null;
	safety_flags?: { parameter: string; tier: string; ratio: number | null }[];
	nutri_score?: string | null;
	parts: { honesty: number | null; safety: number | null; nutrition: number | null };
};

export type Finding = {
	parameter: string;
	kind: 'good' | 'bad' | 'info';
	label: number | null;
	tested: number | null;
	unit: string | null;
	deviation_pct: number | null;
	tolerance_pct?: number;
	text: string;
};

export type Segment = { t: string; mark: 'under' | 'circle' | 'hl' | 'good' | null; note: string | null };

export type Annotations = {
	segments: Segment[];
	findings: Finding[];
	counts: { pass: number; fail: number; measured?: number; untested: number };
};

export type WallItem = {
	kind: 'product' | 'request';
	id: string;
	brand: string;
	name: string;
	variant: string | null;
	category: string | null;
	image_url: string | null;
	ingredients: string | null;
	label_nutrition: LabelNutrition | null;
	state: 'tested' | 'requested';
	grade: string | null;
	grade_source: string | null;
	report_kind: 'user' | 'fallback' | null;
	lab: string | null;
	tested_on: string | null;
	annotations: Annotations | null;
	openlabel_grade: OpenLabelGrade | null;
};

export type TestRequest = {
	id: string;
	brand: string;
	name: string;
	variant: string | null;
	category: string;
	requested_on: string;
	net_quantity?: string | null;
	manufacturer?: string | null;
	fssai_license?: string | null;
	barcode?: string | null;
	buy_url?: string | null;
	image_url?: string | null;
	tests?: string[];
	standard_tests?: { name: string; why: string }[];
};

export type Prefill = {
	asin: string;
	buy_url: string;
	brand: string | null;
	name: string | null;
	category: string | null;
	image_url: string | null;
	manufacturer: string | null;
	net_quantity: string | null;
	existing_request: TestRequest | null;
};

export type Category = { category: string; product_count: number; tests: string[] };
export type Department = { key: string; name: string; product_count: number; categories: { category: string; product_count: number }[] };
export type Brand = { brand: string; product_count: number };

export type ProductCard = {
	id: string;
	brand: string;
	name: string;
	variant: string | null;
	category: string | null;
	image_url: string | null;
	label_nutrition: LabelNutrition | null;
	report_count: number;
	has_user_report: boolean;
	openlabel_grade: OpenLabelGrade | null;
	latest: {
		kind: 'user' | 'fallback';
		verdict: Report['verdict'];
		grade: string | null;
		publisher: string | Source | null;
		lab: string | Source | null;
		tested_on: string | null;
	} | null;
};

export async function api<T>(path: string): Promise<T> {
	const res = await fetch(path, { headers: { Accept: 'application/json' } });
	if (!res.ok) throw new Error(res.status === 404 ? 'Not found' : `Request failed (${res.status})`);
	return res.json();
}

export class ApiError extends Error {
	constructor(public status: number, public detail: unknown) {
		super(typeof detail === 'string' ? detail : `Request failed (${status})`);
	}
}

export async function post<T>(path: string, body: unknown): Promise<T> {
	const res = await fetch(path, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
		body: JSON.stringify(body)
	});
	const data = await res.json().catch(() => null);
	if (!res.ok) throw new ApiError(res.status, data?.detail ?? null);
	return data;
}

export const dash = (v: unknown) => (v === null || v === undefined || v === '' ? '—' : String(v));

export const label = (v: string | null) => (v ? v.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase()) : '—');

export const nameOf = (x: string | Source | null) => (x && typeof x === 'object' ? x.name : x);

export function verdictText(r: { verdict: Report['verdict']; grade: string | null }) {
	if (r.grade) return `Grade ${r.grade}`;
	if (r.verdict === 'pass') return 'Pass';
	if (r.verdict === 'fail') return 'Fail';
	return '';
}

export const httpUrl = (u: string | null) => (u && /^(https?:\/\/|\/)/i.test(u) ? u : null);

const NUTRITION_ROWS: [keyof LabelNutrition, string, string][] = [
	['energy_kcal', 'Energy', 'kcal'],
	['protein_g', 'Protein', 'g'],
	['sugars_g', 'Sugars', 'g'],
	['added_sugars_g', 'Added sugar', 'g'],
	['fiber_g', 'Fibre', 'g'],
	['fat_g', 'Fat', 'g'],
	['saturated_fat_g', 'Sat. fat', 'g'],
	['sodium_mg', 'Sodium', 'mg']
];

const num = (v: number) => (Math.abs(v) >= 100 ? Math.round(v).toString() : (Math.round(v * 10) / 10).toString());

/** Label nutrition as display rows, in a fixed order. */
export function nutritionRows(n: LabelNutrition | null, max = 8) {
	if (!n) return [];
	return NUTRITION_ROWS.filter(([k]) => typeof n[k] === 'number')
		.slice(0, max)
		.map(([k, name, unit]) => ({ key: k, name, value: `${num(n[k] as number)} ${unit}` }));
}

export const productName = (p: { name: string; variant: string | null }) =>
	p.variant && !p.name.toLowerCase().includes(p.variant.toLowerCase()) ? `${p.variant} ${p.name}` : p.name;

/** Amazon search link for a product. Affiliate tag is added once the account exists. */
export const AFFILIATE_TAG = '';
export function buyUrl(p: { brand: string; name: string; variant: string | null; buy_url?: string | null }) {
	if (p.buy_url && httpUrl(p.buy_url)) return p.buy_url;
	const q = encodeURIComponent([p.brand, p.variant, p.name].filter(Boolean).join(' '));
	return `https://www.amazon.in/s?k=${q}${AFFILIATE_TAG ? `&tag=${AFFILIATE_TAG}` : ''}`;
}

export const PLACEHOLDER = '/placeholder.svg';
/** Trimmed, resized thumbnail from /api/thumb (flat borders removed), or the placeholder. */
export const imgSrc = (u: string | null | undefined, w = 600) => {
	const src = httpUrl(u ?? null);
	return src ? `/api/thumb?w=${w}&src=${encodeURIComponent(src)}` : PLACEHOLDER;
};
/** onError: thumbnail failed → try the original photo; original failed → placeholder. */
export const imgFallback = (e: { currentTarget: HTMLImageElement }) => {
	const img = e.currentTarget;
	const url = new URL(img.src, location.href);
	const original = url.pathname === '/api/thumb' ? url.searchParams.get('src') : null;
	if (original) img.src = original;
	else if (!img.src.endsWith(PLACEHOLDER)) img.src = PLACEHOLDER;
};
