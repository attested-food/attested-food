import { useEffect, useRef, useState, type FormEvent } from 'react';
import {
	allowPrivateKey, connectInjected, connectPrivateKey, connectWalletConnect, disconnect,
	hasWalletConnect, short, useInjected, useWallet
} from '@/lib/wallet';
import { useSocialLogin } from '@/lib/privy';
import { Logo } from './bits';
import './SignIn.css';

function GoogleIcon() {
	return (
		<svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
			<path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.6 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34.1 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
			<path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34.1 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
			<path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.3 0-9.7-3.4-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
			<path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
		</svg>
	);
}

function MailIcon() {
	return (
		<svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
			<rect x="3" y="5" width="18" height="14" rx="2" />
			<path d="M3.5 6.5l8.5 6 8.5-6" />
		</svg>
	);
}

function WalletIcon() {
	return (
		<svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
			<path d="M4 7h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a1 1 0 0 1-1-1V7z" />
			<path d="M4 7l11-3v3" />
			<circle cx="16" cy="13.5" r="1.2" fill="currentColor" stroke="none" />
		</svg>
	);
}

/** Sign in: Google or email (Privy creates a wallet), or an existing wallet under "Or use your own wallet". */
export function SignIn() {
	const wallet = useWallet();
	const injected = useInjected();
	const social = useSocialLogin();
	const dialog = useRef<HTMLDialogElement>(null);
	const [key, setKey] = useState('');
	const [error, setError] = useState('');
	const [busy, setBusy] = useState(false);

	const open = () => {
		setError('');
		dialog.current?.showModal();
	};
	const close = () => dialog.current?.close();

	// Close once a wallet is connected.
	useEffect(() => {
		if (wallet.address) close();
	}, [wallet.address]);

	async function run(fn: () => unknown, closeFirst = false) {
		setError('');
		setBusy(true);
		if (closeFirst) close();
		try {
			await fn();
			close();
		} catch (e) {
			setError(e instanceof Error ? e.message.split('\n')[0] : String(e));
			if (closeFirst) dialog.current?.showModal();
		} finally {
			setBusy(false);
		}
	}

	if (wallet.address || social.authenticated) {
		return (
			<div className="signin">
				<span className="addr" title={wallet.address ?? undefined}>{wallet.address ? short(wallet.address) : 'Setting up…'}</span>
				<button type="button" className="btn sm out" onClick={() => (social.authenticated ? social.logout() : disconnect())}>Sign out</button>
			</div>
		);
	}

	const wallets = injected.length
		? injected.map((w) => ({ id: w.info.uuid, name: w.info.name, icon: w.info.icon, go: () => connectInjected(w.provider) }))
		: [{ id: 'browser', name: 'MetaMask / browser wallet', icon: null as string | null, go: () => connectInjected() }];

	return (
		<div className="signin">
			<button type="button" className="btn" onClick={open}>Sign in</button>
			<dialog
				ref={dialog}
				className="si-dialog"
				aria-labelledby="si-title"
				onClick={(e) => {
					if (e.target === dialog.current) close();
				}}
			>
				<div className="si-body">
					<button type="button" className="si-close" onClick={close} aria-label="Close">
						<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M2 2l10 10M12 2L2 12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>
					</button>
					<div className="si-logo"><Logo /></div>
					<h2 id="si-title" className="si-title">Sign in to OpenLabel</h2>
					<p className="si-lede">Fund tests, be the tester, and follow the products you care about.</p>

					{social.enabled && (
						<>
							<button type="button" className="si-primary" autoFocus disabled={!social.ready || busy} onClick={() => run(social.login, true)}>
								<span className="si-icons"><GoogleIcon /><MailIcon /></span>
								Continue with Google or email
							</button>
							<p className="si-note">No crypto wallet needed. We set one up for you.</p>
						</>
					)}

					<details className="si-own" open={!social.enabled}>
						<summary>
							<span>Or use your own wallet</span>
							<svg className="si-chev" width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M3 4.5l3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
						</summary>
						<div className="si-wallets">
							{wallets.map((w) => (
								<button key={w.id} type="button" className="si-wallet" disabled={busy} onClick={() => run(w.go)}>
									{w.icon ? <img src={w.icon} alt="" width={24} height={24} /> : <span className="si-wallet-ico"><WalletIcon /></span>}
									<span>{w.name}</span>
								</button>
							))}
							{hasWalletConnect && (
								<button type="button" className="si-wallet" disabled={busy} onClick={() => run(connectWalletConnect, true)}>
									<span className="si-wallet-ico wc"><WalletIcon /></span>
									<span>WalletConnect</span>
									<span className="si-hint">Mobile wallets</span>
								</button>
							)}
							{allowPrivateKey && (
								<form className="si-dev" onSubmit={(e: FormEvent) => { e.preventDefault(); run(() => connectPrivateKey(key.trim())); }}>
									<label className="field"><span>Developer: private key (local testnet only)</span>
										<input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="0x…" autoComplete="off" />
									</label>
									<button type="submit" className="btn sm outline" disabled={!key.trim() || busy}>Use key</button>
								</form>
							)}
						</div>
					</details>

					{error && <p className="si-error" role="alert">{error}</p>}
					<p className="si-legal">Sign-in is handled by Privy. OpenLabel never sees your password or shows your wallet address to others.</p>
				</div>
			</dialog>
		</div>
	);
}
