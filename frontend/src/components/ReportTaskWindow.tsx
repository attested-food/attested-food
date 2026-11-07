import { Link, useLocation } from 'react-router';
import { dismissReportTask, isActive, submit, useReportTask, type ReportTask } from '@/lib/reportTask';

/** Stage, elapsed time and a progress bar while proving or submitting. */
export function TaskProgress({ task }: { task: ReportTask }) {
	const job = task.job;
	const pct = task.phase === 'posting' ? 100 : Math.round((job?.progress?.fraction ?? 0) * 100);
	const label =
		task.phase === 'posting' ? 'Submitting on-chain… confirm in your wallet' : job?.stage ? `Proving: ${job.stage}` : 'Starting the prover…';
	return (
		<div className="task-progress">
			<span className="bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}><span style={{ width: `${pct}%` }} /></span>
			<p className="small muted" aria-live="polite">
				{label}
				{task.phase === 'proving' && job && <> · {Math.round(job.elapsedMs / 1000)} s · {pct}%</>}
			</p>
		</div>
	);
}

/** Submit button for a proof that's ready; the transaction is only sent on click. */
export function SubmitProof({ task }: { task: ReportTask }) {
	return (
		<div className="task-submit">
			<button type="button" className="btn" disabled={task.phase !== 'ready'} onClick={submit}>
				{task.phase === 'posting' ? 'Submitting…' : 'Submit'}
			</button>
			{task.phase === 'ready' && <span className="small muted">Proof ready. Submit it to post the report and get paid.</span>}
		</div>
	);
}

const HEADS: Record<ReportTask['phase'], string> = {
	proving: 'Proving the lab report',
	ready: 'Proof ready to submit',
	posting: 'Submitting the report',
	done: 'Report verified and posted',
	failed: "Couldn't prove the report"
};

/** Bottom-right window for the tester's background proof, on every page but the request itself.
 *  It can only be closed once the report is posted or proving has failed. */
export function ReportTaskWindow() {
	const task = useReportTask();
	const { pathname } = useLocation();
	if (!task) return null;
	const page = `/requests/${task.requestId}`;
	const active = isActive(task);
	if (active && pathname === page) return null;

	return (
		<aside className="task-window card" role="status" aria-label="Lab report proof">
			<div className="task-head">
				<strong>{HEADS[task.phase]}</strong>
				{!active && <button type="button" className="task-close" aria-label="Close" onClick={dismissReportTask}>×</button>}
			</div>
			<p className="small muted">{task.title}</p>
			{(task.phase === 'proving' || task.phase === 'posting') && <TaskProgress task={task} />}
			{(task.phase === 'ready' || task.phase === 'posting') && <SubmitProof task={task} />}
			{task.phase === 'done' && <p className="small">The proof checked out on-chain and you've been paid.</p>}
			{task.error && <p className="error small">{task.error}</p>}
			{pathname !== page && <Link className="link small" to={page}>{task.phase === 'done' ? 'See the results' : 'Open the request'}</Link>}
		</aside>
	);
}
