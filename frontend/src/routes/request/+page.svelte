<script lang="ts">
	import { goto } from '$app/navigation';
	import { api, post, label, ApiError, type Category, type Prefill, type TestRequest } from '$lib/api';

	const MAX_IMAGE = 5 * 1024 * 1024;
	const empty = () => ({ brand: '', name: '', variant: '', category: '', net_quantity: '', manufacturer: '', fssai_license: '', barcode: '', buy_url: '' });

	type Match = { kind: 'product' | 'request'; id: string; brand: string; name: string; variant: string | null; category?: string | null; requested_on?: string | null };

	let mode = $state<'link' | 'manual'>('link');
	let link = $state('');
	let fetching = $state(false);
	let fetched = $state(false);
	let linkNote = $state('');
	let form = $state(empty());
	let imageMode = $state<'url' | 'file'>('url');
	let imageUrl = $state('');
	let imageData = $state<string | null>(null);
	let imageError = $state('');
	let categories = $state<Category[]>([]);
	let suggestions = $state<Match[]>([]);
	let existing = $state<Match | null>(null);
	let error = $state('');
	let submitting = $state(false);
	let done = $state<{ id: string; tests: string[] } | null>(null);
	let fileInput = $state<HTMLInputElement>();

	const tests = $derived(categories.find((c) => c.category === form.category)?.tests ?? []);
	const preview = $derived(imageMode === 'file' ? imageData : /^https?:\/\//i.test(imageUrl) ? imageUrl : null);
	const showForm = $derived(mode === 'manual' || fetched);

	api<Category[]>('/api/categories').then((c) => (categories = c)).catch((e) => (error = `Could not load categories: ${e.message}`));

	const asRequest = (r: TestRequest): Match => ({ kind: 'request', ...r });
	const fullName = (p: Match) => `${p.brand} ${p.name}${p.variant ? ` — ${p.variant}` : ''}`;

	let timer: ReturnType<typeof setTimeout>;
	let latestQuery = '';
	function search(q = `${form.brand} ${form.name}`.trim()) {
		clearTimeout(timer);
		latestQuery = q;
		if (q.length < 2) return (suggestions = []);
		timer = setTimeout(async () => {
			try {
				const found = await api<Match[]>(`/api/duplicates?q=${encodeURIComponent(q)}`);
				if (q === latestQuery) suggestions = found;
			} catch (e) {
				console.error('duplicate search failed', e);
			}
		}, 250);
	}

	function choose(m: Match) {
		form = { ...empty(), brand: m.brand, name: m.name, variant: m.variant ?? '', category: m.category ?? '' };
		existing = m;
		suggestions = [];
	}

	function reset() {
		form = empty();
		link = '';
		fetched = false;
		linkNote = '';
		imageMode = 'url';
		imageUrl = '';
		imageData = null;
		imageError = '';
		if (fileInput) fileInput.value = '';
		existing = null;
		suggestions = [];
		error = '';
		done = null;
	}

	function switchMode(m: 'link' | 'manual') {
		reset();
		mode = m;
	}

	async function fetchLink(e: SubmitEvent) {
		e.preventDefault();
		existing = null;
		error = '';
		fetching = true;
		try {
			const p = await api<Prefill>(`/api/prefill?url=${encodeURIComponent(link.trim())}`);
			form = { ...empty(), brand: p.brand ?? '', name: p.name ?? '', category: p.category ?? '', net_quantity: p.net_quantity ?? '', manufacturer: p.manufacturer ?? '', buy_url: p.buy_url };
			imageMode = 'url';
			imageUrl = p.image_url ?? '';
			fetched = true;
			linkNote = 'Filled in from Amazon. Check the details and fix anything that looks wrong before sending.';
			if (p.existing_request) existing = asRequest(p.existing_request);
			else search();
		} catch (err) {
			const msg = err instanceof Error ? err.message : String(err);
			if (msg.includes('(422)')) {
				linkNote = '';
				error = 'That doesn\'t look like an amazon.in product link.';
			} else {
				form = { ...empty(), buy_url: /^https?:\/\//i.test(link.trim()) ? link.trim() : '' };
				fetched = true;
				linkNote = 'We couldn\'t read that Amazon page. Please fill in the details below.';
			}
		} finally {
			fetching = false;
		}
	}

	function pickFile(e: Event) {
		const file = (e.currentTarget as HTMLInputElement).files?.[0];
		imageData = null;
		imageError = '';
		if (!file) return;
		if (file.size > MAX_IMAGE) return (imageError = 'Image must be 5 MB or smaller.');
		const reader = new FileReader();
		reader.onload = () => (imageData = reader.result as string);
		reader.onerror = () => (imageError = 'Could not read that file.');
		reader.readAsDataURL(file);
	}

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		error = '';
		if (imageMode === 'file' && !imageData) return (error = imageError || 'Choose an image file.');
		const body = {
			...Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v.trim() || null])),
			image_url: imageMode === 'url' ? imageUrl.trim() : null,
			image_data: imageMode === 'file' ? imageData : null
		};
		submitting = true;
		try {
			done = await post<{ id: string; tests: string[] }>('/api/test-requests', body);
		} catch (err) {
			if (err instanceof ApiError && err.status === 409) {
				const d = err.detail as { product_id?: string; request?: TestRequest };
				existing = d.request
					? asRequest(d.request)
					: { kind: 'product', id: d.product_id ?? '', brand: form.brand, name: form.name, variant: form.variant || null };
			} else if (err instanceof ApiError && Array.isArray(err.detail)) {
				error = err.detail.map((d: { loc: string[]; msg: string }) => `${label(String(d.loc.at(-1)))}: ${d.msg}`).join('; ');
			} else {
				error = err instanceof Error ? err.message : String(err);
			}
		} finally {
			submitting = false;
		}
	}
</script>

<svelte:head><title>Request a test — attested.food</title></svelte:head>

<h1>Request a test</h1>

{#if done}
	<p class="notice">Request received for <strong>{form.brand} {form.name}</strong>. <a href="/requests/{done.id}">View your request</a>.</p>
	<h2>Tests we'll run</h2>
	<ul>{#each done.tests as t (t)}<li>{t}</li>{/each}</ul>
	<p><button class="primary" onclick={() => switchMode(mode)}>Request another product</button></p>
{:else}
	<p class="muted">Tell us which product to get lab tested. If we already have it, we'll take you to its page.</p>

	<div class="modes" role="radiogroup" aria-label="How to add the product">
		<label><input type="radio" name="mode" checked={mode === 'link'} onchange={() => switchMode('link')} /> Paste an Amazon link</label>
		<label><input type="radio" name="mode" checked={mode === 'manual'} onchange={() => switchMode('manual')} /> Enter details manually</label>
	</div>

	{#if existing}
		<div class="notice" role="alert">
			{#if existing.kind === 'product'}
				<p><strong>{fullName(existing)}</strong> already exists on attested.food. Do you want to go to its page?</p>
			{:else}
				<p><strong>{fullName(existing)}</strong> was already requested on {existing.requested_on}. Do you want to go to its page?</p>
			{/if}
			<button type="button" class="primary" onclick={() => goto(existing?.kind === 'product' ? `/products/${existing.id}` : `/requests/${existing?.id}`)}>Yes, open it</button>
			<button type="button" onclick={() => switchMode(mode)}>No, start over</button>
		</div>
	{/if}

	{#if mode === 'link'}
		<form class="request link" onsubmit={fetchLink}>
			<label>Amazon product link
				<input type="url" required maxlength="2000" bind:value={link} disabled={!!existing || fetching} placeholder="https://www.amazon.in/…/dp/B08R3CLJ8H" />
			</label>
			<p><button class="primary" type="submit" disabled={!!existing || fetching}>{fetching ? 'Fetching…' : fetched ? 'Fetch again' : 'Fetch details'}</button></p>
		</form>
		{#if linkNote}<p class="notice">{linkNote}</p>{/if}
	{/if}

	{#if error && !showForm}<p class="error">{error}</p>{/if}

	{#if showForm}
		<form class="request" onsubmit={submit}>
			<fieldset disabled={!!existing}>
				<div class="suggest" onfocusout={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) suggestions = []; }}>
					<label>Brand *<input required maxlength="100" bind:value={form.brand} oninput={() => search()} placeholder="e.g. Pintola" autocomplete="off" /></label>
					<label>Product name *<input required maxlength="200" bind:value={form.name} oninput={() => search()} placeholder="e.g. Peanut Butter" autocomplete="off" /></label>
					{#if suggestions.length}
						<ul aria-label="Products already on attested.food">
							{#each suggestions as s (s.kind + s.id)}
								<li><button type="button" onclick={() => choose(s)}>{fullName(s)}<span class="tag">{s.kind === 'product' ? 'Already listed' : 'Already requested'}</span></button></li>
							{/each}
						</ul>
					{/if}
				</div>
				<label>Variant / flavour<input maxlength="100" bind:value={form.variant} placeholder="e.g. Dark Chocolate, Crunchy" /></label>
				<label>Category *
					<select required bind:value={form.category}>
						<option value="" disabled>Choose a category</option>
						{#each categories as c (c.category)}<option value={c.category}>{label(c.category)}</option>{/each}
					</select>
				</label>
				{#if tests.length}
					<div>
						<p class="muted">Tests we'll run for {label(form.category)}:</p>
						<ul>{#each tests as t (t)}<li>{t}</li>{/each}</ul>
					</div>
				{/if}

				<div>
					<p>Product image *</p>
					<label style="display:inline"><input type="radio" bind:group={imageMode} value="url" style="width:auto" /> Image URL</label>
					<label style="display:inline"><input type="radio" bind:group={imageMode} value="file" style="width:auto" /> Upload file</label>
				</div>
				{#if imageMode === 'url'}
					<label>Image URL<input type="url" required maxlength="2000" bind:value={imageUrl} placeholder="https://…" /></label>
				{:else}
					<label>Image file (JPG, PNG or WebP, up to 5 MB)<input type="file" required accept="image/png,image/jpeg,image/webp" bind:this={fileInput} onchange={pickFile} /></label>
				{/if}
				{#if imageError}<p class="error">{imageError}</p>{/if}
				{#if preview}<img class="preview" src={preview} alt="Product preview" />{/if}

				<label>Net quantity<input maxlength="50" bind:value={form.net_quantity} placeholder="e.g. 1 kg" /></label>
				<label>Where to buy<input type="url" maxlength="2000" bind:value={form.buy_url} placeholder="Amazon, BigBasket or brand site link" /></label>
				<label>Barcode<input inputmode="numeric" pattern={'\\d{8,14}'} title="8 to 14 digits" bind:value={form.barcode} placeholder="From the pack" /></label>
				<label>FSSAI licence no.<input inputmode="numeric" pattern={'\\d{14}'} title="14 digits" bind:value={form.fssai_license} placeholder="14 digits, from the pack" /></label>
				<label>Manufacturer<input maxlength="200" bind:value={form.manufacturer} placeholder="From the pack" /></label>

				{#if error}<p class="error">{error}</p>{/if}
				<p><button class="primary" type="submit" disabled={submitting}>{submitting ? 'Sending…' : 'Request a test'}</button></p>
			</fieldset>
		</form>
	{/if}
{/if}
