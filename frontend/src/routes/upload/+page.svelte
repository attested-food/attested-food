<script lang="ts">
	// Demo only: the extracted fields below are hard-coded sample data, nothing leaves the browser.
	const PRIVATE = ['Client name', 'Client address', 'Contact person'];
	const PUBLIC: [string, string][] = [
		['Lab', 'Equinox Labs (NABL TC-6820)'],
		['Report number', 'EQNX:001:NL:26:10:09217'],
		['ULR', 'TC682026000108177F'],
		['Product', "Kellogg's Millet Muesli — Choco"],
		['Batch', 'S6A280526'],
		['Manufactured / expiry', '2026-05-28 / 2027-02-22']
	];
	const RESULTS: [string, string, string][] = [
		['Protein', '8.31', 'g/100g'],
		['Total Sugars', '21.03', 'g/100g'],
		['Added Sugars', '14.87', 'g/100g'],
		['Sodium', '282.83', 'mg/100g'],
		['Trans Fat', '<0.10', 'g/100g']
	];

	let step = $state<'choose' | 'preview' | 'verify' | 'done'>('choose');
	let file = $state<File | null>(null);
	let hash = $state('');
	let error = $state('');
	let verifying = $state(false);

	async function onFile(e: Event) {
		error = '';
		const f = (e.currentTarget as HTMLInputElement).files?.[0];
		if (!f) return;
		if (f.type !== 'application/pdf' && !f.name.toLowerCase().endsWith('.pdf')) {
			error = 'Please choose a PDF file.';
			return;
		}
		try {
			const digest = await crypto.subtle.digest('SHA-256', await f.arrayBuffer());
			hash = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
			file = f;
			step = 'preview';
		} catch (err) {
			console.error(err);
			error = `Could not read the file: ${(err as Error).message}`;
		}
	}

	function verify() {
		verifying = true;
		setTimeout(() => {
			verifying = false;
			step = 'done';
		}, 1200);
	}

	function reset() {
		step = 'choose';
		file = null;
		hash = '';
	}
</script>

<svelte:head><title>Upload — attested.food</title></svelte:head>

<h1>Upload a lab report</h1>
<p class="notice"><strong>Demo — not connected yet.</strong> Nothing is uploaded; the file is only hashed in your browser and the extracted fields are sample data.</p>

{#if step === 'choose'}
	<h2>1. Choose your report</h2>
	<p><label>Lab report PDF <input type="file" accept="application/pdf" onchange={onFile} /></label></p>
	{#if error}<p class="error">{error}</p>{/if}
{:else if step === 'preview'}
	<h2>2. Check what will be published</h2>
	<p>File: {file?.name} ({Math.round((file?.size ?? 0) / 1024)} KB)</p>
	<p>SHA-256: <span class="hash">{hash}</span></p>
	<h3>Hidden (never published)</h3>
	<dl class="fields">
		{#each PRIVATE as k (k)}<dt>{k}</dt><dd><span class="redacted">████████████</span> <span class="muted">redacted</span></dd>{/each}
	</dl>
	<h3>Public</h3>
	<dl class="fields">
		{#each PUBLIC as [k, v] (k)}<dt>{k}</dt><dd>{v}</dd>{/each}
	</dl>
	<div class="table-wrap">
		<table>
			<thead><tr><th>Parameter</th><th>Tested</th><th>Unit</th></tr></thead>
			<tbody>{#each RESULTS as [p, v, u] (p)}<tr><td>{p}</td><td>{v}</td><td>{u}</td></tr>{/each}</tbody>
		</table>
	</div>
	<p><button onclick={() => (step = 'verify')}>Looks right, continue</button> <button onclick={reset}>Start over</button></p>
{:else if step === 'verify'}
	<h2>3. Verify with lab</h2>
	<p>We would now prove the report came from Equinox Labs, e.g. with a zero-knowledge proof of the lab's email or by matching the copy from the lab's "Download Report" link.</p>
	<p><button onclick={verify} disabled={verifying}>{verifying ? 'Verifying…' : 'Verify with lab'}</button></p>
{:else}
	<h2>4. Done</h2>
	<p>Report verified (simulated). Its hash would be recorded on Ethereum so anyone can check the published report matches.</p>
	<p>SHA-256 of {file?.name}:<br /><span class="hash">{hash}</span></p>
	<p><button onclick={reset}>Upload another</button></p>
{/if}
