// The tester's prove-and-post job lives here, outside any page, so it keeps running while the user
// moves around the app; ReportTaskWindow shows it, Fund shows it inline on the request page.
import { useSyncExternalStore } from 'react';
import { stringToHex, type Hex } from 'viem';
import { MOCK_PROVER, mockProof, pollJob, startProof, type Job } from './prover';
import { fundAbi, fundAddress, send } from './wallet';

export type ReportTask = {
	requestId: string;
	id: Hex;
	title: string;
	phase: 'proving' | 'posting' | 'done' | 'failed';
	job: Job | null;
	error: string | null;
	startedAt: number;
};

type Artifact = { publicValues: Hex; proof: Hex; notarySignature: Hex };

let task: ReportTask | null = null;
const listeners = new Set<() => void>();
const subscribe = (l: () => void) => {
	listeners.add(l);
	return () => listeners.delete(l);
};
function update(patch: Partial<ReportTask> | null) {
	task = patch && task ? { ...task, ...patch } : null;
	listeners.forEach((l) => l());
}
export const useReportTask = () => useSyncExternalStore(subscribe, () => task);
export const isRunning = (t: ReportTask | null) => t?.phase === 'proving' || t?.phase === 'posting';

const hex = (v: unknown) => (String(v).startsWith('0x') ? String(v) : `0x${v}`) as Hex;
const firstLine = (e: unknown) =>
	e instanceof Error ? ('shortMessage' in e && String(e.shortMessage)) || e.message.split('\n')[0] : String(e);

/** A proof made earlier whose posting failed, so a retry needn't prove again. */
export function savedProof(id: Hex): Artifact | null {
	try {
		return JSON.parse(localStorage.getItem(`proof:${id}`) ?? 'null');
	} catch {
		return null;
	}
}

/** Prove `pdf` (or reuse a saved proof) and post it to TestFund. One task at a time. */
export async function proveAndPost(requestId: string, id: Hex, title: string, pdf: File | null) {
	if (isRunning(task)) throw new Error('A lab report is already being proved.');
	task = { requestId, id, title, phase: 'proving', job: null, error: null, startedAt: Date.now() };
	update({});
	try {
		let a = savedProof(id);
		if (!a) {
			if (!pdf) throw new Error('Choose the lab report PDF.');
			const onJob = (job: Job) => update({ job });
			const done = MOCK_PROVER ? await mockProof(onJob) : await pollJob(await startProof(pdf), onJob);
			const raw = done.result?.artifact as Record<string, unknown> | undefined;
			if (done.status === 'failed' || !raw) throw new Error(done.error ?? 'The prover returned no proof.');
			a = { publicValues: hex(raw.publicValues), proof: hex(raw.proof), notarySignature: hex(raw.notarySignature) };
			try { localStorage.setItem(`proof:${id}`, JSON.stringify(a)); } catch { /* storage unavailable: a retry proves again */ }
		}
		update({ phase: 'posting' });
		await send({
			address: fundAddress!, abi: fundAbi, functionName: 'submitReport',
			args: [id, stringToHex('sp1', { size: 32 }), a.publicValues, a.proof, a.notarySignature]
		});
		try { localStorage.removeItem(`proof:${id}`); } catch { /* storage unavailable */ }
		update({ phase: 'done' });
	} catch (e) {
		console.error('[report]', e);
		update({ phase: 'failed', error: firstLine(e) });
	}
}

/** Close a finished or failed task. A running one can't be dismissed. */
export function dismissReportTask() {
	if (!isRunning(task)) update(null);
}

if (typeof window !== 'undefined') {
	window.addEventListener('beforeunload', (e) => {
		if (isRunning(task)) e.preventDefault();
	});
}
