import { memo, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router';
import { api, type WallItem } from '@/lib/api';
import { LabelCard, type Theme } from '@/components/LabelCard';
import { SiteHeader } from '@/components/Layout';
import './Home.css';

const W = 600;
const H = 380;
const GAP = 32;
const DRIFT = 0.3; // px per frame
const STEER = 1.1; // extra px per frame at the screen edge
const PEELED_SLOW = 0.2;
const CLICK_SLOP = 6; // a drag longer than this does not peel

const Card = memo(LabelCard);
const even = (n: number) => n + (n % 2);
const wrap = (v: number, size: number) => ((((v + size / 2) % size) + size) % size) - size / 2;

export default function Home() {
	const [items, setItems] = useState<WallItem[]>([]);
	const [error, setError] = useState('');
	const [peeled, setPeeled] = useState<Record<number, boolean>>({});
	const [view, setView] = useState({ w: 1440, h: 900 });
	const [dragging, setDragging] = useState(false);

	const scale = Math.min(1, view.w / 760);
	// Enough even rows/columns to cover the screen, so the checkerboard survives wrapping.
	const cols = Math.max(4, even(Math.ceil(view.w / scale / (W + GAP)) + 1));
	const rows = Math.max(4, even(Math.ceil(view.h / scale / (H + GAP)) + 1));

	const tiles = useMemo(() => {
		if (!items.length) return [];
		const out: { id: number; r: number; c: number; item: WallItem; theme: Theme }[] = [];
		for (let r = 0; r < rows; r++)
			for (let c = 0; c < cols; c++)
				out.push({ id: r * cols + c, r, c, item: items[(r * cols + c) % items.length], theme: (r + c) % 2 === 0 ? 'light' : 'dark' });
		return out;
	}, [items, cols, rows]);

	// Motion lives in refs; the frame loop writes transforms straight to the tiles.
	const m = useRef({ ox: 0, oy: 0, vx: 0, vy: 0, ang: -2.7, target: -2.7, nextTurn: 0, mx: null as number | null, my: null as number | null, dist: 0, dragging: false, start: { x: 0, y: 0, ox: 0, oy: 0 } });
	const tileEls = useRef(new Map<number, HTMLElement>());
	const layout = useRef({ tiles, cols, rows, scale, anyPeeled: false });
	layout.current = { tiles, cols, rows, scale, anyPeeled: Object.values(peeled).some(Boolean) };

	useEffect(() => {
		api<{ items: WallItem[] }>('/api/wall?limit=36')
			.then((d) => setItems(d.items))
			.catch((e: Error) => setError(e.message));
		const size = () => setView({ w: window.innerWidth, h: window.innerHeight });
		size();
		window.addEventListener('resize', size);
		const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
		const s = m.current;
		s.nextTurn = performance.now() + 6000;
		let last = performance.now();
		let frame = requestAnimationFrame(function tick(now) {
			const k = Math.min(3, (now - last) / (1000 / 60));
			last = now;
			const L = layout.current;
			if (!still && !s.dragging && !document.hidden) {
				if (now > s.nextTurn) {
					s.target = s.ang + (Math.random() < 0.5 ? -1 : 1) * (0.7 + Math.random() * 1.4);
					s.nextTurn = now + 5000 + Math.random() * 4000;
				}
				s.ang += (s.target - s.ang) * 0.012 * k;
				const slow = L.anyPeeled ? PEELED_SLOW : 1;
				let tx = Math.cos(s.ang) * DRIFT * slow;
				let ty = Math.sin(s.ang) * DRIFT * slow;
				if (s.mx !== null && s.my !== null) {
					tx += -s.mx * STEER * slow;
					ty += -s.my * STEER * slow;
				}
				s.vx += (tx - s.vx) * 0.03 * k;
				s.vy += (ty - s.vy) * 0.03 * k;
				s.ox += s.vx * k;
				s.oy += s.vy * k;
			}
			const TW = L.cols * (W + GAP);
			const TH = L.rows * (H + GAP);
			for (const t of L.tiles) {
				const el = tileEls.current.get(t.id);
				if (!el) continue;
				const x = wrap(t.c * (W + GAP) + s.ox, TW);
				const y = wrap(t.r * (H + GAP) + s.oy, TH);
				el.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0)`;
			}
			frame = requestAnimationFrame(tick);
		});
		return () => {
			cancelAnimationFrame(frame);
			window.removeEventListener('resize', size);
		};
	}, []);

	const down = (x: number, y: number) => {
		const s = m.current;
		s.dist = 0;
		s.start = { x, y, ox: s.ox, oy: s.oy };
		s.dragging = true;
		setDragging(true);
	};
	const move = (x: number, y: number) => {
		const s = m.current;
		if (!s.dragging) return;
		s.dist = Math.max(s.dist, Math.abs(x - s.start.x) + Math.abs(y - s.start.y));
		s.ox = s.start.ox + (x - s.start.x) / scale;
		s.oy = s.start.oy + (y - s.start.y) / scale;
	};
	const up = () => {
		const s = m.current;
		if (!s.dragging) return;
		s.dragging = false;
		s.vx = 0;
		s.vy = 0;
		setDragging(false);
	};

	return (
		<div className="home">
			<title>OpenLabel · every label, checked</title>
			<h1 className="sr-only">OpenLabel: every product's label, checked</h1>
			<div
				className={`wall${dragging ? ' dragging' : ''}`}
				aria-label="Wall of products. Move the cursor or drag to explore. Peel a label to see what the tests found."
				onMouseDown={(e) => down(e.clientX, e.clientY)}
				onMouseMove={(e) => {
					m.current.mx = (e.clientX / view.w - 0.5) * 2;
					m.current.my = (e.clientY / view.h - 0.5) * 2;
					move(e.clientX, e.clientY);
				}}
				onMouseUp={up}
				onMouseLeave={() => {
					m.current.mx = m.current.my = null;
					up();
				}}
				onWheel={(e) => {
					m.current.ox -= e.deltaX / scale;
					m.current.oy -= e.deltaY / scale;
				}}
				onTouchStart={(e) => down(e.touches[0].clientX, e.touches[0].clientY)}
				onTouchMove={(e) => move(e.touches[0].clientX, e.touches[0].clientY)}
				onTouchEnd={up}
			>
				<div className="plane" style={{ transform: `scale(${scale})` }}>
					{tiles.map((t) => (
						<article
							key={t.id}
							className="tile"
							aria-label={t.item.name}
							ref={(el) => {
								if (el) tileEls.current.set(t.id, el);
								else tileEls.current.delete(t.id);
							}}
							style={{ zIndex: peeled[t.id] ? 2 : 1 }}
						>
							<Card
								item={t.item}
								theme={t.theme}
								peeled={!!peeled[t.id]}
								onPeel={() => m.current.dist < CLICK_SLOP && setPeeled((p) => ({ ...p, [t.id]: true }))}
								onUnpeel={() => setPeeled((p) => ({ ...p, [t.id]: false }))}
							/>
						</article>
					))}
				</div>
				{error && <p className="wall-error">Couldn't load products ({error}).</p>}
			</div>
			<SiteHeader overlay />
			<div className="ctas">
				<Link className="btn cta cta-main" to="/products">
					Find better food
					<svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10h11M11 5.5l4.5 4.5-4.5 4.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
				</Link>
				<Link className="cta-glass" to="/request">Request a test</Link>
				<Link className="cta-glass" to="/tests">Fund a test</Link>
			</div>
		</div>
	);
}
