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

/** The grade a product shows: the source's own grade for published tests; none for our own reports yet. */
export function sourceGrade(r: { kind: 'user' | 'fallback'; grade: string | null; verdict: string | null } | null | undefined) {
	if (!r || r.kind === 'user') return null;
	return r.grade ?? (r.verdict === 'pass' ? 'Pass' : r.verdict === 'fail' ? 'Fail' : null);
}
