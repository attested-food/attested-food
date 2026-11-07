// Client for the backend2-rs prover (backend2-rs/README.md): POST /prove starts a job,
// GET /jobs/{id} reports its stage, progress and, when done, the proof.

export const PROVER_URL: string = import.meta.env.VITE_PROVER_URL ?? 'https://prover.openlabel.fyi';

export type Job = {
	id: string;
	mode: string;
	format: string;
	status: 'queued' | 'running' | 'done' | 'failed';
	stage: string | null;
	stages: { name: string; ms?: number; elapsedMs?: number }[];
	elapsedMs: number;
	progress: { fraction: number; etaMs?: number } | null;
	preview: { publicValues: unknown; publicValuesHex: string };
	partial: Record<string, unknown>;
	result: Record<string, unknown> | null;
	error: string | null;
};

async function json(res: Response): Promise<any> {
	const body = await res.json().catch(() => ({ error: `${res.status} ${res.statusText}` }));
	if (!res.ok) throw new Error(body.error ?? `${res.status} ${res.statusText}`);
	return body;
}

/**
 * Start an SP1 Groth16 job (the proof `EurekhaReportRegistry.submit` takes) for a lab report PDF;
 * resolves to its id once the server has read the report link from the PDF's QR code. The server
 * fetches the lab's copy under TLSNotary (stage `zktls fetch`), checks it equals the upload, then
 * proves: the SP1 STARK shows up under `partial["sp1-compressed"]` first, the Groth16 artifact
 * under `result.artifact` at the end.
 */
export async function startProof(pdf: File): Promise<string> {
	const form = new FormData();
	form.append('pdf', pdf);
	form.append('format', 'eurekha-attested');
	const body = await json(await fetch(`${PROVER_URL}/prove?mode=sp1-groth16`, { method: 'POST', body: form }));
	console.log('[prover] POST /prove', body);
	return body.jobId;
}

/** Poll a job until it is done or failed, calling `onUpdate` with every response. */
export async function pollJob(id: string, onUpdate: (job: Job) => void, everyMs = 3000): Promise<Job> {
	for (;;) {
		const job: Job = await json(await fetch(`${PROVER_URL}/jobs/${id}`));
		console.log(`[prover] GET /jobs/${id}`, job);
		onUpdate(job);
		if (job.status === 'done' || job.status === 'failed') return job;
		await new Promise((r) => setTimeout(r, everyMs));
	}
}

// TEMP MOCK, remove once the prover server is back: "Post the lab report" skips the server and returns
// backend2-rs's real SP1 Groth16 fixture (choco-millet-muesli), which TestFund accepts once per deployment.
export const MOCK_PROVER = true;

export async function mockProof(onUpdate: (job: Job) => void): Promise<Job> {
	const { default: artifact } = await import('./mock-proof.json');
	const SECONDS = 30;
	const stages = ['zktls fetch', 'prove stark', 'prove groth16'];
	let job: Job = {
		id: 'mock', mode: 'sp1-groth16', format: 'eurekha-attested', status: 'running', stage: null, stages: [], elapsedMs: 0,
		progress: null, preview: { publicValues: null, publicValuesHex: '' }, partial: {}, result: null, error: null
	};
	for (let t = 0; t < SECONDS; t++) {
		const fraction = t / SECONDS;
		job = { ...job, stage: stages[Math.floor(fraction * stages.length)], elapsedMs: t * 1000, progress: { fraction, etaMs: (SECONDS - t) * 1000 } };
		onUpdate(job);
		await new Promise((r) => setTimeout(r, 1000));
	}
	job = { ...job, status: 'done', stage: null, elapsedMs: SECONDS * 1000, progress: { fraction: 1 }, result: { artifact } };
	onUpdate(job);
	return job;
}
