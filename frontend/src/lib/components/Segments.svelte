<script lang="ts" module>
	import type { Segment } from '$lib/api';

	const words = (t: string) => t.split(/(?<=\s)/);

	/** Shorten long unmarked stretches so the marked parts fit on a small card. */
	export function squeeze(segs: Segment[], keep = 4): Segment[] {
		const out: Segment[] = [];
		const firstMark = segs.findIndex((s) => s.mark);
		if (firstMark < 0) return segs;
		let run = '';
		const flush = (where: 'start' | 'middle' | 'end') => {
			if (!run) return;
			const w = words(run);
			let t = run;
			if (w.length > keep * 2 + 1) {
				if (where === 'start') t = w.slice(0, keep).join('') + '… ' + w.slice(-keep).join('');
				else if (where === 'end') t = w.slice(0, keep).join('').trimEnd() + '…';
				else t = w.slice(0, keep).join('') + '… ' + w.slice(-keep).join('');
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
</script>

<script lang="ts">
	let { segments, compact = false }: { segments: Segment[]; compact?: boolean } = $props();

	const pieces = $derived(compact ? squeeze(segments) : segments);
</script>

{#each pieces as p, i (i)}{#if p.mark}<span
			class="m {p.mark}"
			class:wrap={p.t.length > 28}
			>{p.t}{#if p.mark === 'circle'}<svg aria-hidden="true" viewBox="0 0 200 70" preserveAspectRatio="none" class="ring"><path d="M30 8 C 120 -4, 196 14, 192 36 C 188 62, 70 70, 18 56 C -6 48, 4 18, 44 10" /></svg>{:else if p.mark === 'under' || p.mark === 'good'}<svg aria-hidden="true" viewBox="0 0 300 12" preserveAspectRatio="none" class="line"><path d="M2 7 C 80 2, 190 11, 298 5" /></svg>{/if}</span>{:else}{p.t}{/if}{#if p.note}<span class="note {p.mark ?? 'under'}">← {p.note}</span>{/if}{/each}

<style>
	.m {
		position: relative;
		white-space: nowrap;
	}
	.m.wrap {
		white-space: normal;
	}
	.hl {
		background: var(--hl);
		color: #141414;
		padding: 0 4px;
		box-decoration-break: clone;
		-webkit-box-decoration-break: clone;
	}
	.circle {
		padding: 0 3px;
	}
	svg {
		position: absolute;
		overflow: visible;
		pointer-events: none;
	}
	.ring {
		left: -9px;
		top: -3px;
		width: calc(100% + 18px);
		height: calc(100% + 6px);
	}
	.ring path {
		fill: none;
		stroke: var(--red);
		stroke-width: 2.4;
		stroke-linecap: round;
		vector-effect: non-scaling-stroke;
	}
	.line {
		left: 0;
		bottom: -3px;
		width: 100%;
		height: 8px;
	}
	.line path {
		fill: none;
		stroke: var(--blue);
		stroke-width: 2.6;
		stroke-linecap: round;
		vector-effect: non-scaling-stroke;
	}
	.good .line path {
		stroke: var(--good);
	}
	.note {
		display: inline-block;
		margin: 0 4px;
		padding: 1px 7px;
		border-radius: 2px;
		font-family: var(--sans);
		font-size: 11.5px;
		font-weight: 600;
		line-height: 1.6;
		text-transform: none;
		letter-spacing: 0;
		vertical-align: 2px;
		white-space: nowrap;
		background: var(--note-under-bg, #e8ecff);
		color: var(--blue);
	}
	.note.circle {
		background: var(--note-circle-bg, #fdecec);
		color: var(--red);
	}
	.note.hl {
		background: var(--note-hl-bg, #fff4cc);
		color: var(--note-hl-fg, #7a5a00);
	}
	.note.good {
		background: var(--note-good-bg, #eaf3e2);
		color: var(--good);
	}
</style>
