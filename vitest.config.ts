import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    globals: true,
    include: ['tests/**/*.test.ts', 'apps/web/tests/**/*.spec.ts'],
    setupFiles: [],
    coverage: {
      reporter: ['text', 'lcov'],
    },
  },
});
