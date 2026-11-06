<script lang="ts" module>
	/** Background and text colour for a grade as the source gives it: letters, "86/100", Pass/Fail. */
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
		const map: Record<string, [string, string]> = {
			A: ['#1E7B45', '#FFFFFF'],
			B: ['#6BA539', '#141414'],
			C: ['#F2B705', '#141414'],
			D: ['#E8711C', '#141414'],
			E: ['#C8102E', '#FFFFFF'],
			F: ['#C8102E', '#FFFFFF']
		};
		return map[letter] ?? ['#141414', '#FFFFFF'];
	}
</script>

<script lang="ts">
	let { grade, size = 54, empty = 'NO GRADE' }: { grade: string | null; size?: number; empty?: string } = $props();

	const colors = $derived(gradeColors(grade));
	const text = $derived(grade ?? empty);
	const font = $derived(!grade ? size * 0.17 : text.length <= 2 ? size * 0.56 : text.length <= 4 ? size * 0.34 : size * 0.26);
</script>

<div
	class="grade"
	class:none={!grade}
	style:width="{size}px"
	style:height="{size}px"
	style:font-size="{font}px"
	style:background={colors?.[0] ?? 'transparent'}
	style:color={colors?.[1] ?? 'var(--sub)'}
>
	{text}
</div>

<style>
	.grade {
		flex: 0 0 auto;
		border-radius: var(--r);
		display: flex;
		align-items: center;
		justify-content: center;
		text-align: center;
		font-weight: 700;
		letter-spacing: -0.02em;
		line-height: 1.05;
	}
	.none {
		border: 1px dashed currentColor;
		font-family: var(--mono);
		letter-spacing: 0.04em;
	}
</style>
