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

/** A grade as its source gives it. Renders nothing when there is no grade. */
export function GradeChip({ grade, size = 28 }: { grade: string | null; size?: number }) {
	const c = gradeColors(grade);
	if (!grade || !c) return null;
	const font = grade.length <= 2 ? size * 0.54 : size * 0.38;
	return (
		<span className="grade" style={{ minWidth: size, height: size, padding: '0 5px', fontSize: font, background: c[0], color: c[1] }}>
			{grade}
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
