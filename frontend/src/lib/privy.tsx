import { createContext, useContext, useEffect, useRef, type ReactNode } from 'react';
import { PrivyProvider, usePrivy, useWallets } from '@privy-io/react-auth';
import { chain, connectProvider, disconnect } from './wallet';

/** Public Privy app ID (safe to ship). Without it, Sign in offers wallets only. */
export const PRIVY_APP_ID: string | undefined = import.meta.env.VITE_PRIVY_APP_ID || undefined;

type SocialLogin = { enabled: boolean; ready: boolean; authenticated: boolean; login: () => void; logout: () => Promise<void> };
const off: SocialLogin = { enabled: false, ready: false, authenticated: false, login: () => {}, logout: async () => {} };
const Ctx = createContext<SocialLogin>(off);

/** Google / email sign-in through Privy, if configured. */
export const useSocialLogin = () => useContext(Ctx);

/** Hands Privy's embedded wallet to the app's wallet store once the user is signed in. */
function Bridge({ children }: { children: ReactNode }) {
	const { ready, authenticated, login, logout } = usePrivy();
	const { wallets } = useWallets();
	const attached = useRef<string | null>(null);
	const embedded = wallets.find((w) => w.walletClientType === 'privy');

	useEffect(() => {
		if (!authenticated) {
			if (attached.current) {
				attached.current = null;
				disconnect();
			}
			return;
		}
		if (!embedded || attached.current === embedded.address) return;
		attached.current = embedded.address;
		embedded
			.getEthereumProvider()
			.then((provider) => connectProvider(provider as Parameters<typeof connectProvider>[0]))
			.catch((e) => {
				attached.current = null;
				console.error('Could not use the Privy wallet', e);
			});
	}, [authenticated, embedded]);

	const value: SocialLogin = {
		enabled: true,
		ready,
		authenticated,
		login: () => login({ loginMethods: ['google', 'email'] }),
		logout: async () => {
			await logout();
			attached.current = null;
			disconnect();
		}
	};
	return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function SocialLoginProvider({ children }: { children: ReactNode }) {
	if (!PRIVY_APP_ID) return <>{children}</>;
	return (
		<PrivyProvider
			appId={PRIVY_APP_ID}
			config={{
				loginMethods: ['google', 'email'],
				appearance: { theme: 'light', accentColor: '#1D4A37', showWalletLoginFirst: false },
				embeddedWallets: { ethereum: { createOnLogin: 'users-without-wallets' } },
				defaultChain: chain,
				supportedChains: [chain]
			}}
		>
			<Bridge>{children}</Bridge>
		</PrivyProvider>
	);
}
