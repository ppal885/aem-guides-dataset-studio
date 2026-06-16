const XML_BLOCK_LANGUAGES = new Set([
  'dita',
  'ditamap',
  'ditaval',
  'html',
  'svg',
  'xhtml',
  'xml',
]);

const MOJIBAKE_REPLACEMENTS: Array<[string, string]> = [
  ['âš ï¸', '⚠️'],
  ['âœ…', '✅'],
  ['â€¦', '…'],
  ['â€”', '—'],
  ['â€“', '–'],
  ['â€™', '’'],
  ['â€œ', '“'],
  ['â€\u009d', '”'],
  ['â†’', '→'],
  ['â–²', '▲'],
  ['â–¼', '▼'],
  ['Â·', '·'],
];

export function repairTextEncodingArtifacts(value: string): string {
  let repaired = String(value || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  for (const [broken, fixed] of MOJIBAKE_REPLACEMENTS) {
    repaired = repaired.split(broken).join(fixed);
  }
  return repaired;
}

export function prettyPrintCompactXml(value: string): string {
  const text = String(value || '').trim();
  if (!text.startsWith('<') || !text.includes('>')) {
    return text;
  }

  const compact = text.replace(/>\s+</g, '><');
  const tokens = compact
    .replace(/(>)(<)(\/*)/g, '$1\n$2$3')
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean);

  if (tokens.length < 2) {
    return text;
  }

  let indent = 0;
  const lines: string[] = [];
  for (const token of tokens) {
    const isClosing = /^<\//.test(token);
    const isDeclaration = /^<\?/.test(token) || /^<!/.test(token);
    const isSelfClosing = /\/>$/.test(token);
    const isInlineClosed = /^<[^!?/][^>]*>.*<\/[^>]+>$/.test(token);

    if (isClosing) {
      indent = Math.max(indent - 1, 0);
    }

    lines.push(`${'  '.repeat(indent)}${token}`);

    if (!isDeclaration && !isClosing && !isSelfClosing && !isInlineClosed) {
      indent += 1;
    }
  }

  return lines.join('\n');
}

export function normalizeCodeBlockText(code: string, className?: string): string {
  const repaired = repairTextEncodingArtifacts(String(code || '')).replace(/\n$/, '');
  const lang = String(className || '').replace(/^language-/, '').trim().toLowerCase();
  if (!XML_BLOCK_LANGUAGES.has(lang) || repaired.includes('\n')) {
    return repaired;
  }
  return prettyPrintCompactXml(repaired);
}
