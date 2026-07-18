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
    insertText: '/generate_dita_ot_pdf\noutput_format: pdf\n\nDITA-OT PDF smoke test',
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

export function filterChatMentionItems(items: ChatMentionItem[], query: string): ChatMentionItem[] {
  const q = query.trim().toLowerCase();
  if (!q) return items;
  return items.filter((item) => {
    const hay = `${item.label} ${item.description}`.toLowerCase();
    return hay.includes(q);
  });
}
