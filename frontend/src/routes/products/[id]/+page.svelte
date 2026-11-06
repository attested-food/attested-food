<script lang="ts">
	import { page } from '$app/state';
	import { api, buyUrl, dash, label, nutritionRows, productName, verdictText, httpUrl, type Product, type Result } from '$lib/api';
	import GradeBox from '$lib/components/GradeBox.svelte';
	import Segments from '$lib/components/Segments.svelte';
	import StateTag from '$lib/components/StateTag.svelte';

	const GROUPS = ['nutrition', 'heavy_metal', 'toxin', 'pesticide', 'spiking', 'other'];

	const product = $derived(api<Product>(`/api/products/${encodeURIComponent(page.params.id ?? '')}`));
	let title = $state('Product');
	$effect(() => {
		product.then((p) => (title = `${p.brand} ${productName(p)}`)).catch(() => (title = 'Product'));
	});

	function grouped(results: Result[]) {
		const groupOf = (r: Result) => (GROUPS.includes(r.group) ? r.group : 'other');
		return GROUPS.map((g) => [g, results.filter((r) => groupOf(r) === g)] as const).filter(([, rs]) => rs.length);
	}

	// Tested value differs from the label claim by more than 10%.
	function offClaim(r: Result) {
		if (r.value === null || r.label_claim === null) return false;
		if (r.label_claim === 0) return r.value !== 0;
		return Math.abs(r.value - r.label_claim) / Math.abs(r.label_claim) > 0.1;
	}

	const fmt = (v: number | null) => (v === null ? '—' : Math.abs(v) >= 100 ? String(Math.round(v)) : String(Math.round(v * 100) / 100));
	const pct = (v: number | null) => (v === null ? '—' : `${v >= 0 ? '+' : '−'}${Math.round(Math.abs(v))}%`);

	function gradeOf(p: Product) {
		const r = p.reports[0];
		if (!r || r.kind === 'user') return null;
		return r.grade ?? (r.verdict === 'pass' ? 'Pass' : r.verdict === 'fail' ? 'Fail' : null);
	}
	function gradeLabel(p: Product) {
		const r = p.reports[0];
		if (!r) return 'Not tested yet';
		if (r.kind === 'user') return 'Lab-tested · OpenLabel grade pending';
		return gradeOf(p) ? `Grade by ${r.publisher?.name ?? 'the source'}` : 'Not enough data to grade';
	}
</script>

<svelte:head><title>{title} · OpenLabel</title></svelte:head>

<div class="page">
	{#await product}
		<p class="muted">Loading…</p>
	{:then p}
		{@const a = p.annotations}
		{@const compared = a.findings.filter((f) => f.label !== null)}
		{@const nut = nutritionRows(p.label_nutrition)}
		<nav class="crumbs" aria-label="Breadcrumb">
			<a href="/products">Marketplace</a>
			{#if p.category}<span aria-hidden="true">/</span><a href="/products?category={p.category}">{label(p.category)}</a>{/if}
		</nav>

		<section class="hero">
			<div class="photo">
				{#if httpUrl(p.image_url)}
					<img src={httpUrl(p.image_url)} alt="{p.brand} {productName(p)} pack" referrerpolicy="no-referrer" />
				{:else}
					<span class="nophoto">{p.brand}</span>
				{/if}
			</div>
			<div class="summary">
				<div class="row">
					<span class="eyebrow">{label(p.category)}</span>
					<StateTag state={p.reports.length ? 'tested' : 'requested'} />
				</div>
				<a class="brand" href="/products?brand={encodeURIComponent(p.brand)}">{p.brand}</a>
				<h1>{productName(p)}</h1>
				{#if p.net_quantity}<p class="muted qty">{p.net_quantity}</p>{/if}

				<div class="verdict">
					<GradeBox grade={gradeOf(p)} size={72} empty={p.reports[0]?.kind === 'user' ? 'PENDING' : 'NO GRADE'} />
					<div>
						<div class="eyebrow">{gradeLabel(p)}</div>
						<div class="counts">
							<span class="pass">✓ {a.counts.pass} pass</span>
							<span class="fail">✕ {a.counts.fail} fail</span>
							<span class="muted">? {a.counts.untested} not tested</span>
						</div>
					</div>
				</div>

				<div class="actions">
					<a class="btn" href={buyUrl(p)} target="_blank" rel="sponsored noopener">Buy on Amazon</a>
					<a class="btn ghost" href="/request">Request more tests</a>
				</div>
			</div>
		</section>

		{#if compared.length}
			<section aria-labelledby="lvl">
				<h2 id="lvl">Label vs lab</h2>
				<p class="muted sec-lede">Flagged when the lab result is more than 10% off what the pack says.</p>
				<div class="table-wrap">
					<table class="data">
						<thead>
							<tr><th scope="col">Nutrient</th><th scope="col" class="num">Label says</th><th scope="col" class="num">Lab found</th><th scope="col" class="num">Difference</th><th scope="col"><span class="sr-only">Result</span></th></tr>
						</thead>
						<tbody>
							{#each compared as f (f.parameter)}
								<tr>
									<th scope="row">{f.parameter}</th>
									<td class="num">{fmt(f.label)} {f.unit ?? ''}</td>
									<td class="num" class:off={f.kind === 'bad'}>{fmt(f.tested)} {f.unit ?? ''}</td>
									<td class="num" class:off={f.kind === 'bad'} class:ok={f.kind === 'good'}>{pct(f.deviation_pct)}</td>
									<td><span class="mark {f.kind}">{f.kind === 'bad' ? '✕ Off label' : f.kind === 'good' ? '✓ Better than label' : 'Within 10%'}</span></td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</section>
		{/if}

		<div class="two">
			<section aria-labelledby="ing">
				<h2 id="ing">Ingredients</h2>
				{#if p.ingredients}
					<p class="ingredients">
						{#if a.segments.length}<Segments segments={a.segments} />{:else}{p.ingredients}{/if}
					</p>
					{#if p.ingredients_source === 'open_food_facts'}
						<p class="muted small">Ingredient list from <a href="https://world.openfoodfacts.org" rel="noopener">Open Food Facts</a> (CC BY-SA). Marks come from the lab results below.</p>
					{/if}
				{:else}
					<p class="muted">Not on file yet.</p>
				{/if}
			</section>

			<section aria-labelledby="nut">
				<h2 id="nut">Nutrition label</h2>
				{#if nut.length}
					<div class="nut">
						<div class="nut-head"><span>Per 100 g</span><span>Label</span></div>
						{#each nut as n (n.key)}
							<div class="nut-row"><span>{n.name}</span><strong>{n.value}</strong></div>
						{/each}
					</div>
				{:else}
					<p class="muted">Not on file yet.</p>
				{/if}

				<h2 class="cov-h">What's been tested</h2>
				<ul class="coverage">
					{#each p.tests as t (t.name)}
						<li class:tested={t.tested}><span aria-hidden="true">{t.tested ? '✓' : '?'}</span>{t.name}<span class="muted small">{t.tested ? 'tested' : 'not tested yet'}</span></li>
					{/each}
				</ul>
			</section>
		</div>

		<section aria-labelledby="reports">
			<h2 id="reports">Reports ({p.reports.length})</h2>
			{#if !p.reports.length}
				<p>No reports for this product yet. <a href="/request">Request a test</a> and others can chip in.</p>
			{/if}

			{#each p.reports as r (r.id)}
				<article class="report" id="report-{r.id}">
					<header>
						{#if r.kind === 'user'}<span class="lab-tag">Lab report</span>{:else}<span class="src-tag">Published data</span>{/if}
						<h3>{r.lab?.name ?? r.publisher?.name ?? 'Report'}</h3>
						{#if r.tested_on}<span class="muted small">tested {r.tested_on}</span>{/if}
					</header>

					{#if r.kind === 'fallback'}
						<p class="notice">
							Data as published by
							{#if httpUrl(r.source_url)}<a href={httpUrl(r.source_url)} rel="noopener">{r.publisher?.name ?? 'the source'}</a>{:else}{r.publisher?.name ?? 'the source'}{/if}{#if r.lab?.name}, tested by {r.lab.name}{/if}. Not independently verified by OpenLabel.
						</p>
					{/if}

					<dl class="fields">
						{#if r.kind === 'user'}
							<dt>Verification</dt>
							<dd>{r.verified ? `Verified (${r.verification.replace(/_/g, ' ')})` : 'Verification pending'}</dd>
							<dt>Lab</dt><dd>{dash(r.lab?.name)}{#if r.lab?.accreditation} ({r.lab.accreditation}){/if}</dd>
							<dt>Report number</dt><dd>{dash(r.report_number)}</dd>
							<dt>ULR</dt><dd>{dash(r.ulr_number)}</dd>
						{/if}
						<dt>Batch</dt><dd>{dash(r.batch_no)}</dd>
						<dt>Manufactured</dt><dd>{dash(r.mfg_date)}</dd>
						<dt>Expiry</dt><dd>{dash(r.expiry_date)}</dd>
						<dt>Issued</dt><dd>{dash(r.issued_on)}</dd>
						<dt>Verdict</dt><dd>{verdictText(r) || '—'}</dd>
						{#if httpUrl(r.pdf_url)}
							<dt>PDF</dt><dd><a href={httpUrl(r.pdf_url)} rel="noopener">Download report</a></dd>
						{/if}
					</dl>

					{#if r.verdict === 'fail' && !r.results.some((x) => x.status === 'fail')}
						<p class="notice">
							{r.publisher?.name ?? 'The source'} marks this product as failed, but publishes the failing values only as images.
							{#if httpUrl(r.source_url)}<a href={httpUrl(r.source_url)} rel="noopener">See the full result on {r.publisher?.name ?? 'the source'}</a>.{/if}
						</p>
					{/if}

					{#if r.results.length}
						<div class="table-wrap">
							<table class="data results">
								<thead>
									<tr><th scope="col">Parameter</th><th scope="col" class="num">Label claim</th><th scope="col" class="num">Tested</th><th scope="col">Unit</th><th scope="col">Limit / LOQ</th><th scope="col">Method</th><th scope="col">Status</th></tr>
								</thead>
								<tbody>
									{#each grouped(r.results) as [group, rows] (group)}
										<tr class="group"><th colspan="7">{label(group)}</th></tr>
										{#each rows as row, i (i)}
											<tr>
												<td>{row.parameter}</td>
												<td class="num">{dash(row.label_claim)}</td>
												<td class="num" class:off={offClaim(row)} title={offClaim(row) ? 'Differs from label claim by more than 10%' : undefined}>{dash(row.value_raw)}</td>
												<td>{dash(row.unit)}</td>
												<td title={row.detection_limit !== null ? 'Limit of quantification: lowest amount the lab can measure, not a safety limit' : undefined}>{row.limit !== null ? row.limit : row.detection_limit !== null ? `LOQ ${row.detection_limit}` : '—'}</td>
												<td>{dash(row.method)}</td>
												<td class:off={row.status === 'fail'} class:ok={row.status === 'pass'}>{row.status ? row.status.toUpperCase() : '—'}</td>
											</tr>
										{/each}
									{/each}
								</tbody>
							</table>
						</div>
						<p class="muted small">Red values differ from the label claim by more than 10%.</p>
					{:else}
						<p class="muted">No results recorded for this report.</p>
					{/if}
				</article>
			{/each}
		</section>

		<section aria-labelledby="details">
			<h2 id="details">Product details</h2>
			<dl class="fields">
				<dt>Manufacturer</dt><dd>{dash(p.manufacturer)}</dd>
				<dt>FSSAI licence</dt><dd>{dash(p.fssai_license)}</dd>
				<dt>Barcode</dt><dd>{dash(p.barcode)}</dd>
				<dt>Net quantity</dt><dd>{dash(p.net_quantity)}</dd>
			</dl>
		</section>
	{:catch err}
		<p class="error">{err.message === 'Not found' ? 'Product not found.' : `Could not load product: ${err.message}`}</p>
		<p><a href="/products">Back to the marketplace</a></p>
	{/await}
</div>

<style>
	.small { font-size: 13px; }
	section { margin-top: 48px; }
	h2 { font-size: 24px; font-weight: 700; margin: 0 0 14px; }
	.sec-lede { margin: -8px 0 14px; }
	.crumbs { display: flex; gap: 8px; font-size: 14px; color: var(--sub); }
	.crumbs a { text-decoration: none; }
	.hero { margin-top: 18px; display: flex; flex-wrap: wrap; gap: 32px; align-items: flex-start; }
	.photo { flex: 0 0 300px; max-width: 100%; }
	.photo img, .nophoto { display: block; width: 100%; aspect-ratio: 222 / 352; object-fit: contain; padding: 14px; background: #fff; border-radius: var(--r); box-shadow: inset 0 0 0 1px var(--line); }
	.nophoto { display: flex; align-items: center; justify-content: center; background: var(--cream); color: var(--sub); font-weight: 700; font-size: 22px; }
	.summary { flex: 1 1 380px; min-width: 0; }
	.row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
	.brand { display: inline-block; margin-top: 18px; color: var(--sub); text-decoration: none; }
	h1 { margin: 2px 0 0; font-size: clamp(30px, 4.5vw, 44px); font-weight: 700; }
	.qty { margin: 6px 0 0; }
	.verdict { display: flex; align-items: center; gap: 18px; margin-top: 28px; padding: 18px 0; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
	.counts { display: flex; flex-wrap: wrap; gap: 6px 16px; margin-top: 6px; font-size: 17px; font-weight: 600; }
	.pass { color: var(--good); }
	.fail { color: var(--red); }
	.actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 22px; }
	.mark { font-size: 13px; font-weight: 600; white-space: nowrap; }
	.mark.bad { color: var(--red); }
	.mark.good { color: var(--good); }
	.mark.info { color: var(--sub); }
	.two { display: flex; flex-wrap: wrap; gap: 0 48px; }
	.two > section { flex: 1 1 380px; min-width: 0; }
	.ingredients { margin: 0 0 12px; font-family: var(--label); font-weight: 600; font-size: 19px; line-height: 1.6; text-transform: uppercase; letter-spacing: 0.005em; }
	.nut { font-family: var(--label); max-width: 420px; }
	.nut-head { display: flex; justify-content: space-between; border-bottom: 3px solid var(--ink); padding-bottom: 3px; font-weight: 700; font-size: 15px; text-transform: uppercase; letter-spacing: 0.03em; }
	.nut-row { display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid var(--line); font-size: 17px; font-weight: 500; }
	.nut-row strong { font-weight: 700; }
	.cov-h { margin-top: 32px; }
	.coverage { list-style: none; margin: 0; padding: 0; }
	.coverage li { display: flex; align-items: baseline; gap: 10px; padding: 7px 0; border-bottom: 1px solid var(--line-soft); }
	.coverage li > span:first-child { width: 18px; color: var(--sub); font-weight: 700; }
	.coverage li.tested > span:first-child { color: var(--good); }
	.coverage li > span:last-child { margin-left: auto; }
	.report { margin-top: 20px; padding-top: 20px; border-top: 2px solid var(--ink); }
	.report header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 12px; margin-bottom: 12px; }
	.report h3 { margin: 0; font-size: 20px; }
	.lab-tag, .src-tag { font-family: var(--mono); font-size: 10.5px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; padding: 3px 7px; border-radius: var(--r); }
	.lab-tag { background: var(--green); color: var(--gold); }
	.src-tag { color: var(--sub); box-shadow: inset 0 0 0 1px var(--line); }
	.report .notice { margin: 0 0 16px; }
	.fields { display: grid; grid-template-columns: max-content 1fr; gap: 6px 20px; margin: 0 0 18px; }
	.fields dt { color: var(--sub); }
	.fields dd { margin: 0; overflow-wrap: anywhere; }
	.results { min-width: 720px; font-size: 14px; }
	@media (max-width: 600px) {
		.photo { flex-basis: 100%; }
		.photo img, .nophoto { aspect-ratio: 4 / 3; }
	}
</style>
