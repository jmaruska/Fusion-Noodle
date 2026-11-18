import { defineConfig } from 'vite';

// cd "ui" && npm run build

export default defineConfig({
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: 'src/main.jsx',
      output: {
        entryFileNames: 'bundle.js',
        chunkFileNames: 'bundle.js',
        assetFileNames: 'bundle.css'
      }
    },
    minify: false // Keep readable for debugging
  },
  define: {
    'process.env.NODE_ENV': '"production"'
  }
});
