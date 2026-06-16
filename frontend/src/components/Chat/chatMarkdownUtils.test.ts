import { describe, expect, it } from 'vitest';

import { normalizeCodeBlockText, repairTextEncodingArtifacts } from './chatMarkdownUtils';

describe('chatMarkdownUtils', () => {
  it('repairs common mojibake artifacts in assistant text', () => {
    const input = 'GUIDES-881 â€” Native PDF issue Â· click for details';

    expect(repairTextEncodingArtifacts(input)).toBe('GUIDES-881 — Native PDF issue · click for details');
  });

  it('pretty-prints compact xml code blocks for display', () => {
    const input =
      '<table><tgroup cols="2"><tbody><row><entry morerows="1">Spans 2 rows</entry><entry>Row 1, Col 2</entry></row><row><entry>Row 2, Col 2</entry></row></tbody></tgroup></table>';

    expect(normalizeCodeBlockText(input, 'language-xml')).toBe(
      '<table>\n' +
        '  <tgroup cols="2">\n' +
        '    <tbody>\n' +
        '      <row>\n' +
        '        <entry morerows="1">Spans 2 rows</entry>\n' +
        '        <entry>Row 1, Col 2</entry>\n' +
        '      </row>\n' +
        '      <row>\n' +
        '        <entry>Row 2, Col 2</entry>\n' +
        '      </row>\n' +
        '    </tbody>\n' +
        '  </tgroup>\n' +
        '</table>'
    );
  });
});
