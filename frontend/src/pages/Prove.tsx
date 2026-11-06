import { useState } from 'react';
import { pollJob, PROVER_URL, startProof, type Job } from '@/lib/prover';

// Prover test page: sends a lab report PDF and its zktls session files to the backend2-rs
// prover as an SP1 Groth16 job and logs every response to the browser console.
export default function Prove() {
	const [pdf, setPdf] = useState<File | null>(null);
	const [onchain, setOnchain] = useState<File | null>(null);
	const [request, setRequest] = useState<File | null>(null);
	const [blinder, setBlinder] = useState('');
	const [job, setJob] = useState<Job | null>(null);
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState('');

	const ready = !!(pdf && onchain && request && blinder.trim());

	async function submit(e: React.FormEvent) {
		e.preventDefault();
		if (!ready) return;
		setError('');
		setJob(null);
		setBusy(true);
		try {
			const id = await startProof(pdf!, { onchain: onchain!, request: request!, blinder });
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
					<p className="lede">Sends the PDF and its zktls session to the prover at <code>{PROVER_URL}</code> for an SP1 Groth16 proof. Responses are logged to the browser console.</p>
				</div>
			</div>
			<form className="stack" onSubmit={submit}>
				<label className="field">Lab report PDF *
					<input type="file" accept="application/pdf" required onChange={(e) => setPdf(e.target.files?.[0] ?? null)} />
				</label>
				<label className="field">onchain.json (zktls session) *
					<input type="file" accept="application/json" required onChange={(e) => setOnchain(e.target.files?.[0] ?? null)} />
				</label>
				<label className="field">request.json (zktls session) *
					<input type="file" accept="application/json" required onChange={(e) => setRequest(e.target.files?.[0] ?? null)} />
				</label>
				<label className="field">blinder.hex (zktls session) *
					<input value={blinder} required onChange={(e) => setBlinder(e.target.value)} placeholder="32 hex characters" />
				</label>
				<div>
					<button className="btn" type="submit" disabled={!ready || busy}>
						{busy ? 'Proving…' : 'Generate SP1 Groth16 proof'}
					</button>
				</div>
			</form>
			{error && <p className="error">{error}</p>}
			{job && (
				<p className="muted">
					Job {job.id}: {job.status}, stage <strong>{job.stage}</strong>, {Math.round(job.elapsedMs / 1000)} s
					{job.progress?.fraction != null && job.status !== 'done' && <> · ~{Math.round(job.progress.fraction * 100)}%</>}
					{'sp1-compressed' in (job.partial ?? {}) && <> · STARK ready</>}
					{job.result?.artifact != null && <> · Groth16 ready</>}
				</p>
			)}
		</div>
	);
}
