// Client for the backend2-rs prover (backend2-rs/README.md): POST /prove starts a job,
// GET /jobs/{id} reports its stage, progress and, when done, the proof.

export const PROVER_URL: string = import.meta.env.VITE_PROVER_URL ?? 'https://prover.openlabel.fyi';

/** The `onchain.json`, `request.json` and `blinder.hex` of the zktls session that fetched the PDF. */
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
 * Start an SP1 Groth16 job (the proof `EurekhaReportRegistry.submit` takes); resolves to its id
 * once the server's preflight accepts the PDF and attestation. The job shows the SP1 STARK under
 * `partial["sp1-compressed"]` first, then the Groth16 artifact under `result.artifact`.
 */
export async function startProof(pdf: File, attestation: Attestation): Promise<string> {
	const form = new FormData();
	form.append('pdf', pdf);
	form.append('format', 'eurekha-attested');
	form.append('onchain', await attestation.onchain.text());
	form.append('request', await attestation.request.text());
	form.append('blinder', attestation.blinder.trim());
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
