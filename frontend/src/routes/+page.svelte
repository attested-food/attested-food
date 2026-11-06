<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type WallItem } from '$lib/api';
	import LabelCard, { type Theme } from '$lib/components/LabelCard.svelte';
	import SiteHeader from '$lib/components/SiteHeader.svelte';

	const W = 600;
	const H = 380;
	const GAP = 32;
	const DRIFT = 0.3; // px per frame
	const STEER = 1.1; // extra px per frame at the screen edge
	const PEELED_SLOW = 0.2;
	const CLICK_SLOP = 6; // a drag longer than this does not peel

	let items = $state<WallItem[]>([]);
	let error = $state('');
	let ox = $state(0);
	let oy = $state(0);
	let peeled = $state<Record<number, boolean>>({});
	let dragging = $state(false);
	let vw = $state(1440);
	let vh = $state(900);

	const scale = $derived(Math.min(1, vw / 760));
	// Enough even rows/columns to cover the screen, so the checkerboard survives wrapping.
	const even = (n: number) => n + (n % 2);
	const cols = $derived(Math.max(4, even(Math.ceil(vw / scale / (W + GAP)) + 1)));
	const rows = $derived(Math.max(4, even(Math.ceil(vh / scale / (H + GAP)) + 1)));

	const tiles = $derived.by(() => {
		if (!items.length) return [];
		const TW = cols * (W + GAP);
		const TH = rows * (H + GAP);
		const out: { id: number; x: number; y: number; item: WallItem; theme: Theme }[] = [];
		for (let r = 0; r < rows; r++) {
			for (let c = 0; c < cols; c++) {
				let x = c * (W + GAP) + ox;
				x = ((((x + TW / 2) % TW) + TW) % TW) - TW / 2;
				let y = r * (H + GAP) + oy;
				y = ((((y + TH / 2) % TH) + TH) % TH) - TH / 2;
				out.push({
					id: r * cols + c,
					x,
					y,
					item: items[(r * cols + c) % items.length], // unique while tiles <= items; tile (0,0) starts at the centre
					theme: (r + c) % 2 === 0 ? 'light' : 'dark'
				});
			}
		}
		return out;
	});

	// Motion state that doesn't need to re-render anything.
	let still = false;
	let ang = -2.7;
	let target = ang;
	let vx = 0;
	let vy = 0;
	let mx: number | null = null;
	let my: number | null = null;
	let nextTurn = 0;
	let dist = 0;
	let start = { x: 0, y: 0, ox: 0, oy: 0 };

	onMount(() => {
		still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
		const size = () => {
			vw = window.innerWidth;
			vh = window.innerHeight;
		};
		size();
		window.addEventListener('resize', size);

		api<{ items: WallItem[] }>('/api/wall?limit=36')
			.then((d) => (items = d.items))
			.catch((e) => (error = e.message));

		nextTurn = performance.now() + 6000;
		let last = performance.now();
		let frame = requestAnimationFrame(function tick(now) {
			const k = Math.min(3, (now - last) / (1000 / 60));
			last = now;
			if (!still && !dragging && !document.hidden) {
				if (now > nextTurn) {
					target = ang + (Math.random() < 0.5 ? -1 : 1) * (0.7 + Math.random() * 1.4);
					nextTurn = now + 5000 + Math.random() * 4000;
				}
				ang += (target - ang) * 0.012 * k;
				const slow = Object.values(peeled).some(Boolean) ? PEELED_SLOW : 1;
				let tx = Math.cos(ang) * DRIFT * slow;
				let ty = Math.sin(ang) * DRIFT * slow;
				if (mx !== null && my !== null) {
					tx += -mx * STEER * slow;
					ty += -my * STEER * slow;
				}
				vx += (tx - vx) * 0.03 * k;
				vy += (ty - vy) * 0.03 * k;
				ox += vx * k;
				oy += vy * k;
			}
			frame = requestAnimationFrame(tick);
		});

		return () => {
			cancelAnimationFrame(frame);
			window.removeEventListener('resize', size);
		};
	});

	function down(x: number, y: number) {
		dist = 0;
		start = { x, y, ox, oy };
		dragging = true;
	}
	function move(x: number, y: number) {
		if (!dragging) return;
		dist = Math.max(dist, Math.abs(x - start.x) + Math.abs(y - start.y));
		ox = start.ox + (x - start.x) / scale;
		oy = start.oy + (y - start.y) / scale;
	}
	function up() {
		if (!dragging) return;
		dragging = false;
		vx = 0;
		vy = 0;
	}
	function steer(e: MouseEvent) {
		mx = (e.clientX / vw - 0.5) * 2;
		my = (e.clientY / vh - 0.5) * 2;
		move(e.clientX, e.clientY);
	}
	function peel(id: number) {
		if (dist < CLICK_SLOP) peeled[id] = true;
	}
</script>

<svelte:head>
	<title>OpenLabel · every label, checked</title>
	<meta name="description" content="Request lab tests for packaged food in India, fund them together, and see what the label gets wrong." />
</svelte:head>

<div class="home">
	<h1 class="sr-only">OpenLabel: every product's label, checked</h1>

	<!-- svelte-ignore a11y_no_static_element_interactions (pointer-only browsing; every card has its own peel button) -->
	<div
		class="wall"
		class:dragging
		aria-label="Wall of products. Move the cursor or drag to explore. Peel a label to see what the tests found."
		onmousedown={(e) => down(e.clientX, e.clientY)}
		onmousemove={steer}
		onmouseup={up}
		onmouseleave={() => {
			mx = my = null;
			up();
		}}
		onwheel={(e) => {
			ox -= e.deltaX / scale;
			oy -= e.deltaY / scale;
		}}
		ontouchstart={(e) => down(e.touches[0].clientX, e.touches[0].clientY)}
		ontouchmove={(e) => move(e.touches[0].clientX, e.touches[0].clientY)}
		ontouchend={up}
	>
		<div class="plane" style:transform="scale({scale})">
			{#each tiles as t (t.id)}
				<article
					class="tile"
					aria-label={t.item.name}
					style:transform="translate3d({t.x.toFixed(1)}px, {t.y.toFixed(1)}px, 0)"
					style:z-index={peeled[t.id] ? 2 : 1}
				>
					<LabelCard
						item={t.item}
						theme={t.theme}
						peeled={!!peeled[t.id]}
						onpeel={() => peel(t.id)}
						onunpeel={() => (peeled[t.id] = false)}
					/>
				</article>
			{/each}
		</div>
		{#if error}
			<p class="wall-error">Couldn't load products ({error}).</p>
		{/if}
	</div>

	<SiteHeader overlay />

	<div class="ctas">
		<a class="btn cta" href="/products">Find better food</a>
		<a class="btn cta" href="/request">Request a test</a>
		<a class="btn cta" href="/tests#funding">Fund a test</a>
	</div>
</div>

<style>
	:global(body) {
		background: var(--ink);
	}
	.home {
		position: relative;
		height: 100vh;
		height: 100dvh;
		min-height: 560px;
		overflow: hidden;
		background: var(--green);
	}
	.wall {
		position: absolute;
		inset: 0;
		cursor: grab;
		user-select: none;
		-webkit-user-select: none;
		touch-action: none;
	}
	.wall.dragging {
		cursor: grabbing;
	}
	.plane {
		position: absolute;
		inset: 0;
		transform-origin: 50% 50%;
	}
	.tile {
		position: absolute;
		left: 50%;
		top: 50%;
		width: 600px;
		height: 380px;
		margin: -190px 0 0 -300px;
		will-change: transform;
	}
	.wall-error {
		position: absolute;
		left: 50%;
		top: 50%;
		transform: translate(-50%, -50%);
		margin: 0;
		color: var(--gold);
	}
	.ctas {
		position: absolute;
		left: 0;
		right: 0;
		bottom: 0;
		z-index: 4;
		padding: 72px 16px 32px;
		background: linear-gradient(0deg, rgba(7, 22, 15, 0.85) 0%, rgba(7, 22, 15, 0.5) 50%, rgba(7, 22, 15, 0) 100%);
		display: flex;
		flex-wrap: wrap;
		justify-content: center;
		gap: 10px;
		pointer-events: none;
	}
	.cta {
		pointer-events: auto;
		min-height: 54px;
		padding: 0 26px;
		font-size: 16px;
	}
	@media (max-width: 520px) {
		.ctas {
			padding: 56px 16px 20px;
		}
		.cta {
			flex: 1 1 100%;
			min-height: 48px;
		}
	}
</style>
