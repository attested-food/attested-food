import { Link, NavLink, Outlet, useLocation } from 'react-router';
import { Logo } from './bits';
import { SignIn } from './SignIn';

export function SiteHeader({ overlay = false }: { overlay?: boolean }) {
	const links = overlay
		? [['/products', 'Browse Products'], ['/about', 'How it works']]
		: [['/products', 'Browse Products'], ['/tests', 'Tests'], ['/about', 'How it works']];
	return (
		<header className={`site-header${overlay ? ' overlay' : ''}`}>
			<div className="inner">
				<Link className="logo" to="/" aria-label="OpenLabel home"><Logo /></Link>
				<nav className="site-nav" aria-label="Main">
					{links.map(([to, text]) => (
						<NavLink key={to} to={to}>{text}</NavLink>
					))}
				</nav>
				<SignIn />
			</div>
		</header>
	);
}

export function SiteFooter() {
	return (
		<footer className="site-footer">
			<div className="inner">
				<span>OpenLabel · crowd-requested, crowd-funded lab tests of packaged food in India</span>
				<nav aria-label="Footer">
					<Link to="/sources">Sources</Link>
					<Link to="/about">About</Link>
				</nav>
				<span>Ingredients and label nutrition partly from <a href="https://world.openfoodfacts.org" rel="noopener">Open Food Facts</a> (CC BY-SA)</span>
			</div>
		</footer>
	);
}

/** Inner pages get the dark header band and footer; Home draws its own overlay header. */
export function Layout() {
	const { pathname } = useLocation();
	if (pathname === '/') return <Outlet />;
	return (
		<>
			<SiteHeader />
			<main><Outlet /></main>
			<SiteFooter />
		</>
	);
}
