// Client for the backend2-rs prover (backend2-rs/README.md): POST /prove starts a job,
// GET /jobs/{id} reports its stage, progress and, when done, the proof.

export const PROVER_URL: string = import.meta.env.VITE_PROVER_URL ?? 'https://prover.openlabel.fyi';

export type ProveMode = 'execute' | 'stark' | 'sp1-groth16';

/** The `onchain.json`, `request.json` and `blinder.hex` of a zktls run (eurekha-attested only). */
export type Attestation = { onchain: File; request: File; blinder: string };

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
	result: Record<string, unknown> | null;
	error: string | null;
};

async function json(res: Response): Promise<any> {
	const body = await res.json().catch(() => ({ error: `${res.status} ${res.statusText}` }));
	if (!res.ok) throw new Error(body.error ?? `${res.status} ${res.statusText}`);
	return body;
}

/** Start a proving job; resolves to its id once the server's preflight accepts the PDF. */
export async function startProof(pdf: File, mode: ProveMode, attestation?: Attestation): Promise<string> {
	const form = new FormData();
	form.append('pdf', pdf);
	if (attestation) {
		form.append('format', 'eurekha-attested');
		form.append('onchain', await attestation.onchain.text());
		form.append('request', await attestation.request.text());
		form.append('blinder', attestation.blinder.trim());
	} else {
		form.append('format', 'eurekha');
	}
	const body = await json(await fetch(`${PROVER_URL}/prove?mode=${mode}`, { method: 'POST', body: form }));
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
