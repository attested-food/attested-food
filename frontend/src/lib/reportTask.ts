// The tester's prove-then-submit job lives here, outside any page, so proving keeps running while the
// user moves around the app; ReportTaskWindow shows it, Fund shows it inline on the request page.
// Proving ends at `ready`: the transaction is only sent when the tester clicks Submit.
import { useSyncExternalStore } from 'react';
import { stringToHex, type Hex } from 'viem';
import { pollJob, startProof, type Job } from './prover';
import { fundAbi, fundAddress, send } from './wallet';

type Artifact = { publicValues: Hex; proof: Hex; notarySignature: Hex };

export type ReportTask = {
	requestId: string;
	id: Hex;
	title: string;
	phase: 'proving' | 'ready' | 'posting' | 'done' | 'failed';
	job: Job | null;
	artifact: Artifact | null;
	error: string | null;
};

let task: ReportTask | null = null;
const listeners = new Set<() => void>();
const subscribe = (l: () => void) => {
	listeners.add(l);
	return () => listeners.delete(l);
};
function set(next: ReportTask | null) {
	task = next;
	listeners.forEach((l) => l());
}
const update = (patch: Partial<ReportTask>) => task && set({ ...task, ...patch });
export const useReportTask = () => useSyncExternalStore(subscribe, () => task);

/** Proving, waiting for Submit, or submitting: the task can't be closed or replaced. */
export const isActive = (t: ReportTask | null) => t?.phase === 'proving' || t?.phase === 'ready' || t?.phase === 'posting';

const hex = (v: unknown) => (String(v).startsWith('0x') ? String(v) : `0x${v}`) as Hex;
const firstLine = (e: unknown) =>
	e instanceof Error ? ('shortMessage' in e && String(e.shortMessage)) || e.message.split('\n')[0] : String(e);

/** A proof made earlier but not submitted, so the tester needn't prove again. */
export function savedProof(id: Hex): Artifact | null {
	try {
		return JSON.parse(localStorage.getItem(`proof:${id}`) ?? 'null');
	} catch {
		return null;
	}
}

/** Prove `pdf` in the background; ends at `ready` (or reuses a saved proof straight away). */
export async function prove(requestId: string, id: Hex, title: string, pdf: File | null) {
	if (isActive(task)) throw new Error('A lab report is already being proved.');
	const saved = savedProof(id);
	set({ requestId, id, title, phase: saved ? 'ready' : 'proving', job: null, artifact: saved, error: null });
	if (saved) return;
	try {
		if (!pdf) throw new Error('Choose the lab report PDF.');
		const onJob = (job: Job) => update({ job });
		const done = await pollJob(await startProof(pdf), onJob);
		const raw = done.result?.artifact as Record<string, unknown> | undefined;
		if (done.status === 'failed' || !raw) throw new Error(done.error ?? 'The prover returned no proof.');
		const artifact = { publicValues: hex(raw.publicValues), proof: hex(raw.proof), notarySignature: hex(raw.notarySignature) };
		try { localStorage.setItem(`proof:${id}`, JSON.stringify(artifact)); } catch { /* storage unavailable: a reload proves again */ }
		update({ phase: 'ready', artifact });
	} catch (e) {
		console.error('[report] prove', e);
		update({ phase: 'failed', error: firstLine(e) });
	}
}

/** Send the proven report to TestFund. Only from `ready`; a rejected or failed tx goes back to `ready`. */
export async function submit() {
	const t = task;
	if (t?.phase !== 'ready' || !t.artifact) return;
	update({ phase: 'posting', error: null });
	try {
		const a = t.artifact;
		await send({
			address: fundAddress!, abi: fundAbi, functionName: 'submitReport',
			args: [t.id, stringToHex('sp1', { size: 32 }), a.publicValues, a.proof, a.notarySignature]
		});
		try { localStorage.removeItem(`proof:${t.id}`); } catch { /* storage unavailable */ }
		update({ phase: 'done' });
	} catch (e) {
		console.error('[report] submit', e);
		update({ phase: 'ready', error: firstLine(e) });
	}
}

/** Close a finished or failed task. */
export function dismissReportTask() {
	if (!isActive(task)) set(null);
}

if (typeof window !== 'undefined') {
	window.addEventListener('beforeunload', (e) => {
		if (task?.phase === 'proving' || task?.phase === 'posting') e.preventDefault();
	});
}
