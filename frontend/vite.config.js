import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    strictPort: true,
    proxy: { '/predict': { target: 'http://127.0.0.1:8000', timeout: 120000 } },
  },
});
