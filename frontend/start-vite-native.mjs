import { createServer } from 'vite'
import configFactory from './vite.config.js'

const host = process.env.VITE_DEV_HOST || '127.0.0.1'
const port = Number(process.env.VITE_DEV_PORT || 5173)
const config = await configFactory({ mode: 'development', command: 'serve' })

const server = await createServer({
  ...config,
  configFile: false,
  server: {
    ...(config.server || {}),
    host,
    port,
  },
})

await server.listen()
server.printUrls()
