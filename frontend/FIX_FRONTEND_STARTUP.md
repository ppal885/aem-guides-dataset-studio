# Fix Frontend Startup Issue (EPERM Error)

## Problem
The frontend server fails to start with `Error: spawn EPERM` when trying to run esbuild. This is a Windows permission issue, typically caused by Windows Defender or antivirus software blocking esbuild.exe.

## Quick Fix Script (Recommended First Step)

Run the automated fix script:
```powershell
cd c:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio\frontend
.\fix-esbuild-permissions.ps1
```

**Note:** You may need to run PowerShell as Administrator for this script to work.

## Solutions (try in order):

### Solution 1: Exclude folder from Windows Defender (Most Reliable)
1. Open Windows Security
2. Go to Virus & threat protection
3. Click "Manage settings" under Virus & threat protection settings
4. Scroll down to "Exclusions" and click "Add or remove exclusions"
5. Add the following folder as an exclusion:
   ```
   C:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio\frontend\node_modules
   ```
   (Excluding the entire node_modules folder is safer and covers all esbuild instances)

### Solution 2: Run PowerShell as Administrator
1. Right-click PowerShell
2. Select "Run as Administrator"
3. Navigate to the frontend directory:
   ```powershell
   cd c:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio\frontend
   ```
4. Run:
   ```powershell
   npm run dev
   ```

### Solution 3: Use the startup script (Recommended)
```powershell
cd c:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio\frontend
.\start-dev.ps1
```

### Solution 4: Use --force flag
```powershell
cd c:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio\frontend
npm run dev -- --force
```

### Solution 5: Reinstall esbuild (if above don't work)
```powershell
cd c:\UI_Frameowrk\guides-ui-tests\aem-guides-dataset-studio\frontend
Remove-Item -Recurse -Force node_modules\esbuild
npm install esbuild --save-dev
npm run dev -- --force
```

### Solution 4: Use alternative port (if port 5173 is blocked)
Edit `vite.config.ts` and change the port:
```typescript
server: {
  port: 3000,  // Change from 5173
  host: true,
  ...
}
```

## After Fixing
Once the frontend starts, you should see:
```
  VITE v5.x.x  ready in xxx ms

  ➜  Local:   http://localhost:5173/
  ➜  Network:  http://[your-ip]:5173/
```
