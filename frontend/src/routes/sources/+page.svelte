<script lang="ts">
	import { api, httpUrl, type Source } from '$lib/api';

	const sources = api<Source[]>('/api/sources');
	const groups = [['lab', 'Labs'], ['website', 'Websites']] as const;
</script>

<svelte:head><title>Sources — OpenLabel.fyi</title></svelte:head>

<h1>Sources</h1>
<p>Labs that test products, and websites whose published results we show as fallback data.</p>

{#await sources}
	<p class="muted">Loading…</p>
{:then list}
	{#if !list.length}
		<p>No sources yet.</p>
	{/if}
	{#each groups as [type, title]}
		{@const items = list.filter((s) => s.type === type)}
		{#if items.length}
			<h2>{title}</h2>
			<ul>
				{#each items as s (s.id)}
					<li>
						<a href={httpUrl(s.url)} rel="noopener">{s.name}</a>
						{#if s.accreditation}<span class="muted">({s.accreditation})</span>{/if}
						— {s.report_count} report{s.report_count === 1 ? '' : 's'}
						{#if s.description}<br /><span class="muted">{s.description}</span>{/if}
					</li>
				{/each}
			</ul>
		{/if}
	{/each}
{:catch err}
	<p class="error">Could not load sources: {err.message}</p>
{/await}
