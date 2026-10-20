import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Col, Empty, List, Progress, Row, Space, Spin, Statistic, Table, Tag, Typography, message } from 'antd';
import { DatabaseOutlined, MessageOutlined, ReloadOutlined, RightOutlined, RocketOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { requestErrorMessage, workbenchApi } from '../../api';
import { DECISION_STATUS, DECISION_TYPE } from '../../i18n/labels';
import { codedText, countText } from '../../i18n/text';
import { useLabel, useT } from '../../i18n/locale';
import type { Workbench, WorkbenchActionItem } from '../../types';
import type { MessageKey } from '../../i18n/messages';

const { Title, Text, Paragraph } = Typography;

/**
 * Workbench: answers "what should I do next" in one screen.
 *
 * Previously that question required visiting six screens. Everything here is a
 * read-only projection of existing state, and every number links to the screen
 * where it can be acted on -- a dashboard of figures nobody can act on is just
 * decoration.
 */

// Keys, not labels: a label written here would be fixed at import, in whichever language
// the bundle happened to start in.
const SEVERITY_META: Record<WorkbenchActionItem['severity'], { color: string; labelKey: MessageKey }> = {
  blocker: { color: 'red', labelKey: 'workbench.severity.blocker' },
  warning: { color: 'orange', labelKey: 'workbench.severity.warning' },
  info: { color: 'blue', labelKey: 'workbench.severity.info' },
};

// The server sends each item's sentence in Chinese and a stable `code` beside it. A code
// this console knows is rendered in the reader's language; one it does not know keeps the
// server's sentence, which is the right default -- a sentence in the wrong language beats a
// ⟦workbench.item.something.title⟧ in any language.
const ITEM_CODES: Record<string, { title: string; detail: string }> = {
  no_data_source: { title: 'workbench.item.no_data_source.title', detail: 'workbench.item.no_data_source.detail' },
  unscanned_data_source: { title: 'workbench.item.unscanned_data_source.title', detail: 'workbench.item.unscanned_data_source.detail' },
  no_ontology: { title: 'workbench.item.no_ontology.title', detail: 'workbench.item.no_ontology.detail' },
  pending_mappings: { title: 'workbench.item.pending_mappings.title', detail: 'workbench.item.pending_mappings.detail' },
  unbound_objects: { title: 'workbench.item.unbound_objects.title', detail: 'workbench.item.unbound_objects.detail' },
  no_rules: { title: 'workbench.item.no_rules.title', detail: 'workbench.item.no_rules.detail' },
  objects_without_rules: { title: 'workbench.item.objects_without_rules.title', detail: 'workbench.item.objects_without_rules.detail' },
  reviewable_transitions: { title: 'workbench.item.reviewable_transitions.title', detail: 'workbench.item.reviewable_transitions.detail' },
  incorrect_answers_reported: { title: 'workbench.item.incorrect_answers_reported.title', detail: 'workbench.item.incorrect_answers_reported.detail' },
  escalated_conversations: { title: 'workbench.item.escalated_conversations.title', detail: 'workbench.item.escalated_conversations.detail' },
  open_feedback: { title: 'workbench.item.open_feedback.title', detail: 'workbench.item.open_feedback.detail' },
};

const DECISION_COLOR: Record<string, string> = {
  approved: 'green',
  review: 'orange',
  blocked: 'red',
};

const WorkbenchPage: React.FC = () => {
  const navigate = useNavigate();
  const t = useT();
  const label = useLabel();

  /** The item's sentence in the reader's language, or the server's when the code is new. */
  const itemText = (item: WorkbenchActionItem, field: 'title' | 'detail'): string => {
    const keys = ITEM_CODES[item.code];
    if (!keys) return item[field];
    // The count-bearing titles have an English singular (`<key>.one`); the details do not take
    // a count at all. Chinese has one form, so its two entries read the same.
    const key = field === 'title' && item.count === 1 ? `${keys.title}.one` : keys[field];
    return codedText(t, key, item[field], { count: item.count });
  };
  const [data, setData] = useState<Workbench | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (notify = false) => {
    setLoading(true);
    try {
      setData(await workbenchApi.get());
      if (notify) message.success(t('workbench.refreshed'));
    } catch (error) {
      message.error(requestErrorMessage(error, t('workbench.loadFailed')));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !data) {
    return (
      <div style={{ textAlign: 'center', padding: '80px 0' }}>
        <Spin size="large" description={t('workbench.loading')} />
      </div>
    );
  }

  if (!data) {
    return <Alert type="error" showIcon title={t('workbench.loadFailedTitle')} description={t('workbench.loadFailedHint')} />;
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
          <Title level={4} style={{ marginBottom: 4 }}>{t('workbench.title')}</Title>
          <Text type="secondary">{t('workbench.subtitle')}</Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => void load(true)} loading={loading}>{t('shell.common.refresh')}</Button>
      </Space>

      <Card
        title={t('workbench.startTaskTitle')}
        style={{ marginBottom: 16 }}
        extra={<Text type="secondary">{t('workbench.startTaskHint')}</Text>}
      >
        <Row gutter={[12, 12]}>
          <Col xs={24} md={8}>
            <Button block size="large" icon={<RocketOutlined />} onClick={() => navigate('/demo')}>
              {t('workbench.demoButton')}
            </Button>
            <Text type="secondary" style={{ display: 'block', marginTop: 6, fontSize: 12 }}>
              {t('workbench.demoHint')}
            </Text>
          </Col>
          <Col xs={24} md={8}>
            <Button block size="large" icon={<DatabaseOutlined />} onClick={() => navigate('/datasource')}>
              {t('workbench.datasourceButton')}
            </Button>
            <Text type="secondary" style={{ display: 'block', marginTop: 6, fontSize: 12 }}>
              {t('workbench.datasourceHint')}
            </Text>
          </Col>
          <Col xs={24} md={8}>
            <Button block size="large" icon={<MessageOutlined />} onClick={() => navigate('/chat')}>
              {t('workbench.chatButton')}
            </Button>
            <Text type="secondary" style={{ display: 'block', marginTop: 6, fontSize: 12 }}>
              {t('workbench.chatHint')}
            </Text>
          </Col>
        </Row>
      </Card>

      {actionItems.length === 0 ? (
        <Alert
          type="success"
          showIcon
          title={t('workbench.noActionItems')}
          description={t('workbench.noActionItemsHint')}
          style={{ marginBottom: 16 }}
        />
      ) : (
        <Card
          title={
            <Space>
              <span>{t('workbench.actionItemsTitle')}</span>
              {summary.blockers > 0 && <Tag color="red">{t('workbench.blockersTag', { count: summary.blockers })}</Tag>}
              {summary.warnings > 0 && <Tag color="orange">{t('workbench.warningsTag', { count: summary.warnings })}</Tag>}
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
                    {t('workbench.openItem')} <RightOutlined />
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  avatar={<Tag color={SEVERITY_META[item.severity].color}>{t(SEVERITY_META[item.severity].labelKey)}</Tag>}
                  title={itemText(item, 'title')}
                  description={itemText(item, 'detail')}
                />
              </List.Item>
            )}
          />
        </Card>
      )}

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card size="small">
            <Statistic title={t('workbench.dataSources')} value={dataSources.total} suffix={t('workbench.countSuffix')} />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t('workbench.tables', { count: dataSources.tables })} · {dataSources.unscanned ? t('workbench.unscanned', { count: dataSources.unscanned }) : t('workbench.allScanned')}
              {dataSources.withBusinessApi ? ` · ${t('workbench.withBusinessApi', { count: dataSources.withBusinessApi })}` : ''}
            </Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card size="small">
            <Statistic title={t('workbench.businessObjects')} value={ontologies.objects} suffix={t('workbench.countSuffix')} />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {countText('workbench.relations', ontologies.relations, t)} · {countText('workbench.publishedOntologies', ontologies.published, t)} · {countText('workbench.draftOntologies', ontologies.draft, t)}
            </Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card size="small">
            <Statistic
              title={t('workbench.businessRules')}
              value={rules.total}
              styles={rules.total === 0 ? { content: { color: '#cf1322' } } : undefined}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t('workbench.blockingRules', { count: rules.blocking })} · {t('workbench.advisoryRules', { count: rules.warning + rules.info })}
            </Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card size="small">
            <Statistic
              title={t('workbench.decisionLog')}
              value={decisions.total}
              styles={decisions.blocked ? { content: { color: '#cf1322' } } : undefined}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t('workbench.decisionsBlocked', { count: decisions.blocked })} · {t('workbench.decisionsReview', { count: decisions.review })} · {t('workbench.decisionsApproved', { count: decisions.approved })}
            </Text>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={10}>
          <Card title={t('workbench.governanceProgress')} size="small" style={{ marginBottom: 16 }}>
            <Paragraph style={{ marginBottom: 8 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>{t('workbench.mappingGate')}</Text>
            </Paragraph>
            <Progress
              percent={mappingProgress}
              status={governance.pendingMappings ? 'active' : 'success'}
              format={() => `${governance.confirmedMappings}/${totalMappings}`}
            />
            <Space orientation="vertical" size={4} style={{ marginTop: 12, width: '100%' }}>
              <Text style={{ fontSize: 13 }}>{t('workbench.pendingMappings', { count: governance.pendingMappings })}</Text>
              <Text style={{ fontSize: 13 }}>{t('workbench.auditEntries', { count: governance.auditEntries })}</Text>
              <Text style={{ fontSize: 13 }}>
                {t('workbench.valueMappings', { count: knowledge.confirmedValueMappings })}
                {knowledge.pendingValueMappings ? ` · ${t('workbench.valueMappingsPending', { count: knowledge.pendingValueMappings })}` : ''}
              </Text>
            </Space>
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card title={t('workbench.recentDecisions')} size="small" extra={<Button type="link" onClick={() => navigate('/governance')}>{t('workbench.viewAll')}</Button>}>
            {decisions.recent.length === 0 ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  <Space orientation="vertical" size={4}>
                    <Text strong>{t('workbench.noDecisions')}</Text>
                    <Text type="secondary" style={{ maxWidth: 420, display: 'inline-block' }}>
                      {t('workbench.noDecisionsHint')}
                    </Text>
                  </Space>
                }
              />
            ) : (
              <Table
                size="small"
                pagination={false}
                rowKey="decisionId"
                dataSource={decisions.recent}
                columns={[
                  {
                    title: t('workbench.column.status'),
                    dataIndex: 'status',
                    width: 88,
                    render: (status: string) => <Tag color={DECISION_COLOR[status] || 'default'}>{label(DECISION_STATUS, status)}</Tag>,
                  },
                  { title: t('workbench.column.object'), dataIndex: 'objectCode', width: 140, ellipsis: true },
                  { title: t('workbench.column.instance'), dataIndex: 'instanceId', width: 120, ellipsis: true },
                  { title: t('workbench.column.type'), dataIndex: 'decisionType', ellipsis: true, render: (v: string) => label(DECISION_TYPE, v) },
                  { title: t('workbench.column.createdAt'), dataIndex: 'createdAt', width: 160, ellipsis: true },
                ]}
              />
            )}
          </Card>
        </Col>
      </Row>

      <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 12 }}>
        {t('workbench.generatedAt', { time: data.generatedAt })}
      </Text>
    </div>
  );
};

export default WorkbenchPage;
