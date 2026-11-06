<script lang="ts">
	import '../app.css';

	let { children } = $props();
</script>

<header>
	<a class="logo" href="/">OpenLabel.fyi</a>
	<nav>
		<a href="/">Home</a>
		<a href="/products">Products</a>
		<a href="/sources">Sources</a>
		<a href="/request">Request a test</a>
		<a href="/upload">Upload</a>
		<a href="/about">About</a>
	</nav>
</header>

<main>
	{@render children()}
</main>

<footer><p>OpenLabel.fyi — lab test reports for packaged food in India.</p></footer>
