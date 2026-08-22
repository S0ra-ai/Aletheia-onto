import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Card, Col, Descriptions, Empty, Row, Select, Space, Spin, Switch, Tag, Typography, message } from 'antd';
import { graphApi, ontologyApi } from '../../api';
import type { Ontology, OntologyGraph, OntologyGraphNode } from '../../types';

const { Title, Text } = Typography;

/**
 * Knowledge graph preview.
 *
 * An ontology is a graph, but every other screen shows it as tables, which hides
 * exactly the problems a reviewer needs to see: an object nothing points at, a
 * self-referencing hierarchy, a cluster with no rules.
 *
 * Layout is a small force simulation rendered to SVG rather than a charting
 * dependency. Reasons: the graphs here are tens of nodes, not thousands; adding
 * a 500KB library for one screen is a poor trade; and the simulation is
 * deterministic given a seed, so screenshots in the README stay reproducible.
 */

interface Positioned extends OntologyGraphNode {
  x: number;
  y: number;
}

const WIDTH = 860;
const HEIGHT = 520;
const ITERATIONS = 320;

/** Deterministic PRNG so a given ontology always lays out identically. */
const seededRandom = (seed: number) => {
  let state = seed || 1;
  return () => {
    state = (state * 1664525 + 1013904223) % 4294967296;
    return state / 4294967296;
  };
};

function layout(graph: OntologyGraph): Positioned[] {
  const random = seededRandom(graph.ontology.id * 7919 + graph.nodes.length);
  const nodes: Positioned[] = graph.nodes.map((node, index) => {
    // Seed on a circle rather than uniformly at random: it converges faster and
    // avoids the degenerate case where every node starts near the centre.
    const angle = (index / Math.max(graph.nodes.length, 1)) * Math.PI * 2;
    return {
      ...node,
      x: WIDTH / 2 + Math.cos(angle) * 180 + (random() - 0.5) * 40,
      y: HEIGHT / 2 + Math.sin(angle) * 140 + (random() - 0.5) * 40,
    };
  });

  const index = new Map(nodes.map((node, i) => [node.code, i]));
  // Self-loops must not participate in attraction; they would pull a node
  // toward itself and destabilise the simulation.
  const links = graph.edges
    .map(edge => ({ s: index.get(edge.source), t: index.get(edge.target) }))
    .filter((link): link is { s: number; t: number } =>
      link.s !== undefined && link.t !== undefined && link.s !== link.t);

  for (let step = 0; step < ITERATIONS; step += 1) {
    const cooling = 1 - step / ITERATIONS;

    for (let i = 0; i < nodes.length; i += 1) {
      for (let j = i + 1; j < nodes.length; j += 1) {
        const dx = nodes[j].x - nodes[i].x;
        const dy = nodes[j].y - nodes[i].y;
        const distance = Math.max(Math.hypot(dx, dy), 1);
        const force = (9000 / (distance * distance)) * cooling;
        const fx = (dx / distance) * force;
        const fy = (dy / distance) * force;
        nodes[i].x -= fx;
        nodes[i].y -= fy;
        nodes[j].x += fx;
        nodes[j].y += fy;
      }
    }

    for (const link of links) {
      const a = nodes[link.s];
      const b = nodes[link.t];
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const distance = Math.max(Math.hypot(dx, dy), 1);
      const force = ((distance - 170) * 0.012) * cooling;
      const fx = (dx / distance) * force;
      const fy = (dy / distance) * force;
      a.x += fx;
      a.y += fy;
      b.x -= fx;
      b.y -= fy;
    }

    for (const node of nodes) {
      node.x += (WIDTH / 2 - node.x) * 0.004 * cooling;
      node.y += (HEIGHT / 2 - node.y) * 0.004 * cooling;
      node.x = Math.min(WIDTH - 60, Math.max(60, node.x));
      node.y = Math.min(HEIGHT - 44, Math.max(44, node.y));
    }
  }
  return nodes;
}

const nodeRadius = (node: OntologyGraphNode) => 20 + Math.min(node.degree, 6) * 3;

/** Colour encodes a diagnosis, not decoration. */
function nodeFill(node: OntologyGraphNode): string {
  if (node.unbound) return '#ff4d4f';
  if (node.ruleCount === 0) return '#faad14';
  return '#1677ff';
}

const OntologyGraphPage: React.FC = () => {
  const [ontologies, setOntologies] = useState<Ontology[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [graph, setGraph] = useState<OntologyGraph | null>(null);
  const [loading, setLoading] = useState(false);
  const [showIssuesOnly, setShowIssuesOnly] = useState(false);
  const [hovered, setHovered] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    (async () => {
      try {
        const items = await ontologyApi.list();
        setOntologies(items);
        // Default to the ontology with the most objects rather than simply the
        // newest: an empty or two-node graph tells the user nothing about
        // whether the feature works, and published-but-empty versions exist.
        if (items.length) {
          const richest = [...items].sort(
            (a, b) => (b.objectCount ?? 0) - (a.objectCount ?? 0),
          )[0];
          setSelected(richest.id);
        }
      } catch {
        message.error('加载本体列表失败');
      }
    })();
  }, []);

  const loadGraph = useCallback(async (ontologyId: number) => {
    setLoading(true);
    try {
      setGraph(await graphApi.getOntologyGraph(ontologyId));
    } catch {
      message.error('加载知识图谱失败');
      setGraph(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selected != null) void loadGraph(selected);
  }, [selected, loadGraph]);

  const positioned = useMemo(() => (graph ? layout(graph) : []), [graph]);
  const byCode = useMemo(() => new Map(positioned.map(node => [node.code, node])), [positioned]);

  const visible = useMemo(() => {
    if (!showIssuesOnly) return positioned;
    return positioned.filter(node => node.unbound || node.ruleCount === 0 || node.degree === 0);
  }, [positioned, showIssuesOnly]);
  const visibleCodes = useMemo(() => new Set(visible.map(node => node.code)), [visible]);

  const hoveredNode = hovered ? byCode.get(hovered) : undefined;

  return (
    <div>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap' }}>
        <div>
          <Title level={4} style={{ marginBottom: 4 }}>知识图谱预览</Title>
          <Text type="secondary">业务对象与关系的图结构，用于发现建模缺口</Text>
        </div>
        <Space>
          <Text type="secondary">只看有问题的对象</Text>
          <Switch checked={showIssuesOnly} onChange={setShowIssuesOnly} />
          <Select
            style={{ width: 260 }}
            placeholder="选择本体"
            value={selected ?? undefined}
            onChange={setSelected}
            options={ontologies.map(item => ({
              value: item.id,
              label: `${item.name} v${item.version}${item.status === 'published' ? '（已发布）' : ''}`,
            }))}
          />
        </Space>
      </Space>

      {loading && <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>}

      {!loading && graph && graph.nodes.length === 0 && (
        <Empty
          description={
            <span>
              该本体尚无业务对象。请先接入数据源并生成本体草案。
            </span>
          }
        />
      )}

      {!loading && graph && graph.nodes.length > 0 && (
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={17}>
            <Card size="small" styles={{ body: { padding: 8 } }}>
              <svg
                ref={svgRef}
                viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
                style={{ width: '100%', height: 'auto', background: '#fafcff', borderRadius: 6 }}
                role="img"
                aria-label={`${graph.ontology.name} 的业务对象关系图，共 ${graph.stats.nodeCount} 个对象、${graph.stats.edgeCount} 条关系`}
              >
                <defs>
                  <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="#9bb0c9" />
                  </marker>
                </defs>

                {graph.edges.map(edge => {
                  const from = byCode.get(edge.source);
                  const to = byCode.get(edge.target);
                  if (!from || !to) return null;
                  if (!visibleCodes.has(edge.source) || !visibleCodes.has(edge.target)) return null;
                  const active = hovered === edge.source || hovered === edge.target;

                  if (edge.source === edge.target) {
                    // Self-reference (a hierarchy such as parent_id) drawn as a loop.
                    const r = nodeRadius(from);
                    return (
                      <path
                        key={edge.id}
                        d={`M ${from.x} ${from.y - r} a ${r} ${r} 0 1 1 ${r * 0.6} ${-r * 0.2}`}
                        fill="none"
                        stroke={active ? '#1677ff' : '#9bb0c9'}
                        strokeWidth={active ? 2 : 1.2}
                        markerEnd="url(#arrow)"
                      />
                    );
                  }

                  const angle = Math.atan2(to.y - from.y, to.x - from.x);
                  const x2 = to.x - Math.cos(angle) * (nodeRadius(to) + 8);
                  const y2 = to.y - Math.sin(angle) * (nodeRadius(to) + 8);
                  return (
                    <g key={edge.id}>
                      <line
                        x1={from.x}
                        y1={from.y}
                        x2={x2}
                        y2={y2}
                        stroke={active ? '#1677ff' : '#9bb0c9'}
                        strokeWidth={active ? 2 : 1.2}
                        markerEnd="url(#arrow)"
                      />
                      {active && edge.foreignKey && (
                        <text
                          x={(from.x + x2) / 2}
                          y={(from.y + y2) / 2 - 5}
                          fontSize={11}
                          fill="#1677ff"
                          textAnchor="middle"
                        >
                          {edge.foreignKey}
                        </text>
                      )}
                    </g>
                  );
                })}

                {visible.map(node => (
                  <g
                    key={node.code}
                    onMouseEnter={() => setHovered(node.code)}
                    onMouseLeave={() => setHovered(null)}
                    style={{ cursor: 'pointer' }}
                  >
                    <circle
                      cx={node.x}
                      cy={node.y}
                      r={nodeRadius(node)}
                      fill={nodeFill(node)}
                      opacity={hovered && hovered !== node.code ? 0.45 : 0.9}
                      stroke="#fff"
                      strokeWidth={2}
                    />
                    <text
                      x={node.x}
                      y={node.y + nodeRadius(node) + 14}
                      fontSize={12}
                      fill="#1f2937"
                      textAnchor="middle"
                    >
                      {node.name || node.code}
                    </text>
                  </g>
                ))}
              </svg>

              <Space wrap size={[16, 4]} style={{ padding: '8px 4px 2px' }}>
                <Space size={4}><span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 5, background: '#1677ff' }} /><Text style={{ fontSize: 12 }}>正常</Text></Space>
                <Space size={4}><span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 5, background: '#faad14' }} /><Text style={{ fontSize: 12 }}>无规则（不产出判定）</Text></Space>
                <Space size={4}><span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 5, background: '#ff4d4f' }} /><Text style={{ fontSize: 12 }}>未绑定来源表</Text></Space>
                <Text type="secondary" style={{ fontSize: 12 }}>圆圈大小表示关联数量 · 悬停显示外键</Text>
              </Space>
            </Card>
          </Col>

          <Col xs={24} lg={7}>
            <Card size="small" title="图结构" style={{ marginBottom: 16 }}>
              <Descriptions column={1} size="small">
                <Descriptions.Item label="业务对象">{graph.stats.nodeCount}</Descriptions.Item>
                <Descriptions.Item label="关系">{graph.stats.edgeCount}</Descriptions.Item>
                <Descriptions.Item label="领域">{graph.ontology.domain || '—'}</Descriptions.Item>
                <Descriptions.Item label="版本">
                  {graph.ontology.version}
                  <Tag color={graph.ontology.status === 'published' ? 'green' : 'blue'} style={{ marginLeft: 8 }}>
                    {graph.ontology.status}
                  </Tag>
                </Descriptions.Item>
              </Descriptions>
            </Card>

            {hoveredNode ? (
              <Card size="small" title={hoveredNode.name || hoveredNode.code}>
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="编码"><Text code>{hoveredNode.code}</Text></Descriptions.Item>
                  <Descriptions.Item label="来源表">{hoveredNode.sourceTable || '未绑定'}</Descriptions.Item>
                  <Descriptions.Item label="属性">{hoveredNode.attributeCount}</Descriptions.Item>
                  <Descriptions.Item label="规则">{hoveredNode.ruleCount}</Descriptions.Item>
                  <Descriptions.Item label="关联">{hoveredNode.degree}</Descriptions.Item>
                </Descriptions>
              </Card>
            ) : (
              <Card size="small" title="建模缺口">
                {graph.stats.isolatedObjects.length === 0 && graph.stats.objectsWithoutRules.length === 0 ? (
                  <Text type="secondary" style={{ fontSize: 13 }}>未发现孤立对象或缺失规则。</Text>
                ) : (
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    {graph.stats.isolatedObjects.length > 0 && (
                      <div>
                        <Text strong style={{ fontSize: 13 }}>孤立对象（无任何关联）</Text>
                        <div style={{ marginTop: 4 }}>
                          {graph.stats.isolatedObjects.map(code => <Tag key={code}>{code}</Tag>)}
                        </div>
                      </div>
                    )}
                    {graph.stats.objectsWithoutRules.length > 0 && (
                      <div>
                        <Text strong style={{ fontSize: 13 }}>无规则对象（不产出判定）</Text>
                        <div style={{ marginTop: 4 }}>
                          {graph.stats.objectsWithoutRules.slice(0, 12).map(code => <Tag color="orange" key={code}>{code}</Tag>)}
                        </div>
                      </div>
                    )}
                  </Space>
                )}
              </Card>
            )}

            <Alert
              type="info"
              showIcon
              style={{ marginTop: 16 }}
              message="关系表达力限制"
              description={graph.notes.limitation}
            />
          </Col>
        </Row>
      )}
    </div>
  );
};

export default OntologyGraphPage;
