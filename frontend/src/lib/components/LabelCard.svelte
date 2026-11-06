<script lang="ts" module>
	export type Theme = 'light' | 'dark';

	export const THEMES = {
		light: {
			bg: '#FBF9F4', fg: '#13261C', sub: '#5E6B63', line: '#E7E2D6', frame: '#E6E0D0',
			red: '#B3261E', good: '#2F6B4A', blue: '#2846C8', goldInk: '#8C6A32',
			noteUnder: '#E8ECFF', noteCircle: '#FDECEC', noteHl: '#FFF4CC', noteHlFg: '#7A5A00', noteGood: '#EAF3E2'
		},
		dark: {
			bg: '#141414', fg: '#F4F1EA', sub: '#A9AEB4', line: '#2C2E31', frame: '#2A2C2E',
			red: '#FF7B72', good: '#9FD3B0', blue: '#A8B8FF', goldInk: '#C6A26B',
			noteUnder: '#2A3147', noteCircle: '#3A2224', noteHl: '#3A3420', noteHlFg: '#FFE27A', noteGood: '#26331E'
		}
	} as const;

	export function themeVars(theme: Theme) {
		const t = THEMES[theme];
		return [
			`--bg:${t.bg}`, `--fg:${t.fg}`, `--sub:${t.sub}`, `--line:${t.line}`, `--frame:${t.frame}`,
			`--red:${t.red}`, `--good:${t.good}`, `--blue:${t.blue}`, `--gold-ink:${t.goldInk}`,
			`--note-under-bg:${t.noteUnder}`, `--note-circle-bg:${t.noteCircle}`, `--note-hl-bg:${t.noteHl}`,
			`--note-hl-fg:${t.noteHlFg}`, `--note-good-bg:${t.noteGood}`
		].join(';');
	}
</script>

<script lang="ts">
	import { buyUrl, imgFallback, imgSrc, label, nutritionRows, productName, type Finding, type WallItem } from '$lib/api';
	import GradeBox from './GradeBox.svelte';
	import Segments from './Segments.svelte';
	import StateTag from './StateTag.svelte';

	let {
		item,
		theme,
		peeled,
		onpeel,
		onunpeel
	}: { item: WallItem; theme: Theme; peeled: boolean; onpeel: () => void; onunpeel: () => void } = $props();

	const backTheme: Theme = $derived(theme === 'light' ? 'dark' : 'light');
	const name = $derived(productName(item));
	const nut = $derived(nutritionRows(item.label_nutrition, 6));
	const a = $derived(item.annotations);
	const isRequest = $derived(item.kind === 'request');

	const ORDER = { bad: 0, good: 1, info: 2 } as const;
	const rows = $derived.by(() => {
		const f: Finding[] = [...(a?.findings ?? [])].sort((x, y) => ORDER[x.kind] - ORDER[y.kind]);
		if (f.length) return f.slice(0, 3).map((x) => ({ kind: x.kind as string, t: x.parameter, r: x.text }));
		return [{ kind: 'unk', t: 'Lab test', r: isRequest ? 'Requested, not funded yet' : 'Results not on file' }];
	});

	const gradeLabel = $derived(
		isRequest
			? 'Not tested yet'
			: item.grade && item.grade_source
				? `Grade by ${item.grade_source}`
				: item.report_kind === 'user'
					? 'Tested · OpenLabel grade pending'
					: 'Not enough data to grade'
	);

	const month = (d: string | null) =>
		d ? new Date(d).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' }) : null;
	const source = $derived(
		isRequest
			? 'From the label · requested for testing'
			: [item.lab, item.report_kind === 'fallback' && item.grade_source && item.grade_source !== item.lab ? `via ${item.grade_source}` : null, month(item.tested_on)]
					.filter(Boolean)
					.join(' · ')
	);

	const icon = { good: '✓', bad: '✕', info: '•', unk: '?' } as Record<string, string>;
	const stop = (e: Event) => e.stopPropagation();
	const gid = $derived(`curl-${item.kind}-${item.id}`);
</script>

<div class="card" style={themeVars(theme)}>
	<section class="back" style={themeVars(backTheme)} aria-label="What the tests found for {name}" inert={!peeled}>
		<div class="back-in" class:show={peeled}>
			<div class="head">
				<GradeBox grade={item.grade} empty={isRequest ? 'NOT TESTED' : 'NO GRADE'} />
				<div class="head-text">
					<div class="eyebrow">{gradeLabel}</div>
					{#if isRequest}
						<div class="counts"><span class="sub">? Not tested yet</span></div>
					{:else if a}
						<div class="counts">
							<span class="pass">✓ {a.counts.pass} pass</span>
							<span class="fail">✕ {a.counts.fail} fail</span>
							<span class="sub">? {a.counts.untested} not tested</span>
						</div>
					{/if}
				</div>
				<button type="button" class="unpeel" onclick={onunpeel} onmousedown={stop} aria-label="Stick the label back">↺</button>
			</div>

			{#if item.ingredients}
				<p class="ing">
					<span class="sub">{'Ingredients: '}</span>{#if a?.segments.length}<Segments segments={a.segments} compact />{:else}{item.ingredients}{/if}
				</p>
			{/if}

			<ul class="rows">
				{#each rows as x, i (i)}
					<li>
						<span class="ico {x.kind}" aria-hidden="true">{icon[x.kind]}</span>
						<span class="rt">{x.t}</span>
						<span class="rr {x.kind}">{x.r}</span>
					</li>
				{/each}
			</ul>

			<div class="foot">
				<span class="src">{source}</span>
				{#if isRequest}
					<a class="btn small" href="/requests/{item.id}" onmousedown={stop}>Fund this test</a>
				{:else}
					<a class="btn small" href="/products/{item.id}" onmousedown={stop}>Read report</a>
				{/if}
				<a class="btn small ghost buy" href={buyUrl(item)} target="_blank" rel="sponsored noopener" onmousedown={stop}>Buy</a>
			</div>
		</div>
	</section>

	<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions (the peel button below is the keyboard path) -->
	<div class="front" class:peeled onclick={onpeel} inert={peeled}>
		<div class="sheet">
			<div class="photo">
				<img src={imgSrc(item.image_url)} alt="{name} pack" draggable="false" loading="lazy" referrerpolicy="no-referrer" onerror={imgFallback} />
			</div>
			<div class="info">
				<div class="top">
					<span class="eyebrow">{label(item.category)}</span>
					<StateTag state={item.state} />
				</div>
				<div class="brand">{item.brand}</div>
				<div class="name">{name}</div>
				<p class="ing-front">
					<span class="sub">{'Ingredients: '}</span>{item.ingredients ?? 'Not on file yet.'}
				</p>
				<div class="nut">
					<div class="nut-head"><span>Nutrition</span><span class="sub">per 100 g</span></div>
					{#if nut.length}
						<div class="nut-grid">
							{#each nut as n (n.key)}
								<div class="nut-row"><span>{n.name}</span><strong>{n.value}</strong></div>
							{/each}
						</div>
					{:else}
						<div class="nut-none sub">Label values not on file yet</div>
					{/if}
				</div>
			</div>
		</div>
		<button type="button" class="peel" onmousedown={stop} aria-label="Peel the label to see what the tests found for {name}">
			<svg aria-hidden="true" width="96" height="96" viewBox="0 0 100 100">
				<defs>
					<linearGradient id={gid} gradientUnits="userSpaceOnUse" x1="52" y1="52" x2="72" y2="72">
						<stop offset="0" stop-color="#EDEDED" />
						<stop offset="0.3" stop-color="#FFFFFF" />
						<stop offset="0.55" stop-color="#F3F3F3" />
						<stop offset="0.82" stop-color="#D4D4D4" />
						<stop offset="1" stop-color="#BDBDBD" />
					</linearGradient>
				</defs>
				<path d="M100 37.8 C97 42 94 44.5 88 45.5 C76 47 62 49 55 50.5 Q51.5 51.5 51.6 55 C52 66 51.5 80 47 89 C43 95 38 98.5 33.8 100 Z" fill="url(#{gid})" />
			</svg>
		</button>
	</div>
</div>

<style>
	.card {
		position: relative;
		width: 600px;
		height: 380px;
		perspective: 1600px;
		font-family: var(--sans);
	}
	.sub {
		color: var(--sub);
	}
	.eyebrow {
		font-family: var(--mono);
		font-size: 10.5px;
		letter-spacing: 0.07em;
		text-transform: uppercase;
		color: var(--sub);
	}

	/* Back: what the tests found */
	.back {
		position: absolute;
		inset: 0;
		padding: 22px 26px 20px;
		border-radius: 6px;
		background: var(--bg);
		color: var(--fg);
		display: flex;
		flex-direction: column;
		box-shadow: 0 30px 60px -30px rgba(0, 0, 0, 0.6);
	}
	.back-in {
		flex: 1;
		min-height: 0;
		display: flex;
		flex-direction: column;
		opacity: 0;
		visibility: hidden;
		transition: opacity 0.15s ease, visibility 0s linear 0.15s;
	}
	.back-in.show {
		opacity: 1;
		visibility: visible;
		transition: opacity 0.35s ease 0.3s, visibility 0s;
	}
	.head {
		display: flex;
		align-items: center;
		gap: 14px;
	}
	.head-text {
		flex: 1;
		min-width: 0;
	}
	.counts {
		display: flex;
		flex-wrap: wrap;
		gap: 6px 14px;
		margin-top: 6px;
		font-size: 14px;
		font-weight: 600;
	}
	.pass {
		color: var(--good);
	}
	.fail {
		color: var(--red);
	}
	.unpeel {
		flex: 0 0 auto;
		align-self: flex-start;
		width: 34px;
		height: 34px;
		border: 1px solid var(--line);
		border-radius: var(--r);
		background: transparent;
		color: var(--fg);
		font-size: 15px;
		cursor: pointer;
	}
	.ing {
		margin: 14px 0 0;
		flex: 0 1 auto;
		min-height: 0;
		font-family: var(--label);
		font-weight: 600;
		font-size: 17px;
		line-height: 1.55;
		text-transform: uppercase;
		letter-spacing: 0.005em;
		overflow: hidden;
		-webkit-mask-image: linear-gradient(180deg, #000 80%, transparent 100%);
		mask-image: linear-gradient(180deg, #000 80%, transparent 100%);
	}
	.rows {
		margin: 12px 0 0;
		padding: 0;
		list-style: none;
		flex: 0 0 auto;
	}
	.rows li {
		display: flex;
		align-items: center;
		gap: 12px;
		height: 34px;
		border-top: 1px solid var(--line);
	}
	.ico {
		flex: 0 0 auto;
		width: 20px;
		height: 20px;
		border-radius: var(--r);
		display: flex;
		align-items: center;
		justify-content: center;
		font-weight: 700;
		font-size: 11px;
	}
	.ico.good {
		background: var(--good);
		color: var(--bg);
	}
	.ico.bad {
		background: var(--red);
		color: #fff;
	}
	.ico.info {
		box-shadow: inset 0 0 0 1px var(--line);
		color: var(--sub);
	}
	.ico.unk {
		border: 1px dashed var(--sub);
		color: var(--sub);
	}
	.rt {
		flex: 1;
		min-width: 0;
		font-size: 13.5px;
		font-weight: 550;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.rr {
		flex: 0 0 auto;
		font-size: 13.5px;
		font-weight: 650;
	}
	.rr.good {
		color: var(--good);
	}
	.rr.bad {
		color: var(--red);
	}
	.rr.unk,
	.rr.info {
		color: var(--sub);
	}
	.foot {
		margin-top: auto;
		display: flex;
		align-items: center;
		gap: 10px;
		padding-top: 12px;
		border-top: 1px solid var(--line);
	}
	.src {
		flex: 1;
		min-width: 0;
		font-family: var(--mono);
		font-size: 10.5px;
		letter-spacing: 0.02em;
		text-transform: uppercase;
		color: var(--sub);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.foot .btn {
		min-height: 38px;
	}
	.buy {
		color: var(--fg);
		box-shadow: inset 0 0 0 1.5px var(--fg);
	}
	.buy:hover {
		background: var(--fg);
		color: var(--bg);
	}

	/* Front: the label, no spoilers */
	.front {
		position: absolute;
		inset: 0;
		cursor: pointer;
		transform-origin: 0 0;
		transform: rotate3d(1, -1, 0, 0deg);
		transition:
			transform 0.9s cubic-bezier(0.55, 0.06, 0.3, 1),
			opacity 0.1s linear 0s;
		backface-visibility: hidden;
	}
	.front.peeled {
		transform: rotate3d(1, -1, 0, 180deg);
		opacity: 0;
		pointer-events: none;
		transition:
			transform 0.9s cubic-bezier(0.55, 0.06, 0.3, 1),
			opacity 0.2s linear 0.55s;
	}
	.sheet {
		position: absolute;
		inset: 0;
		border-radius: 6px;
		background: var(--bg);
		color: var(--fg);
		clip-path: path('M0 0 H600 V320.3 L536.4 380 H0 Z');
		display: flex;
		box-shadow: 0 30px 60px -30px rgba(0, 0, 0, 0.6);
	}
	.photo {
		flex: 0 0 236px;
		padding: 14px 0 14px 14px;
	}
	.photo img {
		display: block;
		width: 222px;
		height: 352px;
		object-fit: contain;
		padding: 10px;
		background: #ffffff;
		border-radius: var(--r);
		border: 1px solid var(--frame);
	}
	.info {
		flex: 1;
		min-width: 0;
		padding: 22px 26px 22px 22px;
		display: flex;
		flex-direction: column;
	}
	.top {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 10px;
	}
	.brand {
		font-size: 13px;
		color: var(--sub);
		margin-top: 16px;
	}
	.name {
		font-weight: 650;
		font-size: 24px;
		letter-spacing: -0.03em;
		line-height: 1.08;
		margin-top: 2px;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
	.ing-front {
		margin: 14px 0 0;
		flex: 1 1 auto;
		min-height: 0;
		font-family: var(--label);
		font-weight: 600;
		font-size: 15.5px;
		line-height: 1.32;
		text-transform: uppercase;
		letter-spacing: 0.005em;
		overflow: hidden;
		-webkit-mask-image: linear-gradient(180deg, #000 72%, transparent 100%);
		mask-image: linear-gradient(180deg, #000 72%, transparent 100%);
	}
	.nut {
		margin-top: 10px;
		padding-right: 60px;
		font-family: var(--label);
	}
	.nut-head {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		border-bottom: 3px solid var(--fg);
		padding-bottom: 3px;
		font-weight: 700;
		font-size: 14px;
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}
	.nut-head .sub {
		font-weight: 500;
	}
	.nut-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		column-gap: 18px;
	}
	.nut-row {
		display: flex;
		justify-content: space-between;
		gap: 8px;
		padding: 3px 0;
		border-bottom: 1px solid var(--line);
		font-size: 15px;
		font-weight: 500;
	}
	.nut-row strong {
		font-weight: 700;
	}
	.nut-none {
		padding: 8px 0;
		font-size: 15px;
	}
	.peel {
		position: absolute;
		left: 504px;
		top: 284px;
		width: 96px;
		height: 96px;
		padding: 0;
		border: 0;
		background: none;
		cursor: pointer;
	}
	.peel svg {
		position: absolute;
		inset: 0;
		overflow: visible;
		filter: drop-shadow(-3px -3px 8px rgba(0, 0, 0, 0.4)) drop-shadow(-1px -1px 1px rgba(0, 0, 0, 0.22));
		transition: transform 0.3s ease;
		transform-origin: 100% 100%;
	}
	.peel:hover svg,
	.peel:focus-visible svg {
		transform: scale(1.08);
	}
	@media (prefers-reduced-motion: reduce) {
		.front,
		.front.peeled,
		.back-in,
		.back-in.show {
			transition: none;
		}
	}
</style>
