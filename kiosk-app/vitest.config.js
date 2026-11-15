import { defineConfig, mergeConfig } from 'vitest/config';
import viteConfig from './vite.config.js';

export default mergeConfig(viteConfig, defineConfig({
  // src/parity.test.js also checks the phone app's TypeScript (mobile-app/lib), whose tsconfig
  // extends Expo's; that isn't installed here and isn't needed to strip the types
  oxc: { tsconfig: false },
}));
