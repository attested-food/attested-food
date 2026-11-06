const COLORS: Record<string, [string, string]> = {
	A: ['#1E7B45', '#FFFFFF'],
	B: ['#6BA539', '#141414'],
	C: ['#F2B705', '#141414'],
	D: ['#E8711C', '#141414'],
	E: ['#C8102E', '#FFFFFF']
};

/** Background and text colour for a grade as its source gives it: "A+", "86/100", "Pass", "Fail". */
export function gradeColors(grade: string | null): [string, string] | null {
	if (!grade) return null;
	const g = grade.trim().toUpperCase();
	const score = /^(\d+(?:\.\d+)?)\s*\/\s*(\d+)$/.exec(g);
	let letter = g[0];
	if (score) {
		const pct = (Number(score[1]) / Number(score[2])) * 100;
		letter = pct >= 80 ? 'A' : pct >= 60 ? 'B' : pct >= 40 ? 'C' : pct >= 20 ? 'D' : 'E';
	} else if (g === 'PASS') letter = 'A';
	else if (g === 'FAIL') letter = 'E';
	return COLORS[letter] ?? ['#141414', '#FFFFFF'];
}

/** A third party's grade for a published test (none for our own reports; those use the OpenLabel grade). */
export function sourceGrade(r: { kind: 'user' | 'fallback'; grade: string | null; verdict: string | null } | null | undefined) {
	if (!r || r.kind === 'user') return null;
	return r.grade ?? (r.verdict === 'pass' ? 'Pass' : r.verdict === 'fail' ? 'Fail' : null);
}

/** The grade a product card shows, and whose it is. */
export function cardGrade(p: { latest: { kind: 'user' | 'fallback'; grade: string | null; verdict: string | null; publisher?: unknown } | null; openlabel_grade?: { letter: string; provisional: boolean } | null }) {
	if (p.openlabel_grade) return { grade: p.openlabel_grade.letter, ours: true, provisional: p.openlabel_grade.provisional };
	const g = sourceGrade(p.latest);
	return g ? { grade: g, ours: false, provisional: false } : null;
}
