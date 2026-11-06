import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { Link } from 'react-router';
import { buyUrl, imgFallback, imgSrc, label, nutritionRows, productName, type Finding, type WallItem } from '@/lib/api';
import { Segments } from './Segments';
import { GradeChip, ResultCounts, ResultIcon, StateTag } from './bits';
import { S_DONE, S_REST, ease, peelShape, toClipPath, toPoints } from './peel';
import './LabelCard.css';

export type Theme = 'light' | 'dark';

const THEMES = {
	light: { bg: '#FBF9F4', fg: '#13261C', sub: '#5E6B63', line: '#E7E2D6', frame: '#E6E0D0', red: '#B3261E', good: '#2F6B4A', blue: '#2846C8', goldInk: '#8C6A32', noteUnder: '#E8ECFF', noteCircle: '#FDECEC', noteHl: '#FFF4CC', noteHlFg: '#7A5A00', noteGood: '#EAF3E2' },
	dark: { bg: '#141414', fg: '#F4F1EA', sub: '#A9AEB4', line: '#2C2E31', frame: '#2A2C2E', red: '#FF7B72', good: '#9FD3B0', blue: '#A8B8FF', goldInk: '#C6A26B', noteUnder: '#2A3147', noteCircle: '#3A2224', noteHl: '#3A3420', noteHlFg: '#FFE27A', noteGood: '#26331E' }
} as const;

function themeVars(theme: Theme): CSSProperties {
	const t = THEMES[theme];
	return {
		'--bg': t.bg, '--fg': t.fg, '--sub': t.sub, '--line': t.line, '--frame': t.frame, '--red': t.red, '--good': t.good,
		'--blue': t.blue, '--gold-ink': t.goldInk, '--note-under-bg': t.noteUnder, '--note-circle-bg': t.noteCircle,
		'--note-hl-bg': t.noteHl, '--note-hl-fg': t.noteHlFg, '--note-good-bg': t.noteGood
	} as CSSProperties;
}

const ORDER = { bad: 0, good: 1, info: 2 } as const;
const PEEL_MS = 1050;
const CURL_PATH = 'M100 37.8 C97 42 94 44.5 88 45.5 C76 47 62 49 55 50.5 Q51.5 51.5 51.6 55 C52 66 51.5 80 47 89 C43 95 38 98.5 33.8 100 Z';
type Phase = 'rest' | 'moving' | 'off';
const stop = (e: { stopPropagation: () => void }) => e.stopPropagation();
const month = (d: string | null) => (d ? new Date(d).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' }) : null);

/** 600×380 label: the pack on the front, what the lab found on the back. Click to peel. */
export function LabelCard({ item, theme, peeled, onPeel, onUnpeel }: { item: WallItem; theme: Theme; peeled: boolean; onPeel: () => void; onUnpeel: () => void }) {
	const back: Theme = theme === 'light' ? 'dark' : 'light';
	const name = productName(item);
	const nut = nutritionRows(item.label_nutrition, 6);
	const a = item.annotations;
	const isRequest = item.kind === 'request';
	const findings: Finding[] = [...(a?.findings ?? [])].sort((x, y) => ORDER[x.kind] - ORDER[y.kind]);
	const rows = findings.length
		? findings.slice(0, 3).map((x) => ({ kind: x.kind as string, t: x.parameter, r: x.text }))
		: [{ kind: 'unk', t: 'Lab test', r: isRequest ? 'Requested, not funded yet' : 'Results not on file' }];
	const gradeLabel = isRequest
		? 'Not tested yet'
		: item.openlabel_grade
			? item.openlabel_grade.provisional ? 'OpenLabel grade · provisional' : 'OpenLabel grade'
			: item.grade && item.grade_source
				? `3rd-party grade · ${item.grade_source}`
				: item.report_kind === 'user'
					? 'Tested through OpenLabel'
					: `Tested for ${item.grade_source ?? item.lab ?? 'a testing website'}`;
	const source = isRequest
		? 'From the label · requested for testing'
		: [item.lab, item.report_kind === 'fallback' && item.grade_source && item.grade_source !== item.lab ? `via ${item.grade_source}` : null, month(item.tested_on)].filter(Boolean).join(' · ');
	const gid = `curl-${item.kind}-${item.id}`;

	// Peel: a fold line sweeps across the label; frame-by-frame updates go straight to the DOM.
	const [phase, setPhase] = useState<Phase>(peeled ? 'off' : 'rest');
	const front = useRef<HTMLDivElement>(null);
	const flap = useRef<SVGPolygonElement>(null);
	const shade = useRef<SVGLinearGradientElement>(null);
	const at = useRef(peeled ? S_DONE : S_REST);
	useEffect(() => {
		const from = at.current;
		const to = peeled ? S_DONE : S_REST;
		if (from === to) return;
		const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
		let frame = 0;
		const start = performance.now();
		const draw = (s: number) => {
			const g = peelShape(s);
			if (front.current) front.current.style.clipPath = toClipPath(g.front);
			flap.current?.setAttribute('points', toPoints(g.flap));
			if (shade.current) {
				shade.current.setAttribute('x1', String(g.foldPt[0]));
				shade.current.setAttribute('y1', String(g.foldPt[1]));
				shade.current.setAttribute('x2', String(g.tipPt[0]));
				shade.current.setAttribute('y2', String(g.tipPt[1]));
			}
		};
		const finish = () => {
			at.current = to;
			if (front.current) front.current.style.clipPath = '';
			setPhase(peeled ? 'off' : 'rest');
		};
		if (still) {
			finish();
			return;
		}
		setPhase('moving');
		draw(from);
		const tick = (now: number) => {
			const t = Math.min(1, (now - start) / PEEL_MS);
			const s = from + (to - from) * ease(t);
			at.current = s;
			draw(s);
			if (t < 1) frame = requestAnimationFrame(tick);
			else finish();
		};
		frame = requestAnimationFrame(tick);
		return () => cancelAnimationFrame(frame);
	}, [peeled]);

	return (
		<div className="lc" style={themeVars(theme)}>
			<section className="lc-back" style={themeVars(back)} aria-label={`What the tests found for ${name}`} inert={!peeled}>
				<div className={`lc-back-in${phase !== 'rest' ? ' show' : ''}`}>
					<div className="lc-head">
						<GradeChip grade={item.grade} size={54} />
						<div className="lc-head-text">
							<div className="lc-eyebrow">{gradeLabel}</div>
							<div className="lc-counts">
								{isRequest || !a ? <span className="sub">Not tested yet</span> : <ResultCounts counts={a.counts} size="sm" />}
							</div>
						</div>
					</div>
					{item.ingredients && (
						<p className="lc-ing">
							<span className="sub">{'Ingredients: '}</span>
							{a?.segments.length ? <Segments segments={a.segments} compact /> : item.ingredients}
						</p>
					)}
					<ul className="lc-rows">
						{rows.map((x, i) => (
							<li key={i}>
								<ResultIcon kind={x.kind as 'good' | 'bad' | 'info' | 'unk'} size={18} />
								<span className="lc-rt">{x.t}</span>
								<span className={`lc-rr ${x.kind}`} title={x.r}>{x.r}</span>
							</li>
						))}
					</ul>
					<div className="lc-foot">
						<span className="lc-src">{source}</span>
						{isRequest ? (
							<Link className="btn sm" to={`/requests/${item.id}`} onMouseDown={stop}>Fund this test</Link>
						) : (
							<Link className="btn sm" to={`/products/${item.id}`} onMouseDown={stop}>Read report</Link>
						)}
						<a className="btn sm lc-buy" href={buyUrl(item)} target="_blank" rel="sponsored noopener" onMouseDown={stop}>Buy</a>
					</div>
				</div>
				{phase === 'off' && (
					<button type="button" className="lc-stick" onClick={onUnpeel} onMouseDown={stop} aria-label="Stick the label back" title="Stick the label back" style={themeVars(theme)}>
						<svg aria-hidden="true" width="72" height="72" viewBox="0 0 100 100">
							<defs>
								<linearGradient id={`${gid}-s`} gradientUnits="userSpaceOnUse" x1="40" y1="40" x2="80" y2="80">
									<stop offset="0" stopColor="var(--bg)" />
									<stop offset="1" stopColor="var(--line)" />
								</linearGradient>
							</defs>
							<path d={CURL_PATH} fill={`url(#${gid}-s)`} />
						</svg>
						<span>Stick back</span>
					</button>
				)}
			</section>

			<div ref={front} className={`lc-front lc-${phase}`} onClick={() => phase === 'rest' && onPeel()} inert={phase !== 'rest'}>
				<div className="lc-sheet">
					<div className="lc-photo">
						<img src={imgSrc(item.image_url)} alt={`${name} pack`} draggable={false} loading="lazy" referrerPolicy="no-referrer" onError={imgFallback} />
					</div>
					<div className="lc-info">
						<div className="lc-top">
							<span className="lc-eyebrow">{label(item.category)}</span>
							<StateTag state={item.state} />
						</div>
						<div className="lc-brand">{item.brand}</div>
						<div className="lc-name">{name}</div>
						<p className="lc-ing-front">
							<span className="sub">{'Ingredients: '}</span>
							{item.ingredients ?? 'Not on file yet.'}
						</p>
						<div className="lc-nut">
							<div className="lc-nut-head"><span>Nutrition</span><span className="sub">per 100 g</span></div>
							{nut.length ? (
								<div className="lc-nut-grid">
									{nut.map((n) => (
										<div key={n.key} className="lc-nut-row"><span>{n.name}</span><strong>{n.value}</strong></div>
									))}
								</div>
							) : (
								<div className="lc-nut-none sub">Label values not on file yet</div>
							)}
						</div>
					</div>
				</div>
				<button type="button" className="lc-peel" onMouseDown={stop} aria-label={`Peel the label to see what the tests found for ${name}`}>
					<svg aria-hidden="true" width="96" height="96" viewBox="0 0 100 100">
						<defs>
							<linearGradient id={gid} gradientUnits="userSpaceOnUse" x1="52" y1="52" x2="72" y2="72">
								<stop offset="0" stopColor="#EDEDED" />
								<stop offset="0.3" stopColor="#FFFFFF" />
								<stop offset="0.55" stopColor="#F3F3F3" />
								<stop offset="0.82" stopColor="#D4D4D4" />
								<stop offset="1" stopColor="#BDBDBD" />
							</linearGradient>
						</defs>
						<path d={CURL_PATH} fill={`url(#${gid})`} />
					</svg>
				</button>
			</div>

			<svg className={`lc-flap${phase === 'moving' ? ' on' : ''}`} aria-hidden="true" width="600" height="380" viewBox="0 0 600 380">
				<defs>
					<linearGradient ref={shade} id={`${gid}-f`} gradientUnits="userSpaceOnUse">
						<stop offset="0" stopColor="#FFFFFF" />
						<stop offset="0.35" stopColor="#F1F1EF" />
						<stop offset="1" stopColor="#CFCFCB" />
					</linearGradient>
				</defs>
				<polygon ref={flap} points="" fill={`url(#${gid}-f)`} />
			</svg>
		</div>
	);
}
