<svelte:head><title>How it works · OpenLabel</title></svelte:head>

<div class="page narrow">
	<div class="eyebrow">How it works</div>
	<h1>Labels say one thing. Labs check.</h1>
	<p class="lede">OpenLabel lets people in India ask for packaged food to be lab tested, pay for those tests together, and see what the pack gets wrong.</p>

	<ol class="steps">
		<li>
			<b>1</b>
			<div><h2>Request</h2><p>Paste an Amazon link or type in the product. We list the tests that matter for its category: nutrition vs label, heavy metals, aflatoxins, pesticides, protein spiking.</p></div>
		</li>
		<li>
			<b>2</b>
			<div><h2>Fund</h2><p>Anyone can chip in to a test's pool on-chain. Anyone can also take the job by staking $110, which is returned when they submit the lab report. Miss the one-month deadline and the stake is lost and the job reopens.</p></div>
		</li>
		<li>
			<b>3</b>
			<div><h2>Test and publish</h2><p>The full lab report goes up on the product's page. The buyer's personal details on the report stay private; only the findings are published.</p></div>
		</li>
	</ol>

	<section>
		<h2>Reading a label card</h2>
		<p>The front of every card is the pack: photo, ingredients and the nutrition table it prints. Peel it to see what the tests found.</p>
		<ul>
			<li><strong>Off label</strong> means a lab value is more than 10% away from what the pack states, in the direction that's worse for you (more sugar, sodium or fat; less protein or fibre).</li>
			<li><strong>Better than label</strong> means it's more than 10% away in your favour.</li>
			<li>Notes on the ingredients are numbers from the lab report, never opinions.</li>
		</ul>
	</section>

	<section>
		<h2>Grades</h2>
		<p>For products already tested by Trustified, Unbox Health or Consumer Voice, we show their grade and link back to them. Our own grading for OpenLabel tests is still being built, so those show “grade pending”.</p>
	</section>

	<section>
		<h2>Published data, with credit</h2>
		<p>Until we test a product ourselves, we show results other testing websites have published, clearly labelled with the source. We haven't verified that data independently.</p>
	</section>

	<section>
		<h2>Buying</h2>
		<p>Buy links go to Amazon. We may earn a commission; it never changes a grade or a result.</p>
	</section>

	<p><a class="btn" href="/request">Request a test</a></p>
</div>

<style>
	.narrow { max-width: 760px; }
	h1 { margin: 6px 0 0; font-size: clamp(32px, 5vw, 48px); font-weight: 750; }
	h2 { font-size: 21px; margin: 0 0 6px; display: flex; align-items: center; gap: 10px; }
	section { margin-top: 40px; }
	section ul { padding-left: 20px; }
	section li { margin: 6px 0; }
	.steps { list-style: none; padding: 0; margin: 36px 0 0; display: grid; gap: 14px; }
	.steps li { display: flex; gap: 16px; padding: 18px; background: var(--cream); border-radius: 6px; }
	.steps b { flex: 0 0 auto; display: inline-flex; width: 34px; height: 34px; align-items: center; justify-content: center; border-radius: var(--r); background: var(--green); color: var(--gold); }
	.steps p { margin: 0; }
	.narrow > p:last-child { margin-top: 40px; }
</style>
