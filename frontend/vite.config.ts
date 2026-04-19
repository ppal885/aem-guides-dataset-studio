import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

/** Backend URL for `/api` proxy. Override with VITE_PROXY_TARGET in frontend/.env when needed. */
const DEFAULT_API_PROXY_TARGET = 'http://127.0.0.1:8001'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, '')
  const proxyTarget = (env.VITE_PROXY_TARGET || DEFAULT_API_PROXY_TARGET).replace(
    /\/$/,
    ''
  )

  const proxyCommon = {
    target: proxyTarget,
    changeOrigin: true,
    secure: false,
    followRedirects: false,
    timeout: 600000, // 10 min for long-running plan/generate
    configure: (proxy: import('http-proxy').Server) => {
      proxy.on('error', (err, _req, res) => {
        console.error(
          `[Vite proxy] Backend unreachable at ${proxyTarget}. Is the backend running? (Set VITE_PROXY_TARGET in frontend/.env if using another port.)`,
          (err as Error).message
        )
        if (res && !res.headersSent) {
          res.writeHead(503, { 'Content-Type': 'application/json' })
          res.end(
            JSON.stringify({
              detail:
                `Backend unreachable at ${proxyTarget}. Start backend (e.g. .\\START_BACKEND_SIMPLE.ps1) or set VITE_PROXY_TARGET in frontend/.env to match your API port.`,
            })
          )
        }
      })
      proxy.on('proxyReq', (proxyReq, req) => {
        if (process.env.DEBUG_PROXY) {
          console.log('[Vite proxy]', req.method, req.url, '->', proxyReq.path)
        }
      })
      proxy.on('proxyRes', (proxyRes, req, _res) => {
        if (process.env.DEBUG_PROXY && proxyRes.statusCode === 404) {
          console.warn('[Vite proxy] Backend returned 404 for', req.method, req.url)
        }
      })
    },
  }

  return {
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
        '/api': proxyCommon,
      },
    },
    preview: {
      port: 5173,
      proxy: {
        '/api': {
          ...proxyCommon,
        },
      },
    },
  }
})
