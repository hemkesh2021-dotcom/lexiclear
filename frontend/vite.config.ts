import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

/**
 * Build configuration.
 *
 * The dev server proxies `/api` to the FastAPI process so that the browser
 * sees a single origin in development, matching the single-origin deployment
 * produced by the Docker image. That keeps the Content-Security-Policy
 * identical in both environments instead of loosening it for local work.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    target: 'es2022',
    sourcemap: false,
    // React is split out so that application changes do not invalidate the
    // framework chunk in returning visitors' caches.
    rollupOptions: {
      output: {
        manualChunks: (id) =>
          id.includes('node_modules/react') || id.includes('node_modules/scheduler')
            ? 'react'
            : undefined,
      },
    },
    chunkSizeWarningLimit: 250,
  },
});
