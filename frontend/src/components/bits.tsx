import type { CSSProperties } from 'react';
import { imgFallback, imgSrc } from '@/lib/api';
import { gradeColors } from '@/lib/grade';

export type TestState = 'requested' | 'funding' | 'funded' | 'tested';

export function StateTag({ state, text, style }: { state: TestState; text?: string; style?: CSSProperties }) {
	return (
		<span className={`tag ${state}`} style={style}>
			{text ?? state[0].toUpperCase() + state.slice(1)}
		</span>
	);
}

/** Split "84/100" into a big score and a small "/100"; letters and Pass/Fail stay whole. */
export function splitGrade(grade: string) {
	const m = /^(\d+(?:\.\d+)?)\s*(\/\s*\d+)$/.exec(grade.trim());
	return m ? { main: m[1], sub: m[2].replace(/\s/g, '') } : { main: grade, sub: '' };
}

/** A grade as its source gives it. Renders nothing when there is no grade. */
export function GradeChip({ grade, size = 28 }: { grade: string | null; size?: number }) {
	const c = gradeColors(grade);
	if (!grade || !c) return null;
	const { main, sub } = splitGrade(grade);
	const font = main.length <= 2 ? size * 0.52 : main.length <= 4 ? size * 0.36 : size * 0.3;
	return (
		<span className="grade" style={{ minWidth: size, height: size, padding: `0 ${Math.round(size * 0.18)}px`, fontSize: font, background: c[0], color: c[1] }} title={grade}>
			{main}
			{sub && <small style={{ fontSize: Math.max(9, size * 0.22) }}>{sub}</small>}
		</span>
	);
}

type Kind = 'good' | 'bad' | 'info' | 'unk';

/** Result icon: filled check (pass), filled cross (fail), outlined dash (within limits), outlined question (not tested). */
export function ResultIcon({ kind, size = 18 }: { kind: Kind; size?: number }) {
	return (
		<svg className={`ri ri-${kind}`} width={size} height={size} viewBox="0 0 20 20" aria-hidden="true">
			{kind === 'good' && <><circle cx="10" cy="10" r="10" /><path d="M5.8 10.3l2.8 2.8 5.6-5.8" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></>}
			{kind === 'bad' && <><circle cx="10" cy="10" r="10" /><path d="M6.8 6.8l6.4 6.4M13.2 6.8l-6.4 6.4" fill="none" strokeWidth="2" strokeLinecap="round" /></>}
			{kind === 'info' && <><circle cx="10" cy="10" r="9" fill="none" strokeWidth="1.6" /><path d="M6.5 10h7" fill="none" strokeWidth="1.8" strokeLinecap="round" /></>}
			{kind === 'unk' && <><circle cx="10" cy="10" r="9" fill="none" strokeWidth="1.6" strokeDasharray="2.6 2.2" /><path d="M7.9 7.9a2.2 2.2 0 1 1 3.1 2c-.6.3-1 .8-1 1.5v.3" fill="none" strokeWidth="1.6" strokeLinecap="round" /><circle cx="10" cy="14.2" r="1" stroke="none" className="dot" /></>}
		</svg>
	);
}

/** "2 passed · 1 failed · 0 not tested" with icons. */
export function ResultCounts({ counts, size = 'md' }: { counts: { pass: number; fail: number; untested: number }; size?: 'sm' | 'md' | 'lg' }) {
	const px = size === 'lg' ? 20 : size === 'sm' ? 15 : 17;
	return (
		<span className={`rc rc-${size}`}>
			<span className="rc-item"><ResultIcon kind="good" size={px} /><b>{counts.pass}</b> passed</span>
			<span className="rc-item"><ResultIcon kind="bad" size={px} /><b>{counts.fail}</b> failed</span>
			<span className="rc-item rc-muted"><ResultIcon kind="unk" size={px} /><b>{counts.untested}</b> not tested</span>
		</span>
	);
}

/** Product photo in the shared 4:5 frame; falls back to the placeholder image. */
export function Photo({ src, alt, className = '', style }: { src: string | null | undefined; alt: string; className?: string; style?: CSSProperties }) {
	return (
		<span className={`photo ${className}`} style={style}>
			<img src={imgSrc(src)} alt={alt} loading="lazy" referrerPolicy="no-referrer" onError={imgFallback} />
		</span>
	);
}

export function Logo() {
	return (
		<>
			<svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true">
				<rect x="1" y="1" width="28" height="28" rx="3" fill="#1D4A37" />
				<path d="M8 15.5l4.5 4.5L22 10" fill="none" stroke="#C6A26B" strokeWidth="3.2" strokeLinecap="square" />
			</svg>
			<span>OpenLabel</span>
		</>
	);
}
