import { httpUrl, type Source } from '@/lib/api';
import { useApi } from '@/lib/useApi';

const GROUPS = [
	['lab', 'Labs', 'Accredited labs that ran the tests.'],
	['website', 'Published tests', 'Testing websites whose results we show, with credit and a link back, until a product is tested through OpenLabel.']
] as const;

export default function Sources() {
	const { data, error, loading } = useApi<Source[]>('/api/sources');
	return (
		<div className="page narrow">
			<title>Sources · OpenLabel</title>
			<div className="page-head"><div><h1>Sources</h1><p className="lede">Where every number on OpenLabel comes from.</p></div></div>
			{loading && <p className="muted">Loading…</p>}
			{error && <p className="error">Couldn't load sources: {error}</p>}
			{data && GROUPS.map(([type, title, blurb]) => {
				const items = data.filter((s) => s.type === type);
				if (!items.length) return null;
				return (
					<section key={type} className="src-group">
						<h2 className="section-title">{title}</h2>
						<p className="muted">{blurb}</p>
						<ul className="src-list">
							{items.map((s) => (
								<li key={s.id}>
									<span className="src-name">
										{httpUrl(s.url) ? <a className="link" href={httpUrl(s.url)!} rel="noopener">{s.name}</a> : s.name}
										{s.accreditation && <span className="eyebrow"> · {s.accreditation}</span>}
									</span>
									<span className="eyebrow">{s.report_count} report{s.report_count === 1 ? '' : 's'}</span>
									{s.description && <p className="muted small">{s.description}</p>}
								</li>
							))}
						</ul>
					</section>
				);
			})}
			<section className="src-group">
				<h2 className="section-title">Ingredients and label nutrition</h2>
				<p className="muted">Where we haven't scanned a pack ourselves, ingredient lists and label nutrition come from <a className="link" href="https://world.openfoodfacts.org" rel="noopener">Open Food Facts</a>, a crowd-sourced food database, under CC BY-SA.</p>
			</section>
		</div>
	);
}
