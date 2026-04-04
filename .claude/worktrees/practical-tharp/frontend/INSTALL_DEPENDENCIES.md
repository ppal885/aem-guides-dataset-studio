# Fix: Cannot find module 'vite'

## Problem
TypeScript cannot find the `vite` module because dependencies are not installed.

## Solution
Install dependencies using npm:

```bash
cd aem-guides-dataset-studio/frontend
npm install
```

This will install all required dependencies including:
- `vite` - Build tool
- `@vitejs/plugin-react` - React plugin for Vite
- `typescript` - TypeScript compiler
- `react` and `react-dom` - React libraries
- Other dependencies listed in `package.json`

## After Installation
The TypeScript errors should disappear. If using an IDE like VS Code, you may need to:
1. Reload the window (Ctrl+Shift+P → "Reload Window")
2. Or restart the TypeScript server (Ctrl+Shift+P → "TypeScript: Restart TS Server")

## Verify
After installation, run:
```bash
npm run dev
```

This should start the Vite dev server without errors.
