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
		<span class="hash" title={wallet.address}>{short(wallet.address)}</span>
		<button onclick={disconnect}>Disconnect</button>
	{:else}
		<details bind:this={menu}>
			<summary>Connect wallet</summary>
			<div class="menu">
				{#each injected as w (w.info.uuid)}
					<button onclick={() => run(() => connectInjected(w.provider))}>
						<img src={w.info.icon} alt="" width="16" height="16" style="vertical-align: middle" /> {w.info.name}
					</button>
				{:else}
					<button onclick={() => run(() => connectInjected())}>MetaMask / browser wallet</button>
				{/each}
				{#if hasWalletConnect}<button onclick={() => run(connectWalletConnect)}>WalletConnect</button>{/if}
				{#if allowPrivateKey}
					<form onsubmit={(e) => { e.preventDefault(); run(() => connectPrivateKey(key.trim())); }}>
						<label>Private key (testing only)
							<input type="password" bind:value={key} placeholder="0x…" autocomplete="off" />
						</label>
						<button type="submit" disabled={!key.trim()}>Use private key</button>
					</form>
				{/if}
				{#if error}<p class="error">{error}</p>{/if}
			</div>
		</details>
	{/if}
</div>
