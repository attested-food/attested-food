import { Link } from 'react-router';

export default function About() {
	return (
		<div className="page narrow">
			<title>How it works · OpenLabel</title>
			<div className="page-head">
				<div>
					<div className="eyebrow">How it works</div>
					<h1 style={{ marginTop: 8 }}>Labels say one thing. Labs check.</h1>
					<p className="lede">OpenLabel lets people in India ask for packaged food to be lab tested, pay for those tests together, and see what the pack gets wrong.</p>
				</div>
			</div>
			<ol className="ab-steps">
				<li><b>1</b><div><h2>Request</h2><p>Paste an Amazon link or type in the product. We list the tests that matter for its category: nutrition vs label, heavy metals, aflatoxins, pesticides, protein spiking.</p></div></li>
				<li><b>2</b><div><h2>Fund</h2><p>Anyone can contribute toward the lab’s quote. Anyone can also be the tester by putting down a refundable stake and taking the product to an accredited (NABL) lab.</p></div></li>
				<li><b>3</b><div><h2>Test and publish</h2><p>The tester posts the full lab report before the deadline and gets the stake back. The buyer’s personal details on the report stay private; only the findings are published.</p></div></li>
			</ol>
			<section className="ab-sec">
				<h2 className="section-title">Reading the results</h2>
				<ul>
					<li><strong>Off label</strong> means a lab value is more than 10% away from what the pack states, in the direction that’s worse for you (more sugar, sodium or fat; less protein or fibre).</li>
					<li><strong>Better than label</strong> means it’s more than 10% away in your favour.</li>
					<li>Notes on the ingredients are numbers from the lab report, never opinions.</li>
				</ul>
			</section>
			<section className="ab-sec" id="grading">
				<h2 className="section-title">How we grade</h2>
				<p>Products tested through OpenLabel get an <strong>OpenLabel grade</strong> from A to E, built from three parts:</p>
				<ul>
					<li><strong>Label honesty (40%).</strong> How close the lab’s numbers are to what the pack says. Every nutrient more than 10% off, in the direction that’s worse for you, costs points; the further off, the more it costs.</li>
					<li><strong>Safety (40%).</strong> Heavy metals, aflatoxins, pesticides, microbes and adulterants against their limits. Any failure scores zero and caps the grade at D.</li>
					<li><strong>Nutrition (20%).</strong> A Nutri-Score style score from the lab’s values: sugar, saturated fat, sodium and energy count against; fibre and protein count for.</li>
				</ul>
				<p>If a part wasn’t tested, the grade is worked out from the parts that were. Until all of a category’s standard tests are done, the grade is marked <strong>provisional</strong>.</p>
				<p>Products tested by Trustified, Unbox Health or Consumer Voice are tagged <span className="tag tested">3rd-party tested</span> and show <strong>their</strong> grade, named and linked back to them. We don’t change or re-grade their results.</p>
			</section>
			<section className="ab-sec">
				<h2 className="section-title">Published tests, with credit</h2>
				<p>Until a product is tested through OpenLabel, we show results other testing websites have published, clearly labelled with the source. We haven’t verified that data independently.</p>
			</section>
			<section className="ab-sec">
				<h2 className="section-title">Buying</h2>
				<p>Buy links go to Amazon. We may earn a commission; it never changes a grade or a result.</p>
			</section>
			<p style={{ marginTop: 40 }}><Link className="btn lg" to="/request">Request a test</Link></p>
		</div>
	);
}
