import { Link, useLocation } from 'react-router';
import { dismissReportTask, isRunning, useReportTask, type ReportTask } from '@/lib/reportTask';

/** Stage, elapsed time and a progress bar for a prove-and-post task. */
export function TaskProgress({ task }: { task: ReportTask }) {
	const job = task.job;
	const pct = task.phase === 'posting' ? 100 : Math.round((job?.progress?.fraction ?? 0) * 100);
	const label =
		task.phase === 'posting' ? 'Posting the proof on-chain…' : job?.stage ? `Proving: ${job.stage}` : 'Starting the prover…';
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

/** Bottom-right window for the tester's background prove-and-post, shown on every other page.
 *  It can only be closed once the proof is posted or has failed. */
export function ReportTaskWindow() {
	const task = useReportTask();
	const { pathname } = useLocation();
	if (!task) return null;
	const page = `/requests/${task.requestId}`;
	const running = isRunning(task);
	if (running && pathname === page) return null;

	return (
		<aside className="task-window card" role="status" aria-label="Lab report proof">
			<div className="task-head">
				<strong>{task.phase === 'done' ? 'Report verified and posted' : task.phase === 'failed' ? "Couldn't post the report" : 'Proving the lab report'}</strong>
				{!running && <button type="button" className="task-close" aria-label="Close" onClick={dismissReportTask}>×</button>}
			</div>
			<p className="small muted task-title">{task.title}</p>
			{running && <TaskProgress task={task} />}
			{task.phase === 'done' && <p className="small">The proof checked out on-chain and you've been paid.</p>}
			{task.phase === 'failed' && <p className="error small">{task.error}</p>}
			{pathname !== page && <Link className="link small" to={page}>{task.phase === 'done' ? 'See the results' : 'Open the request'}</Link>}
		</aside>
	);
}
