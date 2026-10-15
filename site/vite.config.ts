import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ command }) => ({
  plugins: [react()],
  server: { host: '127.0.0.1', port: 5174 },
  // public/ only holds dev sample data (password «test»): never ship it
  publicDir: command === 'serve' ? 'public' : false,
}))
