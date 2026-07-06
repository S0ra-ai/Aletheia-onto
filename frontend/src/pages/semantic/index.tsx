import React, { useState } from 'react';
import { Card, Form, Input, Button, Typography, Alert, Descriptions, Tag, Divider, message, Tabs } from 'antd';
import { SearchOutlined, BugOutlined, RocketOutlined } from '@ant-design/icons';
import { semanticApi, automationApi } from '../../api';
import type { InstanceExplainResult, InstanceAssessResult, OperationPreflightResult } from '../../types';

const { Title, Paragraph } = Typography;
const { TabPane } = Tabs;

const SemanticService: React.FC = () => {
  const [explainResult, setExplainResult] = useState<InstanceExplainResult | null>(null);
  const [assessResult, setAssessResult] = useState<InstanceAssessResult | null>(null);
  const [preflightResult, setPreflightResult] = useState<OperationPreflightResult | null>(null);
  const [loading, setLoading] = useState(false);

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

  const handlePreflight = async (values: { operationCode: string; ontologyId: number; dataSourceId: number; instanceId: string; objectCode?: string }) => {
    setLoading(true);
    try {
      const result = await automationApi.preflight(values.operationCode, values);
      setPreflightResult(result);
    } catch (error) {
      message.error('操作预检失败');
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

        <TabPane tab="操作预检" key="preflight">
          <Card>
            <Form layout="vertical" onFinish={handlePreflight}>
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
              <Form.Item>
                <Button type="primary" icon={<RocketOutlined />} htmlType="submit" loading={loading}>
                  预检
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
          </Card>
        </TabPane>
      </Tabs>
    </div>
  );
};

export default SemanticService;
