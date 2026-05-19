import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ToolResult } from './ChatMessage';

describe('ToolResult', () => {
  it('renders a structured DITA spec content-model card', () => {
    const html = renderToStaticMarkup(
      <ToolResult
        name="lookup_dita_spec"
        result={{
          kind: 'guidance',
          status: 'success',
          status_tone: 'success',
          summary: 'Inside <taskbody>, DITA allows `prereq`, `context`, `steps`, `steps-unordered`, `result`, and `postreq`.',
          warnings: [],
          sources: [
            {
              label: 'taskbody',
              url: 'https://example.com/taskbody',
              snippet: '<taskbody> is the main body element inside a DITA task topic.',
            },
          ],
          element_name: 'taskbody',
          query_type: 'content_model',
          content_model_summary:
            'Inside <taskbody>, DITA allows `prereq`, `context`, `steps`, `steps-unordered`, `result`, and `postreq`.',
          allowed_children: ['prereq', 'context', 'steps', 'steps-unordered', 'result', 'postreq'],
          supported_attributes: ['outputclass', 'id'],
          text_content: '<taskbody> is the main body element inside a DITA task topic.',
        }}
      />
    );

    expect(html).toContain('taskbody');
    expect(html).toContain('content model');
    expect(html).toContain('Allowed children');
    expect(html).toContain('steps-unordered');
    expect(html).toContain('Common attributes');
    expect(html).toContain('Sources');
  });

  it('renders a generate_dita preview plan with review-first guidance', () => {
    const html = renderToStaticMarkup(
      <ToolResult
        name="_agent_plan"
        result={{
          goal: 'Review the interpreted DITA bundle before generation',
          mode: 'generate_dita_preview',
          status: 'proposed',
          requires_approval: true,
          expected_outputs: ['1 DITA map', '10 glossary entries'],
          preview: {
            status: 'preview_ready',
            summary: 'Previewing a DITA bundle with 1 DITA map, 10 glossary entries.',
            bundle_type: 'mixed_bundle',
            content_mode: 'auto_hybrid',
            artifacts: [
              { kind: 'ditamap', label: '1 DITA map' },
              { kind: 'glossentry', label: '10 glossary entries' },
            ],
            assumptions: ['The map will reference the generated glossary entries.'],
          },
          steps: [
            {
              id: 'generate_dita-step-1',
              title: 'Generate DITA bundle',
              status: 'pending',
              approval_required: true,
              gate_type: 'review',
              summary: 'Previewing a DITA bundle with 1 DITA map, 10 glossary entries.',
            },
          ],
        }}
      />
    );

    expect(html).toContain('What I understood');
    expect(html).toContain('mixed bundle');
    expect(html).toContain('10 glossary entries');
    expect(html).toContain('Review');
    expect(html).toContain('Preview');
  });

  it('renders review-needed approval copy', () => {
    const html = renderToStaticMarkup(
      <ToolResult
        name="_approval_state"
        result={{
          state: 'required',
          kind: 'review',
          pending_tool_name: 'generate_dita',
          prompt: 'Review the proposed `generate_dita` bundle before generation.',
          affected_artifacts: ['1 DITA map', '10 glossary entries'],
          allowed_responses: ['approve', 'continue'],
        }}
      />
    );

    expect(html).toContain('Ready when you are');
    expect(html).toContain('10 glossary entries');
    expect(html).toContain('Quick replies');
  });

  it('renders clarification guidance with plain next-input copy', () => {
    const html = renderToStaticMarkup(
      <ToolResult
        name="_agent_plan"
        result={{
          goal: 'Review the interpreted DITA bundle before generation',
          mode: 'generate_dita_preview',
          status: 'clarification_required',
          preview: {
            clarification_needed: true,
            clarification_question: 'Do you want 20 concept, task, reference, or generic topic files?',
            clarification_request: {
              options: ['concept', 'task', 'reference', 'topic'],
            },
            required_metadata: [
              { field_name: 'author' },
              { field_name: 'keywords' },
            ],
          },
          steps: [
            {
              id: 'generate_dita-step-1',
              title: 'Generate DITA bundle',
              status: 'blocked',
              approval_required: true,
              gate_type: 'review',
              summary: 'I need the topic family before I can continue.',
            },
          ],
        }}
      />
    );

    expect(html).toContain('One quick detail');
    expect(html).toContain('A short reply is enough');
    expect(html).toContain('concept');
    expect(html).toContain('Required prolog metadata');
    expect(html).toContain('author');
  });

  it('renders DITA XML review findings as human-readable guidance', () => {
    const html = renderToStaticMarkup(
      <ToolResult
        name="review_dita_xml"
        result={{
          quality_score: 33,
          dita_type: 'map',
          review_summary: 'Reviewed this DITA map and scored it 33/100. It is not production-ready yet.',
          score_improvement_guidance: 'Fastest score lift: Missing AEM Guides DTD header; Map is missing references or branches.',
          review_counts: { errors: 2, warnings: 0, suggestions: 2 },
          review_scope: 'full_structural_scan',
          review_scope_explanation: 'Full DITA review: the tool checked document structure.',
          document_profile: {
            root_element: 'map',
            element_count: 3,
            line_count: 1,
            large_document: false,
            top_tags: [{ tag: 'map', count: 1 }, { tag: 'title', count: 1 }],
          },
          warnings: ['Map review mode is active: topic-only checks are not treated as map requirements.'],
          normalized_validation_issues: [
            {
              severity: 'error',
              label: 'Required DTD header',
              message: 'Required DTD header is missing.',
              recommendation: 'Add the correct DITA DOCTYPE immediately after the XML declaration.',
              impact: 'This can affect import and validation quality.',
            },
          ],
          priority_fixes: [
            {
              severity: 'error',
              title: 'Missing AEM Guides DTD header',
              recommendation: 'Add the exact map DTD header immediately after the XML declaration.',
              impact: 'High: validation and import become safer.',
            },
          ],
          normalized_suggestions: [
            {
              severity: 'error',
              title: 'Map is missing references or branches',
              description: 'A DITA map should organize deliverable content with map constructs.',
              recommendation: 'Add at least one topicref.',
            },
          ],
          suggestions: { total: 1, errors: 1, warnings: 0 },
        }}
      />
    );

    expect(html).toContain('What to improve first');
    expect(html).toContain('Review scope');
    expect(html).toContain('Root: &lt;map&gt;');
    expect(html).toContain('Map review mode is active');
    expect(html).toContain('Required DTD header is missing');
    expect(html).toContain('Show detailed suggestions');
    expect(html).toContain('Map is missing references or branches');
    expect(html).not.toContain('&quot;label&quot;');
    expect(html).not.toContain('JSON.stringify');
  });

  it('renders simplified XML flowchart scope clearly', () => {
    const html = renderToStaticMarkup(
      <ToolResult
        name="generate_xml_flowchart"
        result={{
          diagram_kind: 'map',
          title: 'Large map',
          node_count: 30,
          edge_count: 29,
          visible_node_count: 30,
          visible_edge_count: 29,
          total_node_count: 80,
          total_edge_count: 79,
          omitted_node_count: 50,
          omitted_edge_count: 50,
          display_mode: 'structure_overview',
          is_simplified: true,
          preview_focus: 'First-level structure, map branches, keys, and major references',
          structure_summary: 'Showing 30 of 80 structural nodes; 50 lower-priority nodes omitted from the preview.',
          warnings: ['Large or dense XML is rendered as a scoped structure overview, not exhaustive node-by-node output.'],
          legend: [{ kind: 'root', label: 'Root topic or map' }, { kind: 'topicref', label: 'Topic reference' }],
          xml_profile: {
            root_element: 'map',
            element_count: 240,
            line_count: 120,
          },
          mermaid: 'flowchart TD\n  A["Large map"]',
          preview_svg: '',
          preview_svg_data_url: '',
        }}
      />
    );

    expect(html).toContain('Structure overview');
    expect(html).toContain('30 of 80 nodes');
    expect(html).toContain('Preview focus');
    expect(html).toContain('not exhaustive');
    expect(html).toContain('Root: &lt;map&gt;');
    expect(html).toContain('Mermaid source');
  });

  it('renders a generate_dita result card with bundle summary and representative files', () => {
    const html = renderToStaticMarkup(
      <ToolResult
        name="generate_dita"
        result={{
          download_url: '/api/v1/ai/bundle/TEXT-123/run-1/download',
          jira_id: 'TEXT-123',
          run_id: 'run-1',
          bundle_summary: 'Generated a DITA bundle with 1 map file and 10 topic files.',
          artifact_counts: { total_files: 11, map_files: 1, topic_files: 10 },
          contract_summary: {
            bundle_type: 'map_bundle',
            topic_family: 'task',
            subject: 'cars',
            include_map: true,
            content_mode: 'auto_hybrid',
            glossary_usage_mode: 'standalone',
          },
          contract_compliance: {
            status: 'satisfied',
            required_elements: ['choicetable', 'stepxmp'],
            required_attributes: ['conref'],
            required_metadata: ['author'],
            issues: [],
          },
          build_validation: {
            status: 'not_run',
            validator: 'DITA-OT',
            issues: [],
          },
          llm_usage: {
            path: 'deterministic_plus_llm_draft',
            provider_label: 'OpenAI',
            model: 'gpt-4o-mini',
            call_count: 1,
            attempt_count: 1,
            steps: ['dita_deterministic_draft'],
            draft_stage: {
              llm_draft_used: true,
              fields: ['titles', 'shortdescs'],
            },
          },
          representative_files: ['root-map.ditamap', 'glossary-01.dita'],
        }}
      />
    );

    expect(html).toContain('Download DITA Bundle');
    expect(html).toContain('1 map file and 10 topic files');
    expect(html).toContain('Generation contract');
    expect(html).toContain('Contract compliance');
    expect(html).toContain('choicetable');
    expect(html).toContain('@conref');
    expect(html).toContain('author');
    expect(html).toContain('auto hybrid');
    expect(html).toContain('DITA-OT');
    expect(html).toContain('AI usage');
    expect(html).toContain('Deterministic generator + LLM drafting');
    expect(html).toContain('OpenAI');
    expect(html).toContain('titles, shortdescs');
    expect(html).toContain('Representative files');
    expect(html).toContain('root-map.ditamap');
  });
});
