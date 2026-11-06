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

/** A grade as its source gives it ("A+", "82/100", "Pass"), on one line; the box widens to fit. */
export function GradeChip({ grade, size = 28 }: { grade: string | null; size?: number }) {
	const c = gradeColors(grade);
	if (!grade || !c) return null;
	const text = grade.replace(/\s+/g, '');
	const font = text.length <= 2 ? size * 0.54 : Math.max(11, size * 0.4);
	return (
		<span className="grade" style={{ minWidth: size, height: size, padding: `0 ${Math.round(size * 0.2)}px`, fontSize: font, background: c[0], color: c[1] }} title={grade}>
			{text}
		</span>
	);
}

/** Whose grade it is: OpenLabel's own (filled) or a third party's (outlined). */
export function GradeTag({ ours, provisional = false }: { ours: boolean; provisional?: boolean }) {
	return (
		<span className={`gtag ${ours ? 'ours' : 'third'}`} title={ours ? 'Graded by OpenLabel from our own lab test' : 'Grade from a third-party testing website'}>
			{ours ? (provisional ? 'OpenLabel · provisional' : 'OpenLabel') : '3rd-party'}
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

/**
 * OpenLabel mark: a white label with its top-right corner folded, carrying a green "O" and a
 * flipped tick that reads as "L" (OL).
 */
export function LogoMark({ size = 32, outline = false }: { size?: number; outline?: boolean }) {
	return (
		<svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" className="logo-mark">
			<path d="M4 2h32a2 2 0 0 1 2 2v25l-9 9H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#FFFFFF" stroke={outline ? '#1D4A37' : 'none'} strokeWidth={outline ? 1.4 : 0} />
			<path d="M38 29h-7a2 2 0 0 0-2 2v7z" fill="#D9D6CC" />
			<path d="M31 29a2 2 0 0 0-2 2v7" fill="none" stroke="rgba(0,0,0,0.14)" strokeWidth="0.8" />
			<circle cx="12.4" cy="19.6" r="6.3" fill="none" stroke="#1D4A37" strokeWidth="3.4" />
			<path d="M21.4 11.6l6 14.2 7-7" fill="none" stroke="#1D4A37" strokeWidth="3.4" strokeLinecap="square" strokeLinejoin="miter" />
		</svg>
	);
}

export function Logo({ outline = false }: { outline?: boolean }) {
	return (
		<>
			<LogoMark outline={outline} />
			<span>OpenLabel</span>
		</>
	);
}
