import { useEffect, useState } from 'react';
import { type Address, type Hex } from 'viem';
import { fundAbi, fundAddress, publicClient, registryAbi, txUrl, usd } from '@/lib/wallet';

type Proven = {
	tx: Hex;
	payout: bigint;
	sessionTime: Date;
	host: string;
	kv: { key: string; value: string }[];
	rows: { group: string; parameter: string; unit: string; method: string; result: string }[];
};

/** A posted report: the values the tester's ZK proof committed to, read back from the chain. */
export function ProvenReport({ id, reportBlock }: { id: Hex; tester?: Address; reportBlock: bigint }) {
	const [p, setP] = useState<Proven | null>(null);
	const [error, setError] = useState('');

	useEffect(() => {
		(async () => {
			const [log] = await publicClient.getContractEvents({
				address: fundAddress!, abi: fundAbi, eventName: 'ReportSubmitted', args: { id }, fromBlock: reportBlock, toBlock: reportBlock
			});
			if (!log) throw new Error('report event not found');
			const registry = await publicClient.readContract({ address: fundAddress!, abi: fundAbi, functionName: 'registry' });
			const [h, , kv, rows] = await publicClient.readContract({ address: registry, abi: registryAbi, functionName: 'decode', args: [log.args.publicValues!] });
			setP({ tx: log.transactionHash, payout: log.args.payout!, sessionTime: new Date(Number(h.sessionTime) * 1000), host: h.serverName, kv: [...kv], rows: [...rows] });
		})().catch((e: Error) => setError(e.message.split('\n')[0]));
	}, [id, reportBlock]);

	const link = p && txUrl(p.tx);
	return (
		<section className="proven card" aria-labelledby="proven-h">
			<h2 id="proven-h" className="fund-title">Tested · lab report proven on-chain</h2>
			<p className="muted fund-lede">
				The tester posted a zero-knowledge proof that this report is the lab's own copy (fetched from <code>{p?.host ?? 'the lab'}</code> under TLSNotary).
				Customer details are redacted inside the proof; only the values below are public.
			</p>
			{error && <p className="error">Couldn't read the proven report: {error}</p>}
			{!p && !error && <p className="muted">Reading the proof from the chain…</p>}
			{p && (
				<>
					<p className="small muted">
						Tester paid {usd(p.payout)} · lab copy fetched {p.sessionTime.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
						{link && <> · <a href={link} target="_blank" rel="noopener">transaction</a></>}
					</p>
					{p.rows.length > 0 && (
						<div className="table-wrap">
							<table>
								<thead><tr><th>Parameter</th><th>Result</th><th>Unit</th><th>Method</th></tr></thead>
								<tbody>
									{p.rows.map((r, i) => (
										<tr key={i}><td>{r.parameter}</td><td><strong>{r.result}</strong></td><td>{r.unit}</td><td className="small muted">{r.method}</td></tr>
									))}
								</tbody>
							</table>
						</div>
					)}
					{p.kv.length > 0 && (
						<details>
							<summary>Report details ({p.kv.length})</summary>
							<dl className="fields">{p.kv.map((f, i) => <div key={i} style={{ display: 'contents' }}><dt>{f.key}</dt><dd>{f.value}</dd></div>)}</dl>
						</details>
					)}
				</>
			)}
		</section>
	);
}
