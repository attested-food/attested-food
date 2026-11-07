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
					<li><strong>Off label</strong> means a lab value is further from the pack’s number than the official label tolerance allows, in the direction that’s worse for you (more energy, sugar, fat, saturated fat or sodium; less protein or fibre).</li>
					<li><strong>Within tolerance</strong> means it’s inside that allowance. <strong>Better than label</strong> means it’s past it in your favour.</li>
					<li>Notes on the ingredients are numbers from the lab report, never opinions.</li>
				</ul>
			</section>
			<section className="ab-sec" id="grading">
				<h2 className="section-title">How we grade</h2>
				<p>Products tested through OpenLabel get an <strong>OpenLabel grade</strong> from A to E. It’s our own score, but each part follows a published standard:</p>
				<ul>
					<li><strong>Label honesty (40%).</strong> Each nutrient is checked against the official label tolerances in the European Commission’s 2012 guidance (for example ±2 g of protein or sugar under 10 g, ±20% from 10 to 40 g; ±150 mg of sodium under 500 mg). Energy uses the US FDA rule of no more than 120% of the label, and supplements use FSSAI’s rule of no more than 10% below the declared amount. Inside the tolerance costs nothing; past it costs more the further off it is.</li>
					<li><strong>Safety (40%).</strong> Failed results are sorted by how serious they are, following US FDA recall classes, the EU food alert system and India’s FSS Act (“unsafe” versus “sub-standard”). A critical hazard (such as Salmonella, melamine, a banned dye, or a heavy metal or aflatoxin five times over its limit) makes the grade E. A result over a safety limit (a heavy metal, aflatoxin, pesticide or hygiene bacteria) means the grade can’t be better than D. A quality miss (moisture, ash, acid value, yeast and mould) costs points.</li>
					<li><strong>Nutrition (20%).</strong> The updated Nutri-Score (2022 for foods, 2023 for drinks), with its separate rules for drinks, for oils, fats and nuts, and for cheese and paneer. We don’t know the fruit and vegetable share, so that part counts zero. Supplements, protein powders, infant formula, salt, spices and plain tea or coffee aren’t given a nutrition score.</li>
				</ul>
				<p>The weights and the letter cut-offs (A from 85, B from 70, C from 55, D from 40) are OpenLabel’s choices. If a part wasn’t tested, the grade is worked out from the parts that were. Until all of a category’s standard tests are done, the grade is <strong>provisional</strong>.</p>
				<p>India hasn’t adopted a front-of-pack rating yet: FSSAI’s 2022 draft star rating was never finalised. We’ll follow it when it is.</p>
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
