import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
        followRedirects: false,
        timeout: 600000, // 10 min for long-running plan/generate
        configure: (proxy) => {
          proxy.on('error', (err, _req, res) => {
            console.error('[Vite proxy] Backend unreachable at http://127.0.0.1:8000. Is the backend running?', err.message);
            if (res && !res.headersSent) {
              res.writeHead(503, { 'Content-Type': 'application/json' });
              res.end(JSON.stringify({ detail: 'Backend unreachable. Start backend with .\\START_BACKEND_SIMPLE.ps1 or .\\RUN_BOTH.ps1' }));
            }
          });
          proxy.on('proxyReq', (proxyReq, req) => {
            if (process.env.DEBUG_PROXY) {
              console.log('[Vite proxy]', req.method, req.url, '->', proxyReq.path);
            }
          });
          proxy.on('proxyRes', (proxyRes, req, res) => {
            if (process.env.DEBUG_PROXY && proxyRes.statusCode === 404) {
              console.warn('[Vite proxy] Backend returned 404 for', req.method, req.url);
            }
          });
        },
      },
    },
  },
  preview: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
        timeout: 600000,
      },
    },
  },
})
