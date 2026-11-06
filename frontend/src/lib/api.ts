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
	reports: Report[];
	tests: { name: string; tested: boolean }[];
};

export type Category = { category: string; product_count: number; tests: string[] };

export type ProductCard = {
	id: string;
	brand: string;
	name: string;
	variant: string | null;
	category: string | null;
	image_url: string | null;
	report_count: number;
	has_user_report: boolean;
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

export const label = (v: string | null) => (v ? v.replace(/_/g, ' ') : '—');

export const nameOf = (x: string | Source | null) => (x && typeof x === 'object' ? x.name : x);

export function verdictText(r: { verdict: Report['verdict']; grade: string | null }) {
	if (r.grade) return `Grade ${r.grade}`;
	if (r.verdict === 'pass') return 'Pass';
	if (r.verdict === 'fail') return 'Fail';
	return '';
}

export const httpUrl = (u: string | null) => (u && /^(https?:\/\/|\/)/i.test(u) ? u : null);
