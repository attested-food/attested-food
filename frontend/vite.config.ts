import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	envDir: '..',
	server: { proxy: { '/api': 'http://localhost:8000' } }
});
