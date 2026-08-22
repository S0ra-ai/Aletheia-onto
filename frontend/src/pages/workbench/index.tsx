import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Col, Empty, List, Progress, Row, Space, Spin, Statistic, Table, Tag, Typography, message } from 'antd';
import { ReloadOutlined, RightOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { workbenchApi } from '../../api';
import type { Workbench, WorkbenchActionItem } from '../../types';

const { Title, Text, Paragraph } = Typography;

/**
 * Workbench: answers "what should I do next" in one screen.
 *
 * Previously that question required visiting six screens. Everything here is a
 * read-only projection of existing state, and every number links to the screen
 * where it can be acted on -- a dashboard of figures nobody can act on is just
 * decoration.
 */

const SEVERITY_META: Record<WorkbenchActionItem['severity'], { color: string; label: string }> = {
  blocker: { color: 'red', label: '阻断' },
  warning: { color: 'orange', label: '待处理' },
  info: { color: 'blue', label: '提示' },
};

const DECISION_COLOR: Record<string, string> = {
  approved: 'green',
  review: 'orange',
  blocked: 'red',
};

const WorkbenchPage: React.FC = () => {
  const navigate = useNavigate();
  const [data, setData] = useState<Workbench | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (notify = false) => {
    setLoading(true);
    try {
      setData(await workbenchApi.get());
      if (notify) message.success('工作台已刷新');
    } catch {
      message.error('加载工作台失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !data) {
    return (
      <div style={{ textAlign: 'center', padding: '80px 0' }}>
        <Spin size="large" tip="正在汇总平台状态..." />
      </div>
    );
  }

  if (!data) {
    return <Alert type="error" showIcon message="无法加载工作台" description="请确认后端服务可用。" />;
  }

  const { dataSources, ontologies, governance, rules, decisions, knowledge, actionItems, summary } = data;
  // Confirmed mappings are what the release gate counts, so show progress
  // against the total rather than a bare pending number.
  const totalMappings = governance.pendingMappings + governance.confirmedMappings + governance.rejectedMappings;
  const mappingProgress = totalMappings ? Math.round((governance.confirmedMappings / totalMappings) * 100) : 0;

  return (
    <div>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <Title level={4} style={{ marginBottom: 4 }}>工作台</Title>
          <Text type="secondary">平台当前状态与待处理事项</Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => void load(true)} loading={loading}>刷新</Button>
      </Space>

      {actionItems.length === 0 ? (
        <Alert
          type="success"
          showIcon
          message="没有待处理事项"
          description="数据源已扫描、映射已审核、对象已配置规则。"
          style={{ marginBottom: 16 }}
        />
      ) : (
        <Card
          title={
            <Space>
              <span>待处理事项</span>
              {summary.blockers > 0 && <Tag color="red">{summary.blockers} 项阻断</Tag>}
              {summary.warnings > 0 && <Tag color="orange">{summary.warnings} 项待处理</Tag>}
            </Space>
          }
          style={{ marginBottom: 16 }}
        >
          <List
            dataSource={actionItems}
            renderItem={item => (
              <List.Item
                actions={[
                  <Button key="go" type="link" onClick={() => navigate(item.route)}>
                    去处理 <RightOutlined />
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  avatar={<Tag color={SEVERITY_META[item.severity].color}>{SEVERITY_META[item.severity].label}</Tag>}
                  title={item.title}
                  description={item.detail}
                />
              </List.Item>
            )}
          />
        </Card>
      )}

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card size="small">
            <Statistic title="数据源" value={dataSources.total} suffix={`/ ${dataSources.tables} 张表`} />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {dataSources.unscanned ? `${dataSources.unscanned} 个未扫描` : '全部已扫描'}
              {dataSources.withBusinessApi ? ` · ${dataSources.withBusinessApi} 个含业务 API` : ''}
            </Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card size="small">
            <Statistic title="业务对象" value={ontologies.objects} suffix={`/ ${ontologies.relations} 关系`} />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {ontologies.published} 个已发布本体 · {ontologies.draft} 个草案
            </Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card size="small">
            <Statistic
              title="业务规则"
              value={rules.total}
              valueStyle={rules.total === 0 ? { color: '#cf1322' } : undefined}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              阻断级 {rules.blocking} · 提示级 {rules.warning + rules.info}
            </Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card size="small">
            <Statistic
              title="决策留痕"
              value={decisions.total}
              valueStyle={decisions.blocked ? { color: '#cf1322' } : undefined}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              阻断 {decisions.blocked} · 复核 {decisions.review} · 通过 {decisions.approved}
            </Text>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={10}>
          <Card title="治理进度" size="small" style={{ marginBottom: 16 }}>
            <Paragraph style={{ marginBottom: 8 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>语义映射审核（发布门禁依据此项）</Text>
            </Paragraph>
            <Progress
              percent={mappingProgress}
              status={governance.pendingMappings ? 'active' : 'success'}
              format={() => `${governance.confirmedMappings}/${totalMappings}`}
            />
            <Space direction="vertical" size={4} style={{ marginTop: 12, width: '100%' }}>
              <Text style={{ fontSize: 13 }}>待审映射：{governance.pendingMappings}</Text>
              <Text style={{ fontSize: 13 }}>审计条目：{governance.auditEntries}</Text>
              <Text style={{ fontSize: 13 }}>
                值域映射：{knowledge.confirmedValueMappings} 已确认
                {knowledge.pendingValueMappings ? ` · ${knowledge.pendingValueMappings} 待确认` : ''}
              </Text>
            </Space>
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card title="最近决策" size="small" extra={<Button type="link" onClick={() => navigate('/governance')}>全部</Button>}>
            {decisions.recent.length === 0 ? (
              <Empty description="尚无决策记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <Table
                size="small"
                pagination={false}
                rowKey="decisionId"
                dataSource={decisions.recent}
                columns={[
                  {
                    title: '状态',
                    dataIndex: 'status',
                    width: 88,
                    render: (status: string) => <Tag color={DECISION_COLOR[status] || 'default'}>{status}</Tag>,
                  },
                  { title: '对象', dataIndex: 'objectCode', width: 140, ellipsis: true },
                  { title: '实例', dataIndex: 'instanceId', width: 120, ellipsis: true },
                  { title: '类型', dataIndex: 'decisionType', ellipsis: true },
                  { title: '时间', dataIndex: 'createdAt', width: 160, ellipsis: true },
                ]}
              />
            )}
          </Card>
        </Col>
      </Row>

      <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 12 }}>
        统计生成于 {data.generatedAt}
      </Text>
    </div>
  );
};

export default WorkbenchPage;
