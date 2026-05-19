/**
 * UAC Copilot — POST /api/v1/ai/uac/analyze
 */
import { apiUrl, fetchJson } from '@/utils/api';

export interface UacClassification {
  domain?: string;
  sub_domain?: string;
  issue_type?: string;
  status?: string;
  priority?: string;
  customer_names?: string[];
  affected_outputs?: string[];
  dita_entities?: string[];
  labels?: string[];
  components?: string[];
  qa_risk_tags?: string[];
}

export interface UacSimilarJira {
  jira_key: string;
  /** Same Jira summary line as stored on the indexed ticket. */
  summary?: string;
  title?: string;
  domain?: string;
  matching_entities?: string[];
  matching_outputs?: string[];
  matching_customers?: string[];
  why_similar?: string;
  what_we_learned?: string;
  /** 0–1 heuristic confidence from structured overlap + retrieval scores. */
  confidence_score?: number;
  chunk_type?: string;
  scores?: {
    final?: number;
    vector?: number;
    keyword?: number;
    metadata?: number;
  };
  document_excerpt?: string;
}

export interface UacRetrievalScore {
  jira_key: string;
  final: number;
  vector: number;
  keyword: number;
  metadata: number;
}

export interface UacRetrievalDebug {
  domain?: string;
  entities?: string[];
  outputs?: string[];
  scores?: UacRetrievalScore[];
}

export interface UacDroppedPoint {
  text: string;
  reason: string;
}

export interface UacAnswerQuality {
  score: number;
  generic_phrases_found: string[];
  missing_specificity: string[];
  recommendation: 'accept' | 'rewrite' | 'reject';
}

export interface UacParityPair {
  source: string;
  target: string;
  risk: string;
}

export interface UacOutputParity {
  parity_required?: boolean;
  parity_pairs?: UacParityPair[];
  validation_points?: string[];
}

/** Telemetry from SQLite-backed anti-repetition pass (backend `services.uac.anti_repetition_service`). */
export interface UacAntiRepetitionMeta {
  changed: boolean;
  skipped: boolean;
  scenarios_deduped: number;
  scenarios_rewritten_memory: number;
  scenarios_strengthened_anchor: number;
  drivers_dropped_generic: number;
  drivers_rewritten: number;
  clarifications_rewritten: number;
  markdown_refreshed: boolean;
  reasons: string[];
}

/** Structured JSON for dashboard cards/tables (no Markdown). Mirrors backend ``UacUiContract``. */
export interface UacUiRiskBadge {
  level: string;
  label: string;
  risk_score?: number | null;
  message?: string | null;
}

export interface UacUiClassificationCard {
  jira_key: string;
  classification: UacClassification;
}

export interface UacUiExecutiveSummaryCard {
  summary: string;
  release_risk?: string;
  decisions_needed_preview?: string[];
  qa_commitments_preview?: string[];
}

export interface UacUiSimilarJiraLearningCard {
  jira_key: string;
  title?: string;
  why_relevant?: string;
  what_we_learned?: string;
  confidence_score?: number | null;
  scores?: Record<string, unknown> | null;
  chunk_type?: string | null;
}

export interface UacUiMustTestScenarioRow {
  id: string;
  scenario: string;
  why?: string;
  evidence?: string;
  test_layer?: string;
  priority?: string;
  automation_fit?: unknown;
  impacted_output?: unknown;
  related_entity?: unknown;
}

export interface UacUiMissingClarificationRow {
  id: string;
  question: string;
  why?: string;
  evidence?: string;
  related_entity?: string | null;
}

export interface UacUiAutomationStrategyCard {
  fit: string;
  primary_test_layer: string;
  framework: string;
  suggested_test_name: string;
}

export interface UacUiDatasetRecommendationCard {
  items: string[];
  hints_from_guardrails: string[];
  insufficient_similar_pool: boolean;
}

export interface UacUiClaimVerificationSummary {
  dropped_count: number;
  downgraded_count: number;
  unsupported_count: number;
}

export interface UacUiGuardrailWarning {
  code?: string | null;
  message?: string | null;
  detail?: string | null;
}

export interface UacConfidenceScore {
  score?: number | null;
  level?: 'high' | 'medium' | 'low' | string | null;
  signals?: string[] | null;
}

export interface UacGuardrailsDetail {
  warnings?: UacUiGuardrailWarning[] | null;
  blocked_claims?: string[] | null;
  warnings_count?: number | null;
  blocked_claims_count?: number | null;
}

export interface UacUiConfidenceWarningsCard {
  confidence: UacConfidenceScore;
  quality_score?: number | null;
  answer_quality?: UacAnswerQuality | null;
  uac_validation_ok: boolean;
  uac_validation_errors: string[];
  insufficient_similar_evidence: boolean;
  claim_verification: UacUiClaimVerificationSummary;
  guardrails_warnings: UacUiGuardrailWarning[];
  blocked_claims_count: number;
}

export interface UacUiDebugAccordion {
  debug_mode: boolean;
  retrieval_debug?: Record<string, unknown> | null;
  anti_repetition?: UacAntiRepetitionMeta | null;
  claim_verification_detail?: Record<string, unknown> | null;
  uac_guardrails_detail?: UacGuardrailsDetail | null;
  dropped_generic_points?: UacDroppedPoint[] | null;
  generic_phrases_removed?: string[] | null;
  regeneration_used?: boolean | null;
  structured_uac_available?: boolean;
}

export interface UacUiQaBlockingRow {
  question: string;
  owner_role: string;
}

export interface UacUiJiraTestScriptOutline {
  title?: string;
  preconditions?: string[];
  steps?: string[];
  expected_result?: string;
}

/** Second-pass LLM output when `include_qa_handoff` is true. */
export interface UacUiQaHandoffCard {
  requested: boolean;
  generated: boolean;
  note?: string | null;
  regression_breadth?: string;
  smoke_checks?: string[];
  deep_regression_focus?: string[];
  blocking_for_signoff?: UacUiQaBlockingRow[];
  exit_criteria?: string[];
  exploratory_angles?: string[];
  jira_test_script?: UacUiJiraTestScriptOutline;
  qa_lead_note?: string;
}

export interface UacUiContract {
  version: number;
  risk_badge: UacUiRiskBadge;
  classification_card: UacUiClassificationCard;
  executive_summary_card: UacUiExecutiveSummaryCard;
  similar_jira_learning_cards: UacUiSimilarJiraLearningCard[];
  must_test_scenario_table: { rows: UacUiMustTestScenarioRow[] };
  missing_clarification_table: { rows: UacUiMissingClarificationRow[] };
  automation_strategy_card: UacUiAutomationStrategyCard;
  dataset_recommendation_card: UacUiDatasetRecommendationCard;
  confidence_warnings_card: UacUiConfidenceWarningsCard;
  debug_accordion: UacUiDebugAccordion;
  qa_handoff_card?: UacUiQaHandoffCard;
}

export interface UacAnalyzeResponse {
  jira_key: string;
  /** Prefer this for UI rendering (cards/tables). */
  uac_ui?: UacUiContract;
  classification?: UacClassification;
  similar_jiras?: UacSimilarJira[];
  /** Legacy Markdown brief; optional when migrating to ``uac_ui``. */
  uac_answer?: string;
  /** 0–100 specificity score on the final (post-critic) answer. */
  quality_score?: number | null;
  /** True if the first draft scored below 70 and a stricter-prompt retry ran. */
  regeneration_used?: boolean;
  /** Regex pattern strings for generic phrases present pre-critic but absent in the final answer. */
  generic_phrases_removed?: string[];
  answer_quality?: UacAnswerQuality;
  dropped_generic_points?: UacDroppedPoint[];
  retrieval_debug?: UacRetrievalDebug;
  /** Deterministic cross-output parity (preview, Native PDF, Sites, baseline, authoring). */
  output_parity?: UacOutputParity;
  /** Present when the server ran the anti-repetition post-processor on structured UAC fields. */
  anti_repetition?: UacAntiRepetitionMeta;
  /** True when similar-Jira evidence pool is too thin (mirrors ``confidence_warnings_card.insufficient_similar_evidence``). */
  insufficient_similar_evidence?: boolean;
  warning?: string;
  error?: string;
}

export async function postUacAnalyze(body: {
  jira_key: string;
  include_similar?: boolean;
  max_similar?: number;
  /** When true, the server may return expanded retrieval debug; anti-repetition meta is always included when applied. */
  debug?: boolean;
  /**
   * When true, runs an extra LLM pass for structured QA handoff (smoke vs deep regression, sign-off blockers, Jira-style steps).
   * Increases latency and token usage.
   */
  include_qa_handoff?: boolean;
}): Promise<UacAnalyzeResponse> {
  return fetchJson<UacAnalyzeResponse>(apiUrl('/api/v1/ai/uac/analyze'), {
    method: 'POST',
    body: JSON.stringify({
      jira_key: body.jira_key.trim(),
      include_similar: body.include_similar ?? true,
      max_similar: body.max_similar ?? 8,
      debug: body.debug ?? false,
      include_qa_handoff: body.include_qa_handoff ?? false,
    }),
  });
}
