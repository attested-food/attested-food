/**
 * PLACEHOLDER DATA, shown only when this deployment has no TestFund contract configured
 * (VITE_FUND_ADDRESS). Always rendered with a "Placeholder" tag so nobody mistakes it for real numbers.
 */
export type FundingPlaceholder = {
	productHint: string;
	tests: string;
	pct: number;
	raised: string;
	goal: string;
	backers: string;
	daysLeft: string;
	state: 'funding' | 'funded';
};

export const FUNDING: FundingPlaceholder[] = [
	{ productHint: 'Protein bar', tests: 'Protein vs label, sugars', pct: 31, raised: '₹[raised]', goal: '₹[goal]', backers: '[n] backers', daysLeft: '[n] days left', state: 'funding' },
	{ productHint: 'Malt health drink', tests: 'Heavy metals, sugars', pct: 68, raised: '₹[raised]', goal: '₹[goal]', backers: '[n] backers', daysLeft: '[n] days left', state: 'funding' },
	{ productHint: 'Whey protein', tests: 'Protein, amino spiking, heavy metals', pct: 12, raised: '₹[raised]', goal: '₹[goal]', backers: '[n] backers', daysLeft: '[n] days left', state: 'funding' },
	{ productHint: 'Peanut butter', tests: 'Aflatoxins', pct: 100, raised: '₹[raised]', goal: '₹[goal]', backers: '[n] backers', daysLeft: 'At the lab', state: 'funded' },
	{ productHint: 'Desi ghee', tests: 'Adulteration (vegetable fat)', pct: 100, raised: '₹[raised]', goal: '₹[goal]', backers: '[n] backers', daysLeft: 'At the lab', state: 'funded' }
];
