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
	/** Results ready before the end (`sp1-compressed`: the SP1 STARK), without their proof bytes. */
	partial: Record<string, PartialInfo>;
	result: Record<string, unknown> | null;
	error: string | null;
};

/** A partial result as polled; its proof is at `proofUrl` ({@link fetchPartial}). */
export type PartialInfo = {
	proofUrl?: string;
	proofBytes?: number;
	encoding?: string;
	vkey?: string;
	proveMs?: number;
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
 * proves: the SP1 STARK shows up under `partial["sp1-compressed"]` first (without the 1.7 MB proof,
 * which {@link fetchPartial} downloads), the Groth16 artifact under `result.artifact` at the end.
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

/** A partial result with its proof (`partial["sp1-compressed"].proof`: base64 bincode SP1 STARK). */
export async function fetchPartial(id: string, name: string): Promise<PartialInfo & { proof: string }> {
	const body = await json(await fetch(`${PROVER_URL}/jobs/${id}/partial/${name}`));
	console.log(`[prover] GET /jobs/${id}/partial/${name}`, { ...body, proof: `${body.proof?.length ?? 0} base64 chars` });
	return body;
}
