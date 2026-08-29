import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    // Fingerprinted assets get a one-year immutable cache; index.html does not.
    // The deployment workflow relies on that split when it sets object metadata.
    assetsDir: 'assets',
    sourcemap: false,
    target: 'es2022',
    reportCompressedSize: true,
  },
  server: {
    port: 5173,
  },
  test: {
    environment: 'jsdom',
    globals: false,
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.test.{ts,tsx}'],
    css: false,
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/main.tsx', 'src/**/*.d.ts'],
      reporter: ['text', 'lcov'],
    },
  },
});
