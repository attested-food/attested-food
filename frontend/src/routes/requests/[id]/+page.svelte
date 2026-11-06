<script lang="ts">
	import { page } from '$app/state';
	import { api, buyUrl, dash, label, productName, httpUrl, type TestRequest } from '$lib/api';
	import StateTag from '$lib/components/StateTag.svelte';

	const req = $derived(api<TestRequest>(`/api/test-requests/${encodeURIComponent(page.params.id ?? '')}`));
</script>

<svelte:head><title>Test request · OpenLabel</title></svelte:head>

<div class="page">
	{#await req}
		<p class="muted">Loading…</p>
	{:then r}
		<nav class="crumbs" aria-label="Breadcrumb"><a href="/tests">Tests</a><span aria-hidden="true">/</span><span>Requested</span></nav>
		<section class="hero">
			<div class="photo">
				{#if httpUrl(r.image_url ?? null)}<img src={httpUrl(r.image_url ?? null)} alt="{r.brand} {r.name} pack" referrerpolicy="no-referrer" />{:else}<span class="nophoto">{r.brand}</span>{/if}
			</div>
			<div class="summary">
				<div class="row"><span class="eyebrow">{label(r.category)}</span><StateTag state="requested" /></div>
				<div class="muted brand">{r.brand}</div>
				<h1>{productName(r)}</h1>
				<p class="muted">Requested on {r.requested_on}. Waiting for backers.</p>

				<div class="fund">
					<div class="fund-top"><span class="placeholder-tag">Placeholder</span><span class="muted small">Funding isn't live yet</span></div>
					<div class="bar"><span style:width="0%"></span></div>
					<div class="nums"><span><b>₹[raised]</b> of ₹[goal]</span><span class="muted">[n] backers</span></div>
					<div class="actions">
						<button type="button" class="btn" aria-disabled="true" title="Funding is coming soon">Fund this test</button>
						<a class="btn ghost" href={buyUrl(r)} target="_blank" rel="sponsored noopener">Buy</a>
					</div>
				</div>

				<h2>Tests we'll run</h2>
				<ul class="tests">{#each r.tests ?? [] as t (t)}<li><span aria-hidden="true">?</span>{t}<span class="muted small">not tested yet</span></li>{/each}</ul>

				<h2>Details</h2>
				<dl class="fields">
					<dt>Net quantity</dt><dd>{dash(r.net_quantity)}</dd>
					<dt>Manufacturer</dt><dd>{dash(r.manufacturer)}</dd>
					<dt>FSSAI licence</dt><dd>{dash(r.fssai_license)}</dd>
					<dt>Barcode</dt><dd>{dash(r.barcode)}</dd>
					<dt>Where to buy</dt><dd>{#if httpUrl(r.buy_url ?? null)}<a href={httpUrl(r.buy_url ?? null)} rel="noopener">{r.buy_url}</a>{:else}—{/if}</dd>
				</dl>
			</div>
		</section>
	{:catch err}
		<p class="error">{err.message === 'Not found' ? 'Request not found.' : `Could not load request: ${err.message}`}</p>
		<p><a href="/request">Request a test</a></p>
	{/await}
</div>

<style>
	.small { font-size: 13px; }
	.crumbs { display: flex; gap: 8px; font-size: 14px; color: var(--sub); }
	.crumbs a { text-decoration: none; }
	.hero { margin-top: 18px; display: flex; flex-wrap: wrap; gap: 32px; align-items: flex-start; }
	.photo { flex: 0 0 300px; max-width: 100%; }
	.photo img, .nophoto { display: block; width: 100%; aspect-ratio: 222 / 352; object-fit: contain; padding: 14px; background: #fff; border-radius: var(--r); box-shadow: inset 0 0 0 1px var(--line); }
	.nophoto { display: flex; align-items: center; justify-content: center; background: var(--cream); font-weight: 700; }
	.summary { flex: 1 1 380px; min-width: 0; }
	.row { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
	.brand { margin-top: 18px; }
	h1 { margin: 2px 0 6px; font-size: clamp(28px, 4.5vw, 40px); font-weight: 700; }
	h2 { font-size: 20px; margin: 32px 0 10px; }
	.fund { margin-top: 24px; padding: 18px; background: var(--cream); border-radius: 6px; display: grid; gap: 10px; }
	.fund-top { display: flex; gap: 10px; align-items: center; }
	.bar { height: 8px; border-radius: 4px; background: var(--line); overflow: hidden; }
	.bar span { display: block; height: 100%; background: var(--gold); }
	.nums { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 6px; }
	.actions { display: flex; gap: 10px; flex-wrap: wrap; }
	.tests { list-style: none; margin: 0; padding: 0; }
	.tests li { display: flex; gap: 10px; padding: 7px 0; border-bottom: 1px solid var(--line-soft); }
	.tests li > span:first-child { width: 16px; color: var(--sub); font-weight: 700; }
	.tests li > span:last-child { margin-left: auto; }
	.fields { display: grid; grid-template-columns: max-content 1fr; gap: 6px 20px; margin: 0; }
	.fields dt { color: var(--sub); }
	.fields dd { margin: 0; overflow-wrap: anywhere; }
	@media (max-width: 600px) { .photo { flex-basis: 100%; } .photo img, .nophoto { aspect-ratio: 4 / 3; } }
</style>
