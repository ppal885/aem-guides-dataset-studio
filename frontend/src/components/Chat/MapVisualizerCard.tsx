import { useCallback, useMemo, useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  FileText,
  FolderOpen,
  Info,
  Layers,
  Map,
} from 'lucide-react';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface MapNode {
  id: string;
  label: string;
  type: string;
  level: number;
  href?: string;
}

interface MapEdge {
  source: string;
  target: string;
  type: string;
}

interface MapGraphData {
  nodes: MapNode[];
  edges: MapEdge[];
  stats: { total_nodes: number; max_depth: number; topic_count: number };
  title: string;
  ai_suggestions: string[];
}

interface MapVisualizerCardProps {
  data: MapGraphData;
}

/* ------------------------------------------------------------------ */
/*  Colour palette per node type                                       */
/* ------------------------------------------------------------------ */

const TYPE_COLOURS: Record<string, { bg: string; border: string; text: string; dot: string }> = {
  map:        { bg: 'bg-blue-50',   border: 'border-blue-300',   text: 'text-blue-800',   dot: 'bg-blue-500' },
  topic:      { bg: 'bg-emerald-50',border: 'border-emerald-300',text: 'text-emerald-800',dot: 'bg-emerald-500' },
  topicgroup: { bg: 'bg-orange-50', border: 'border-orange-300', text: 'text-orange-800', dot: 'bg-orange-500' },
  topichead:  { bg: 'bg-purple-50', border: 'border-purple-300', text: 'text-purple-800', dot: 'bg-purple-500' },
  chapter:    { bg: 'bg-sky-50',    border: 'border-sky-300',    text: 'text-sky-800',    dot: 'bg-sky-500' },
  appendix:   { bg: 'bg-rose-50',   border: 'border-rose-300',   text: 'text-rose-800',   dot: 'bg-rose-500' },
};

const DEFAULT_COLOUR = { bg: 'bg-gray-50', border: 'border-gray-300', text: 'text-gray-800', dot: 'bg-gray-500' };

function colourFor(type: string) {
  return TYPE_COLOURS[type] ?? DEFAULT_COLOUR;
}

/* ------------------------------------------------------------------ */
/*  Build a tree from flat nodes + edges                               */
/* ------------------------------------------------------------------ */

interface TreeNode extends MapNode {
  children: TreeNode[];
}

function buildTree(nodes: MapNode[], edges: MapEdge[]): TreeNode[] {
  const nodeMap = new Map<string, TreeNode>();
  for (const n of nodes) {
    nodeMap.set(n.id, { ...n, children: [] });
  }

  const childIds = new Set<string>();
  for (const e of edges) {
    if (e.type !== 'contains') continue;
    const parent = nodeMap.get(e.source);
    const child = nodeMap.get(e.target);
    if (parent && child) {
      parent.children.push(child);
      childIds.add(e.target);
    }
  }

  // Roots are nodes that are never a child
  return nodes
    .filter((n) => !childIds.has(n.id))
    .map((n) => nodeMap.get(n.id)!)
    .filter(Boolean);
}

/* ------------------------------------------------------------------ */
/*  Single tree node row                                               */
/* ------------------------------------------------------------------ */

function NodeIcon({ type }: { type: string }) {
  const cls = 'h-4 w-4 shrink-0';
  switch (type) {
    case 'map':
      return <Map className={cls} />;
    case 'topicgroup':
    case 'topichead':
      return <FolderOpen className={cls} />;
    case 'chapter':
    case 'appendix':
      return <Layers className={cls} />;
    default:
      return <FileText className={cls} />;
  }
}

function TreeRow({ node, defaultExpanded }: { node: TreeNode; defaultExpanded: boolean }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const hasChildren = node.children.length > 0;
  const c = colourFor(node.type);

  return (
    <div>
      <button
        type="button"
        onClick={() => hasChildren && setExpanded((v) => !v)}
        className={`flex w-full items-center gap-2 rounded-lg border px-3 py-1.5 text-left text-[13px] font-medium transition-colors ${c.bg} ${c.border} ${c.text} ${hasChildren ? 'cursor-pointer hover:brightness-95' : 'cursor-default'}`}
      >
        {/* expand / collapse chevron */}
        <span className="w-4 shrink-0">
          {hasChildren ? (
            expanded ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )
          ) : null}
        </span>

        <NodeIcon type={node.type} />

        <span className="truncate">{node.label}</span>

        <span
          className={`ml-auto rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider opacity-70 ${c.dot} text-white`}
        >
          {node.type}
        </span>
      </button>

      {hasChildren && expanded && (
        <div className="ml-5 mt-1 border-l border-gray-200 pl-3 space-y-1">
          {node.children.map((child) => (
            <TreeRow key={child.id} node={child} defaultExpanded={child.level < 2} />
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main card                                                          */
/* ------------------------------------------------------------------ */

export function MapVisualizerCard({ data }: MapVisualizerCardProps) {
  const roots = useMemo(() => buildTree(data.nodes, data.edges), [data.nodes, data.edges]);

  const relatedEdges = useMemo(
    () => data.edges.filter((e) => e.type === 'related'),
    [data.edges],
  );

  const nodeById = useMemo(() => {
    const m = new Map<string, MapNode>();
    for (const n of data.nodes) m.set(n.id, n);
    return m;
  }, [data.nodes]);

  const [showSuggestions, setShowSuggestions] = useState(true);

  return (
    <div className="rounded-2xl border border-indigo-200 bg-[linear-gradient(135deg,#eef2ff_0%,#f8f9ff_100%)] p-4 text-sm">
      {/* Header */}
      <div className="flex items-center gap-3 mb-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-indigo-600 text-white shadow-sm">
          <Map className="h-5 w-5" />
        </div>
        <div>
          <div className="text-sm font-semibold text-indigo-950">{data.title}</div>
          <div className="text-xs text-indigo-800/70">Topic Map Visualization</div>
        </div>
      </div>

      {/* Stats bar */}
      <div className="mb-3 flex flex-wrap gap-2 text-[11px] font-medium text-indigo-800/90">
        <span className="rounded-full border border-indigo-200 bg-white px-3 py-1">
          {data.stats.topic_count} topics
        </span>
        <span className="rounded-full border border-indigo-200 bg-white px-3 py-1">
          {data.stats.max_depth} depth
        </span>
        <span className="rounded-full border border-indigo-200 bg-white px-3 py-1">
          {data.stats.total_nodes} nodes
        </span>
        {relatedEdges.length > 0 && (
          <span className="rounded-full border border-indigo-200 bg-white px-3 py-1">
            {relatedEdges.length} related links
          </span>
        )}
      </div>

      {/* Tree */}
      <div className="space-y-1 mb-3 max-h-[420px] overflow-y-auto pr-1">
        {roots.map((root) => (
          <TreeRow key={root.id} node={root} defaultExpanded={true} />
        ))}
      </div>

      {/* Related edges summary */}
      {relatedEdges.length > 0 && (
        <div className="mb-3 rounded-lg border border-indigo-100 bg-white/60 p-3">
          <div className="text-xs font-semibold text-indigo-900 mb-1">Related Links (reltable)</div>
          <div className="space-y-1">
            {relatedEdges.map((e, idx) => {
              const src = nodeById.get(e.source);
              const tgt = nodeById.get(e.target);
              return (
                <div key={idx} className="flex items-center gap-2 text-xs text-indigo-700">
                  <span className="font-medium">{src?.label ?? e.source}</span>
                  <span className="text-indigo-400">&harr;</span>
                  <span className="font-medium">{tgt?.label ?? e.target}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* AI Suggestions */}
      {data.ai_suggestions.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => setShowSuggestions((v) => !v)}
            className="flex items-center gap-1.5 text-xs font-semibold text-amber-700 mb-1 hover:text-amber-900 transition-colors"
          >
            <Info className="h-3.5 w-3.5" />
            {showSuggestions ? 'Hide' : 'Show'} suggestions ({data.ai_suggestions.length})
          </button>
          {showSuggestions && (
            <div className="space-y-1.5">
              {data.ai_suggestions.map((s, idx) => (
                <div
                  key={idx}
                  className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900"
                >
                  {s}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
