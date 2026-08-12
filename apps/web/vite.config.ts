import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const apiTarget = process.env.PHYSICS_API_TARGET || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    manifest: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          const moduleId = id.replaceAll('\\', '/');
          if (!moduleId.includes('/node_modules/')) {
            return;
          }
          if (moduleId.includes('/node_modules/react-router-dom/')) {
            return 'router';
          }
          // Avoid matching every package whose name merely contains "react"
          // (lucide-react, react-virtuoso, Radix, etc.).  Those packages are
          // route-specific and should stay behind the existing lazy routes.
          if (
            moduleId.includes('/node_modules/react/')
            || moduleId.includes('/node_modules/react-dom/')
            || moduleId.includes('/node_modules/scheduler/')
          ) {
            return 'react';
          }
          if (moduleId.includes('/node_modules/katex/')) {
            return 'math';
          }
        },
      },
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': apiTarget,
      '^/assets(?:/|$)': apiTarget,
      '/health': apiTarget,
      '/search': apiTarget,
      '/questions': apiTarget,
      '/papers': apiTarget,
      '/images': apiTarget,
      '/knowledge-points': apiTarget,
      '/filters': apiTarget,
      '/review-queue': apiTarget,
      '/processing-runs': apiTarget,
      '/embeddings': apiTarget,
      '/files': apiTarget,
      '/thumbs': apiTarget,
    },
  },
})
