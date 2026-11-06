import { lazy, Suspense } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router';
import { Layout } from './components/Layout';
import Home from './pages/Home';

const Marketplace = lazy(() => import('./pages/Marketplace'));
const Product = lazy(() => import('./pages/Product'));
const Tests = lazy(() => import('./pages/Tests'));
const Request = lazy(() => import('./pages/Request'));
const RequestDetail = lazy(() => import('./pages/RequestDetail'));
const Sources = lazy(() => import('./pages/Sources'));
const About = lazy(() => import('./pages/About'));
const Prove = lazy(() => import('./pages/Prove'));
const NotFound = lazy(() => import('./pages/NotFound'));

export function App() {
	return (
		<BrowserRouter>
			<Suspense fallback={<p className="page muted">Loading…</p>}>
				<Routes>
					<Route element={<Layout />}>
						<Route index element={<Home />} />
						<Route path="products" element={<Marketplace />} />
						<Route path="products/:id" element={<Product />} />
						<Route path="tests" element={<Tests />} />
						<Route path="request" element={<Request />} />
						<Route path="requests/:id" element={<RequestDetail />} />
						<Route path="sources" element={<Sources />} />
						<Route path="about" element={<About />} />
						<Route path="prove" element={<Prove />} />
						<Route path="*" element={<NotFound />} />
					</Route>
				</Routes>
			</Suspense>
		</BrowserRouter>
	);
}
