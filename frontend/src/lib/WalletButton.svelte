<script lang="ts">
	import {
		wallet, short, connectInjected, connectWalletConnect, connectPrivateKey, disconnect,
		hasWalletConnect, allowPrivateKey, injected
	} from '$lib/wallet.svelte';

	let key = $state('');
	let error = $state('');
	let menu = $state<HTMLDetailsElement>();

	async function run(fn: () => unknown) {
		error = '';
		try {
			await fn();
			if (menu) menu.open = false;
		} catch (e) {
			error = e instanceof Error ? e.message.split('\n')[0] : String(e);
		}
	}
</script>

<div class="wallet">
	{#if wallet.address}
		<span class="addr" title={wallet.address}>{short(wallet.address)}</span>
		<button type="button" class="btn ghost-dark" onclick={disconnect}>Disconnect</button>
	{:else}
		<details bind:this={menu}>
			<summary class="btn">Connect wallet</summary>
			<div class="menu">
				{#each injected as w (w.info.uuid)}
					<button type="button" class="opt" onclick={() => run(() => connectInjected(w.provider))}>
						<img src={w.info.icon} alt="" width="18" height="18" /> {w.info.name}
					</button>
				{:else}
					<button type="button" class="opt" onclick={() => run(() => connectInjected())}>MetaMask / browser wallet</button>
				{/each}
				{#if hasWalletConnect}<button type="button" class="opt" onclick={() => run(connectWalletConnect)}>WalletConnect</button>{/if}
				{#if allowPrivateKey}
					<form onsubmit={(e) => { e.preventDefault(); run(() => connectPrivateKey(key.trim())); }}>
						<label class="field"><span>Private key (testing only)</span>
							<input type="password" bind:value={key} placeholder="0x…" autocomplete="off" />
						</label>
						<button type="submit" class="btn small" disabled={!key.trim()}>Use private key</button>
					</form>
				{/if}
				{#if error}<p class="error">{error}</p>{/if}
			</div>
		</details>
	{/if}
</div>

<style>
	.wallet { position: relative; display: flex; align-items: center; gap: 10px; }
	.addr { font-family: var(--mono); font-size: 13px; }
	summary { list-style: none; }
	summary::-webkit-details-marker { display: none; }
	.ghost-dark { background: transparent; color: inherit; box-shadow: inset 0 0 0 1.5px currentColor; min-height: 38px; padding: 0 12px; font-size: 13px; }
	.ghost-dark:hover { background: var(--green); color: var(--gold); box-shadow: none; }
	.menu {
		position: absolute; right: 0; z-index: 10; margin-top: 8px; width: 19rem; display: grid; gap: 8px; padding: 12px;
		background: var(--paper); color: var(--ink); border-radius: var(--r); box-shadow: 0 18px 40px -16px rgba(0, 0, 0, 0.45), 0 0 0 1px var(--line);
	}
	.opt { display: flex; align-items: center; gap: 10px; width: 100%; min-height: 44px; padding: 0 12px; border: 0; border-radius: var(--r); background: var(--cream); cursor: pointer; font-weight: 600; text-align: left; }
	.opt:hover { background: var(--line); }
	form { display: grid; gap: 8px; padding-top: 8px; border-top: 1px solid var(--line); }
	.error { margin: 0; font-size: 13px; }
</style>
