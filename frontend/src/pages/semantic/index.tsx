import { adviceTexts, explanationParts, joinSentences } from '../../i18n/text';
import React, { useEffect, useRef, useState } from 'react';
import { Card, Form, Input, Button, Typography, Alert, Descriptions, Tag, Divider, message, Tabs, Switch, Table, Space } from 'antd';
import { SearchOutlined, BugOutlined, RocketOutlined, AuditOutlined, MessageOutlined } from '@ant-design/icons';
import { automationApi, requestErrorMessage, semanticApi } from '../../api';
import { CONSISTENCY_STATUS, DECISION_STATUS, EXECUTION_STATUS, NEXT_ACTION } from '../../i18n/labels';
import { useLabel, useT } from '../../i18n/locale';
import type { InstanceExplainAttribute, InstanceExplainResult, InstanceAssessResult, OperationPreflightResult, OperationExecuteResult, DecisionConsistencyResult, NaturalLanguageQueryResult } from '../../types';
import { useSearchParams } from 'react-router-dom';
import { useTabParam } from '../../hooks/useTabParam';

const { Title, Paragraph } = Typography;
const { TabPane } = Tabs;

const SemanticService: React.FC = () => {
  const label = useLabel();
  const t = useT();
  const [tab, setTab] = useTabParam('natural');
/**
 * The kernel's recommendation, in the reader's language.
 *
 * The server sends `recommendationCode` beside the Chinese sentence -- see
 * `semantic_kernel._decision_from_results`. The code is what the console translates; the
 * sentence is the fallback for a code this build does not know.
 */
const recommendationText = (source: { recommendation?: string; recommendationCode?: string }): string => {
  const code = source.recommendationCode;
  if (!code) return source.recommendation ?? '';
  const translated = t(`semantic.recommendation.${code}` as never);
  return translated.startsWith('⟦') ? source.recommendation ?? '' : translated;
};

  const [explainResult, setExplainResult] = useState<InstanceExplainResult | null>(null);
  const [assessResult, setAssessResult] = useState<InstanceAssessResult | null>(null);
  const [consistencyResult, setConsistencyResult] = useState<DecisionConsistencyResult | null>(null);
  const [preflightResult, setPreflightResult] = useState<OperationPreflightResult | null>(null);
  const [executeResult, setExecuteResult] = useState<OperationExecuteResult | null>(null);
  const [naturalLanguageResult, setNaturalLanguageResult] = useState<NaturalLanguageQueryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [operationForm] = Form.useForm();
  const [explainForm] = Form.useForm();
  const [assessForm] = Form.useForm();
  const [consistencyForm] = Form.useForm();

  /**
   * The query in the URL, so an explanation is a place rather than a form somebody filled in.
   *
   * `/admin/semantic?tab=explain&object=contract&instance=1` opens that instance's
   * explanation: it can be pasted into a ticket, and the recipient sees the same thing the
   * sender did. It is also the only way `scripts/ui_smoke.py` can reach these two tables --
   * that check loads a route and reads the DOM, and cannot type into a form, so the columns
   * of the attributes table and the consistency table were outside it entirely.
   */
  const [searchParams] = useSearchParams();
  const fromUrl = {
    objectCode: searchParams.get('object') ?? '',
    instanceId: searchParams.get('instance') ?? '',
    ontologyId: searchParams.get('ontology') ?? '',
  };
  const ranFromUrl = useRef(false);

  const handleNaturalLanguageQuery = async (values: {
    question: string;
    ontologyId?: number;
    dataSourceId?: number;
    objectCode?: string;
    instanceId?: string;
  }) => {
    setLoading(true);
    try {
      const result = await semanticApi.query({
        question: values.question,
        ontologyId: values.ontologyId ? Number(values.ontologyId) : undefined,
        dataSourceId: values.dataSourceId ? Number(values.dataSourceId) : undefined,
        objectCode: values.objectCode,
        instanceId: values.instanceId,
      });
      setNaturalLanguageResult(result);
    } catch (error) {
      message.error(requestErrorMessage(error, t('semantic.queryFailed')));
    } finally {
      setLoading(false);
    }
  };

  const handleExplain = async (values: { objectCode: string; instanceId: string; ontologyId?: number }) => {
    setLoading(true);
    try {
      const result = await semanticApi.explain(values.objectCode, values.instanceId, values.ontologyId);
      setExplainResult(result);
    } catch (error) {
      message.error(requestErrorMessage(error, t('semantic.explainFailed')));
    } finally {
      setLoading(false);
    }
  };

  const handleAssess = async (values: { objectCode: string; instanceId: string; ontologyId?: number }) => {
    setLoading(true);
    try {
      const result = await semanticApi.assess(values.objectCode, values.instanceId, values.ontologyId);
      setAssessResult(result);
    } catch (error) {
      message.error(requestErrorMessage(error, t('semantic.assessFailed')));
    } finally {
      setLoading(false);
    }
  };

  const handleConsistency = async (values: { objectCode: string; ontologyId: number; instanceIds?: string; limit?: number }) => {
    setLoading(true);
    try {
      const instanceIds = values.instanceIds
        ? values.instanceIds.split(/[\n,，\s]+/).map(item => item.trim()).filter(Boolean)
        : undefined;
      const result = await semanticApi.consistency(values.objectCode, {
        ontologyId: Number(values.ontologyId),
        instanceIds,
        limit: Number(values.limit || 50),
      });
      setConsistencyResult(result);
    } catch (error) {
      message.error(requestErrorMessage(error, t('semantic.consistencyFailed')));
    } finally {
      setLoading(false);
    }
  };

  // Runs once, on arrival. A URL that names an object and an instance is a request for that
  // answer -- the alternative is a form that looks filled in and answers nothing, which is
  // what a reader of a shared link would get.
  useEffect(() => {
    if (ranFromUrl.current) return;
    ranFromUrl.current = true;
    const ontologyId = fromUrl.ontologyId ? Number(fromUrl.ontologyId) : undefined;
    if (tab === 'explain' && fromUrl.objectCode && fromUrl.instanceId) {
      explainForm.setFieldsValue({
        objectCode: fromUrl.objectCode,
        instanceId: fromUrl.instanceId,
        ontologyId: fromUrl.ontologyId,
      });
      void handleExplain({ objectCode: fromUrl.objectCode, instanceId: fromUrl.instanceId, ontologyId });
    } else if (tab === 'assess' && fromUrl.objectCode && fromUrl.instanceId) {
      assessForm.setFieldsValue({
        objectCode: fromUrl.objectCode,
        instanceId: fromUrl.instanceId,
        ontologyId: fromUrl.ontologyId,
      });
      void handleAssess({ objectCode: fromUrl.objectCode, instanceId: fromUrl.instanceId, ontologyId });
    } else if (tab === 'consistency' && fromUrl.objectCode && ontologyId) {
      consistencyForm.setFieldsValue({
        objectCode: fromUrl.objectCode,
        ontologyId: fromUrl.ontologyId,
        instanceIds: fromUrl.instanceId,
      });
      void handleConsistency({
        objectCode: fromUrl.objectCode,
        ontologyId,
        instanceIds: fromUrl.instanceId || undefined,
      });
    }
    // Deliberately once: the parameters are the arrival state, not a live binding. Re-running
    // on every keystroke in the address bar would fire a request per character.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handlePreflight = async (values: { operationCode: string; ontologyId: number; dataSourceId: number; instanceId: string; objectCode?: string }) => {
    setLoading(true);
    try {
      const result = await automationApi.preflight(values.operationCode, {
        ontologyId: Number(values.ontologyId),
        dataSourceId: Number(values.dataSourceId),
        instanceId: values.instanceId,
        objectCode: values.objectCode,
      });
      setPreflightResult(result);
    } catch (error) {
      message.error(requestErrorMessage(error, t('semantic.preflightFailed')));
    } finally {
      setLoading(false);
    }
  };

  const decisionColor = (decision: string) => {
    if (decision === 'approved') return 'green';
    if (decision === 'review') return 'orange';
    return 'red';
  };

  const consistencyColor = (status: string) => {
    if (status === 'consistent') return 'green';
    if (status === 'mixed') return 'orange';
    return 'red';
  };

  const consistencyColumns = [
    {
      title: t('semantic.instanceId'),
      dataIndex: 'instanceId',
      key: 'instanceId',
    },
    {
      title: t('semantic.decision'),
      dataIndex: 'decision',
      key: 'decision',
      render: (decision: string) => <Tag color={decisionColor(decision)}>{label(DECISION_STATUS, decision)}</Tag>,
    },
    {
      title: t('semantic.failedRuleCount'),
      dataIndex: 'failedRuleCount',
      key: 'failedRuleCount',
      width: 110,
    },
    {
      title: t('semantic.failedRules'),
      dataIndex: 'failedRules',
      key: 'failedRules',
      render: (rules: string[]) => rules.length ? rules.map(rule => <Tag color="red" key={rule}>{rule}</Tag>) : '-',
    },
    {
      title: t('semantic.decisionId'),
      dataIndex: 'decisionId',
      key: 'decisionId',
    },
  ];

  const handleExecute = async () => {
    const values = await operationForm.validateFields();
    setLoading(true);
    try {
      const payload = values.payloadJson ? JSON.parse(values.payloadJson) : {};
      const result = await automationApi.execute(values.operationCode, {
        ontologyId: Number(values.ontologyId),
        dataSourceId: Number(values.dataSourceId),
        instanceId: values.instanceId,
        objectCode: values.objectCode,
        actor: values.actor || 'console_user',
        dryRun: values.dryRun !== false,
        payload,
      });
      setExecuteResult(result);
    } catch (error) {
      message.error(error instanceof SyntaxError ? t('semantic.invalidPayload') : t('semantic.executeFailed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <Title level={3}>{t('semantic.title')}</Title>
      <Paragraph type="secondary">
        {t('semantic.subtitle')}
      </Paragraph>

      <Tabs activeKey={tab} onChange={setTab}>
        <TabPane tab={t('semantic.tab.natural')} key="natural">
          <Card>
            <Form
              layout="vertical"
              onFinish={handleNaturalLanguageQuery}
              // No prefilled object code and no prefilled question: this platform ships no industry
    // vocabulary (ADR-0003), and a prefilled `contract` showed a user in another domain a
    // value that meant nothing while looking like an answer they could just submit.
    initialValues={{ question: '', objectCode: '' }}
            >
              <Form.Item name="question" label={t('semantic.question')} rules={[{ required: true }]}>
                <Input.TextArea rows={3} placeholder={t('semantic.questionPlaceholder')} />
              </Form.Item>
              <Space wrap align="start">
                <Form.Item name="ontologyId" label={t('semantic.ontologyId')}>
                  <Input placeholder={t('semantic.optional')} type="number" style={{ width: 140 }} />
                </Form.Item>
                <Form.Item name="dataSourceId" label={t('semantic.dataSourceId')}>
                  <Input placeholder={t('semantic.optional')} type="number" style={{ width: 140 }} />
                </Form.Item>
                <Form.Item name="objectCode" label={t('semantic.objectCode')}>
                  <Input placeholder={t('semantic.objectCodePlaceholder')} style={{ width: 180 }} />
                </Form.Item>
                <Form.Item name="instanceId" label={t('semantic.instanceId')}>
                  <Input placeholder={t('semantic.optional')} style={{ width: 140 }} />
                </Form.Item>
              </Space>
              <Form.Item>
                <Button type="primary" icon={<MessageOutlined />} htmlType="submit" loading={loading}>
                  {t('semantic.askButton')}
                </Button>
              </Form.Item>
            </Form>

            {naturalLanguageResult && (
              <Card style={{ marginTop: 16 }} type="inner" title={t('semantic.answerTitle')}>
                <Alert
                  message={naturalLanguageResult.answer}
                  type={
                    naturalLanguageResult.intent === 'operation_preflight' || naturalLanguageResult.intent === 'compliance_assessment'
                      ? 'info'
                      : naturalLanguageResult.intent === 'unknown'
                      ? 'warning'
                      : 'success'
                  }
                />
                <Divider />
                <Descriptions column={3}>
                  <Descriptions.Item label={t('semantic.intent')}>{naturalLanguageResult.intent}</Descriptions.Item>
                  <Descriptions.Item label={t('semantic.confidence')}>{Math.round(naturalLanguageResult.confidence * 100)}%</Descriptions.Item>
                  <Descriptions.Item label={t('semantic.ontologyId')}>{naturalLanguageResult.resolved.ontologyId}</Descriptions.Item>
                  <Descriptions.Item label={t('semantic.dataSourceId')}>{naturalLanguageResult.resolved.dataSourceId || '-'}</Descriptions.Item>
                  <Descriptions.Item label={t('semantic.businessObject')}>{naturalLanguageResult.resolved.objectCode}</Descriptions.Item>
                  <Descriptions.Item label={t('semantic.instanceId')}>{naturalLanguageResult.resolved.instanceId || '-'}</Descriptions.Item>
                  <Descriptions.Item label={t('semantic.operationCode')}>{naturalLanguageResult.resolved.operationCode || '-'}</Descriptions.Item>
                </Descriptions>
                {naturalLanguageResult.nextActions.length > 0 && (
                  <>
                    <Divider />
                    <Title level={5}>{t('semantic.nextActions')}</Title>
                    {naturalLanguageResult.nextActions.map(action => (
                      <Tag color="blue" key={action}>{action}</Tag>
                    ))}
                  </>
                )}
                <Divider />
                <Title level={5}>{t('semantic.evidence')}</Title>
                <pre style={{ background: '#f5f5f5', padding: 16, borderRadius: 8, maxHeight: 360, overflow: 'auto' }}>
                  {JSON.stringify(naturalLanguageResult.evidence, null, 2)}
                </pre>
              </Card>
            )}
          </Card>
        </TabPane>

        <TabPane tab={t('semantic.tab.explain')} key="explain">
          <Card>
            <Form form={explainForm} layout="inline" onFinish={handleExplain}>
              <Form.Item name="objectCode" label={t('semantic.objectCode')} rules={[{ required: true }]}>
                <Input placeholder={t('semantic.objectCodePlaceholder')} />
              </Form.Item>
              <Form.Item name="instanceId" label={t('semantic.instanceId')} rules={[{ required: true }]}>
                <Input placeholder={t('semantic.idPlaceholder')} />
              </Form.Item>
              <Form.Item name="ontologyId" label={t('semantic.ontologyId')}>
                <Input placeholder={t('semantic.ontologyIdOptionalPlaceholder')} type="number" />
              </Form.Item>
              <Form.Item>
                <Button type="primary" icon={<SearchOutlined />} htmlType="submit" loading={loading}>
                  {t('semantic.explainButton')}
                </Button>
              </Form.Item>
            </Form>

            {explainResult && (
              <Card style={{ marginTop: 16 }} type="inner" title={t('semantic.explainResultTitle')}>
                <Descriptions column={2}>
                  <Descriptions.Item label={t('semantic.businessObject')}>{explainResult.objectCode}</Descriptions.Item>
                  <Descriptions.Item label={t('semantic.instanceId')}>{explainResult.instanceId}</Descriptions.Item>
                </Descriptions>
                <Divider />
                <Title level={5}>{t('semantic.attributes')}</Title>
                {/* This printed the attributes through `JSON.stringify` in a `<pre>`, because
                    the response type declared them as an untyped blob. A type that says
                    "some object" produces a renderer that treats it as one -- and the
                    fields being thrown away (the attribute name, the source column each
                    value was read from) are the ones that make the mapping checkable
                    rather than asserted. */}
                <Table
                  size="small"
                  rowKey="attributeCode"
                  pagination={false}
                  dataSource={explainResult.attributes}
                  columns={[
                    { title: t('semantic.attributeColumn'), dataIndex: 'attributeName', key: 'attributeName' },
                    {
                      title: t('semantic.codeColumn'),
                      dataIndex: 'attributeCode',
                      key: 'attributeCode',
                      render: (code: string) => <Typography.Text code>{code}</Typography.Text>,
                    },
                    {
                      title: t('semantic.sourceColumn'),
                      key: 'source',
                      render: (_: unknown, row: InstanceExplainAttribute) =>
                        // A derived attribute has no column behind it, and saying so is the
                        // explanation. An empty code tag here read as a missing value.
                        row.derived ? (
                          <Typography.Text code style={{ fontSize: 12 }}>
                            {row.derivedExpression}
                          </Typography.Text>
                        ) : row.sourceColumn ? (
                          <Typography.Text code>{row.sourceColumn}</Typography.Text>
                        ) : (
                          <Typography.Text type="secondary">—</Typography.Text>
                        ),
                    },
                    {
                      title: t('semantic.valueColumn'),
                      key: 'value',
                      render: (_: unknown, row: InstanceExplainAttribute) => (
                        <Space size={4}>
                          <Typography.Text>{row.value === null || row.value === undefined ? t('semantic.emptyValue') : String(row.value)}</Typography.Text>
                          {row.unitName && <Tag>{row.unitName}</Tag>}
                        </Space>
                      ),
                    },
                  ]}
                />
                <Title level={5} style={{ marginTop: 16 }}>{t('semantic.explanation')}</Title>
                <Alert message={explanationParts(explainResult.explanationParts, t, explainResult.explanation)} type="info" />
                <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginTop: 8, marginBottom: 0 }}>
                  {t('semantic.objectsHint')}
                </Typography.Paragraph>
              </Card>
            )}
          </Card>
        </TabPane>

        <TabPane tab={t('semantic.tab.assess')} key="assess">
          <Card>
            <Form form={assessForm} layout="inline" onFinish={handleAssess}>
              <Form.Item name="objectCode" label={t('semantic.objectCode')} rules={[{ required: true }]}>
                <Input placeholder={t('semantic.objectCodePlaceholder')} />
              </Form.Item>
              <Form.Item name="instanceId" label={t('semantic.instanceId')} rules={[{ required: true }]}>
                <Input placeholder={t('semantic.idPlaceholder')} />
              </Form.Item>
              <Form.Item name="ontologyId" label={t('semantic.ontologyId')}>
                <Input placeholder={t('semantic.ontologyIdOptionalPlaceholder')} type="number" />
              </Form.Item>
              <Form.Item>
                <Button type="primary" icon={<BugOutlined />} htmlType="submit" loading={loading}>
                  {t('semantic.assessButton')}
                </Button>
              </Form.Item>
            </Form>

            {assessResult && (
              <Card style={{ marginTop: 16 }} type="inner" title={t('semantic.assessResultTitle')}>
                <Descriptions column={2}>
                  <Descriptions.Item label={t('semantic.businessObject')}>{assessResult.objectCode}</Descriptions.Item>
                  <Descriptions.Item label={t('semantic.instanceId')}>{assessResult.instanceId}</Descriptions.Item>
                  <Descriptions.Item label={t('semantic.decision')}>
                    <Tag color={
                      assessResult.decision === 'approved' ? 'green' :
                      assessResult.decision === 'review' ? 'orange' : 'red'
                    }>
                      {label(DECISION_STATUS, assessResult.decision)}
                    </Tag>
                  </Descriptions.Item>
                </Descriptions>
                <Divider />
                <Title level={5}>{t('semantic.rulesHit')}</Title>
                <ul>
                  {assessResult.rulesHit.map((rule, index) => (
                    <li key={index}>
                      <Tag color={rule.passed ? 'green' : 'red'}>{rule.passed ? t('semantic.rulePassed') : t('semantic.ruleFailed')}</Tag>
                      <strong>{rule.ruleName}</strong>{t('semantic.ruleSeparator')}{rule.message}
                    </li>
                  ))}
                </ul>
                <Divider />
                <Title level={5}>{t('semantic.explanation')}</Title>
                <Alert message={assessResult.explanation} type={assessResult.decision === 'approved' ? 'success' : assessResult.decision === 'review' ? 'warning' : 'error'} />
              </Card>
            )}
          </Card>
        </TabPane>

        <TabPane tab={t('semantic.tab.consistency')} key="consistency">
          <Card>
            <Form form={consistencyForm} layout="vertical" onFinish={handleConsistency} initialValues={{ limit: 50 }}>
              <Form.Item name="objectCode" label={t('semantic.objectCode')} rules={[{ required: true }]}>
                <Input placeholder={t('semantic.objectCodePlaceholder')} />
              </Form.Item>
              <Form.Item name="ontologyId" label={t('semantic.ontologyId')} rules={[{ required: true }]}>
                <Input placeholder={t('semantic.idPlaceholder')} type="number" />
              </Form.Item>
              <Form.Item name="limit" label={t('semantic.sampleLimit')}>
                <Input placeholder={t('semantic.sampleLimitPlaceholder')} type="number" />
              </Form.Item>
              <Form.Item name="instanceIds" label={t('semantic.instanceIds')}>
                <Input.TextArea rows={3} placeholder={t('semantic.instanceIdsPlaceholder')} />
              </Form.Item>
              <Form.Item>
                <Button type="primary" icon={<AuditOutlined />} htmlType="submit" loading={loading}>
                  {t('semantic.batchAssessButton')}
                </Button>
              </Form.Item>
            </Form>

            {consistencyResult && (
              <Card style={{ marginTop: 16 }} type="inner" title={t('semantic.consistencyResultTitle')}>
                <Descriptions column={4}>
                  <Descriptions.Item label={t('semantic.businessObject')}>{consistencyResult.objectCode}</Descriptions.Item>
                  <Descriptions.Item label={t('semantic.sampleSize')}>{consistencyResult.sampleSize}</Descriptions.Item>
                  <Descriptions.Item label={t('semantic.assessed')}>{consistencyResult.assessed}</Descriptions.Item>
                  <Descriptions.Item label={t('semantic.status')}>
                    <Tag color={consistencyColor(consistencyResult.status)}>
                      {label(CONSISTENCY_STATUS, consistencyResult.status)}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label={t('semantic.summaryApproved')}>{consistencyResult.summary.approved}</Descriptions.Item>
                  <Descriptions.Item label={t('semantic.summaryReview')}>{consistencyResult.summary.review}</Descriptions.Item>
                  <Descriptions.Item label={t('semantic.summaryBlocked')}>{consistencyResult.summary.blocked}</Descriptions.Item>
                  <Descriptions.Item label={t('semantic.summaryErrors')}>{consistencyResult.summary.errors}</Descriptions.Item>
                </Descriptions>
                {consistencyResult.nextActions.length > 0 && (
                  <>
                    <Divider />
                    <Alert
                      message={t('semantic.governanceAdvice')}
                      description={joinSentences(adviceTexts(consistencyResult.nextActions, consistencyResult.nextActionCodes, t, 'semantic'))}
                      type={consistencyResult.status === 'consistent' ? 'success' : 'warning'}
                    />
                  </>
                )}
                {consistencyResult.ruleFailures.length > 0 && (
                  <>
                    <Divider />
                    <Title level={5}>{t('semantic.ruleFailureDistribution')}</Title>
                    {consistencyResult.ruleFailures.map(item => (
                      <Tag color="red" key={item.ruleCode}>{item.ruleCode}: {item.failures}</Tag>
                    ))}
                  </>
                )}
                <Divider />
                <Table
                  columns={consistencyColumns}
                  dataSource={consistencyResult.items}
                  rowKey="instanceId"
                  pagination={false}
                />
                {consistencyResult.errors.length > 0 && (
                  <>
                    <Divider />
                    <Alert
                      message={t('semantic.assessmentErrors')}
                      description={consistencyResult.errors.map(item => `${item.instanceId}: ${item.error}`).join(t('semantic.listSeparator'))}
                      type="error"
                    />
                  </>
                )}
              </Card>
            )}
          </Card>
        </TabPane>

        <TabPane tab={t('semantic.tab.preflight')} key="preflight">
          <Card>
            <Form form={operationForm} layout="vertical" onFinish={handlePreflight} initialValues={{ dryRun: true }}>
              <Form.Item name="operationCode" label={t('semantic.operationCode')} rules={[{ required: true }]}>
                <Input placeholder={t('semantic.operationCodePlaceholder')} />
              </Form.Item>
              <Form.Item name="ontologyId" label={t('semantic.ontologyId')} rules={[{ required: true }]}>
                <Input placeholder={t('semantic.idPlaceholder')} type="number" />
              </Form.Item>
              <Form.Item name="dataSourceId" label={t('semantic.dataSourceId')} rules={[{ required: true }]}>
                <Input placeholder={t('semantic.idPlaceholder')} type="number" />
              </Form.Item>
              <Form.Item name="instanceId" label={t('semantic.instanceId')} rules={[{ required: true }]}>
                <Input placeholder={t('semantic.idPlaceholder')} />
              </Form.Item>
              <Form.Item name="objectCode" label={t('semantic.objectCode')}>
                <Input placeholder={t('semantic.objectCodeOptionalPlaceholder')} />
              </Form.Item>
              <Form.Item name="actor" label={t('semantic.actor')}>
                <Input placeholder={t('semantic.actorPlaceholder')} />
              </Form.Item>
              <Form.Item name="payloadJson" label={t('semantic.payloadJson')}>
                <Input.TextArea rows={4} placeholder={t('semantic.payloadPlaceholder')} />
              </Form.Item>
              <Form.Item name="dryRun" label={t('semantic.dryRun')} valuePropName="checked">
                <Switch />
              </Form.Item>
              <Form.Item>
                <Button type="primary" icon={<RocketOutlined />} htmlType="submit" loading={loading} style={{ marginRight: 8 }}>
                  {t('semantic.preflightButton')}
                </Button>
                <Button icon={<RocketOutlined />} onClick={handleExecute} loading={loading}>
                  {t('semantic.executeButton')}
                </Button>
              </Form.Item>
            </Form>

            {preflightResult && (
              <Card style={{ marginTop: 16 }} type="inner" title={t('semantic.preflightResultTitle')}>
                <Descriptions column={2}>
                  <Descriptions.Item label={t('semantic.operationCode')}>{preflightResult.operationCode}</Descriptions.Item>
                  <Descriptions.Item label={t('semantic.instanceId')}>{preflightResult.instanceId}</Descriptions.Item>
                  <Descriptions.Item label={t('semantic.decision')}>
                    <Tag color={
                      preflightResult.decision === 'approved' ? 'green' :
                      preflightResult.decision === 'review' ? 'orange' : 'red'
                    }>
                      {label(DECISION_STATUS, preflightResult.decision)}
                    </Tag>
                  </Descriptions.Item>
                </Descriptions>
                <Divider />
                <Title level={5}>{t('semantic.rulesHit')}</Title>
                <ul>
                  {preflightResult.rulesHit.map((rule, index) => (
                    <li key={index}>
                      <Tag color={rule.passed ? 'green' : 'red'}>{rule.passed ? t('semantic.rulePassed') : t('semantic.ruleFailed')}</Tag>
                      <strong>{rule.ruleName}</strong>{t('semantic.ruleSeparator')}{rule.message}
                    </li>
                  ))}
                </ul>
                <Divider />
                <Title level={5}>{t('semantic.recommendation')}</Title>
                <Alert
                  message={
                    recommendationText(preflightResult) ||
                    label(NEXT_ACTION, preflightResult.nextAction) ||
                    t('semantic.none')
                  }
                  type="info"
                />
              </Card>
            )}

            {executeResult && (
              <Card style={{ marginTop: 16 }} type="inner" title={t('semantic.executeResultTitle')}>
                <Descriptions column={2}>
                  <Descriptions.Item label={t('semantic.operationCode')}>{executeResult.operationCode}</Descriptions.Item>
                  <Descriptions.Item label={t('semantic.instanceId')}>{executeResult.instanceId}</Descriptions.Item>
                  <Descriptions.Item label={t('semantic.status')}>
                    <Tag color={executeResult.executed ? 'green' : executeResult.status === 'blocked_by_semantic_kernel' ? 'red' : 'blue'}>
                      {label(EXECUTION_STATUS, executeResult.status)}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label={t('semantic.decision')}>{label(DECISION_STATUS, executeResult.decision)}</Descriptions.Item>
                </Descriptions>
                <Divider />
                <Alert message={executeResult.message} type={executeResult.status === 'blocked_by_semantic_kernel' ? 'error' : 'success'} />
                {executeResult.execution && (
                  <>
                    <Divider />
                    <Title level={5}>{t('semantic.executionPlan')}</Title>
                    <pre style={{ background: '#f5f5f5', padding: 16, borderRadius: 8 }}>
                      {JSON.stringify(executeResult.execution, null, 2)}
                    </pre>
                  </>
                )}
              </Card>
            )}
          </Card>
        </TabPane>
      </Tabs>
    </div>
  );
};

export default SemanticService;
