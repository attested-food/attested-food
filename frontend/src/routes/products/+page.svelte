<script lang="ts">
	import { page } from '$app/state';
	import { api, label, nameOf, verdictText, httpUrl, type ProductCard, type TestRequest } from '$lib/api';

	type Page = { items: ProductCard[]; page: number; page_size: number; total: number };

	const params = $derived(page.url.searchParams);
	const q = $derived(params.get('q') ?? '');
	const brand = $derived(params.get('brand') ?? '');
	const category = $derived(params.get('category') ?? '');

	const categories = api<{ category: string; product_count: number }[]>('/api/categories');
	const results = $derived(api<Page>(`/api/products?${params}`));
	const firstPage = $derived((params.get('page') ?? '1') === '1');
	const requests = $derived(firstPage ? api<TestRequest[]>(`/api/test-requests?${params}`) : Promise.resolve([]));

	function pageHref(n: number) {
		const p = new URLSearchParams(params);
		p.set('page', String(n));
		return `/products?${p}`;
	}
</script>

<svelte:head><title>Products — OpenLabel.fyi</title></svelte:head>

<h1>Products</h1>

<form class="search" action="/products" method="get" role="search">
	<input type="search" name="q" value={q} placeholder="Search brand or product" aria-label="Search" />
	<input name="brand" value={brand} placeholder="Brand" aria-label="Brand" />
	<select name="category" aria-label="Category" value={category}>
		<option value="">All categories</option>
		{#await categories then cats}
			{#each cats as c (c.category)}
				<option value={c.category} selected={c.category === category}>{label(c.category)} ({c.product_count})</option>
			{/each}
		{:catch}
			<option disabled>Categories unavailable</option>
		{/await}
	</select>
	<button type="submit">Search</button>
</form>

{#await requests then reqs}
	{#if reqs.length}
		<h2>Requested — waiting for lab testing ({reqs.length})</h2>
		<ul class="grid">
			{#each reqs as t (t.id)}
				<li>
					<a class="card" href="/requests/{t.id}">
						{#if httpUrl(t.image_url ?? null)}<img src={httpUrl(t.image_url ?? null)} alt="" loading="lazy" />{/if}
						<p class="muted">{t.brand}</p>
						<p><strong>{t.name}</strong>{#if t.variant} — {t.variant}{/if}</p>
						<p class="muted">{label(t.category)}</p>
						<p><span class="badge fallback">Requested</span></p>
						<p class="muted">Requested {t.requested_on}</p>
					</a>
				</li>
			{/each}
		</ul>
		<h2>Tested products</h2>
	{/if}
{:catch err}
	<p class="error">Could not load requested products: {err.message}</p>
{/await}

{#await results}
	<p class="muted">Loading…</p>
{:then r}
	{#if !r.items.length}
		<p>No products found{q || brand || category ? ' for these filters' : ' yet'}.</p>
	{:else}
		<p class="muted">{r.total} product{r.total === 1 ? '' : 's'}</p>
		<ul class="grid">
			{#each r.items as p (p.id)}
				<li>
					<a class="card" href="/products/{p.id}">
						{#if httpUrl(p.image_url)}<img src={httpUrl(p.image_url)} alt="" loading="lazy" />{/if}
						<p class="muted">{p.brand}</p>
						<p><strong>{p.name}</strong>{#if p.variant} — {p.variant}{/if}</p>
						<p class="muted">{label(p.category)}</p>
						<p>
							{#if p.has_user_report}
								<span class="badge user">User report</span>
							{:else if p.latest}
								<span class="badge fallback">From {nameOf(p.latest.publisher) ?? 'unknown source'}</span>
							{/if}
						</p>
						{#if p.latest}
							{#if verdictText(p.latest)}<p>{verdictText(p.latest)}</p>{/if}
							{#if p.latest.tested_on}<p class="muted">Tested {p.latest.tested_on}</p>{/if}
						{:else}
							<p class="muted">No reports yet</p>
						{/if}
					</a>
				</li>
			{/each}
		</ul>
		{@const pages = Math.max(1, Math.ceil(r.total / r.page_size))}
		{#if pages > 1}
			<p class="pager">
				{#if r.page > 1}<a href={pageHref(r.page - 1)}>← Previous</a>{/if}
				<span>Page {r.page} of {pages}</span>
				{#if r.page < pages}<a href={pageHref(r.page + 1)}>Next →</a>{/if}
			</p>
		{/if}
	{/if}
{:catch err}
	<p class="error">Could not load products: {err.message}</p>
{/await}
