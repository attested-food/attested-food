<script lang="ts">
	export type TestState = 'requested' | 'funding' | 'funded' | 'tested';

	let { state, pct = null }: { state: TestState; pct?: number | null } = $props();

	const text = $derived(
		state === 'funding' && pct !== null ? `Funding · ${pct}%` : state[0].toUpperCase() + state.slice(1)
	);
</script>

<span class="tag {state}">{text}</span>

<style>
	.tag {
		display: inline-flex;
		align-items: center;
		padding: 3px 8px;
		border-radius: var(--r);
		font-family: var(--mono);
		font-size: 10px;
		font-weight: 600;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		white-space: nowrap;
	}
	/* Colours come from the surrounding card (--fg, --bg, --sub, --line, --gold-ink) with page defaults. */
	.requested { color: var(--sub); box-shadow: inset 0 0 0 1px var(--line); }
	.funding { color: var(--gold-ink); box-shadow: inset 0 0 0 1px var(--gold-ink); }
	.funded { background: var(--fg, var(--ink)); color: var(--bg, var(--paper)); }
	.tested { background: var(--green); color: var(--gold); }
</style>
