import type { Segment } from '@/lib/api';

const words = (t: string) => t.split(/(?<=\s)/);

/** Shorten long unmarked stretches so the marked parts fit on a small card. */
export function squeeze(segs: Segment[], keep = 4): Segment[] {
	if (!segs.some((s) => s.mark)) return segs;
	const out: Segment[] = [];
	let run = '';
	const flush = (where: 'start' | 'middle' | 'end') => {
		if (!run) return;
		const w = words(run);
		let t = run;
		if (w.length > keep * 2 + 1) {
			t = where === 'end' ? w.slice(0, keep).join('').trimEnd() + '…' : w.slice(0, keep).join('') + '… ' + w.slice(-keep).join('');
		}
		out.push({ t, mark: null, note: null });
		run = '';
	};
	for (const s of segs) {
		if (s.mark || s.note) {
			flush(out.length === 0 ? 'start' : 'middle');
			out.push(s);
		} else run += s.t;
	}
	flush('end');
	return out;
}

/** Ingredient list with lab-derived marks: red circles, highlights, underlines and numeric notes. */
export function Segments({ segments, compact = false }: { segments: Segment[]; compact?: boolean }) {
	const pieces = compact ? squeeze(segments) : segments;
	return (
		<>
			{pieces.map((p, i) => (
				<span key={i}>
					{p.mark ? (
						<span className={`seg-m ${p.mark}${p.t.length > 28 ? ' wrap' : ''}`}>
							{p.t}
							{p.mark === 'circle' && (
								<svg aria-hidden="true" viewBox="0 0 200 70" preserveAspectRatio="none" className="ring">
									<path d="M30 8 C 120 -4, 196 14, 192 36 C 188 62, 70 70, 18 56 C -6 48, 4 18, 44 10" />
								</svg>
							)}
							{(p.mark === 'under' || p.mark === 'good') && (
								<svg aria-hidden="true" viewBox="0 0 300 12" preserveAspectRatio="none" className="uline">
									<path d="M2 7 C 80 2, 190 11, 298 5" />
								</svg>
							)}
						</span>
					) : (
						p.t
					)}
					{p.note && <span className={`seg-note ${p.mark ?? 'under'}`}>← {p.note}</span>}
				</span>
			))}
		</>
	);
}
