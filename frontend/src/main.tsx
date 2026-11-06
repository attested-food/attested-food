import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { SocialLoginProvider } from './lib/privy';
import './styles.css';

createRoot(document.getElementById('root')!).render(
	<StrictMode>
		<SocialLoginProvider>
			<App />
		</SocialLoginProvider>
	</StrictMode>
);
