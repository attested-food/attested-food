<script lang="ts">
	import { onMount } from 'svelte';
	import { api, imgFallback, imgSrc, label, nameOf, productName, type ProductCard, type TestRequest } from '$lib/api';
	import { FUNDING } from '$lib/placeholders';
	import { FUND_GOAL, campaignId, fundAbi, fundAddress, publicClient, usd } from '$lib/wallet.svelte';
	import StateTag from '$lib/components/StateTag.svelte';

	const TABS = [
		{ id: 'requested', text: 'Requested' },
		{ id: 'funding', text: 'Funding' },
		{ id: 'funded', text: 'Funded' },
		{ id: 'tested', text: 'Tested' }
	] as const;
	type Tab = (typeof TABS)[number]['id'];

	let tab = $state<Tab>('requested');
	const fromHash = () => {
		const h = location.hash.slice(1);
		if (TABS.some((t) => t.id === h)) tab = h as Tab;
	};
	onMount(() => {
		fromHash();
		window.addEventListener('hashchange', fromHash);
		return () => window.removeEventListener('hashchange', fromHash);
	});
	function pick(t: Tab) {
		tab = t;
		history.replaceState(history.state, '', `#${t}`);
	}

	const requests = api<TestRequest[]>('/api/test-requests');
	const tested = api<{ items: ProductCard[] }>('/api/products?page_size=48').then((r) => r.items.filter((p) => p.has_user_report));
	const placeholderFunding = FUNDING.filter((f) => f.state === 'funding');
	const placeholderFunded = FUNDING.filter((f) => f.state === 'funded');

	// Campaign states from the TestFund contract, when this deployment has one.
	type Campaign = { r: TestRequest; pool: bigint; status: number; pct: number };
	const STATUS_LABEL = ['Waiting for a tester', 'Tester assigned', 'Report submitted'];
	const campaigns: Promise<Campaign[]> | null = fundAddress
		? requests.then((rs) =>
				Promise.all(
					rs.map(async (r) => {
						const [pool, , , status] = await publicClient.readContract({
							address: fundAddress!, abi: fundAbi, functionName: 'campaigns', args: [campaignId(r.id)]
						});
						return { r, pool, status, pct: Math.min(100, Number((pool * 100n) / FUND_GOAL)) };
					})
				)
			)
		: null;
	const inTab = (c: Campaign, t: Tab) =>
		t === 'funding' ? c.status === 0 && c.pool > 0n && c.pool < FUND_GOAL : c.status > 0 || c.pool >= FUND_GOAL;
	const firstLine = (e: unknown) => (e instanceof Error ? e.message : String(e)).split(String.fromCharCode(10))[0];
</script>

<svelte:head><title>Tests · OpenLabel</title></svelte:head>

<div class="page">
	<div class="page-head">
		<div>
			<h1>Tests</h1>
			<p class="lede">Anyone can ask for a product to be tested. Once enough people chip in, it goes to an accredited lab and the full report is published here.</p>
		</div>
		<a class="btn" href="/request">Request a test</a>
	</div>

	<ol class="steps" aria-label="How a test happens">
		<li><b>1</b> Requested</li>
		<li><b>2</b> Funding</li>
		<li><b>3</b> Funded, at the lab</li>
		<li><b>4</b> Tested, report published</li>
	</ol>

	<div class="tabs" role="tablist" aria-label="Test stage">
		{#each TABS as t (t.id)}
			<button type="button" role="tab" id="tab-{t.id}" aria-selected={tab === t.id} aria-controls="panel" onclick={() => pick(t.id)}>{t.text}</button>
		{/each}
	</div>

	<div id="panel" role="tabpanel" aria-labelledby="tab-{tab}">
		{#if tab === 'requested'}
			{#await requests}
				<p class="muted">Loading…</p>
			{:then reqs}
				{#if !reqs.length}
					<p>No requests yet. <a href="/request">Be the first.</a></p>
				{:else}
					<ul class="grid">
						{#each reqs as r (r.id)}
							<li>
								<a class="tile" href="/requests/{r.id}">
									<span class="img"><img src={imgSrc(r.image_url)} alt="" loading="lazy" referrerpolicy="no-referrer" onerror={imgFallback} /></span>
									<span class="body">
										<span class="top"><span class="eyebrow">{label(r.category)}</span><StateTag state="requested" /></span>
										<span class="muted small">{r.brand}</span>
										<span class="name">{productName(r)}</span>
										<span class="muted small">Requested {r.requested_on}</span>
									</span>
								</a>
							</li>
						{/each}
					</ul>
				{/if}
			{:catch err}
				<p class="error">Could not load requests: {err.message}</p>
			{/await}
		{:else if (tab === 'funding' || tab === 'funded') && campaigns}
			{#await campaigns}
				<p class="muted">Reading campaigns…</p>
			{:then all}
				{@const list = all.filter((c) => inTab(c, tab))}
				{#if !list.length}
					<p>{tab === 'funding' ? 'No tests are part-funded right now.' : 'No tests are fully funded yet.'} <a href="#requested" onclick={() => pick('requested')}>Back a requested test.</a></p>
				{:else}
					<ul class="grid">
						{#each list as c (c.r.id)}
							<li>
								<a class="tile" href="/requests/{c.r.id}">
									<span class="img"><img src={imgSrc(c.r.image_url)} alt="" loading="lazy" referrerpolicy="no-referrer" onerror={imgFallback} /></span>
									<span class="body">
										<span class="top"><span class="eyebrow">{label(c.r.category)}</span><StateTag state={tab} pct={tab === 'funding' ? c.pct : null} /></span>
										<span class="muted small">{c.r.brand}</span>
										<span class="name">{productName(c.r)}</span>
										<span class="bar" aria-label="{c.pct}% funded"><span style:width="{c.pct}%"></span></span>
										<span class="nums"><span><b>{usd(c.pool)}</b> of {usd(FUND_GOAL)}</span>{#if tab === 'funded'}<span class="muted">{STATUS_LABEL[c.status]}</span>{/if}</span>
									</span>
								</a>
							</li>
						{/each}
					</ul>
				{/if}
			{:catch err}
				<p class="error">Could not read campaigns: {firstLine(err)}</p>
			{/await}
		{:else if tab === 'funding' || tab === 'funded'}
			<p class="notice"><span class="placeholder-tag">Placeholder</span> On-chain funding isn't configured for this deployment. These cards show how it looks; the products and numbers are not real.</p>
			<ul class="grid">
				{#each tab === 'funding' ? placeholderFunding : placeholderFunded as f, i (i)}
					<li>
						<div class="tile fund">
							<span class="body">
								<span class="top"><span class="eyebrow">{f.productHint}</span><StateTag state={f.state} pct={f.state === 'funding' ? f.pct : null} /></span>
								<span class="name">{f.tests}</span>
								<span class="bar" aria-label="{f.pct}% funded"><span style:width="{f.pct}%"></span></span>
								<span class="nums"><span><b>{f.raised}</b> of {f.goal}</span><span class="muted">{f.backers} · {f.daysLeft}</span></span>
								<button type="button" class="btn small" aria-disabled="true" title="Funding is coming soon">{f.state === 'funding' ? 'Fund this test' : 'Notify me'}</button>
							</span>
						</div>
					</li>
				{/each}
			</ul>
		{:else}
			{#await tested}
				<p class="muted">Loading…</p>
			{:then items}
				{#if !items.length}
					<p>No OpenLabel lab reports yet.</p>
				{:else}
					<ul class="grid">
						{#each items as p (p.id)}
							<li>
								<a class="tile" href="/products/{p.id}">
									<span class="img"><img src={imgSrc(p.image_url)} alt="" loading="lazy" referrerpolicy="no-referrer" onerror={imgFallback} /></span>
									<span class="body">
										<span class="top"><span class="eyebrow">{label(p.category)}</span><StateTag state="tested" /></span>
										<span class="muted small">{p.brand}</span>
										<span class="name">{productName(p)}</span>
										<span class="muted small">{nameOf(p.latest?.lab ?? null) ?? 'Lab'}{p.latest?.tested_on ? ` · ${p.latest.tested_on}` : ''}</span>
									</span>
								</a>
							</li>
						{/each}
					</ul>
				{/if}
			{:catch err}
				<p class="error">Could not load tested products: {err.message}</p>
			{/await}
		{/if}
	</div>
</div>

<style>
	.small { font-size: 13px; }
	.steps { list-style: none; margin: 0 0 28px; padding: 0; display: flex; flex-wrap: wrap; gap: 8px; }
	.steps li { display: flex; align-items: center; gap: 8px; padding: 8px 14px 8px 8px; background: var(--cream); border-radius: var(--r); font-weight: 600; font-size: 14px; }
	.steps b { display: inline-flex; width: 24px; height: 24px; align-items: center; justify-content: center; border-radius: 2px; background: var(--green); color: var(--gold); font-size: 12px; }
	.grid { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
	.tile { display: flex; gap: 14px; height: 100%; padding: 12px; border-radius: 6px; background: var(--cream); text-decoration: none; color: var(--ink); }
	a.tile:hover { box-shadow: inset 0 0 0 1px var(--green); color: var(--ink); }
	.img { flex: 0 0 96px; height: 132px; background: #fff; border-radius: var(--r); box-shadow: inset 0 0 0 1px var(--line); overflow: hidden; }
	.img img { width: 100%; height: 100%; object-fit: contain; padding: 6px; }
	.body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
	.top { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 6px; }
	.name { font-weight: 650; font-size: 17px; letter-spacing: -0.02em; line-height: 1.2; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
	.fund .body { gap: 8px; }
	.bar { display: block; height: 6px; border-radius: 3px; background: var(--line); overflow: hidden; margin-top: 4px; }
	.bar span { display: block; height: 100%; background: var(--gold); }
	.nums { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 4px 12px; font-size: 14px; }
	.fund .btn { align-self: flex-start; margin-top: 4px; }
	.notice { margin: 0 0 18px; display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
</style>
