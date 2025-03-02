import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    proxy: {
      '/stream': {
        target: 'http://192.168.1.130:8080/?action=stream',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/stream/, '')
      }
    }
  }
});
