import React, { useCallback, useEffect, useState } from 'react';
import { FEEDBACK_STATUS } from '../../i18n/labels';
import {
  Alert, Button, Card, Col, Empty, Row, Select, Space, Statistic, Table, Tag,
  Tooltip, Typography, message,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { conversationApi, feedbackApi, requestErrorMessage } from '../../api';
import { useLabel, useT } from '../../i18n/locale';
import type { AnswerFeedback, Conversation, FeedbackSummary } from '../../types';
import type { MessageKey } from '../../i18n/messages';

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

const RATING_META: Record<string, { color: string; labelKey: MessageKey }> = {
  incorrect: { color: 'red', labelKey: 'feedback.rating.incorrect' },
  unhelpful: { color: 'orange', labelKey: 'feedback.rating.unhelpful' },
  helpful: { color: 'green', labelKey: 'feedback.rating.helpful' },
};

const STATUS_COLOR: Record<string, string> = {
  open: 'orange',
  resolved: 'green',
  dismissed: 'default',
};

const FeedbackConsolePage: React.FC = () => {
  const label = useLabel();
  const navigate = useNavigate();
  const t = useT();
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
    } catch (error) {
      message.error(requestErrorMessage(error, t('feedback.loadFailed')));
    } finally {
      setLoading(false);
    }
  }, [ratingFilter, statusFilter, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleResolve = async (item: AnswerFeedback, resolution: string) => {
    try {
      await feedbackApi.resolve(item.id, resolution);
      message.success(resolution === 'resolved' ? t('feedback.resolveDone') : t('feedback.dismissDone'));
      await load();
    } catch (error) {
      message.error(requestErrorMessage(error, t('feedback.actionFailed')));
    }
  };

  return (
    <div>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap' }}>
        <div>
          <Title level={4} style={{ marginBottom: 4 }}>{t('feedback.title')}</Title>
          <Text type="secondary">{t('feedback.subtitle')}</Text>
        </div>
        <Space>
          <Select
            style={{ width: 150 }}
            value={ratingFilter}
            onChange={setRatingFilter}
            options={[
              { value: '', label: t('feedback.allRatings') },
              { value: 'incorrect', label: t('feedback.rating.incorrect') },
              { value: 'unhelpful', label: t('feedback.rating.unhelpful') },
              { value: 'helpful', label: t('feedback.rating.helpful') },
            ]}
          />
          <Select
            style={{ width: 140 }}
            value={statusFilter}
            onChange={setStatusFilter}
            // Derived from the vocabulary rather than retyped: the inline list had two of
            // the three states, so 已忽略 could not be filtered for at all.
            options={[
              ...Object.entries(FEEDBACK_STATUS).map(([value]) => ({ value, label: label(FEEDBACK_STATUS, value) })),
              { value: '', label: t('feedback.allStatuses') },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>{t('shell.common.refresh')}</Button>
        </Space>
      </Space>

      {summary && (
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={6}>
            <Card size="small">
              <Statistic
                title={t('feedback.statIncorrect')}
                value={summary.incorrect}
                valueStyle={summary.incorrect ? { color: '#cf1322' } : undefined}
              />
              <Text type="secondary" style={{ fontSize: 12 }}>{t('feedback.statIncorrectHint')}</Text>
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small"><Statistic title={t('feedback.rating.unhelpful')} value={summary.unhelpful} /></Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small"><Statistic title={t('feedback.rating.helpful')} value={summary.helpful} /></Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small">
              <Statistic title={t('feedback.statCorrections')} value={summary.corrections} />
              <Text type="secondary" style={{ fontSize: 12 }}>{t('feedback.statCorrectionsHint')}</Text>
            </Card>
          </Col>
        </Row>
      )}

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message={t('feedback.correctionsAlertTitle')}
        description={t('feedback.correctionsAlertBody')}
      />

      {escalated.length > 0 && (
        <Card
          size="small"
          title={<Space><span>{t('feedback.escalationQueue')}</span><Tag color="orange">{escalated.length}</Tag></Space>}
          style={{ marginBottom: 16 }}
        >
          <Table
            size="small"
            rowKey="sessionId"
            pagination={false}
            dataSource={escalated}
            columns={[
              { title: t('feedback.column.conversation'), dataIndex: 'title', ellipsis: true },
              { title: t('feedback.column.assignee'), dataIndex: 'escalatedTo', width: 120, render: (v: string) => v || '—' },
              { title: t('feedback.column.reason'), dataIndex: 'escalationReason', ellipsis: true },
              {
                title: '',
                key: 'go',
                width: 80,
                render: (_: unknown, row: Conversation) => (
                  <Button type="link" size="small" onClick={() => navigate(`/chat?session=${encodeURIComponent(row.sessionId)}`)}>
                    {t('feedback.view')}
                  </Button>
                ),
              },
            ]}
          />
        </Card>
      )}

      <Card size="small" title={t('feedback.itemsTitle', { count: items.length })}>
        {items.length === 0 ? (
          <Empty description={t('feedback.noItems')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
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
                      <Text strong>{t('feedback.commentLabel')}</Text>{row.comment}
                    </Paragraph>
                  )}
                  {row.correction && (
                    <Paragraph style={{ marginBottom: 6 }}>
                      <Text strong>{t('feedback.correctionLabel')}</Text>{row.correction}
                    </Paragraph>
                  )}
                  {row.decisionId && (
                    <Paragraph style={{ marginBottom: 0 }}>
                      <Text strong>{t('feedback.decisionLabel')}</Text><Text code>{row.decisionId}</Text>
                      <Text type="secondary" style={{ fontSize: 12, marginInlineStart: 8 }}>
                        {t('feedback.decisionHint')}
                      </Text>
                    </Paragraph>
                  )}
                  {!row.comment && !row.correction && !row.decisionId && (
                    <Text type="secondary">{t('feedback.noNote')}</Text>
                  )}
                </div>
              ),
            }}
            columns={[
              {
                title: t('feedback.column.rating'),
                dataIndex: 'rating',
                width: 110,
                render: (rating: string) => (
                  <Tag color={RATING_META[rating]?.color || 'default'}>
                    {RATING_META[rating] ? t(RATING_META[rating].labelKey) : rating}
                  </Tag>
                ),
              },
              {
                title: t('feedback.column.correction'),
                key: 'correction',
                width: 80,
                render: (_: unknown, row: AnswerFeedback) =>
                  row.correction ? <Tag color="blue">{t('feedback.hasCorrection')}</Tag> : <Text type="secondary">—</Text>,
              },
              {
                title: t('feedback.column.decision'),
                dataIndex: 'decisionId',
                width: 190,
                ellipsis: true,
                render: (value: string) =>
                  value ? (
                    <Tooltip title={t('feedback.decisionTooltip')}>
                      <Text code style={{ fontSize: 12 }}>{value}</Text>
                    </Tooltip>
                  ) : (
                    <Text type="secondary">—</Text>
                  ),
              },
              { title: t('feedback.column.actor'), dataIndex: 'actor', width: 110, render: (v: string) => v || t('feedback.anonymous') },
              {
                title: t('feedback.column.status'),
                dataIndex: 'status',
                width: 90,
                render: (status: string) => <Tag color={STATUS_COLOR[status] || 'default'}>{label(FEEDBACK_STATUS, status)}</Tag>,
              },
              { title: t('feedback.column.createdAt'), dataIndex: 'createdAt', width: 160, ellipsis: true },
              {
                title: '',
                key: 'action',
                width: 130,
                render: (_: unknown, row: AnswerFeedback) =>
                  row.status === 'open' ? (
                    <Space size={4}>
                      <Button type="link" size="small" onClick={() => void handleResolve(row, 'resolved')}>
                        {t('feedback.resolve')}
                      </Button>
                      <Button type="link" size="small" onClick={() => void handleResolve(row, 'dismissed')}>
                        {t('feedback.dismiss')}
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
