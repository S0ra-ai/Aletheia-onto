import React, { useState } from 'react';
import { Card, Form, Input, Button, Typography, Alert, Descriptions, Tag, Divider, message, Tabs, Switch, Table } from 'antd';
import { SearchOutlined, BugOutlined, RocketOutlined, AuditOutlined } from '@ant-design/icons';
import { semanticApi, automationApi } from '../../api';
import type { InstanceExplainResult, InstanceAssessResult, OperationPreflightResult, OperationExecuteResult, DecisionConsistencyResult } from '../../types';

const { Title, Paragraph } = Typography;
const { TabPane } = Tabs;

const SemanticService: React.FC = () => {
  const [explainResult, setExplainResult] = useState<InstanceExplainResult | null>(null);
  const [assessResult, setAssessResult] = useState<InstanceAssessResult | null>(null);
  const [consistencyResult, setConsistencyResult] = useState<DecisionConsistencyResult | null>(null);
  const [preflightResult, setPreflightResult] = useState<OperationPreflightResult | null>(null);
  const [executeResult, setExecuteResult] = useState<OperationExecuteResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [operationForm] = Form.useForm();

  const handleExplain = async (values: { objectCode: string; instanceId: string; ontologyId?: number }) => {
    setLoading(true);
    try {
      const result = await semanticApi.explain(values.objectCode, values.instanceId, values.ontologyId);
      setExplainResult(result);
    } catch (error) {
      message.error('语义解释失败');
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
      message.error('语义研判失败');
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
    } catch {
      message.error('决策一致性评估失败');
    } finally {
      setLoading(false);
    }
  };

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
      message.error('操作预检失败');
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
      title: '实例ID',
      dataIndex: 'instanceId',
      key: 'instanceId',
    },
    {
      title: '决策',
      dataIndex: 'decision',
      key: 'decision',
      render: (decision: string) => <Tag color={decisionColor(decision)}>{decision}</Tag>,
    },
    {
      title: '失败规则数',
      dataIndex: 'failedRuleCount',
      key: 'failedRuleCount',
      width: 110,
    },
    {
      title: '失败规则',
      dataIndex: 'failedRules',
      key: 'failedRules',
      render: (rules: string[]) => rules.length ? rules.map(rule => <Tag color="red" key={rule}>{rule}</Tag>) : '-',
    },
    {
      title: '决策ID',
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
      message.error(error instanceof SyntaxError ? '请求载荷不是合法 JSON' : '操作执行失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <Title level={3}>语义服务</Title>
      <Paragraph type="secondary">
        提供实例解释、风险研判和操作预检能力
      </Paragraph>

      <Tabs defaultActiveKey="explain">
        <TabPane tab="实例解释" key="explain">
          <Card>
            <Form layout="inline" onFinish={handleExplain}>
              <Form.Item name="objectCode" label="业务对象编码" rules={[{ required: true }]}>
                <Input placeholder="例如：contract" />
              </Form.Item>
              <Form.Item name="instanceId" label="实例ID" rules={[{ required: true }]}>
                <Input placeholder="例如：1" />
              </Form.Item>
              <Form.Item name="ontologyId" label="本体ID">
                <Input placeholder="可选，默认为1" type="number" />
              </Form.Item>
              <Form.Item>
                <Button type="primary" icon={<SearchOutlined />} htmlType="submit" loading={loading}>
                  解释
                </Button>
              </Form.Item>
            </Form>

            {explainResult && (
              <Card style={{ marginTop: 16 }} type="inner" title="解释结果">
                <Descriptions column={2}>
                  <Descriptions.Item label="业务对象">{explainResult.objectCode}</Descriptions.Item>
                  <Descriptions.Item label="实例ID">{explainResult.instanceId}</Descriptions.Item>
                </Descriptions>
                <Divider />
                <Title level={5}>属性</Title>
                <pre style={{ background: '#f5f5f5', padding: 16, borderRadius: 8 }}>
                  {JSON.stringify(explainResult.attributes, null, 2)}
                </pre>
                <Title level={5}>解释</Title>
                <Alert message={explainResult.explanation} type="info" />
              </Card>
            )}
          </Card>
        </TabPane>

        <TabPane tab="风险研判" key="assess">
          <Card>
            <Form layout="inline" onFinish={handleAssess}>
              <Form.Item name="objectCode" label="业务对象编码" rules={[{ required: true }]}>
                <Input placeholder="例如：contract" />
              </Form.Item>
              <Form.Item name="instanceId" label="实例ID" rules={[{ required: true }]}>
                <Input placeholder="例如：1" />
              </Form.Item>
              <Form.Item name="ontologyId" label="本体ID">
                <Input placeholder="可选，默认为1" type="number" />
              </Form.Item>
              <Form.Item>
                <Button type="primary" icon={<BugOutlined />} htmlType="submit" loading={loading}>
                  研判
                </Button>
              </Form.Item>
            </Form>

            {assessResult && (
              <Card style={{ marginTop: 16 }} type="inner" title="研判结果">
                <Descriptions column={2}>
                  <Descriptions.Item label="业务对象">{assessResult.objectCode}</Descriptions.Item>
                  <Descriptions.Item label="实例ID">{assessResult.instanceId}</Descriptions.Item>
                  <Descriptions.Item label="决策">
                    <Tag color={
                      assessResult.decision === 'approved' ? 'green' :
                      assessResult.decision === 'review' ? 'orange' : 'red'
                    }>
                      {assessResult.decision}
                    </Tag>
                  </Descriptions.Item>
                </Descriptions>
                <Divider />
                <Title level={5}>命中的规则</Title>
                <ul>
                  {assessResult.rulesHit.map((rule, index) => (
                    <li key={index}>
                      <Tag color={rule.passed ? 'green' : 'red'}>{rule.passed ? '通过' : '未通过'}</Tag>
                      <strong>{rule.ruleName}</strong>：{rule.message}
                    </li>
                  ))}
                </ul>
                <Divider />
                <Title level={5}>解释</Title>
                <Alert message={assessResult.explanation} type={assessResult.decision === 'approved' ? 'success' : assessResult.decision === 'review' ? 'warning' : 'error'} />
              </Card>
            )}
          </Card>
        </TabPane>

        <TabPane tab="决策一致性" key="consistency">
          <Card>
            <Form layout="vertical" onFinish={handleConsistency} initialValues={{ limit: 50 }}>
              <Form.Item name="objectCode" label="业务对象编码" rules={[{ required: true }]}>
                <Input placeholder="例如：contract" />
              </Form.Item>
              <Form.Item name="ontologyId" label="本体ID" rules={[{ required: true }]}>
                <Input placeholder="例如：1" type="number" />
              </Form.Item>
              <Form.Item name="limit" label="抽样上限">
                <Input placeholder="默认 50，最大 200" type="number" />
              </Form.Item>
              <Form.Item name="instanceIds" label="指定实例ID">
                <Input.TextArea rows={3} placeholder="可选。多个实例可用逗号、空格或换行分隔，例如：1,2,3" />
              </Form.Item>
              <Form.Item>
                <Button type="primary" icon={<AuditOutlined />} htmlType="submit" loading={loading}>
                  批量评估
                </Button>
              </Form.Item>
            </Form>

            {consistencyResult && (
              <Card style={{ marginTop: 16 }} type="inner" title="一致性评估结果">
                <Descriptions column={4}>
                  <Descriptions.Item label="业务对象">{consistencyResult.objectCode}</Descriptions.Item>
                  <Descriptions.Item label="样本数">{consistencyResult.sampleSize}</Descriptions.Item>
                  <Descriptions.Item label="已评估">{consistencyResult.assessed}</Descriptions.Item>
                  <Descriptions.Item label="状态">
                    <Tag color={consistencyColor(consistencyResult.status)}>{consistencyResult.status}</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="通过">{consistencyResult.summary.approved}</Descriptions.Item>
                  <Descriptions.Item label="复核">{consistencyResult.summary.review}</Descriptions.Item>
                  <Descriptions.Item label="阻断">{consistencyResult.summary.blocked}</Descriptions.Item>
                  <Descriptions.Item label="错误">{consistencyResult.summary.errors}</Descriptions.Item>
                </Descriptions>
                {consistencyResult.nextActions.length > 0 && (
                  <>
                    <Divider />
                    <Alert
                      message="治理建议"
                      description={consistencyResult.nextActions.join('；')}
                      type={consistencyResult.status === 'consistent' ? 'success' : 'warning'}
                    />
                  </>
                )}
                {consistencyResult.ruleFailures.length > 0 && (
                  <>
                    <Divider />
                    <Title level={5}>规则失败分布</Title>
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
                      message="评估错误"
                      description={consistencyResult.errors.map(item => `${item.instanceId}: ${item.error}`).join('；')}
                      type="error"
                    />
                  </>
                )}
              </Card>
            )}
          </Card>
        </TabPane>

        <TabPane tab="操作预检" key="preflight">
          <Card>
            <Form form={operationForm} layout="vertical" onFinish={handlePreflight} initialValues={{ dryRun: true }}>
              <Form.Item name="operationCode" label="操作码" rules={[{ required: true }]}>
                <Input placeholder="例如：submit_contract" />
              </Form.Item>
              <Form.Item name="ontologyId" label="本体ID" rules={[{ required: true }]}>
                <Input placeholder="例如：1" type="number" />
              </Form.Item>
              <Form.Item name="dataSourceId" label="数据源ID" rules={[{ required: true }]}>
                <Input placeholder="例如：1" type="number" />
              </Form.Item>
              <Form.Item name="instanceId" label="实例ID" rules={[{ required: true }]}>
                <Input placeholder="例如：1" />
              </Form.Item>
              <Form.Item name="objectCode" label="业务对象编码">
                <Input placeholder="可选，例如：contract" />
              </Form.Item>
              <Form.Item name="actor" label="操作者">
                <Input placeholder="例如：业务控制台" />
              </Form.Item>
              <Form.Item name="payloadJson" label="执行载荷 JSON">
                <Input.TextArea rows={4} placeholder='例如：{"comment":"自动提交"}' />
              </Form.Item>
              <Form.Item name="dryRun" label="仅生成执行计划" valuePropName="checked">
                <Switch />
              </Form.Item>
              <Form.Item>
                <Button type="primary" icon={<RocketOutlined />} htmlType="submit" loading={loading} style={{ marginRight: 8 }}>
                  预检
                </Button>
                <Button icon={<RocketOutlined />} onClick={handleExecute} loading={loading}>
                  执行
                </Button>
              </Form.Item>
            </Form>

            {preflightResult && (
              <Card style={{ marginTop: 16 }} type="inner" title="预检结果">
                <Descriptions column={2}>
                  <Descriptions.Item label="操作码">{preflightResult.operationCode}</Descriptions.Item>
                  <Descriptions.Item label="实例ID">{preflightResult.instanceId}</Descriptions.Item>
                  <Descriptions.Item label="决策">
                    <Tag color={
                      preflightResult.decision === 'approved' ? 'green' :
                      preflightResult.decision === 'review' ? 'orange' : 'red'
                    }>
                      {preflightResult.decision}
                    </Tag>
                  </Descriptions.Item>
                </Descriptions>
                <Divider />
                <Title level={5}>命中的规则</Title>
                <ul>
                  {preflightResult.rulesHit.map((rule, index) => (
                    <li key={index}>
                      <Tag color={rule.passed ? 'green' : 'red'}>{rule.passed ? '通过' : '未通过'}</Tag>
                      <strong>{rule.ruleName}</strong>：{rule.message}
                    </li>
                  ))}
                </ul>
                <Divider />
                <Title level={5}>建议</Title>
                <Alert message={preflightResult.recommendation} type="info" />
              </Card>
            )}

            {executeResult && (
              <Card style={{ marginTop: 16 }} type="inner" title="执行结果">
                <Descriptions column={2}>
                  <Descriptions.Item label="操作码">{executeResult.operationCode}</Descriptions.Item>
                  <Descriptions.Item label="实例ID">{executeResult.instanceId}</Descriptions.Item>
                  <Descriptions.Item label="状态">
                    <Tag color={executeResult.executed ? 'green' : executeResult.status === 'blocked_by_semantic_kernel' ? 'red' : 'blue'}>
                      {executeResult.status}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="决策">{executeResult.decision}</Descriptions.Item>
                </Descriptions>
                <Divider />
                <Alert message={executeResult.message} type={executeResult.status === 'blocked_by_semantic_kernel' ? 'error' : 'success'} />
                {executeResult.execution && (
                  <>
                    <Divider />
                    <Title level={5}>执行计划</Title>
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
