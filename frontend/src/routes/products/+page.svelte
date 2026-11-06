<script lang="ts">
	import { page } from '$app/state';
	import { api, buyUrl, label, nameOf, productName, httpUrl, type LabelNutrition, type ProductCard, type TestRequest } from '$lib/api';
	import GradeBox from '$lib/components/GradeBox.svelte';
	import StateTag from '$lib/components/StateTag.svelte';

	type Page = { items: ProductCard[]; page: number; page_size: number; total: number };

	const params = $derived(page.url.searchParams);
	const q = $derived(params.get('q') ?? '');
	const brand = $derived(params.get('brand') ?? '');
	const category = $derived(params.get('category') ?? '');

	const categories = api<{ category: string; product_count: number }[]>('/api/categories');
	const results = $derived(api<Page>(`/api/products?${params}`));
	const firstPage = $derived((params.get('page') ?? '1') === '1');
	const requests = $derived(firstPage ? api<TestRequest[]>(`/api/test-requests?${params}`) : Promise.resolve([]));

	function href(changes: Record<string, string | null>) {
		const p = new URLSearchParams(params);
		for (const [k, v] of Object.entries(changes)) v === null ? p.delete(k) : p.set(k, v);
		const s = p.toString();
		return s ? `/products?${s}` : '/products';
	}

	const cell = (n: LabelNutrition | null, k: keyof LabelNutrition, unit: string) => {
		const v = n?.[k];
		return typeof v === 'number' ? `${Math.abs(v) >= 100 ? Math.round(v) : Math.round(v * 10) / 10} ${unit}` : null;
	};

	function evidence(p: ProductCard) {
		if (p.has_user_report) return { lab: true, text: nameOf(p.latest?.lab ?? null) ?? 'Lab report' };
		if (p.latest) return { lab: false, text: `via ${nameOf(p.latest.publisher) ?? 'source'}` };
		return null;
	}

	function grade(p: ProductCard) {
		if (!p.latest || p.has_user_report) return null;
		return p.latest.grade ?? (p.latest.verdict === 'pass' ? 'Pass' : p.latest.verdict === 'fail' ? 'Fail' : null);
	}
</script>

<svelte:head><title>Marketplace · OpenLabel</title></svelte:head>

<div class="page">
	<div class="page-head">
		<div>
			<h1>Marketplace</h1>
			<p class="lede">Every product with what its label says, what the tests found, and where to buy it.</p>
		</div>
		<form class="search" action="/products" method="get" role="search">
			<label for="mq" class="sr-only">Search products or brands</label>
			<input id="mq" type="search" name="q" value={q} placeholder="Search products or brands" />
			{#if category}<input type="hidden" name="category" value={category} />{/if}
			{#if brand}<input type="hidden" name="brand" value={brand} />{/if}
			<button type="submit">Search</button>
		</form>
	</div>

	<nav class="tabs" aria-label="Shelves">
		<a href={href({ category: null, page: null })} aria-current={!category ? 'page' : undefined}>All</a>
		{#await categories then cats}
			{#each [...cats].sort((a, b) => b.product_count - a.product_count).slice(0, 9) as c (c.category)}
				<a href={href({ category: c.category, page: null })} aria-current={c.category === category ? 'page' : undefined}>{label(c.category)}</a>
			{/each}
		{/await}
	</nav>

	{#if brand}
		<p class="filter">Brand: <strong>{brand}</strong> <a href={href({ brand: null, page: null })}>Clear</a></p>
	{/if}

	{#await requests then reqs}
		{#if reqs.length}
			<section class="requested" aria-labelledby="req-h">
				<div class="sec-head">
					<h2 id="req-h">Waiting for a lab test</h2>
					<a href="/tests">All requests</a>
				</div>
				<ul>
					{#each reqs.slice(0, 6) as t (t.id)}
						<li>
							<a href="/requests/{t.id}">
								{#if httpUrl(t.image_url ?? null)}<img src={httpUrl(t.image_url ?? null)} alt="" loading="lazy" />{:else}<span class="noimg"></span>{/if}
								<span class="rq-text">
									<span class="muted small">{t.brand}</span>
									<span class="rq-name">{productName(t)}</span>
									<StateTag state="requested" />
								</span>
							</a>
						</li>
					{/each}
				</ul>
			</section>
		{/if}
	{/await}

	{#await results}
		<p class="muted">Loading…</p>
	{:then r}
		<section aria-labelledby="ratings">
			<div class="sec-head ruled">
				<h2 id="ratings">{category ? label(category) : q ? `Results for “${q}”` : 'All products'}</h2>
				<span class="muted">{r.total} product{r.total === 1 ? '' : 's'}</span>
			</div>
			{#if !r.items.length}
				<p>No products found{q || brand || category ? ' for these filters' : ' yet'}. <a href="/request">Request a test</a> for a product we don't have.</p>
			{:else}
				<div class="table-wrap">
					<table class="data ratings">
						<thead>
							<tr>
								<th scope="col">Product</th>
								<th scope="col">Grade</th>
								<th scope="col">Evidence</th>
								<th scope="col" class="num">Added sugar</th>
								<th scope="col" class="num">Fibre</th>
								<th scope="col" class="num">Protein</th>
								<th scope="col" class="num">Sodium</th>
								<th scope="col"><span class="sr-only">Buy</span></th>
							</tr>
						</thead>
						<tbody>
							{#each r.items as p (p.id)}
								{@const ev = evidence(p)}
								<tr>
									<th scope="row">
										<a class="prod" href="/products/{p.id}">
											{#if httpUrl(p.image_url)}<img src={httpUrl(p.image_url)} alt="" loading="lazy" referrerpolicy="no-referrer" />{:else}<span class="noimg"></span>{/if}
											<span>
												<span class="muted small">{p.brand}</span>
												<span class="pname">{productName(p)}</span>
											</span>
										</a>
									</th>
									<td><GradeBox grade={grade(p)} size={38} empty={p.has_user_report ? 'PENDING' : '—'} /></td>
									<td>
										{#if ev?.lab}<span class="lab">Lab</span> <span class="muted small">{ev.text}</span>
										{:else if ev}<span class="muted small">{ev.text}</span>
										{:else}<span class="muted small">Label only</span>{/if}
									</td>
									<td class="num">{cell(p.label_nutrition, 'added_sugars_g', 'g') ?? '—'}</td>
									<td class="num">{cell(p.label_nutrition, 'fiber_g', 'g') ?? '—'}</td>
									<td class="num">{cell(p.label_nutrition, 'protein_g', 'g') ?? '—'}</td>
									<td class="num">{cell(p.label_nutrition, 'sodium_mg', 'mg') ?? '—'}</td>
									<td class="num"><a class="btn small" href={buyUrl(p)} target="_blank" rel="sponsored noopener">Buy</a></td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
				<p class="muted small note">Nutrition per 100 g, from the pack label. Grades are the source's own until OpenLabel grading ships.</p>
				{@const pages = Math.max(1, Math.ceil(r.total / r.page_size))}
				{#if pages > 1}
					<nav class="pager" aria-label="Pages">
						{#if r.page > 1}<a class="btn small ghost" href={href({ page: String(r.page - 1) })}>← Previous</a>{/if}
						<span class="muted">Page {r.page} of {pages}</span>
						{#if r.page < pages}<a class="btn small ghost" href={href({ page: String(r.page + 1) })}>Next →</a>{/if}
					</nav>
				{/if}
			{/if}
		</section>
	{:catch err}
		<p class="error">Could not load products: {err.message}</p>
	{/await}
</div>

<style>
	.small { font-size: 13px; }
	.filter { margin: -12px 0 20px; }
	.sec-head { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
	.sec-head h2 { margin: 0; font-size: 24px; font-weight: 700; }
	.sec-head.ruled { padding-bottom: 12px; border-bottom: 2px solid var(--ink); margin-bottom: 0; }
	.requested { margin-bottom: 44px; }
	.requested ul { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
	.requested a { display: flex; gap: 12px; align-items: center; padding: 10px; border-radius: var(--r); background: var(--cream); text-decoration: none; height: 100%; }
	.requested img, .requested .noimg { flex: 0 0 auto; width: 52px; height: 64px; object-fit: contain; background: #fff; border-radius: 2px; }
	.rq-text { display: flex; flex-direction: column; align-items: flex-start; gap: 3px; min-width: 0; }
	.rq-name { font-weight: 600; line-height: 1.25; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
	.ratings { min-width: 860px; }
	.ratings tbody th { font-weight: 600; }
	.prod { display: flex; align-items: center; gap: 14px; text-decoration: none; }
	.prod img, .prod .noimg { flex: 0 0 auto; width: 44px; height: 60px; object-fit: contain; background: #fff; border-radius: 2px; box-shadow: inset 0 0 0 1px var(--line); }
	.noimg { display: block; background: var(--cream); }
	.prod > span { display: flex; flex-direction: column; }
	.pname { line-height: 1.25; }
	.lab { display: inline-flex; padding: 3px 7px; background: var(--green); color: var(--gold); font-family: var(--mono); font-size: 10.5px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; border-radius: var(--r); }
	.note { margin-top: 12px; }
	.pager { display: flex; align-items: center; gap: 16px; margin-top: 24px; }
</style>
