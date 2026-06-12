import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // React, react-router, etc. reference process.env.NODE_ENV at runtime. The
  // dashboard loads this bundle as a plain <script> — no Node polyfills — so
  // we must define both the env string (build-time replace) and a minimal
  // `process` global (runtime typeof process checks in React error handlers).
  define: {
    'process.env.NODE_ENV': JSON.stringify('production'),
  },
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  build: {
    // Inline brand PNGs into index.js (served via dashboard-plugins script URL).
    assetsInlineLimit: 100_000,
    outDir: path.resolve(__dirname, '../dashboard/dist'),
    emptyOutDir: true,
    lib: {
      entry: path.resolve(__dirname, 'src/main.tsx'),
      name: 'LivingColorPlugin',
      formats: ['iife'],
      fileName: () => 'index.js',
    },
    rollupOptions: {
      output: {
        assetFileNames: 'style.css',
        banner:
          'var process=typeof process!=="undefined"?process:{env:{NODE_ENV:"production"}};',
      },
    },
  },
})
