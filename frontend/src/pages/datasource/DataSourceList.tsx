import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Card, Table, Button, Space, Typography, Tag, Modal, Form, Input, Select, message, Steps, List, Divider, Collapse, Empty } from 'antd';
import { PlusOutlined, ScanOutlined, ApiOutlined, LinkOutlined, BulbOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { CONNECTION_STATUS, READINESS_STATUS } from '../../i18n/labels';
import { useLabel, useT } from '../../i18n/locale';
import { aiApi, dataSourceApi, industryBlueprintApi, onboardingApi, requestErrorMessage } from '../../api';
import { initializeReport, scanReport } from '../../i18n/text';
import MarkdownMessage from '../../components/MarkdownMessage';
import type { DataSource, DataSourceCreate, IndustryBlueprint, OnboardingResult, OntologyReasoningChainResult } from '../../types';
import type { MessageKey } from '../../i18n/messages';

const { Title, Text } = Typography;
const { Option } = Select;

// Typed as `MessageKey`, not `string`: the value reaches `t()` through a variable, so a
// `string` declaration would make every call below need a cast -- and a cast is what turns
// a misspelled key into a `⟦key⟧` on the screen instead of an error at build time.
const ONBOARDING_STEP_KEYS: Record<string, MessageKey> = {
  register_data_source: 'datasource.stepRegisterDataSource',
  test_connection: 'datasource.stepTestConnection',
  test_api_gateway: 'datasource.stepTestApiGateway',
  scan_metadata: 'datasource.stepScanMetadata',
  import_openapi: 'datasource.stepImportOpenApi',
  generate_ontology: 'datasource.stepGenerateOntology',
  seed_permissions: 'datasource.stepSeedPermissions',
  assess_readiness: 'datasource.stepAssessReadiness',
};

const DataSourceList: React.FC = () => {
  const label = useLabel();
  const t = useT();
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
  const [initializingId, setInitializingId] = useState<number | null>(null);
  const [form] = Form.useForm();

  const fetchDataSources = useCallback(async () => {
    setLoading(true);
    try {
      const data = await dataSourceApi.list();
      setDataSources(data);
    } catch (error) {
      message.error(requestErrorMessage(error, t('datasource.loadFailed')));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void fetchDataSources();
    industryBlueprintApi.list().then(setBlueprints).catch(() => undefined);
  }, [fetchDataSources]);

  const parseApiHeaders = (value?: string): Record<string, string> => {
    if (!value?.trim()) return {};
    const parsed = JSON.parse(value);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error(t('datasource.apiHeadersInvalid'));
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
      throw new Error(t('datasource.openApiJsonNotObject'));
    }
    return parsed as Record<string, unknown>;
  };

  const handleCreate = async (values: DataSourceCreate & { apiHeadersJson?: string }) => {
    try {
      const { apiHeadersJson, ...payload } = values as DataSourceCreate & {
        apiHeadersJson?: string;
      };
      await dataSourceApi.create({ ...payload, apiHeaders: parseApiHeaders(apiHeadersJson) });
      message.success(t('datasource.createSuccess'));
      setModalVisible(false);
      form.resetFields();
      fetchDataSources();
    } catch (error) {
      message.error(requestErrorMessage(error, t('datasource.createFailed')));
    }
  };

  const handleTestConnection = async () => {
    try {
      const values = await form.validateFields(['sourceType', 'connectionUri']);
      setTestingConnection(true);
      const result = await dataSourceApi.testConnection(values);
      setConnectionResult(result);
      if (result.reachable) {
        message.success(t('datasource.connectionOk'));
      } else {
        message.warning(result.message);
      }
    } catch (error) {
      if (!(error instanceof Error)) {
        message.error(t('datasource.connectionTestFailed'));
      }
    } finally {
      setTestingConnection(false);
    }
  };

  const handleRegisteredConnectionTest = async (record: DataSource) => {
    try {
      const result = await dataSourceApi.testRegisteredConnection(record.id);
      if (result.reachable) {
        message.success(t('datasource.registeredConnectionOk', { name: record.name }));
      } else {
        message.warning(result.message);
      }
    } catch (error) {
      message.error(requestErrorMessage(error, t('datasource.connectionTestFailed')));
    }
  };

  const handleScan = async (id: number) => {
    try {
      // Both screens that scan report through `scanReport`, so they cannot say different
      // things about the same response.
      const report = scanReport(await dataSourceApi.scan(id), t);
      if (report.level === 'warning') message.warning(report.text, 8);
      else message.success(report.text);
      fetchDataSources();
    } catch (error) {
      message.error(requestErrorMessage(error, t('datasource.scanFailed')));
    }
  };

  const handleInitialize = async (record: DataSource) => {
    setInitializingId(record.id);
    try {
      const result = await dataSourceApi.initialize(record.id);
      // `void result` was the whole use of the response: the endpoint reports how many tables
      // it scanned and how many objects the reasoning chain has, and the message said
      // 「已初始化」. The counts are what tell the reader it produced anything at all.
      message.success(initializeReport(record.name, result, t));
      await fetchDataSources();
      navigate(`/datasource/${record.id}`);
    } catch (error) {
      message.error(requestErrorMessage(error, t('datasource.initializeFailed')));
    } finally {
      setInitializingId(null);
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
        message.success(t('datasource.reasoningRemoteToast'));
      } else {
        message.warning(result.remoteError ? t('datasource.reasoningFallback', { reason: result.remoteError }) : t('datasource.reasoningLocalToast'));
      }
    } catch (error) {
      message.error(requestErrorMessage(error, t('datasource.reasoningGenerateFailed')));
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
        message.warning(t('datasource.onboardingBlocked'));
      } else {
        message.success(t('datasource.onboardingDone'));
        fetchDataSources();
      }
    } catch (error) {
      message.error(requestErrorMessage(error, t('datasource.onboardingFailed')));
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
      title: t('datasource.name'),
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: t('datasource.type'),
      dataIndex: 'sourceType',
      key: 'sourceType',
      render: (type: string) => <Tag color="blue">{type}</Tag>,
    },
    {
      title: t('datasource.domain'),
      dataIndex: 'domain',
      key: 'domain',
      render: (domain: string) => domain || '-',
    },
    {
      title: t('datasource.systemCategory'),
      dataIndex: 'systemCategory',
      key: 'systemCategory',
      render: (category: string) => <Tag>{category}</Tag>,
    },
    {
      title: t('datasource.actions'),
      key: 'action',
      render: (_: unknown, record: DataSource) => (
        <Space>
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            loading={initializingId === record.id}
            onClick={() => handleInitialize(record)}
          >
            {t('datasource.initializeButton')}
          </Button>
          <Button
            type="link"
            icon={<ScanOutlined />}
            onClick={() => handleScan(record.id)}
          >
            {t('datasource.scanButton')}
          </Button>
          <Button
            type="link"
            icon={<LinkOutlined />}
            onClick={() => handleRegisteredConnectionTest(record)}
          >
            {t('datasource.testButton')}
          </Button>
          <Button
            type="link"
            icon={<ApiOutlined />}
            onClick={() => navigate(`/datasource/${record.id}`)}
          >
            {t('datasource.detailButton')}
          </Button>
          <Button
            type="link"
            icon={<BulbOutlined />}
            onClick={() => handleReasoningChain(record)}
          >
            {t('datasource.reasoningButton')}
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={3}>{t('datasource.title')}</Title>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setModalVisible(true)}
        >
          {t('datasource.addButton')}
        </Button>
      </div>

      <Card>
        {!loading && dataSources.length === 0 ? (
          // The workbench sends a first-time reader here with "接入一个业务库", and this page
          // answered with an empty table and the words 暂无数据 -- the least instructive
          // screen on the path it is the destination of. What a reader needs at that moment
          // is what a data source is *for* and what happens after adding one.
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <Space direction="vertical" size={4} style={{ maxWidth: 620 }}>
                <Text strong>{t('datasource.emptyTitle')}</Text>
                <Text type="secondary">
                  {t('datasource.emptyBody')}
                </Text>
                <Text type="secondary">
                  <Text strong>{t('datasource.emptyReadonly')}</Text>
                  {t('datasource.emptyReadonlyNote')} {t('datasource.emptyDemo')}
                </Text>
              </Space>
            }
          >
            <Space>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalVisible(true)}>
                {t('datasource.connectButton')}
              </Button>
              <Button onClick={() => navigate('/workbench')}>{t('datasource.backToWorkbench')}</Button>
            </Space>
          </Empty>
        ) : (
          <Table
            columns={columns}
            dataSource={dataSources}
            rowKey="id"
            loading={loading}
          />
        )}
      </Card>

      <Modal
        title={t('datasource.connectButton')}
        open={modalVisible}
        onCancel={() => {
          setModalVisible(false);
          setConnectionResult(null);
          setOnboardingResult(null);
          form.resetFields();
        }}
        onOk={() => form.submit()}
      >
        <Alert
          type="info"
          showIcon
          message={t('datasource.introTitle')}
          description={t('datasource.introBody')}
          style={{ marginBottom: 16 }}
        />
        <Form
          form={form}
          layout="vertical"
          onFinish={handleCreate}
        >
          <Form.Item
            name="name"
            label={t('datasource.name')}
            rules={[{ required: true, message: t('datasource.nameRequired') }]}
          >
            <Input placeholder={t('datasource.namePlaceholder')} />
          </Form.Item>
          <Form.Item
            name="sourceType"
            label={t('datasource.type')}
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
            label={t('datasource.connectionUriLabel')}
            rules={[{ required: true, message: t('datasource.connectionUriRequired') }]}
          >
            <Input placeholder={t('datasource.connectionUriPlaceholder')} />
          </Form.Item>
          <Form.Item>
            <Button
              icon={<LinkOutlined />}
              loading={testingConnection}
              onClick={handleTestConnection}
            >
              {t('datasource.testConnectionButton')}
            </Button>
          </Form.Item>
          {connectionResult && (
            <Alert
              style={{ marginBottom: 16 }}
              type={connectionResult.reachable ? 'success' : 'warning'}
              message={label(CONNECTION_STATUS, connectionResult.status)}
              description={connectionResult.message}
              showIcon
            />
          )}
          <Form.Item
            name="domain"
            label={t('datasource.businessDomain')}
          >
            <Input placeholder={t('datasource.businessDomainPlaceholder')} />
          </Form.Item>
          <Form.Item
            name="systemCategory"
            label={t('datasource.systemCategoryLabel')}
            initialValue="database"
          >
            <Select>
              <Option value="database">{t('datasource.systemCategoryDatabase')}</Option>
              <Option value="api">API</Option>
              <Option value="database+api">{t('datasource.systemCategoryDatabaseApi')}</Option>
            </Select>
          </Form.Item>
          <Collapse
            ghost
            items={[{
              key: 'advanced',
              label: t('datasource.advancedLabel'),
              children: <>
                <Form.Item name="apiBaseUrl" label={t('datasource.apiBaseUrlLabel')}>
                  <Input placeholder={t('datasource.apiBaseUrlPlaceholder')} />
                </Form.Item>
                <Form.Item name="apiHeadersJson" label={t('datasource.apiHeadersLabel')}>
                  <Input.TextArea rows={3} placeholder={t('datasource.apiHeadersPlaceholder')} />
                </Form.Item>
                <Form.Item name="openApiUrl" label={t('datasource.openApiUrlLabel')}>
                  <Input placeholder={t('datasource.openApiUrlPlaceholder')} />
                </Form.Item>
                <Form.Item name="openApiSpecJson" label="OpenAPI JSON">
                  <Input.TextArea rows={3} placeholder={t('datasource.openApiSpecHint')} />
                </Form.Item>
                <Form.Item name="blueprintId" label={t('datasource.blueprintLabel')}>
                  <Select placeholder={t('datasource.blueprintPlaceholder')} allowClear>
                    {blueprints.map(blueprint => (
                      <Option key={blueprint.id} value={blueprint.id}>
                        {blueprint.name} ({blueprint.domain})
                      </Option>
                    ))}
                  </Select>
                </Form.Item>
              </>,
            }]}
          />
          <Form.Item>
            <Button
              type="primary"
              icon={<ScanOutlined />}
              loading={onboardingLoading}
              onClick={handleOnboarding}
            >
              {t('datasource.onboardingButton')}
            </Button>
          </Form.Item>
          {onboardingResult && (
            <Card size="small" title={t('datasource.onboardingResultTitle', { status: label(READINESS_STATUS, onboardingResult.status) })} style={{ marginBottom: 16 }}>
              <Steps
                direction="vertical"
                size="small"
                items={onboardingResult.steps.map(step => ({
                  title: ONBOARDING_STEP_KEYS[step.code] ? t(ONBOARDING_STEP_KEYS[step.code]) : step.code,
                  description: step.message,
                  status: step.status === 'completed' ? 'finish' : step.status === 'failed' ? 'error' : 'wait',
                }))}
              />
              <Space wrap style={{ marginTop: 16 }}>
                <Button onClick={() => navigate(`/datasource/${onboardingResult.dataSource.id}`)}>
                  {t('datasource.viewOnboardingDetail')}
                </Button>
                {onboardingResult.ontology?.ontology?.id && (
                  <Button onClick={() => navigate(`/ontology/${onboardingResult.ontology?.ontology.id}`)}>
                    {t('datasource.viewOntology')}
                  </Button>
                )}
                <Button type="primary" onClick={() => navigate('/chat')}>
                  {t('datasource.goToChat')}
                </Button>
              </Space>
            </Card>
          )}
        </Form>
      </Modal>

      <Modal
        title={reasoningSource ? t('datasource.reasoningTitleWithName', { name: reasoningSource.name }) : t('datasource.reasoningTitle')}
        open={reasoningVisible}
        onCancel={() => setReasoningVisible(false)}
        footer={[
          <Button key="close" onClick={() => setReasoningVisible(false)}>{t('datasource.close')}</Button>,
          <Button key="manual" onClick={() => navigate('/ontology')}>{t('datasource.buildManually')}</Button>,
          <Button key="auto" type="primary" onClick={() => setModalVisible(true)}>{t('datasource.buildWithOnboarding')}</Button>,
        ]}
        width={920}
      >
        {reasoningLoading && <Alert type="info" showIcon message={t('datasource.reasoningLoading')} />}
        {reasoningResult && (
          <div>
            <Alert
              type={reasoningResult.usedRemoteModel ? 'success' : 'warning'}
              showIcon
              message={reasoningResult.usedRemoteModel ? t('datasource.reasoningRemoteDone') : t('datasource.reasoningLocalDone')}
              description={reasoningResult.remoteError || t('datasource.modelLabel', { model: reasoningResult.model })}
              style={{ marginBottom: 16 }}
            />
            {/* Model output is Markdown; rendering it raw showed literal "##"
                and "**" to the user. */}
            <MarkdownMessage content={reasoningResult.chain.summary} variant="document" />
            <Divider />
            <Title level={5}>{t('datasource.reasoningSteps')}</Title>
            <Steps
              direction="vertical"
              size="small"
              items={reasoningResult.chain.reasoningSteps.map(step => ({ title: step }))}
            />
            <Divider />
            <Title level={5}>{t('datasource.objectCandidates')}</Title>
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
            <Title level={5}>{t('datasource.relationRuleCandidates')}</Title>
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
            <Title level={5}>{t('datasource.buildPlan')}</Title>
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
