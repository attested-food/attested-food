<script lang="ts">
	import { page } from '$app/state';
	import { api, dash, label, verdictText, httpUrl, type Product, type Result } from '$lib/api';

	const GROUPS = ['nutrition', 'heavy_metal', 'toxin', 'pesticide', 'spiking', 'other'];

	const product = $derived(api<Product>(`/api/products/${encodeURIComponent(page.params.id ?? '')}`));
	let title = $state('Product');
	$effect(() => {
		product.then((p) => (title = `${p.brand} ${p.name}`)).catch(() => (title = 'Product'));
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
</script>

<svelte:head><title>{title} — attested.food</title></svelte:head>

{#await product}
	<p class="muted">Loading…</p>
{:then p}
	<p class="muted">{p.brand}</p>
	<h1>{p.name}{#if p.variant} — {p.variant}{/if}</h1>
	{#if httpUrl(p.image_url)}<img src={httpUrl(p.image_url)} alt="{p.brand} {p.name}" style="max-height: 16rem" />{/if}
	<dl class="fields">
		<dt>Brand</dt><dd>{dash(p.brand)}</dd>
		<dt>Name</dt><dd>{dash(p.name)}</dd>
		<dt>Variant</dt><dd>{dash(p.variant)}</dd>
		<dt>Category</dt><dd>{label(p.category)}</dd>
		<dt>Manufacturer</dt><dd>{dash(p.manufacturer)}</dd>
		<dt>FSSAI licence</dt><dd>{dash(p.fssai_license)}</dd>
		<dt>Barcode</dt><dd>{dash(p.barcode)}</dd>
		<dt>Net quantity</dt><dd>{dash(p.net_quantity)}</dd>
	</dl>

	<h2>Reports ({p.reports.length})</h2>
	{#if !p.reports.length}
		<p>No reports for this product yet. Community-funded testing is coming soon.</p>
	{/if}

	{#each p.reports as r (r.id)}
		<section class="report" id="report-{r.id}">
			<h3>
				{#if r.kind === 'user'}
					<span class="badge user">User report</span>
				{:else}
					<span class="badge fallback">Fallback data</span>
				{/if}
				{r.lab?.name ?? r.publisher?.name ?? 'Report'}
			</h3>

			{#if r.kind === 'fallback'}
				<p>
					Source:
					{#if httpUrl(r.source_url)}<a href={httpUrl(r.source_url)} rel="noopener">{r.publisher?.name ?? 'source'}</a>{:else}{r.publisher?.name ?? '—'}{/if}
					· Tested by {r.lab?.name ?? '—'}
				</p>
				<p class="notice">Data as published by {r.publisher?.name ?? 'the source'}; not independently verified by attested.food.</p>
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
				<dt>Tested</dt><dd>{dash(r.tested_on)}</dd>
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
					<table>
						<thead>
							<tr><th>Parameter</th><th>Label claim</th><th>Tested</th><th>Unit</th><th>Limit / LOQ</th><th>Method</th><th>Status</th></tr>
						</thead>
						<tbody>
							{#each grouped(r.results) as [group, rows] (group)}
								<tr class="group"><th colspan="7">{label(group)}</th></tr>
								{#each rows as row, i (i)}
									<tr>
										<td>{row.parameter}</td>
										<td>{dash(row.label_claim)}</td>
										<td class:off={offClaim(row)} title={offClaim(row) ? 'Differs from label claim by more than 10%' : undefined}>{dash(row.value_raw)}</td>
										<td>{dash(row.unit)}</td>
										<td title={row.detection_limit !== null ? 'Limit of quantification: lowest amount the lab can measure, not a safety limit' : undefined}>{row.limit !== null ? row.limit : row.detection_limit !== null ? `LOQ ${row.detection_limit}` : '—'}</td>
										<td>{dash(row.method)}</td>
										<td class={row.status ?? ''}>{row.status ? row.status.toUpperCase() : '—'}</td>
									</tr>
								{/each}
							{/each}
						</tbody>
					</table>
				</div>
				<p class="muted">Highlighted values differ from the label claim by more than 10%.</p>
			{:else}
				<p class="muted">No results recorded for this report.</p>
			{/if}
		</section>
	{/each}
{:catch err}
	<p class="error">{err.message === 'Not found' ? 'Product not found.' : `Could not load product: ${err.message}`}</p>
	<p><a href="/products">Back to products</a></p>
{/await}
