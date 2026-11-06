<script lang="ts">
	import '../app.css';
	import { page } from '$app/state';
	import SiteHeader from '$lib/components/SiteHeader.svelte';

	let { children } = $props();
	const home = $derived(page.url.pathname === '/');
</script>

<svelte:head><title>OpenLabel</title></svelte:head>

{#if home}
	{@render children()}
{:else}
	<SiteHeader />
	<main>{@render children()}</main>
	<footer class="site-footer">
		<div class="inner">
			<span>OpenLabel · crowd-requested, crowd-funded lab tests of packaged food in India.</span>
			<nav aria-label="Footer">
				<a href="/sources">Sources</a>
				<a href="/about">About</a>
			</nav>
			<span>Ingredient lists and label nutrition from <a href="https://world.openfoodfacts.org">Open Food Facts</a> (ODbL / CC BY-SA) where the pack wasn't scanned by us.</span>
		</div>
	</footer>
{/if}
