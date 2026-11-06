import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [react()],
	resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
	envDir: '..',
	publicDir: 'static',
	build: { outDir: 'build', emptyOutDir: true },
	server: { proxy: { '/api': 'http://localhost:8000' } }
});
