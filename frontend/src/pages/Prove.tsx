import { useState } from 'react';
import { pollJob, PROVER_URL, startProof, type Job, type ProveMode } from '@/lib/prover';

// Prover test page: sends a lab report PDF to the backend2-rs prover and logs every
// response to the browser console. Optional zktls files switch to the TLS-attested
// statement, which `sp1-groth16` (the EVM-verifiable proof) needs.
export default function Prove() {
	const [pdf, setPdf] = useState<File | null>(null);
	const [mode, setMode] = useState<ProveMode>('stark');
	const [onchain, setOnchain] = useState<File | null>(null);
	const [request, setRequest] = useState<File | null>(null);
	const [blinder, setBlinder] = useState('');
	const [job, setJob] = useState<Job | null>(null);
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState('');

	const attested = !!(onchain && request && blinder.trim());

	async function submit(e: React.FormEvent) {
		e.preventDefault();
		if (!pdf) return;
		setError('');
		setJob(null);
		setBusy(true);
		try {
			const id = await startProof(pdf, mode, attested ? { onchain: onchain!, request: request!, blinder } : undefined);
			const done = await pollJob(id, setJob);
			if (done.status === 'failed') setError(done.error ?? 'proof failed');
		} catch (err) {
			console.error('[prover]', err);
			setError((err as Error).message);
		} finally {
			setBusy(false);
		}
	}

	return (
		<div className="page narrow">
			<title>Prove a report · OpenLabel</title>
			<div className="page-head">
				<div>
					<h1>Prove a lab report</h1>
					<p className="lede">Sends the PDF to the prover at <code>{PROVER_URL}</code>. Responses are logged to the browser console.</p>
				</div>
			</div>
			<form className="stack" onSubmit={submit}>
				<label className="field">Lab report PDF *
					<input type="file" accept="application/pdf" required onChange={(e) => setPdf(e.target.files?.[0] ?? null)} />
				</label>
				<label className="field">Proof
					<select value={mode} onChange={(e) => setMode(e.target.value as ProveMode)}>
						<option value="execute">Execute only (no proof, seconds)</option>
						<option value="stark">OpenVM STARK (~40 s)</option>
						<option value="sp1-groth16">SP1 Groth16 for the contract (needs the TLS files)</option>
					</select>
				</label>
				<details>
					<summary>TLS attestation (optional, from a zktls run)</summary>
					<label className="field">onchain.json<input type="file" accept="application/json" onChange={(e) => setOnchain(e.target.files?.[0] ?? null)} /></label>
					<label className="field">request.json<input type="file" accept="application/json" onChange={(e) => setRequest(e.target.files?.[0] ?? null)} /></label>
					<label className="field">blinder.hex<input value={blinder} onChange={(e) => setBlinder(e.target.value)} placeholder="32 hex characters" /></label>
				</details>
				<div>
					<button className="btn" type="submit" disabled={!pdf || busy || (mode === 'sp1-groth16' && !attested)}>
						{busy ? 'Proving…' : 'Generate proof'}
					</button>
				</div>
			</form>
			{error && <p className="error">{error}</p>}
			{job && (
				<p className="muted">
					Job {job.id}: {job.status}, stage <strong>{job.stage}</strong>, {Math.round(job.elapsedMs / 1000)} s
					{job.progress?.fraction != null && job.status !== 'done' && <> · ~{Math.round(job.progress.fraction * 100)}%</>}
				</p>
			)}
		</div>
	);
}
