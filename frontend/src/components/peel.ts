/**
 * Sticker-peel geometry for a W×H label peeled from its bottom-right corner.
 *
 * A fold line sweeps from the corner towards the top-left. Everything past the line has been
 * lifted: the front is clipped to the part before the line, and the lifted part is drawn as the
 * flap, i.e. that region mirrored across the fold line (the label's underside, folded back).
 */
export type Pt = [number, number];

export const W = 600;
export const H = 380;
const LEN = Math.hypot(W, H);
/** Peel direction: from the top-left towards the bottom-right corner. */
const U: Pt = [W / LEN, H / LEN];
const RECT: Pt[] = [[0, 0], [W, 0], [W, H], [0, H]];

/** Fold position at rest: a small lifted corner, about the size of the drawn curl. */
export const S_REST = LEN - 58;
/** Fold position once the whole label is off (just past the top-left corner). */
export const S_DONE = -40;

const along = (p: Pt) => p[0] * U[0] + p[1] * U[1];

/** Part of a convex polygon where side(p) <= 0 (Sutherland–Hodgman against one line). */
function keep(poly: Pt[], side: (p: Pt) => number): Pt[] {
	const out: Pt[] = [];
	for (let i = 0; i < poly.length; i++) {
		const a = poly[i];
		const b = poly[(i + 1) % poly.length];
		const sa = side(a);
		const sb = side(b);
		if (sa <= 0) out.push(a);
		if ((sa < 0 && sb > 0) || (sa > 0 && sb < 0)) {
			const t = sa / (sa - sb);
			out.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]);
		}
	}
	return out;
}

/** Front (still stuck down) and flap (lifted, mirrored) polygons for fold position s. */
export function peelShape(s: number) {
	const side = (p: Pt) => along(p) - s;
	const front = keep(RECT, side);
	const lifted = keep(RECT, (p) => -side(p));
	const flap = lifted.map((p): Pt => {
		const d = side(p);
		return [p[0] - 2 * d * U[0], p[1] - 2 * d * U[1]];
	});
	// Gradient across the flap: bright at the fold, darker towards the tip.
	const depth = Math.max(1, Math.max(0, ...lifted.map(side)));
	const foldPt: Pt = [s * U[0], s * U[1]];
	const tipPt: Pt = [foldPt[0] - depth * U[0], foldPt[1] - depth * U[1]];
	return { front, flap, foldPt, tipPt };
}

export const toClipPath = (poly: Pt[]) =>
	poly.length >= 3 ? `polygon(${poly.map(([x, y]) => `${x.toFixed(1)}px ${y.toFixed(1)}px`).join(', ')})` : 'polygon(0 0, 0 0, 0 0)';

export const toPoints = (poly: Pt[]) => poly.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');

/** Smooth start and finish; the peel speeds up in the middle like a hand pulling it. */
export const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
