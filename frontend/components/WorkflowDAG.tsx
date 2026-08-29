"use client";

import dagre from "dagre";
import { useCallback, useMemo, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  Handle,
  Position,
  type Edge,
  type Node,
  type NodeProps,
} from "reactflow";
import "reactflow/dist/style.css";
import PolicyProofPanel from "@/components/PolicyProofPanel";
import type { NodeStatus, WorkflowNode } from "@/types";

const NODE_WIDTH = 230;
const NODE_HEIGHT = 78;

const STATUS_STYLE: Record<NodeStatus, { bg: string; border: string; text: string; mark: string }> =
  {
    approved: { bg: "#14532D", border: "#4ADE80", text: "#4ADE80", mark: "✓" },
    active: { bg: "#1A1200", border: "#F0C040", text: "#F0C040", mark: "⏳" },
    rejected: { bg: "#450A0A", border: "#EF4444", text: "#EF4444", mark: "✗" },
    blocked: { bg: "#151920", border: "#2E3545", text: "#6B7280", mark: "○" },
  };

interface FlowNodeData {
  node: WorkflowNode;
  selected: boolean;
}

function ApprovalNode({ data }: NodeProps<FlowNodeData>) {
  const { node, selected } = data;
  const style = STATUS_STYLE[node.status] ?? STATUS_STYLE.blocked;

  return (
    <div
      className="rounded-xl border px-4 py-3 transition-colors"
      style={{
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
        background: style.bg,
        borderColor: selected ? "#F0C040" : style.border,
        borderWidth: selected ? 2 : 1,
      }}
    >
      <Handle type="target" position={Position.Top} />
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-medium leading-tight" style={{ color: style.text }}>
          {node.label}
        </span>
        <span style={{ color: style.text }}>{style.mark}</span>
      </div>
      <div className="mt-1.5 flex items-center gap-2 text-[10px] uppercase tracking-wider text-muted">
        <span>{node.role.replace(/_/g, " ")}</span>
        {node.parallel_group && (
          <span className="rounded-full border border-orange px-1.5 py-px text-orange">
            parallel
          </span>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

const nodeTypes = { approval: ApprovalNode };

/** Nodes carry `order_index`, not edges: every node in a tier feeds every node in the next. */
function buildEdges(nodes: WorkflowNode[]): Edge[] {
  const tiers = Array.from(new Set(nodes.map((n) => n.order_index))).sort((a, b) => a - b);
  const edges: Edge[] = [];

  for (let i = 0; i < tiers.length - 1; i++) {
    const from = nodes.filter((n) => n.order_index === tiers[i]);
    const to = nodes.filter((n) => n.order_index === tiers[i + 1]);
    from.forEach((a) => {
      to.forEach((b) => {
        edges.push({
          id: `e-${a.id}-${b.id}`,
          source: String(a.id),
          target: String(b.id),
          type: "smoothstep",
          animated: b.status === "active",
          style: { stroke: b.status === "active" ? "#F0C040" : "#2E3545", strokeWidth: 1.5 },
        });
      });
    });
  }

  return edges;
}

function layout(nodes: WorkflowNode[], edges: Edge[], selectedId: number | null): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "TB", ranksep: 60, nodesep: 40 });

  nodes.forEach((n) => g.setNode(String(n.id), { width: NODE_WIDTH, height: NODE_HEIGHT }));
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);

  return nodes.map((n) => {
    const pos = g.node(String(n.id));
    return {
      id: String(n.id),
      type: "approval",
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
      data: { node: n, selected: selectedId === n.id },
      draggable: false,
      connectable: false,
    } satisfies Node<FlowNodeData>;
  });
}

export default function WorkflowDAG({ nodes }: { nodes: WorkflowNode[] }) {
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const edges = useMemo(() => buildEdges(nodes), [nodes]);
  const flowNodes = useMemo(() => layout(nodes, edges, selectedId), [nodes, edges, selectedId]);
  const selected = nodes.find((n) => n.id === selectedId) ?? null;

  const onNodeClick = useCallback((_: unknown, node: Node) => {
    setSelectedId(Number(node.id));
  }, []);

  if (nodes.length === 0) {
    return (
      <div className="card text-sm text-muted">
        No approval chain yet. It appears once NIRVAH finishes compiling the request.
      </div>
    );
  }

  return (
    <div>
      <div className="h-[520px] overflow-hidden rounded-xl border border-line bg-surface">
        <ReactFlow
          nodes={flowNodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodeClick={onNodeClick}
          onPaneClick={() => setSelectedId(null)}
          nodesDraggable={false}
          nodesConnectable={false}
          proOptions={{ hideAttribution: true }}
          fitView
          fitViewOptions={{ padding: 0.2 }}
        >
          <Background color="#252A36" gap={24} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>

      <p className="mt-2 text-xs text-muted">Click any node to see why it is required.</p>

      {selected && (
        <div className="mt-4">
          <PolicyProofPanel node={selected} onClose={() => setSelectedId(null)} />
        </div>
      )}
    </div>
  );
}
