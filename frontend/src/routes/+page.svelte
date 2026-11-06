<svelte:head><title>OpenLabel.fyi</title></svelte:head>

<h1>OpenLabel.fyi</h1>
<p>Verified lab test reports for packaged food sold in India, with the contributor's personal details kept private.</p>
<form class="search" action="/products" method="get" role="search">
	<label for="q" class="muted">Search products</label>
	<input type="search" id="q" name="q" placeholder="Brand or product, e.g. Kellogg's muesli" />
	<button type="submit">Search</button>
</form>

<p><a class="button" href="/request">Request a test</a> <span class="muted">Can't find a product? Ask us to get it lab tested.</span></p>
