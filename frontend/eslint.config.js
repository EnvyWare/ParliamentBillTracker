import js from '@eslint/js';
import globals from 'globals';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import jsxA11y from 'eslint-plugin-jsx-a11y';

export default tseslint.config(
  { ignores: ['dist', 'coverage', 'playwright-report', 'test-results', 'node_modules'] },
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
      parserOptions: {
        // Both projects are listed explicitly: the end-to-end tests live in a
        // separate TypeScript project so that Node typings never reach the
        // browser bundle.
        project: ['./tsconfig.json', './tsconfig.e2e.json'],
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
      'jsx-a11y': jsxA11y,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // Accessibility is a stated requirement, so these are errors rather than hints.
      ...jsxA11y.flatConfigs.strict.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      // A scrollable region must be keyboard operable (WCAG 2.1.1), which axe
      // enforces as scrollable-region-focusable. That requires a tabIndex on
      // an element this rule considers non-interactive, so group and region
      // are allowed to carry one.
      'jsx-a11y/no-noninteractive-tabindex': [
        'error',
        { tags: [], roles: ['group', 'region'], allowExpressionValues: true },
      ],
      '@typescript-eslint/no-unnecessary-condition': 'off',
      '@typescript-eslint/restrict-template-expressions': [
        'error',
        { allowNumber: true, allowBoolean: true },
      ],
      // The snapshot arrives as unknown JSON and is narrowed deliberately in
      // src/model, which is the one place unchecked access is appropriate.
      '@typescript-eslint/no-unsafe-assignment': 'error',
      eqeqeq: ['error', 'always', { null: 'ignore' }],
      'no-restricted-globals': [
        'error',
        {
          name: 'fetch',
          message: 'Use loadSnapshot from src/model so the source contract stays in one place.',
        },
      ],
    },
  },
  {
    // The model layer is the boundary where untyped JSON becomes typed data.
    files: ['src/model/**/*.ts'],
    rules: {
      'no-restricted-globals': 'off',
    },
  },
  {
    // The flat config itself is plain JavaScript and is not part of the
    // TypeScript program, so the type-aware rules cannot apply to it.
    files: ['**/*.js'],
    ...tseslint.configs.disableTypeChecked,
  },
  {
    files: ['tests/**/*.{ts,tsx}', 'e2e/**/*.ts', '*.config.{ts,js}'],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
    rules: {
      '@typescript-eslint/no-non-null-assertion': 'off',
      'no-restricted-globals': 'off',
      // Fast refresh does not apply to test files.
      'react-refresh/only-export-components': 'off',
    },
  },
);
