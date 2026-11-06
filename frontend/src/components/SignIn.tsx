import { useRef, useState, type FormEvent } from 'react';
import {
	allowPrivateKey, connectInjected, connectPrivateKey, connectWalletConnect, disconnect,
	hasWalletConnect, short, useInjected, useWallet
} from '@/lib/wallet';
import { useSocialLogin } from '@/lib/privy';

/** Sign in with Google or email (Privy embedded wallet), or with an existing wallet. */
export function SignIn() {
	const wallet = useWallet();
	const injected = useInjected();
	const social = useSocialLogin();
	const menu = useRef<HTMLDetailsElement>(null);
	const [key, setKey] = useState('');
	const [error, setError] = useState('');

	async function run(fn: () => unknown) {
		setError('');
		try {
			await fn();
			if (menu.current) menu.current.open = false;
		} catch (e) {
			setError(e instanceof Error ? e.message.split('\n')[0] : String(e));
		}
	}

	if (wallet.address) {
		return (
			<div className="signin">
				<span className="addr" title={wallet.address}>{short(wallet.address)}</span>
				<button type="button" className="btn sm out" onClick={() => (social.authenticated ? social.logout() : disconnect())}>Sign out</button>
			</div>
		);
	}
	if (social.authenticated) {
		return (
			<div className="signin">
				<span className="addr">Setting up your wallet…</span>
				<button type="button" className="btn sm out" onClick={() => social.logout()}>Sign out</button>
			</div>
		);
	}

	return (
		<div className="signin">
			<details ref={menu}>
				<summary className="btn">Sign in</summary>
				<div className="signin-menu">
					{social.enabled && (
						<>
							<button type="button" className="btn" disabled={!social.ready} onClick={() => run(social.login)}>Continue with Google or email</button>
							<p className="head or">No crypto wallet needed. We create one for you.</p>
						</>
					)}
					<p className="head">{social.enabled ? 'Or use your own wallet' : 'Sign in with your wallet'}</p>
					{injected.length ? (
						injected.map((w) => (
							<button key={w.info.uuid} type="button" className="opt" onClick={() => run(() => connectInjected(w.provider))}>
								<img src={w.info.icon} alt="" width={18} height={18} /> {w.info.name}
							</button>
						))
					) : (
						<button type="button" className="opt" onClick={() => run(() => connectInjected())}>MetaMask / browser wallet</button>
					)}
					{hasWalletConnect && <button type="button" className="opt" onClick={() => run(connectWalletConnect)}>WalletConnect</button>}
					{allowPrivateKey && (
						<form onSubmit={(e: FormEvent) => { e.preventDefault(); run(() => connectPrivateKey(key.trim())); }}>
							<label className="field">
								<span>Private key (testing only)</span>
								<input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="0x…" autoComplete="off" />
							</label>
							<button type="submit" className="btn sm" disabled={!key.trim()}>Use private key</button>
						</form>
					)}
					{error && <p className="error small" style={{ margin: 0 }}>{error}</p>}
				</div>
			</details>
		</div>
	);
}
