<script lang="ts">
	import { api, httpUrl, type Source } from '$lib/api';

	const sources = api<Source[]>('/api/sources');
	const groups = [
		['lab', 'Labs', 'Accredited labs that ran the tests.'],
		['website', 'Published data', 'Testing websites whose results we show, with credit and a link back, until we test a product ourselves.']
	] as const;
</script>

<svelte:head><title>Sources · OpenLabel</title></svelte:head>

<div class="page narrow">
	<h1>Sources</h1>
	<p class="lede">Where every number on OpenLabel comes from.</p>

	{#await sources}
		<p class="muted">Loading…</p>
	{:then list}
		{#if !list.length}<p>No sources yet.</p>{/if}
		{#each groups as [type, title, blurb] (type)}
			{@const items = list.filter((s) => s.type === type)}
			{#if items.length}
				<section>
					<h2>{title}</h2>
					<p class="muted">{blurb}</p>
					<ul>
						{#each items as s (s.id)}
							<li>
								<div class="name">
									{#if httpUrl(s.url)}<a href={httpUrl(s.url)} rel="noopener">{s.name}</a>{:else}{s.name}{/if}
									{#if s.accreditation}<span class="acc">{s.accreditation}</span>{/if}
								</div>
								<span class="count">{s.report_count} report{s.report_count === 1 ? '' : 's'}</span>
								{#if s.description}<p class="muted desc">{s.description}</p>{/if}
							</li>
						{/each}
					</ul>
				</section>
			{/if}
		{/each}
		<section>
			<h2>Ingredients and label nutrition</h2>
			<p class="muted">Where we haven't scanned a pack ourselves, ingredient lists and label nutrition come from <a href="https://world.openfoodfacts.org" rel="noopener">Open Food Facts</a>, a crowd-sourced food database, under CC BY-SA.</p>
		</section>
	{:catch err}
		<p class="error">Could not load sources: {err.message}</p>
	{/await}
</div>

<style>
	.narrow { max-width: 860px; }
	h1 { margin: 0; font-size: clamp(32px, 5vw, 44px); font-weight: 750; }
	section { margin-top: 40px; }
	h2 { font-size: 22px; margin: 0 0 4px; }
	ul { list-style: none; margin: 14px 0 0; padding: 0; border-top: 2px solid var(--ink); }
	li { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 16px; padding: 12px 0; border-bottom: 1px solid var(--line); }
	.name { flex: 1; min-width: 0; font-weight: 600; }
	.acc { margin-left: 8px; font-family: var(--mono); font-size: 11px; color: var(--sub); font-weight: 400; }
	.count { font-family: var(--mono); font-size: 12px; color: var(--sub); }
	.desc { flex-basis: 100%; margin: 0; font-size: 14px; }
</style>
