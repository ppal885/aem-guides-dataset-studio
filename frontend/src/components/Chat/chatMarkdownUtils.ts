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

/** Wrap evidence IDs like [E1] in inline code for Cursor-style citation chips. */
export function highlightEvidenceCitations(markdown: string): string {
  return String(markdown || '').replace(/\[E(\d+)\]/g, '`[E$1]`');
}

const DITA_ELEMENT_TERMS = new Set([
  'topic',
  'task',
  'concept',
  'reference',
  'map',
  'ditamap',
  'topicref',
  'topicmeta',
  'keydef',
  'keywords',
  'keyword',
  'conref',
  'conkeyref',
  'keyref',
  'navtitle',
  'shortdesc',
  'body',
  'steps',
  'step',
  'cmd',
  'info',
  'note',
  'table',
  'tgroup',
  'row',
  'entry',
  'fig',
  'image',
  'xref',
  'link',
  'reltable',
  'relrow',
  'relcell',
  'ditaval',
  'prop',
  'revprop',
  'alt',
  'title',
  'section',
  'p',
  'ul',
  'li',
  'ol',
  'codeblock',
  'codeph',
  'ph',
  'uicontrol',
  'menucascade',
  'filepath',
  'term',
  'glossentry',
  'glossdef',
]);

const DITA_ATTR_TERMS = new Set([
  'keys',
  'href',
  'keyscope',
  'keyref',
  'conref',
  'conrefend',
  'conaction',
  'format',
  'scope',
  'type',
  'collection-type',
  'processing-role',
  'toc',
  'navtitle',
  'copy-to',
  'chunk',
  'outputclass',
  'audience',
  'platform',
  'product',
  'props',
  'rev',
  'translate',
  'id',
  'class',
  'morerows',
  'name',
  'value',
  'action',
  'href',
]);

/** Semantic section class for colored answer headings (Summary, XML example, Sources, …). */
export function resolveSectionHeadingClass(heading: string): string {
  const t = String(heading || '')
    .toLowerCase()
    .replace(/[^\w\s]/g, ' ')
    .trim();

  if (/\b(summary|overview|answer|key takeaway|direct answer)\b/.test(t)) return 'cursor-section-summary';
  if (/\b(detail|explanation|how it works|why|background|understanding)\b/.test(t)) {
    return 'cursor-section-details';
  }
  if (/\b(example|xml|sample|snippet|markup|dita|map example|code)\b/.test(t)) return 'cursor-section-example';
  if (/\b(expected result|expected outcome|result|outcome|output|what you should see)\b/.test(t)) {
    return 'cursor-section-result';
  }
  if (/\b(common mistakes?|pitfalls?|watch out|avoid|gotcha|troubleshoot)\b/.test(t)) {
    return 'cursor-section-warning';
  }
  if (/\b(sources?|references?|citations?|evidence|limits of evidence|further reading)\b/.test(t)) {
    return 'cursor-section-sources';
  }
  if (/\b(next step|action item|recommended|follow up|try this)\b/.test(t)) return 'cursor-section-next';
  if (/\b(note|important|remember|scope)\b/.test(t)) return 'cursor-section-note';
  if (/\b(comparison|versus|vs|difference|when to use)\b/.test(t)) return 'cursor-section-compare';
  return 'cursor-section-default';
}

export type InlineCodeKind = 'citation' | 'dita-element' | 'dita-attr' | 'xml' | 'path' | 'default';

export function classifyInlineCode(text: string): InlineCodeKind {
  const t = String(text || '').trim();
  const lower = t.toLowerCase();

  if (/^\[E\d+\]$/.test(t)) return 'citation';
  if (DITA_ELEMENT_TERMS.has(lower)) return 'dita-element';
  if (t.startsWith('@') || DITA_ATTR_TERMS.has(lower)) return 'dita-attr';
  if (/^<\/?[\w:-]+/.test(t) || /^[\w:-]+$/.test(t) && t.includes(':')) return 'xml';
  if (/\.(dita|ditamap|xml|html|md|json)$/i.test(t) || t.includes('/') || t.includes('\\')) return 'path';
  return 'default';
}

export function inlineCodeClassName(kind: InlineCodeKind): string {
  switch (kind) {
    case 'citation':
      return 'cursor-citation-chip';
    case 'dita-element':
      return 'cursor-dita-element-code';
    case 'dita-attr':
      return 'cursor-dita-attr-code';
    case 'xml':
      return 'cursor-xml-code';
    case 'path':
      return 'cursor-path-code';
    default:
      return 'cursor-inline-code';
  }
}

/** Split cell text on literal `<br>` tags (common in LLM markdown tables). */
export function containsHtmlBreakToken(text: string): boolean {
  return /<\s*br\s*\/?>/i.test(text);
}

const PRISM_LANGUAGE_ALIASES: Record<string, string> = {
  dita: 'markup',
  ditamap: 'markup',
  ditaval: 'markup',
  xhtml: 'markup',
  svg: 'markup',
  xml: 'markup',
  html: 'markup',
};

export function resolvePrismLanguage(lang: string): string {
  const normalized = String(lang || 'text').trim().toLowerCase();
  return PRISM_LANGUAGE_ALIASES[normalized] || normalized || 'text';
}

export function normalizeCodeBlockText(code: string, className?: string): string {
  const repaired = repairTextEncodingArtifacts(String(code || '')).replace(/\n$/, '');
  const lang = String(className || '').replace(/^language-/, '').trim().toLowerCase();
  if (!XML_BLOCK_LANGUAGES.has(lang) || repaired.includes('\n')) {
    return repaired;
  }
  return prettyPrintCompactXml(repaired);
}
