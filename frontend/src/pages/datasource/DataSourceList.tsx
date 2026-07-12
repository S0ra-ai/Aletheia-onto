import React, { useEffect, useState } from 'react';
import { Alert, Card, Table, Button, Space, Typography, Tag, Modal, Form, Input, Select, message, Steps, List, Divider } from 'antd';
import { PlusOutlined, ScanOutlined, ApiOutlined, LinkOutlined, BulbOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { aiApi, dataSourceApi, industryBlueprintApi, onboardingApi } from '../../api';
import type { DataSource, DataSourceCreate, IndustryBlueprint, OnboardingResult, OntologyReasoningChainResult } from '../../types';

const { Title, Paragraph, Text } = Typography;
const { Option } = Select;

const DataSourceList: React.FC = () => {
  const navigate = useNavigate();
  const [dataSources, setDataSources] = useState<DataSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [connectionResult, setConnectionResult] = useState<{ reachable: boolean; status: string; message: string } | null>(null);
  const [testingConnection, setTestingConnection] = useState(false);
  const [blueprints, setBlueprints] = useState<IndustryBlueprint[]>([]);
  const [onboardingResult, setOnboardingResult] = useState<OnboardingResult | null>(null);
  const [onboardingLoading, setOnboardingLoading] = useState(false);
  const [reasoningVisible, setReasoningVisible] = useState(false);
  const [reasoningLoading, setReasoningLoading] = useState(false);
  const [reasoningResult, setReasoningResult] = useState<OntologyReasoningChainResult | null>(null);
  const [reasoningSource, setReasoningSource] = useState<DataSource | null>(null);
  const [form] = Form.useForm();

  const fetchDataSources = async () => {
    setLoading(true);
    try {
      const data = await dataSourceApi.list();
      setDataSources(data);
    } catch (error) {
      message.error('获取数据源列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDataSources();
    industryBlueprintApi.list().then(setBlueprints).catch(() => undefined);
  }, []);

  const parseApiHeaders = (value?: string): Record<string, string> => {
    if (!value?.trim()) return {};
    const parsed = JSON.parse(value);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error('业务 API 请求头必须是 JSON 对象');
    }
    return Object.fromEntries(
      Object.entries(parsed)
        .filter(([key, headerValue]) => key.trim() && headerValue !== null && headerValue !== undefined)
        .map(([key, headerValue]) => [key.trim(), String(headerValue)])
    );
  };

  const parseOpenApiSpec = (value?: string): Record<string, unknown> | undefined => {
    if (!value?.trim()) return undefined;
    const parsed = JSON.parse(value);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error('OpenAPI JSON 必须是对象');
    }
    return parsed as Record<string, unknown>;
  };

  const handleCreate = async (values: DataSourceCreate & { apiHeadersJson?: string }) => {
    try {
      const { apiHeadersJson, openApiUrl, openApiSpecJson, blueprintId, ...payload } = values as DataSourceCreate & {
        apiHeadersJson?: string;
        openApiUrl?: string;
        openApiSpecJson?: string;
        blueprintId?: string;
      };
      await dataSourceApi.create({ ...payload, apiHeaders: parseApiHeaders(apiHeadersJson) });
      message.success('数据源创建成功');
      setModalVisible(false);
      form.resetFields();
      fetchDataSources();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '创建失败');
    }
  };

  const handleTestConnection = async () => {
    try {
      const values = await form.validateFields(['sourceType', 'connectionUri']);
      setTestingConnection(true);
      const result = await dataSourceApi.testConnection(values);
      setConnectionResult(result);
      if (result.reachable) {
        message.success('连接测试成功');
      } else {
        message.warning(result.message);
      }
    } catch (error) {
      if (!(error instanceof Error)) {
        message.error('连接测试失败');
      }
    } finally {
      setTestingConnection(false);
    }
  };

  const handleRegisteredConnectionTest = async (record: DataSource) => {
    try {
      const result = await dataSourceApi.testRegisteredConnection(record.id);
      if (result.reachable) {
        message.success(`${record.name} 连接正常`);
      } else {
        message.warning(result.message);
      }
    } catch {
      message.error('连接测试失败');
    }
  };

  const handleScan = async (id: number) => {
    try {
      await dataSourceApi.scan(id);
      message.success('扫描完成');
      fetchDataSources();
    } catch (error) {
      message.error('扫描失败');
    }
  };

  const handleReasoningChain = async (record: DataSource) => {
    setReasoningSource(record);
    setReasoningResult(null);
    setReasoningVisible(true);
    setReasoningLoading(true);
    try {
      const result = await aiApi.getOntologyReasoningChain(record.id);
      setReasoningResult(result);
      if (result.usedRemoteModel) {
        message.success('大模型已生成本体推理链');
      } else {
        message.warning(result.remoteError ? `已回退到本地推理：${result.remoteError}` : '已使用本地启发式推理');
      }
    } catch (error) {
      message.error('生成本体推理链失败，请先扫描数据源');
    } finally {
      setReasoningLoading(false);
    }
  };

  const handleOnboarding = async () => {
    try {
      const values = await form.validateFields(['name', 'sourceType', 'connectionUri', 'apiBaseUrl', 'apiHeadersJson', 'openApiUrl', 'openApiSpecJson', 'domain', 'systemCategory', 'blueprintId']);
      setOnboardingLoading(true);
      const { apiHeadersJson, openApiSpecJson, ...payload } = values;
      const result = await onboardingApi.run({
        ...payload,
        apiHeaders: parseApiHeaders(apiHeadersJson),
        openApiSpec: parseOpenApiSpec(openApiSpecJson),
        generateOntology: true,
      });
      setOnboardingResult(result);
      if (result.status === 'blocked') {
        message.warning('一键接入未完成，请查看步骤详情');
      } else {
        message.success('一键接入流水线完成');
        fetchDataSources();
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : '一键接入失败');
    } finally {
      setOnboardingLoading(false);
    }
  };

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
    },
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '类型',
      dataIndex: 'sourceType',
      key: 'sourceType',
      render: (type: string) => <Tag color="blue">{type}</Tag>,
    },
    {
      title: '领域',
      dataIndex: 'domain',
      key: 'domain',
      render: (domain: string) => domain || '-',
    },
    {
      title: '系统分类',
      dataIndex: 'systemCategory',
      key: 'systemCategory',
      render: (category: string) => <Tag>{category}</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: DataSource) => (
        <Space>
          <Button
            type="link"
            icon={<ScanOutlined />}
            onClick={() => handleScan(record.id)}
          >
            扫描
          </Button>
          <Button
            type="link"
            icon={<LinkOutlined />}
            onClick={() => handleRegisteredConnectionTest(record)}
          >
            测试
          </Button>
          <Button
            type="link"
            icon={<ApiOutlined />}
            onClick={() => navigate(`/datasource/${record.id}`)}
          >
            详情
          </Button>
          <Button
            type="link"
            icon={<BulbOutlined />}
            onClick={() => handleReasoningChain(record)}
          >
            AI推理链
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={3}>数据源管理</Title>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setModalVisible(true)}
        >
          新增数据源
        </Button>
      </div>

      <Card>
        <Table
          columns={columns}
          dataSource={dataSources}
          rowKey="id"
          loading={loading}
        />
      </Card>

      <Modal
        title="新增数据源"
        open={modalVisible}
        onCancel={() => {
          setModalVisible(false);
          setConnectionResult(null);
          setOnboardingResult(null);
          form.resetFields();
        }}
        onOk={() => form.submit()}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleCreate}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入数据源名称' }]}
          >
            <Input placeholder="例如：合同管理系统" />
          </Form.Item>
          <Form.Item
            name="sourceType"
            label="类型"
            initialValue="sqlite"
          >
            <Select>
              <Option value="sqlite">SQLite</Option>
              <Option value="postgresql">PostgreSQL</Option>
              <Option value="mysql">MySQL</Option>
            </Select>
          </Form.Item>
          <Form.Item
            name="connectionUri"
            label="连接地址"
            rules={[{ required: true, message: '请输入连接地址' }]}
          >
            <Input placeholder="例如：/path/to/database.sqlite3" />
          </Form.Item>
          <Form.Item
            name="apiBaseUrl"
            label="业务 API 基址"
          >
            <Input placeholder="例如：https://legacy.example/api" />
          </Form.Item>
          <Form.Item
            name="apiHeadersJson"
            label="业务 API 请求头"
          >
            <Input.TextArea
              rows={3}
              placeholder={'例如：{"Authorization":"Bearer token","X-Tenant":"demo"}'}
            />
          </Form.Item>
          <Form.Item
            name="openApiUrl"
            label="OpenAPI URL"
          >
            <Input placeholder="例如：https://legacy.example/openapi.json" />
          </Form.Item>
          <Form.Item
            name="openApiSpecJson"
            label="OpenAPI JSON"
          >
            <Input.TextArea
              rows={3}
              placeholder='{"openapi":"3.0.0","paths":{"/contracts/{id}/submit":{"post":{"operationId":"submit_contract"}}}}'
            />
          </Form.Item>
          <Form.Item>
            <Button
              icon={<LinkOutlined />}
              loading={testingConnection}
              onClick={handleTestConnection}
            >
              测试连接
            </Button>
          </Form.Item>
          {connectionResult && (
            <Alert
              style={{ marginBottom: 16 }}
              type={connectionResult.reachable ? 'success' : 'warning'}
              message={connectionResult.status}
              description={connectionResult.message}
              showIcon
            />
          )}
          <Form.Item
            name="domain"
            label="业务领域"
          >
            <Input placeholder="例如：合同管理" />
          </Form.Item>
          <Form.Item
            name="systemCategory"
            label="系统分类"
            initialValue="database"
          >
            <Select>
              <Option value="database">数据库</Option>
              <Option value="api">API</Option>
              <Option value="database+api">数据库+API</Option>
            </Select>
          </Form.Item>
          <Form.Item
            name="blueprintId"
            label="行业蓝图"
          >
            <Select placeholder="自动推断或手动选择" allowClear>
              {blueprints.map(blueprint => (
                <Option key={blueprint.id} value={blueprint.id}>
                  {blueprint.name} ({blueprint.domain})
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item>
            <Button
              type="primary"
              icon={<ScanOutlined />}
              loading={onboardingLoading}
              onClick={handleOnboarding}
            >
              一键接入并生成本体
            </Button>
          </Form.Item>
          {onboardingResult && (
            <Card size="small" title={`接入结果：${onboardingResult.status}`} style={{ marginBottom: 16 }}>
              <Steps
                direction="vertical"
                size="small"
                items={onboardingResult.steps.map(step => ({
                  title: step.code,
                  description: step.message,
                  status: step.status === 'completed' ? 'finish' : step.status === 'failed' ? 'error' : 'wait',
                }))}
              />
            </Card>
          )}
        </Form>
      </Modal>

      <Modal
        title={reasoningSource ? `${reasoningSource.name}：本体推理链` : '本体推理链'}
        open={reasoningVisible}
        onCancel={() => setReasoningVisible(false)}
        footer={[
          <Button key="close" onClick={() => setReasoningVisible(false)}>关闭</Button>,
          <Button key="manual" onClick={() => navigate('/ontology')}>自行构建</Button>,
          <Button key="auto" type="primary" onClick={() => setModalVisible(true)}>一键接入构建</Button>,
        ]}
        width={920}
      >
        {reasoningLoading && <Alert type="info" showIcon message="正在让模型读取表结构并构建推理链..." />}
        {reasoningResult && (
          <div>
            <Alert
              type={reasoningResult.usedRemoteModel ? 'success' : 'warning'}
              showIcon
              message={reasoningResult.usedRemoteModel ? '已使用 OpenRouter 大模型推理' : '使用本地启发式推理'}
              description={reasoningResult.remoteError || `模型：${reasoningResult.model}`}
              style={{ marginBottom: 16 }}
            />
            <Paragraph>{reasoningResult.chain.summary}</Paragraph>
            <Divider />
            <Title level={5}>推理步骤</Title>
            <Steps
              direction="vertical"
              size="small"
              items={reasoningResult.chain.reasoningSteps.map(step => ({ title: step }))}
            />
            <Divider />
            <Title level={5}>业务对象候选</Title>
            <List
              size="small"
              dataSource={reasoningResult.chain.proposedObjects.slice(0, 12)}
              renderItem={item => (
                <List.Item>
                  <Text code>{String(item.objectCode || item.sourceTable || item.code || '-')}</Text>
                  <span style={{ marginLeft: 8 }}>{String(item.objectName || item.name || item.reason || '')}</span>
                </List.Item>
              )}
            />
            <Divider />
            <Title level={5}>关系与规则候选</Title>
            <Space direction="vertical" style={{ width: '100%' }}>
              {reasoningResult.chain.proposedRelations.slice(0, 8).map((item, index) => (
                <Tag key={`rel-${index}`} color="blue">
                  {String(item.sourceObject || item.source || '-') } → {String(item.targetObject || item.target || '-')}
                </Tag>
              ))}
              {reasoningResult.chain.proposedRules.slice(0, 8).map((item, index) => (
                <Tag key={`rule-${index}`} color="orange">
                  {String(item.ruleName || item.name || item.rule || '-')}
                </Tag>
              ))}
            </Space>
            <Divider />
            <Title level={5}>构建路径</Title>
            <List
              size="small"
              dataSource={reasoningResult.chain.buildPlan}
              renderItem={item => <List.Item>{item}</List.Item>}
            />
          </div>
        )}
      </Modal>
    </div>
  );
};

export default DataSourceList;
