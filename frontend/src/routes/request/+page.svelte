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
	const fullName = (p: Match) => `${p.brand} ${p.name}${p.variant ? ` · ${p.variant}` : ''}`;

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

<svelte:head><title>Request a test · OpenLabel</title></svelte:head>

<div class="page narrow">
	<div class="eyebrow">Step 1 of 3 · request → fund → test</div>
	<h1>Request a test</h1>

	{#if done}
		<div class="notice done">
			<p>Request received for <strong>{form.brand} {form.name}</strong>. Once others back it, it goes to an accredited lab.</p>
			<p><a class="btn small" href="/requests/{done.id}">View your request</a></p>
		</div>
		<h2>Tests we'll run</h2>
		<ul class="tests">{#each done.tests as t (t)}<li><span aria-hidden="true">?</span>{t}</li>{/each}</ul>
		<p><button type="button" class="btn ghost" onclick={() => switchMode(mode)}>Request another product</button></p>
	{:else}
		<p class="lede">Tell us which product to get lab tested. If we already have it, we'll take you to its page.</p>

		<div class="seg" role="radiogroup" aria-label="How to add the product">
			<label class:on={mode === 'link'}><input class="sr-only" type="radio" name="mode" checked={mode === 'link'} onchange={() => switchMode('link')} />Paste an Amazon link</label>
			<label class:on={mode === 'manual'}><input class="sr-only" type="radio" name="mode" checked={mode === 'manual'} onchange={() => switchMode('manual')} />Enter details</label>
		</div>

		{#if existing}
			<div class="notice" role="alert">
				{#if existing.kind === 'product'}
					<p><strong>{fullName(existing)}</strong> is already on OpenLabel. Go to its page?</p>
				{:else}
					<p><strong>{fullName(existing)}</strong> was already requested on {existing.requested_on}. Go to its page?</p>
				{/if}
				<div class="row">
					<button type="button" class="btn small" onclick={() => goto(existing?.kind === 'product' ? `/products/${existing.id}` : `/requests/${existing?.id}`)}>Yes, open it</button>
					<button type="button" class="btn small ghost" onclick={() => switchMode(mode)}>No, start over</button>
				</div>
			</div>
		{/if}

		{#if mode === 'link'}
			<form class="stack" onsubmit={fetchLink}>
				<label class="field"><span>Amazon product link</span>
					<input type="url" required maxlength="2000" bind:value={link} disabled={!!existing || fetching} placeholder="https://www.amazon.in/…/dp/B08R3CLJ8H" />
				</label>
				<div><button class="btn" type="submit" disabled={!!existing || fetching}>{fetching ? 'Fetching…' : fetched ? 'Fetch again' : 'Fetch details'}</button></div>
			</form>
			{#if linkNote}<p class="notice">{linkNote}</p>{/if}
		{/if}

		{#if error && !showForm}<p class="error">{error}</p>{/if}

		{#if showForm}
			<form class="stack" onsubmit={submit}>
				<fieldset disabled={!!existing}>
					<div class="suggest" onfocusout={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) suggestions = []; }}>
						<div class="pair">
							<label class="field"><span>Brand *</span><input required maxlength="100" bind:value={form.brand} oninput={() => search()} placeholder="e.g. Pintola" autocomplete="off" /></label>
							<label class="field"><span>Product name *</span><input required maxlength="200" bind:value={form.name} oninput={() => search()} placeholder="e.g. Peanut Butter" autocomplete="off" /></label>
						</div>
						{#if suggestions.length}
							<ul aria-label="Products already on OpenLabel">
								{#each suggestions as s (s.kind + s.id)}
									<li><button type="button" onclick={() => choose(s)}>{fullName(s)}<span class="tag">{s.kind === 'product' ? 'Already listed' : 'Already requested'}</span></button></li>
								{/each}
							</ul>
						{/if}
					</div>
					<div class="pair">
						<label class="field"><span>Variant / flavour</span><input maxlength="100" bind:value={form.variant} placeholder="e.g. Dark Chocolate, Crunchy" /></label>
						<label class="field"><span>Category *</span>
							<select required bind:value={form.category}>
								<option value="" disabled>Choose a category</option>
								{#each categories as c (c.category)}<option value={c.category}>{label(c.category)}</option>{/each}
							</select>
						</label>
					</div>
					{#if tests.length}
						<div class="tests-box">
							<div class="eyebrow">Tests we'll run for {label(form.category)}</div>
							<ul class="tests">{#each tests as t (t)}<li><span aria-hidden="true">?</span>{t}</li>{/each}</ul>
						</div>
					{/if}

					<div class="field">
						<span>Product image *</span>
						<div class="seg small" role="radiogroup" aria-label="Image source">
							<label class:on={imageMode === 'url'}><input class="sr-only" type="radio" bind:group={imageMode} value="url" />Image URL</label>
							<label class:on={imageMode === 'file'}><input class="sr-only" type="radio" bind:group={imageMode} value="file" />Upload file</label>
						</div>
					</div>
					{#if imageMode === 'url'}
						<label class="field"><span>Image URL</span><input type="url" required maxlength="2000" bind:value={imageUrl} placeholder="https://…" /></label>
					{:else}
						<label class="field"><span>Image file</span><input type="file" required accept="image/png,image/jpeg,image/webp" bind:this={fileInput} onchange={pickFile} /><small class="hint">JPG, PNG or WebP, up to 5 MB</small></label>
					{/if}
					{#if imageError}<p class="error">{imageError}</p>{/if}
					{#if preview}<img class="preview" src={preview} alt="Product preview" />{/if}

					<div class="pair">
						<label class="field"><span>Net quantity</span><input maxlength="50" bind:value={form.net_quantity} placeholder="e.g. 1 kg" /></label>
						<label class="field"><span>Where to buy</span><input type="url" maxlength="2000" bind:value={form.buy_url} placeholder="Amazon, BigBasket or brand site link" /></label>
					</div>
					<div class="pair">
						<label class="field"><span>Barcode</span><input inputmode="numeric" pattern={'\\d{8,14}'} title="8 to 14 digits" bind:value={form.barcode} placeholder="From the pack" /></label>
						<label class="field"><span>FSSAI licence no.</span><input inputmode="numeric" pattern={'\\d{14}'} title="14 digits" bind:value={form.fssai_license} placeholder="14 digits, from the pack" /></label>
					</div>
					<label class="field"><span>Manufacturer</span><input maxlength="200" bind:value={form.manufacturer} placeholder="From the pack" /></label>

					{#if error}<p class="error">{error}</p>{/if}
					<div><button class="btn" type="submit" disabled={submitting}>{submitting ? 'Sending…' : 'Request a test'}</button></div>
				</fieldset>
			</form>
		{/if}
	{/if}
</div>

<style>
	.narrow { max-width: 760px; }
	h1 { margin: 6px 0 0; font-size: clamp(32px, 5vw, 44px); font-weight: 750; }
	h2 { font-size: 22px; margin: 28px 0 10px; }
	.lede { margin-bottom: 24px; }
	.stack, fieldset { display: grid; gap: 18px; }
	fieldset { border: 0; padding: 0; margin: 0; min-width: 0; }
	.stack { margin-bottom: 20px; }
	.pair { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 18px; }
	.seg { display: inline-flex; padding: 3px; border-radius: var(--r); background: var(--cream); box-shadow: inset 0 0 0 1px var(--line); margin-bottom: 22px; }
	.seg input.sr-only { position: absolute; width: 1px; height: 1px; min-height: 0; padding: 0; border: 0; opacity: 0; }
	.seg label { position: relative; padding: 9px 16px; border-radius: 2px; cursor: pointer; font-weight: 600; font-size: 15px; color: var(--sub); }
	.seg label.on { background: var(--green); color: var(--gold); }
	.seg.small { margin: 0; justify-self: start; }
	.seg.small label { padding: 6px 12px; font-size: 14px; }
	.notice { margin-bottom: 20px; }
	.notice p { margin: 0 0 10px; }
	.notice p:last-child { margin: 0; }
	.row { display: flex; flex-wrap: wrap; gap: 8px; }
	.suggest { position: relative; }
	.suggest ul { position: absolute; z-index: 3; left: 0; right: 0; top: calc(100% + 4px); margin: 0; padding: 4px 0; list-style: none; background: var(--paper); border: 1px solid var(--ink); border-radius: var(--r); max-height: 18rem; overflow-y: auto; box-shadow: 0 12px 30px -12px rgba(0,0,0,.3); }
	.suggest li button { display: flex; justify-content: space-between; gap: 12px; width: 100%; text-align: left; background: none; border: 0; padding: 10px 14px; cursor: pointer; }
	.suggest li button:hover, .suggest li button:focus { background: var(--cream); }
	.tag { flex: 0 0 auto; font-family: var(--mono); font-size: 10.5px; letter-spacing: 0.05em; text-transform: uppercase; color: var(--gold-ink); }
	.tests-box { padding: 14px 16px; background: var(--cream); border-radius: var(--r); }
	.tests { list-style: none; margin: 8px 0 0; padding: 0; }
	.tests li { display: flex; gap: 10px; padding: 5px 0; border-bottom: 1px solid var(--line); }
	.tests li:last-child { border-bottom: 0; }
	.tests li span { width: 16px; color: var(--sub); font-weight: 700; }
	.preview { max-height: 10rem; justify-self: start; border-radius: var(--r); box-shadow: inset 0 0 0 1px var(--line); }
	.field input[type='file'] { padding: 10px 12px; }
</style>
