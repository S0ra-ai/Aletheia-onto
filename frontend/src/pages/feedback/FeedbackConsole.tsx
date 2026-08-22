import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert, Button, Card, Col, Empty, Row, Select, Space, Statistic, Table, Tag,
  Tooltip, Typography, message,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { conversationApi, feedbackApi } from '../../api';
import type { AnswerFeedback, Conversation, FeedbackSummary } from '../../types';

const { Title, Text, Paragraph } = Typography;

/**
 * Feedback console: closes the loop between an answer and whether it was right.
 *
 * Two things this screen deliberately does not do:
 *
 * - **No average satisfaction score.** An average tells you nothing about which
 *   answer to fix, and this project's premise is traceability to a specific case.
 *   Counts per rating, with "incorrect" first, are actionable.
 * - **No one-click "apply correction".** A correction is one user's claim, not a
 *   new rule. Promoting it goes through governance (ADR-0002), so the console
 *   shows the text and links to the decision rather than offering to apply it.
 */

const RATING_META: Record<string, { color: string; label: string }> = {
  incorrect: { color: 'red', label: '结论错误' },
  unhelpful: { color: 'orange', label: '没有帮助' },
  helpful: { color: 'green', label: '有帮助' },
};

const STATUS_COLOR: Record<string, string> = {
  open: 'orange',
  resolved: 'green',
  dismissed: 'default',
};

const FeedbackConsolePage: React.FC = () => {
  const navigate = useNavigate();
  const [items, setItems] = useState<AnswerFeedback[]>([]);
  const [summary, setSummary] = useState<FeedbackSummary | null>(null);
  const [escalated, setEscalated] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(false);
  const [ratingFilter, setRatingFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('open');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [feedback, conversations] = await Promise.all([
        feedbackApi.list({ rating: ratingFilter || undefined, status: statusFilter || undefined }),
        conversationApi.list({ status: 'escalated' }),
      ]);
      setItems(feedback.items);
      setSummary(feedback.summary);
      setEscalated(conversations);
    } catch {
      message.error('加载反馈失败');
    } finally {
      setLoading(false);
    }
  }, [ratingFilter, statusFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleResolve = async (item: AnswerFeedback, resolution: string) => {
    try {
      await feedbackApi.resolve(item.id, resolution);
      message.success(resolution === 'resolved' ? '已标记为已处理' : '已忽略');
      await load();
    } catch {
      message.error('操作失败');
    }
  };

  return (
    <div>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap' }}>
        <div>
          <Title level={4} style={{ marginBottom: 4 }}>反馈闭环</Title>
          <Text type="secondary">用户对判定结论的评价、纠正建议与转人工队列</Text>
        </div>
        <Space>
          <Select
            style={{ width: 150 }}
            value={ratingFilter}
            onChange={setRatingFilter}
            options={[
              { value: '', label: '全部评价' },
              { value: 'incorrect', label: '结论错误' },
              { value: 'unhelpful', label: '没有帮助' },
              { value: 'helpful', label: '有帮助' },
            ]}
          />
          <Select
            style={{ width: 140 }}
            value={statusFilter}
            onChange={setStatusFilter}
            options={[
              { value: 'open', label: '待处理' },
              { value: 'resolved', label: '已处理' },
              { value: '', label: '全部状态' },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>刷新</Button>
        </Space>
      </Space>

      {summary && (
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={6}>
            <Card size="small">
              <Statistic
                title="标记为错误"
                value={summary.incorrect}
                valueStyle={summary.incorrect ? { color: '#cf1322' } : undefined}
              />
              <Text type="secondary" style={{ fontSize: 12 }}>最强的复核信号</Text>
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small"><Statistic title="没有帮助" value={summary.unhelpful} /></Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small"><Statistic title="有帮助" value={summary.helpful} /></Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small">
              <Statistic title="纠正建议" value={summary.corrections} />
              <Text type="secondary" style={{ fontSize: 12 }}>需人工判断是否入规则</Text>
            </Card>
          </Col>
        </Row>
      )}

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="纠正建议不会自动生效"
        description="用户提交的纠正是一方主张，不是新规则。若确认应当调整判定，请在业务规则或文档知识库中走正常的治理与发布流程。"
      />

      {escalated.length > 0 && (
        <Card
          size="small"
          title={<Space><span>转人工队列</span><Tag color="orange">{escalated.length}</Tag></Space>}
          style={{ marginBottom: 16 }}
        >
          <Table
            size="small"
            rowKey="sessionId"
            pagination={false}
            dataSource={escalated}
            columns={[
              { title: '会话', dataIndex: 'title', ellipsis: true },
              { title: '指派给', dataIndex: 'escalatedTo', width: 120, render: (v: string) => v || '—' },
              { title: '原因', dataIndex: 'escalationReason', ellipsis: true },
              {
                title: '',
                key: 'go',
                width: 80,
                render: (_: unknown, row: Conversation) => (
                  <Button type="link" size="small" onClick={() => navigate(`/conversations?session=${row.sessionId}`)}>
                    查看
                  </Button>
                ),
              },
            ]}
          />
        </Card>
      )}

      <Card size="small" title={`反馈条目（${items.length}）`}>
        {items.length === 0 ? (
          <Empty description="没有符合条件的反馈" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <Table
            size="small"
            rowKey="id"
            dataSource={items}
            pagination={{ pageSize: 10, size: 'small' }}
            expandable={{
              expandedRowRender: (row: AnswerFeedback) => (
                <div style={{ paddingInlineStart: 8 }}>
                  {row.comment && (
                    <Paragraph style={{ marginBottom: 6 }}>
                      <Text strong>用户评论：</Text>{row.comment}
                    </Paragraph>
                  )}
                  {row.correction && (
                    <Paragraph style={{ marginBottom: 6 }}>
                      <Text strong>纠正建议：</Text>{row.correction}
                    </Paragraph>
                  )}
                  {row.decisionId && (
                    <Paragraph style={{ marginBottom: 0 }}>
                      <Text strong>关联决策：</Text><Text code>{row.decisionId}</Text>
                      <Text type="secondary" style={{ fontSize: 12, marginInlineStart: 8 }}>
                        可在治理与留痕中查看该判定的规则与证据链
                      </Text>
                    </Paragraph>
                  )}
                  {!row.comment && !row.correction && !row.decisionId && (
                    <Text type="secondary">该反馈没有附加说明。</Text>
                  )}
                </div>
              ),
            }}
            columns={[
              {
                title: '评价',
                dataIndex: 'rating',
                width: 110,
                render: (rating: string) => (
                  <Tag color={RATING_META[rating]?.color || 'default'}>
                    {RATING_META[rating]?.label || rating}
                  </Tag>
                ),
              },
              {
                title: '纠正',
                key: 'correction',
                width: 80,
                render: (_: unknown, row: AnswerFeedback) =>
                  row.correction ? <Tag color="blue">有</Tag> : <Text type="secondary">—</Text>,
              },
              {
                title: '关联决策',
                dataIndex: 'decisionId',
                width: 190,
                ellipsis: true,
                render: (value: string) =>
                  value ? (
                    <Tooltip title="反馈已关联到具体判定，可回溯规则与证据">
                      <Text code style={{ fontSize: 12 }}>{value}</Text>
                    </Tooltip>
                  ) : (
                    <Text type="secondary">—</Text>
                  ),
              },
              { title: '提交人', dataIndex: 'actor', width: 110, render: (v: string) => v || '匿名' },
              {
                title: '状态',
                dataIndex: 'status',
                width: 90,
                render: (status: string) => <Tag color={STATUS_COLOR[status] || 'default'}>{status}</Tag>,
              },
              { title: '时间', dataIndex: 'createdAt', width: 160, ellipsis: true },
              {
                title: '',
                key: 'action',
                width: 130,
                render: (_: unknown, row: AnswerFeedback) =>
                  row.status === 'open' ? (
                    <Space size={4}>
                      <Button type="link" size="small" onClick={() => void handleResolve(row, 'resolved')}>
                        已处理
                      </Button>
                      <Button type="link" size="small" onClick={() => void handleResolve(row, 'dismissed')}>
                        忽略
                      </Button>
                    </Space>
                  ) : (
                    <Text type="secondary" style={{ fontSize: 12 }}>{row.resolvedBy || '—'}</Text>
                  ),
              },
            ]}
          />
        )}
      </Card>
    </div>
  );
};

export default FeedbackConsolePage;
