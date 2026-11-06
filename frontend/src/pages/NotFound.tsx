import { Link } from 'react-router';

export default function NotFound() {
	return (
		<div className="page narrow">
			<title>Not found · OpenLabel</title>
			<h1 className="section-title">Page not found</h1>
			<p className="muted">That page doesn't exist. <Link className="link" to="/products">Browse products</Link>.</p>
		</div>
	);
}
