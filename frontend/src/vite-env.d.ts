/// <reference types="vite/client" />

/**
 * Side-effect imports of stylesheets.
 *
 * Vite resolves `import '@/styles/app.css'` at build time; TypeScript needs to
 * be told the module exists, or a strict build rejects the import.
 */
declare module '*.css' {
  const content: string;
  export default content;
}
