<svelte:head><title>About — attested.food</title></svelte:head>

<h1>About</h1>
<p>attested.food is a platform for sharing independently tested packaged-food reports without exposing the personal details of the person who commissioned the test. It also lets people pool funds to test products they want investigated.</p>
<h2>How it works</h2>
<ol>
	<li><strong>User lab reports, verified.</strong> A contributor buys a product, gets it tested at a reputed lab (e.g. Equinox Labs, Eurofins), and uploads the report PDF. attested.food checks that the report came from that lab and has not been altered, using a lab's digital signature or a zero-knowledge proof of the email the lab sent.</li>
	<li><strong>Personal details hidden.</strong> The contributor's name, address, phone and email are kept private. Only the test findings are published. The report's hash and verification status are recorded on Ethereum, so later changes are detectable.</li>
	<li><strong>Fallback data, with attribution.</strong> When no user report exists for a product, we show results published by established testing websites, clearly labelled with the source and a link back: if you trust that source, this is what it reports. We do not claim to have verified this data ourselves.</li>
	<li><strong>Community-funded testing (coming soon).</strong> For products without a report, people will be able to contribute to a test fund. Once the target is reached, the test is commissioned and the report published for everyone.</li>
</ol>
<h2>What verification does and doesn't prove</h2>
<p>These checks establish evidence about a report's source and integrity. They do not independently prove that a lab used sound methods or that its conclusions are correct.</p>
