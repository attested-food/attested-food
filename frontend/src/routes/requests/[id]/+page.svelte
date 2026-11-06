<script lang="ts">
	import { page } from '$app/state';
	import { api, dash, label, httpUrl, type TestRequest } from '$lib/api';

	const req = $derived(api<TestRequest>(`/api/test-requests/${encodeURIComponent(page.params.id ?? '')}`));
</script>

<svelte:head><title>Test request — attested.food</title></svelte:head>

{#await req}
	<p class="muted">Loading…</p>
{:then r}
	<p class="muted">{r.brand}</p>
	<h1>{r.name}{#if r.variant} — {r.variant}{/if}</h1>
	<p><span class="badge fallback">Requested</span> Waiting for lab testing. Requested on {r.requested_on}.</p>
	{#if httpUrl(r.image_url ?? null)}<img src={httpUrl(r.image_url ?? null)} alt="{r.brand} {r.name}" style="max-height: 16rem" />{/if}
	<dl class="fields">
		<dt>Category</dt><dd>{label(r.category)}</dd>
		<dt>Net quantity</dt><dd>{dash(r.net_quantity)}</dd>
		<dt>Manufacturer</dt><dd>{dash(r.manufacturer)}</dd>
		<dt>FSSAI licence</dt><dd>{dash(r.fssai_license)}</dd>
		<dt>Barcode</dt><dd>{dash(r.barcode)}</dd>
		<dt>Where to buy</dt><dd>{#if httpUrl(r.buy_url ?? null)}<a href={httpUrl(r.buy_url ?? null)} rel="noopener">{r.buy_url}</a>{:else}—{/if}</dd>
	</dl>
	<h2>Tests we'll run</h2>
	<ul class="tests">{#each r.tests ?? [] as t (t)}<li>○ {t} <span class="muted">not tested yet</span></li>{/each}</ul>
{:catch err}
	<p class="error">{err.message === 'Not found' ? 'Request not found.' : `Could not load request: ${err.message}`}</p>
	<p><a href="/request">Request a test</a></p>
{/await}
