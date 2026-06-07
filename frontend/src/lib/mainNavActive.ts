/** Whether a top-level header nav item should show the active (teal) state. */
export function isMainNavActive(pathname: string, itemPath: string): boolean {
  return pathname === itemPath;
}
