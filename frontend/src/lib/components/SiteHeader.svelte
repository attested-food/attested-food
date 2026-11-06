<script lang="ts">
	import { page } from '$app/state';

	let { overlay = false }: { overlay?: boolean } = $props();

	const links = $derived(
		overlay
			? [
					{ href: '/products', text: 'Marketplace' },
					{ href: '/about', text: 'How it works' }
				]
			: [
					{ href: '/products', text: 'Marketplace' },
					{ href: '/request', text: 'Request a test' },
					{ href: '/tests', text: 'Fund tests' },
					{ href: '/about', text: 'How it works' }
				]
	);
	const current = (href: string) => page.url.pathname === href || page.url.pathname.startsWith(href + '/');
</script>

<header class:overlay>
	<div class="inner">
		<a class="logo" href="/" aria-label="OpenLabel home">
			<svg width="22" height="22" viewBox="0 0 30 30" aria-hidden="true"><path d="M7 15.5l5 5L23 9.5" fill="none" stroke="currentColor" stroke-width="3.6" stroke-linecap="square" /></svg>
			<span>OpenLabel</span>
		</a>
		<nav aria-label="Main">
			{#each links as l (l.href)}
				<a href={l.href} aria-current={current(l.href) ? 'page' : undefined}>{l.text}</a>
			{/each}
		</nav>
		<button type="button" class="btn signin" aria-disabled="true" title="Accounts are coming soon">Sign in</button>
	</div>
</header>

<style>
	header {
		position: relative;
		z-index: 5;
		background: var(--paper);
		border-bottom: 1px solid var(--line);
	}
	header.overlay {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		border: 0;
		padding-bottom: 56px;
		background: linear-gradient(180deg, rgba(7, 22, 15, 0.85) 0%, rgba(7, 22, 15, 0.5) 55%, rgba(7, 22, 15, 0) 100%);
		color: #fff;
		pointer-events: none;
	}
	.inner {
		max-width: 1360px;
		margin: 0 auto;
		padding: 14px 24px;
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 10px 32px;
		pointer-events: auto;
	}
	.logo {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		min-height: 44px;
		padding: 0 14px 0 11px;
		border-radius: var(--r);
		background: var(--green);
		color: var(--gold);
		text-decoration: none;
		font-weight: 700;
		font-size: 21px;
		letter-spacing: -0.035em;
	}
	.logo:hover {
		color: var(--gold);
	}
	nav {
		flex: 1;
		display: flex;
		flex-wrap: wrap;
		gap: 0 28px;
		font-size: 15px;
		font-weight: 500;
	}
	nav a {
		text-decoration: none;
		padding: 12px 0;
	}
	nav a[aria-current='page'] {
		box-shadow: inset 0 -3px 0 var(--gold);
	}
	.overlay nav a {
		color: #fff;
	}
	.overlay nav a:hover {
		color: var(--gold);
	}
	.signin {
		cursor: default;
	}
	@media (max-width: 640px) {
		.inner {
			padding: 12px 16px;
			gap: 4px 18px;
		}
		nav {
			order: 3;
			flex-basis: 100%;
			gap: 0 20px;
		}
		.signin {
			margin-left: auto;
		}
	}
</style>
