# Clear Vite Cache to Fix CardFooter Error

## Problem
Even though `CardFooter` is exported from `card.tsx`, Vite/esbuild is still showing the error. This is a caching issue.

## Solution

### Option 1: Clear Vite Cache and Restart
```bash
cd aem-guides-dataset-studio/frontend

# Delete Vite cache
rm -rf node_modules/.vite
# Or on Windows:
Remove-Item -Recurse -Force node_modules\.vite -ErrorAction SilentlyContinue

# Restart dev server
npm run dev
```

### Option 2: Force Rebuild
```bash
cd aem-guides-dataset-studio/frontend

# Stop the dev server (Ctrl+C)
# Clear cache
npm run build -- --force

# Restart dev server
npm run dev
```

### Option 3: Full Clean (if above doesn't work)
```bash
cd aem-guides-dataset-studio/frontend

# Remove node_modules and reinstall
rm -rf node_modules
npm install

# Restart dev server
npm run dev
```

## Verification
After clearing cache, the error should disappear. The `CardFooter` component is correctly defined and exported in `card.tsx` (lines 66-78).
