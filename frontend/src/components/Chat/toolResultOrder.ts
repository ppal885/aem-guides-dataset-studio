export const TOOL_RESULT_ORDER = [
  '_agent_plan',
  '_approval_state',
  '_agent_execution',
  '_grounding',
] as const;

export function sortToolResultEntries(
  entries: [string, unknown][]
): [string, unknown][] {
  return [...entries].sort(([a], [b]) => {
    const ai = TOOL_RESULT_ORDER.indexOf(a as (typeof TOOL_RESULT_ORDER)[number]);
    const bi = TOOL_RESULT_ORDER.indexOf(b as (typeof TOOL_RESULT_ORDER)[number]);
    const av = ai === -1 ? TOOL_RESULT_ORDER.length : ai;
    const bv = bi === -1 ? TOOL_RESULT_ORDER.length : bi;
    return av - bv;
  });
}
