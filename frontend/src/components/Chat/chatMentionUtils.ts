export type ChatMentionItem =
  | {
      type: 'insert';
      id: string;
      label: string;
      description: string;
      insertText: string;
    }
  | {
      type: 'action';
      id: 'pick-image' | 'pick-dita';
      label: string;
      description: string;
    };

export const CHAT_MENTION_ITEMS: ChatMentionItem[] = [
  {
    type: 'insert',
    id: 'dita-spec',
    label: 'DITA Spec',
    description: 'Look up elements and attributes in DITA 1.3',
    insertText: 'Look up in the DITA 1.3 spec: ',
  },
  {
    type: 'insert',
    id: 'aem-guides',
    label: 'AEM Guides docs',
    description: 'Search Experience League documentation',
    insertText: 'Search AEM Guides documentation for: ',
  },
  {
    type: 'insert',
    id: 'jira',
    label: 'Jira',
    description: 'Search project issues and bugs',
    insertText: 'Search Jira for: ',
  },
  {
    type: 'insert',
    id: 'xml-review',
    label: 'Review XML',
    description: 'Paste a DITA topic to validate',
    insertText: 'Review this DITA XML and list validation issues:\n\n',
  },
  {
    type: 'insert',
    id: 'dita-ot-pdf',
    label: 'DITA-OT PDF',
    description: 'Run local DITA-OT and generate PDF output',
    insertText: '/generate_dita_ot_pdf\noutput_format: pdf\n\nGenerate a DITA-OT publishing QA corpus for the current DITA construct question.',
  },
  {
    type: 'insert',
    id: 'dita-ot-all',
    label: 'DITA-OT all',
    description: 'Run local DITA-OT and generate PDF, HTML/xhtml, and HTML5',
    insertText: '/generate_dita_ot_pdf\noutput_format: all\n\nGenerate a DITA-OT publishing QA corpus for the current DITA construct question.',
  },
  {
    type: 'action',
    id: 'pick-image',
    label: 'Attach screenshot…',
    description: 'Reference a UI screenshot in your prompt',
  },
  {
    type: 'action',
    id: 'pick-dita',
    label: 'Attach DITA file…',
    description: 'Reference a .dita or .xml topic',
  },
];

export const CHAT_SLASH_ITEMS: ChatMentionItem[] = [
  {
    type: 'insert',
    id: 'slash-generate-dita-ot-pdf',
    label: '/generate_dita_ot_pdf',
    description: 'Run local DITA-OT and generate PDF output',
    insertText: '/generate_dita_ot_pdf\noutput_format: pdf\n\nGenerate a DITA-OT publishing QA corpus for the current DITA construct question.',
  },
  {
    type: 'insert',
    id: 'slash-generate-dita-ot-html',
    label: '/generate_dita_ot_html',
    description: 'Run local DITA-OT and generate classic HTML/xhtml output',
    insertText: '/generate_dita_ot_pdf\noutput_format: html\n\nGenerate a DITA-OT publishing QA corpus for the current DITA construct question.',
  },
  {
    type: 'insert',
    id: 'slash-generate-dita-ot-html5',
    label: '/generate_dita_ot_html5',
    description: 'Run local DITA-OT and generate HTML5 output',
    insertText: '/generate_dita_ot_pdf\noutput_format: html5\n\nGenerate a DITA-OT publishing QA corpus for the current DITA construct question.',
  },
  {
    type: 'insert',
    id: 'slash-generate-dita-ot-all',
    label: '/generate_dita_ot_all',
    description: 'Run local DITA-OT and generate PDF, HTML/xhtml, and HTML5',
    insertText: '/generate_dita_ot_pdf\noutput_format: all\n\nGenerate a DITA-OT publishing QA corpus for the current DITA construct question.',
  },
  {
    type: 'insert',
    id: 'slash-generate-dita',
    label: '/generate_dita',
    description: 'Generate a reviewed DITA topic',
    insertText: '/generate_dita\n\n',
  },
  {
    type: 'insert',
    id: 'slash-create-job',
    label: '/create_job',
    description: 'Create a DITA dataset generation job',
    insertText: '/create_job\nrecipe_type: freeform\n\n',
  },
  {
    type: 'insert',
    id: 'slash-lookup-aem-guides',
    label: '/lookup_aem_guides',
    description: 'Search Experience League / AEM Guides docs',
    insertText: '/lookup_aem_guides ',
  },
  {
    type: 'insert',
    id: 'slash-lookup-dita-spec',
    label: '/lookup_dita_spec',
    description: 'Look up DITA spec elements and attributes',
    insertText: '/lookup_dita_spec ',
  },
  {
    type: 'insert',
    id: 'slash-review-dita-xml',
    label: '/review_dita_xml',
    description: 'Validate pasted DITA XML',
    insertText: '/review_dita_xml\n\n',
  },
];

export function filterChatMentionItems(items: ChatMentionItem[], query: string): ChatMentionItem[] {
  const q = query.trim().toLowerCase();
  if (!q) return items;
  return items.filter((item) => {
    const hay = `${item.label} ${item.description}`.toLowerCase();
    return hay.includes(q);
  });
}

export interface ChatToolCatalogLike {
  name: string;
  slash_alias: string;
  slash_aliases?: string[];
  title?: string;
  description?: string;
  category?: string;
  primary_arg?: string;
  enabled?: boolean;
}

function slashInsertText(alias: string, tool: ChatToolCatalogLike): string {
  const command = `/${alias}`;
  if (tool.name === 'generate_dita_ot_pdf') {
    return `${command}\n\nGenerate a DITA-OT publishing QA corpus for the current DITA construct question.`;
  }
  const primary = String(tool.primary_arg || '').trim();
  return primary ? `${command} ` : `${command}\n`;
}

export function chatToolsToSlashItems(tools: ChatToolCatalogLike[]): ChatMentionItem[] {
  const items: ChatMentionItem[] = [];
  const seen = new Set<string>();
  for (const tool of tools) {
    if (tool.enabled === false) continue;
    const aliases = tool.slash_aliases?.length ? tool.slash_aliases : [tool.slash_alias || tool.name];
    for (const rawAlias of aliases) {
      const alias = String(rawAlias || '').trim().replace(/^\//, '');
      if (!alias || seen.has(alias)) continue;
      seen.add(alias);
      items.push({
        type: 'insert',
        id: `catalog-${alias}`,
        label: `/${alias}`,
        description: String(tool.description || tool.title || tool.name || 'Run tool'),
        insertText: slashInsertText(alias, tool),
      });
    }
  }
  return items;
}

export interface ActiveSlashCommand {
  start: number;
  query: string;
}

export function getActiveSlashCommand(value: string, caret: number): ActiveSlashCommand | null {
  const before = value.slice(0, caret);
  const lineStart = Math.max(before.lastIndexOf('\n') + 1, 0);
  const linePrefix = before.slice(lineStart);
  if (!linePrefix.startsWith('/')) return null;
  if (/\s/.test(linePrefix)) return null;
  return { start: lineStart, query: linePrefix.slice(1) };
}
