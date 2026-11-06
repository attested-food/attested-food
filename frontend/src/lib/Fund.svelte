<script lang="ts">
	import { parseUnits, zeroAddress } from 'viem';
	import {
		wallet, publicClient, send, ensureAllowance, campaignId, usd, short,
		fundAddress, usdAddress, fundAbi, usdAbi
	} from '$lib/wallet.svelte';

	let { requestId }: { requestId: string } = $props();

	const GOAL = parseUnits('100', 6);
	const STAKE = parseUnits('110', 6);
	const STATUS = ['Open', 'Pending', 'Submitted'] as const;
	const id = $derived(campaignId(requestId));

	type State = { pool: bigint; tester: string; deadline: Date; status: (typeof STATUS)[number]; mine: bigint; balance: bigint };
	let s = $state<State | null>(null);
	let busy = $state('');
	let error = $state('');
	let custom = $state('');

	async function load() {
		const [pool, tester, deadline, status] = await publicClient.readContract({
			address: fundAddress!, abi: fundAbi, functionName: 'campaigns', args: [id]
		});
		const me = wallet.address;
		const [mine, balance] = me
			? await Promise.all([
					publicClient.readContract({ address: fundAddress!, abi: fundAbi, functionName: 'contributed', args: [id, me] }),
					publicClient.readContract({ address: usdAddress!, abi: usdAbi, functionName: 'balanceOf', args: [me] })
				])
			: [0n, 0n];
		s = { pool, tester, deadline: new Date(Number(deadline) * 1000), status: STATUS[status], mine, balance };
	}

	$effect(() => {
		void wallet.address;
		if (fundAddress) load().catch((e) => (error = `Could not read campaign: ${e.message.split('\n')[0]}`));
	});

	async function act(label: string, fn: () => Promise<unknown>) {
		busy = label;
		error = '';
		try {
			await fn();
			await load();
		} catch (e) {
			error = e instanceof Error ? (('shortMessage' in e && String(e.shortMessage)) || e.message.split('\n')[0]) : String(e);
		} finally {
			busy = '';
		}
	}

	const contribute = (amount: bigint) =>
		act('contribute', async () => {
			await ensureAllowance(amount);
			await send({ address: fundAddress!, abi: fundAbi, functionName: 'contribute', args: [id, amount] });
		});
	const commit = () =>
		act('commit', async () => {
			await ensureAllowance(STAKE);
			await send({ address: fundAddress!, abi: fundAbi, functionName: 'commit', args: [id] });
		});
	const call = (fn: 'submitReport' | 'slash') =>
		act(fn, () => send({ address: fundAddress!, abi: fundAbi, functionName: fn, args: [id] }));
	const faucet = () =>
		act('faucet', () => send({ address: usdAddress!, abi: usdAbi, functionName: 'mint', args: [wallet.address!, parseUnits('200', 6)] }));

	const remaining = $derived(s && s.pool < GOAL ? GOAL - s.pool : 0n);
	const customAmount = $derived(/^\d+(\.\d{1,6})?$/.test(custom) ? parseUnits(custom, 6) : 0n);
	const isTester = $derived(!!s && !!wallet.address && s.tester.toLowerCase() === wallet.address.toLowerCase());
	const late = $derived(!!s && s.status === 'Pending' && s.deadline.getTime() < Date.now());
</script>

<section class="fund">
	<h2>Fund this test</h2>
	<p>Testing costs <strong>{usd(GOAL)}</strong>. Anyone can chip in. Anyone can also take the job at any time by staking
		<strong>{usd(STAKE)}</strong>. The stake is returned when the report is submitted.
		<strong>If the tester doesn't submit the report within 1 month, the stake is lost</strong> and the job reopens for someone else.</p>

	{#if !fundAddress}
		<p class="notice">On-chain funding isn't configured for this deployment.</p>
	{:else if !s}
		<p class="muted">{error || 'Loading campaign…'}</p>
	{:else}
		<progress max={Number(GOAL)} value={Number(s.pool > GOAL ? GOAL : s.pool)}></progress>
		<p><strong>{usd(s.pool)}</strong> of {usd(GOAL)} raised
			{#if s.status === 'Open' && remaining === 0n}· <span class="badge user">Fully funded, waiting for a tester</span>{/if}
			{#if s.status === 'Pending'}· <span class="badge fallback">Tester assigned</span>{/if}
			{#if s.status === 'Submitted'}· <span class="badge user">Report submitted</span>{/if}
		</p>
		{#if s.status !== 'Open'}
			<dl class="fields">
				<dt>Tester</dt><dd class="hash" title={s.tester}>{s.tester === zeroAddress ? '—' : short(s.tester)}</dd>
				{#if s.status === 'Pending'}<dt>Report due</dt><dd>{s.deadline.toLocaleString()}{#if late} <span class="error">overdue</span>{/if}</dd>{/if}
			</dl>
		{/if}

		{#if !wallet.address}
			<p class="notice">Connect your wallet (top right) to contribute or take this test.</p>
		{:else}
			<p class="muted">Your contribution: {usd(s.mine)} · Wallet balance: {usd(s.balance)} tUSD
				<button onclick={faucet} disabled={!!busy}>{busy === 'faucet' ? 'Minting…' : 'Get 200 test USD'}</button></p>

			{#if s.status !== 'Submitted' && remaining > 0n}
				<div class="row">
					{#each [1, 2, 10, 20] as d (d)}
						{@const amount = parseUnits(String(d), 6)}
						<button class="primary" disabled={!!busy || amount > remaining} onclick={() => contribute(amount)}>${d}</button>
					{/each}
					<form class="row" onsubmit={(e) => { e.preventDefault(); contribute(customAmount); }}>
						<input inputmode="decimal" placeholder="Other $" aria-label="Other amount in dollars" bind:value={custom} />
						<button disabled={!!busy || !customAmount || customAmount > remaining}>Contribute</button>
					</form>
				</div>
				<p class="muted">{usd(remaining)} still needed.</p>
			{/if}
			{#if s.status === 'Open'}
				<button class="primary" disabled={!!busy} onclick={commit}>{busy === 'commit' ? 'Staking…' : `Take this test (stake ${usd(STAKE)})`}</button>
			{:else if s.status === 'Pending' && isTester && !late}
				<button class="primary" disabled={!!busy} onclick={() => call('submitReport')}>{busy === 'submitReport' ? 'Submitting…' : 'Submit report'}</button>
			{:else if late}
				<button disabled={!!busy} onclick={() => call('slash')}>{busy === 'slash' ? 'Slashing…' : 'Slash overdue stake'}</button>
			{/if}
			{#if busy && busy !== 'faucet'}<p class="muted">Confirm in your wallet, then wait for the transaction to be mined…</p>{/if}
		{/if}
		{#if error}<p class="error">{error}</p>{/if}
	{/if}
</section>
