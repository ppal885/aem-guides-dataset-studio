/** Normalize user input: bare key or Jira browse URL → issue key (uppercase). */

export function normalizeJiraKeyInput(raw: string): string {
  const s = raw.trim();
  if (!s) return '';
  const browse = /\/browse\/([A-Za-z][A-Za-z0-9]*-\d+)/i.exec(s);
  if (browse) return browse[1].toUpperCase();
  const compact = s.replace(/\s+/g, '');
  const bare = /^([A-Za-z][A-Za-z0-9]*-\d+)$/.exec(compact);
  if (bare) return bare[1].toUpperCase();
  return compact.toUpperCase();
}
