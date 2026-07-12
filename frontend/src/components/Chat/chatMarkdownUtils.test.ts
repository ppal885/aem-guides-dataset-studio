import { describe, expect, it } from 'vitest';

import {
  classifyInlineCode,
  highlightEvidenceCitations,
  inlineCodeClassName,
  normalizeCodeBlockText,
  repairTextEncodingArtifacts,
  resolvePrismLanguage,
  resolveSectionHeadingClass,
  containsHtmlBreakToken,
} from './chatMarkdownUtils';

describe('chatMarkdownUtils', () => {
  it('repairs common mojibake artifacts in assistant text', () => {
    const input = 'GUIDES-881 â€” Native PDF issue Â· click for details';

    expect(repairTextEncodingArtifacts(input)).toBe('GUIDES-881 — Native PDF issue · click for details');
  });

  it('wraps evidence citations for inline styling', () => {
    expect(highlightEvidenceCitations('See [E1] and [E12] for sources.')).toBe(
      'See `[E1]` and `[E12]` for sources.'
    );
  });

  it('maps dita/xml aliases to prism markup language', () => {
    expect(resolvePrismLanguage('dita')).toBe('markup');
    expect(resolvePrismLanguage('xml')).toBe('markup');
    expect(resolvePrismLanguage('json')).toBe('json');
  });

  it('classifies inline code tokens for semantic coloring', () => {
    expect(classifyInlineCode('[E3]')).toBe('citation');
    expect(classifyInlineCode('conref')).toBe('dita-element');
    expect(classifyInlineCode('keyscope')).toBe('dita-attr');
    expect(classifyInlineCode('topic.dita')).toBe('path');
  });

  it('assigns section heading color classes from title text', () => {
    expect(resolveSectionHeadingClass('## Summary')).toBe('cursor-section-summary');
    expect(resolveSectionHeadingClass('XML Example')).toBe('cursor-section-example');
    expect(resolveSectionHeadingClass('Common mistakes')).toBe('cursor-section-warning');
    expect(resolveSectionHeadingClass('Sources')).toBe('cursor-section-sources');
  });

  it('detects html break tokens in table cell text', () => {
    expect(containsHtmlBreakToken('body<br>section')).toBe(true);
    expect(containsHtmlBreakToken('body <br /> section')).toBe(true);
    expect(containsHtmlBreakToken('plain text')).toBe(false);
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
