import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const apiTarget = process.env.PHYSICS_API_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return;
          }
          if (id.includes('react-router-dom')) {
            return 'router';
          }
          if (id.includes('react')) {
            return 'react';
          }
          if (id.includes('katex')) {
            return 'math';
          }
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': apiTarget,
      '/assets': apiTarget,
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
    },
  },
})
