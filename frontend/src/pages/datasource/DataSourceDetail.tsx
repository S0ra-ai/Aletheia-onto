import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Table, Button, Space, Typography, Tag, Tabs, Descriptions, message, Spin, Progress, Alert, Modal, Form, Input, Upload } from 'antd';
import { ApiOutlined, ArrowLeftOutlined, ScanOutlined, PlusOutlined, ImportOutlined, DownloadOutlined, BulbOutlined, BranchesOutlined, UploadOutlined } from '@ant-design/icons';
import { aiApi, dataSourceApi, documentApi, ontologyApi } from '../../api';
import type { DataSource, SourceTable, SourceApi, DataSourceReadiness, IndustryBlueprint, SchemaDriftResult, SchemaDriftTableChange, SemanticCoverageResult, SemanticCoverageObject, OperationBindingResult, ContractDocumentParseResult, RuleWordImportResult } from '../../types';

const { Title } = Typography;
const { TabPane } = Tabs;

type DataSourceRule = {
  id: number;
  ontologyId: number;
  code: string;
  name: string;
  rule_type: string;
  scope_object_code: string;
  expression: string;
  severity: string;
  natural_language: string;
  status: string;
};

const DataSourceDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [dataSource, setDataSource] = useState<DataSource | null>(null);
  const [tables, setTables] = useState<SourceTable[]>([]);
  const [apis, setApis] = useState<SourceApi[]>([]);
  const [readiness, setReadiness] = useState<DataSourceReadiness | null>(null);
  const [schemaDrift, setSchemaDrift] = useState<SchemaDriftResult | null>(null);
  const [semanticCoverage, setSemanticCoverage] = useState<SemanticCoverageResult | null>(null);
  const [operationBindings, setOperationBindings] = useState<OperationBindingResult | null>(null);
  const [businessRules, setBusinessRules] = useState<DataSourceRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [scanLoading, setScanLoading] = useState(false);
  const [gatewayTesting, setGatewayTesting] = useState(false);
  const [driftLoading, setDriftLoading] = useState(false);
  const [openApiModalVisible, setOpenApiModalVisible] = useState(false);
  const [importLoading, setImportLoading] = useState(false);
  const [blueprintDraftVisible, setBlueprintDraftVisible] = useState(false);
  const [blueprintDraftLoading, setBlueprintDraftLoading] = useState(false);
  const [blueprintDraft, setBlueprintDraft] = useState<IndustryBlueprint | null>(null);
  const [documentParsing, setDocumentParsing] = useState(false);
  const [documentParseResult, setDocumentParseResult] = useState<ContractDocumentParseResult | null>(null);
  const [ruleImporting, setRuleImporting] = useState(false);
  const [ruleImportResult, setRuleImportResult] = useState<RuleWordImportResult | null>(null);
  const [openApiForm] = Form.useForm();

  const fetchData = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [tablesData, apisData, readinessData, coverageData, bindingData] = await Promise.all([
        dataSourceApi.getTables(parseInt(id)),
        dataSourceApi.getApis(parseInt(id)),
        dataSourceApi.getReadiness(parseInt(id)),
        dataSourceApi.getSemanticCoverage(parseInt(id)),
        dataSourceApi.getOperationBindings(parseInt(id)),
      ]);
      setTables(tablesData);
      setApis(apisData);
      setReadiness(readinessData);
      setSemanticCoverage(coverageData);
      setOperationBindings(bindingData);
      const ontologyIds = Array.from(new Set(coverageData.objects.map(item => item.ontologyId)));
      const ruleGroups = await Promise.all(
        ontologyIds.map(async ontologyId => {
          const rules = await ontologyApi.getRules(ontologyId);
          return rules.map((rule: any) => ({ ...rule, ontologyId }));
        })
      );
      setBusinessRules(ruleGroups.flat());
      // 获取数据源基本信息（从列表中获取）
      const sources = await dataSourceApi.list();
      const source = sources.find(s => s.id === parseInt(id));
      if (source) setDataSource(source);
    } catch (error) {
      message.error('获取数据详情失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [id]);

  const handleScan = async () => {
    if (!id) return;
    setScanLoading(true);
    try {
      await dataSourceApi.scan(parseInt(id));
      message.success('扫描完成');
      setSchemaDrift(null);
      fetchData();
    } catch (error) {
      message.error('扫描失败');
    } finally {
      setScanLoading(false);
    }
  };

  const handleImportOpenApi = async (values: { specJson?: string; specUrl?: string }) => {
    if (!id) return;
    setImportLoading(true);
    try {
      const specUrl = values.specUrl?.trim();
      const result = specUrl
        ? await dataSourceApi.importOpenApiUrl(parseInt(id), specUrl)
        : await dataSourceApi.importOpenApi(parseInt(id), JSON.parse(values.specJson || ''));
      message.success(`已导入 ${result.count} 个业务 API`);
      setOpenApiModalVisible(false);
      openApiForm.resetFields();
      fetchData();
    } catch (error) {
      message.error(error instanceof SyntaxError ? 'OpenAPI JSON 格式不正确' : 'OpenAPI 导入失败');
    } finally {
      setImportLoading(false);
    }
  };

  const handleAnalyzeDrift = async () => {
    if (!id) return;
    setDriftLoading(true);
    try {
      const result = await dataSourceApi.getSchemaDrift(parseInt(id));
      setSchemaDrift(result);
      if (result.status === 'drift_detected') {
        message.warning('检测到结构漂移，请先评估影响再重新扫描');
      } else if (result.status === 'not_scanned') {
        message.info('当前数据源还没有扫描基线');
      } else {
        message.success('未发现结构漂移');
      }
    } catch {
      message.error('结构漂移分析失败');
    } finally {
      setDriftLoading(false);
    }
  };

  const handleGenerateBlueprintDraft = async () => {
    if (!id) return;
    setBlueprintDraftLoading(true);
    try {
      const result = await aiApi.getBlueprintDraft(parseInt(id));
      setBlueprintDraft(result.blueprint);
      setBlueprintDraftVisible(true);
      message.success(result.usedRemoteModel ? '已由 OpenRouter 生成蓝图草案' : '已生成本地蓝图草案');
    } catch {
      message.error('生成蓝图草案失败');
    } finally {
      setBlueprintDraftLoading(false);
    }
  };

  const handleParseContractDocument = async (file: File) => {
    setDocumentParsing(true);
    try {
      const result = await documentApi.parseContractWord(file);
      setDocumentParseResult(result);
      message.success('Word 合同解析完成');
    } catch (error) {
      message.error('Word 合同解析失败，请确认文件为 .docx 格式');
    } finally {
      setDocumentParsing(false);
    }
  };

  const handleImportRulesFromWord = async (file: File) => {
    const ontologyId = Array.from(new Set(semanticCoverage?.objects.map(item => item.ontologyId) || []))[0];
    if (!ontologyId) {
      message.warning('当前数据源还没有关联本体，请先生成本体草案');
      return;
    }
    setRuleImporting(true);
    try {
      const result = await ontologyApi.importRulesFromWord(ontologyId, file, true);
      setRuleImportResult(result);
      if (result.errorCount > 0) {
        message.warning(`识别 ${result.rules.length} 条规则，成功导入 ${result.importedCount} 条，失败 ${result.errorCount} 条`);
      } else {
        message.success(`已从 Word 导入 ${result.importedCount} 条自定义规则`);
      }
      await fetchData();
    } catch {
      message.error('规则 Word 导入失败，请确认文件格式和规则字段');
    } finally {
      setRuleImporting(false);
    }
  };

  const handleTestApiGateway = async () => {
    if (!id) return;
    setGatewayTesting(true);
    try {
      const result = await dataSourceApi.testApiGateway(parseInt(id));
      if (result.reachable) {
        message.success(result.message);
      } else {
        message.warning(result.message);
      }
      fetchData();
    } catch {
      message.error('业务 API 网关测试失败');
    } finally {
      setGatewayTesting(false);
    }
  };

  const tableColumns = [
    {
      title: '表名',
      dataIndex: 'tableName',
      key: 'tableName',
    },
    {
      title: '行数',
      dataIndex: 'rowCount',
      key: 'rowCount',
    },
    {
      title: '主键',
      dataIndex: 'primaryKey',
      key: 'primaryKey',
      render: (pk: string) => <Tag>{pk}</Tag>,
    },
    {
      title: '扫描时间',
      dataIndex: 'scannedAt',
      key: 'scannedAt',
    },
  ];

  function bindingColor(status?: string) {
    if (status === 'ready') return 'green';
    if (status === 'partial' || status === 'incomplete' || status === 'bound') return 'orange';
    return 'red';
  }

  const apiColumns = [
    {
      title: '操作码',
      dataIndex: 'operationCode',
      key: 'operationCode',
    },
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '方法',
      dataIndex: 'method',
      key: 'method',
      render: (method: string) => (
        <Tag color={method === 'GET' ? 'green' : method === 'POST' ? 'blue' : 'orange'}>
          {method}
        </Tag>
      ),
    },
    {
      title: '路径',
      dataIndex: 'path',
      key: 'path',
    },
    {
      title: '语义动作',
      dataIndex: 'semanticAction',
      key: 'semanticAction',
      render: (action: string) => action || '-',
    },
  ];

  const operationBindingColumns = [
    ...apiColumns,
    {
      title: '绑定对象',
      dataIndex: 'objectCode',
      key: 'objectCode',
      render: (objectCode: string) => objectCode || '-',
    },
    {
      title: '绑定状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => <Tag color={bindingColor(status)}>{status}</Tag>,
    },
    {
      title: '自动化',
      dataIndex: 'automationReady',
      key: 'automationReady',
      render: (ready: boolean) => <Tag color={ready ? 'green' : 'orange'}>{ready ? '就绪' : '待补齐'}</Tag>,
    },
    {
      title: '缺口',
      dataIndex: 'gaps',
      key: 'gaps',
      render: (gaps: string[]) => gaps.length ? gaps.join('；') : '-',
    },
  ];

  const readinessColumns = [
    {
      title: '检查项',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '状态',
      dataIndex: 'passed',
      key: 'passed',
      render: (passed: boolean) => <Tag color={passed ? 'green' : 'orange'}>{passed ? '通过' : '待处理'}</Tag>,
    },
    {
      title: '证据',
      dataIndex: 'evidence',
      key: 'evidence',
    },
    {
      title: '建议动作',
      dataIndex: 'remediation',
      key: 'remediation',
    },
    {
      title: '权重',
      dataIndex: 'weight',
      key: 'weight',
      width: 80,
    },
  ];

  const readinessColor = (status?: string) => {
    if (status === 'ready') return 'green';
    if (status === 'partial') return 'orange';
    return 'red';
  };

  const coverageColor = (status?: string) => {
    if (status === 'ready') return 'green';
    if (status === 'partial') return 'orange';
    return 'red';
  };

  const driftStatusColor = (status?: string) => {
    if (status === 'no_drift') return 'green';
    if (status === 'drift_detected') return 'orange';
    return 'red';
  };

  const driftTableColumns = [
    {
      title: '表名',
      dataIndex: 'tableName',
      key: 'tableName',
    },
    {
      title: '行数',
      key: 'rowCount',
      render: (_: unknown, record: SchemaDriftTableChange) => (
        record.rowCountChanged ? `${record.oldRowCount} -> ${record.newRowCount}` : record.newRowCount
      ),
    },
    {
      title: '主键',
      key: 'primaryKey',
      render: (_: unknown, record: SchemaDriftTableChange) => (
        record.primaryKeyChanged ? `${record.oldPrimaryKey || '-'} -> ${record.newPrimaryKey || '-'}` : (record.newPrimaryKey || '-')
      ),
    },
    {
      title: '新增字段',
      key: 'addedColumns',
      render: (_: unknown, record: SchemaDriftTableChange) => record.addedColumns.map(item => <Tag color="green" key={item.columnName}>{item.columnName}</Tag>),
    },
    {
      title: '删除字段',
      key: 'removedColumns',
      render: (_: unknown, record: SchemaDriftTableChange) => record.removedColumns.map(item => <Tag color="red" key={item.columnName}>{item.columnName}</Tag>),
    },
    {
      title: '变更字段',
      key: 'changedColumns',
      render: (_: unknown, record: SchemaDriftTableChange) => record.changedColumns.map(item => <Tag color="orange" key={item.columnName}>{item.columnName}</Tag>),
    },
  ];

  const coverageColumns = [
    {
      title: '业务对象',
      key: 'object',
      render: (_: unknown, record: SemanticCoverageObject) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{record.objectName}</Typography.Text>
          <Typography.Text type="secondary">{record.objectCode}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '来源表',
      dataIndex: 'sourceTable',
      key: 'sourceTable',
      render: (table: string) => <Tag>{table}</Tag>,
    },
    {
      title: '本体版本',
      key: 'ontology',
      render: (_: unknown, record: SemanticCoverageObject) => `${record.ontologyName} ${record.ontologyVersion}`,
    },
    {
      title: '映射',
      key: 'mappings',
      render: (_: unknown, record: SemanticCoverageObject) => `${record.confirmedMappings} 已确认 / ${record.pendingMappings} 待审`,
    },
    {
      title: '规则',
      dataIndex: 'ruleCount',
      key: 'ruleCount',
    },
    {
      title: 'API',
      dataIndex: 'operationCount',
      key: 'operationCount',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => <Tag color={coverageColor(status)}>{status}</Tag>,
    },
    {
      title: '自动化',
      dataIndex: 'automationReady',
      key: 'automationReady',
      render: (ready: boolean) => <Tag color={ready ? 'green' : 'orange'}>{ready ? '就绪' : '待补齐'}</Tag>,
    },
  ];

  const ruleSeverityColor = (severity: string) => {
    if (severity === 'blocking') return 'red';
    if (severity === 'warning') return 'orange';
    return 'blue';
  };

  const ruleColumns = [
    {
      title: '规则编码',
      dataIndex: 'code',
      key: 'code',
      width: 220,
      render: (code: string) => <Typography.Text code>{code}</Typography.Text>,
    },
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 220,
    },
    {
      title: '对象',
      dataIndex: 'scope_object_code',
      key: 'scope_object_code',
      width: 130,
      render: (objectCode: string) => <Tag>{objectCode}</Tag>,
    },
    {
      title: '类型',
      dataIndex: 'rule_type',
      key: 'rule_type',
      width: 120,
    },
    {
      title: '严重程度',
      dataIndex: 'severity',
      key: 'severity',
      width: 120,
      render: (severity: string) => <Tag color={ruleSeverityColor(severity)}>{severity}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (status: string) => <Tag color={status === 'published' ? 'green' : 'orange'}>{status}</Tag>,
    },
    {
      title: '规则表达式',
      dataIndex: 'expression',
      key: 'expression',
      render: (expression: string) => (
        <code style={{ background: '#f5f5f5', padding: '2px 6px', borderRadius: 4 }}>
          {expression}
        </code>
      ),
    },
    {
      title: '业务说明',
      dataIndex: 'natural_language',
      key: 'natural_language',
      ellipsis: true,
    },
  ];

  const riskColor = (severity: string) => {
    if (severity === 'blocking') return 'red';
    if (severity === 'warning') return 'orange';
    return 'blue';
  };

  const renderDocumentParser = () => (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Alert
        type="info"
        message="上传 Word 合同进行平台级解析"
        description="平台会直接读取 .docx，抽取合同编号、标题、甲乙方、金额、日期、付款条款、条款结构、风险提示和本体映射建议。"
      />
      <Upload.Dragger
        accept=".docx"
        maxCount={1}
        beforeUpload={(file) => {
          handleParseContractDocument(file);
          return false;
        }}
        showUploadList={false}
        disabled={documentParsing}
      >
        <p className="ant-upload-drag-icon"><UploadOutlined /></p>
        <p className="ant-upload-text">点击或拖拽 Word 合同到这里解析</p>
        <p className="ant-upload-hint">当前支持 .docx。解析结果只用于平台语义接入和演示验证。</p>
      </Upload.Dragger>
      {documentParsing && <Spin tip="正在解析 Word 合同..." />}
      {documentParseResult && (
        <>
          <Card size="small" title="文件与合同要素">
            <Descriptions column={3}>
              <Descriptions.Item label="文件名">{documentParseResult.file.name}</Descriptions.Item>
              <Descriptions.Item label="大小">{documentParseResult.file.size} bytes</Descriptions.Item>
              <Descriptions.Item label="MD5">{documentParseResult.file.md5}</Descriptions.Item>
              <Descriptions.Item label="合同编号">{documentParseResult.entities.contractNo || '-'}</Descriptions.Item>
              <Descriptions.Item label="标题">{documentParseResult.entities.title || '-'}</Descriptions.Item>
              <Descriptions.Item label="金额">{documentParseResult.entities.amount ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="甲方">{documentParseResult.entities.partyA || '-'}</Descriptions.Item>
              <Descriptions.Item label="乙方">{documentParseResult.entities.partyB || '-'}</Descriptions.Item>
              <Descriptions.Item label="签订日期">{documentParseResult.entities.signDate || '-'}</Descriptions.Item>
              <Descriptions.Item label="开始日期">{documentParseResult.entities.startDate || '-'}</Descriptions.Item>
              <Descriptions.Item label="结束日期">{documentParseResult.entities.endDate || '-'}</Descriptions.Item>
              <Descriptions.Item label="文本长度">{documentParseResult.textLength}</Descriptions.Item>
            </Descriptions>
          </Card>
          <Card size="small" title={`风险提示 (${documentParseResult.risks.length})`}>
            {documentParseResult.risks.length === 0 ? (
              <Alert type="success" message="未发现基础解析风险" />
            ) : (
              <Space wrap>
                {documentParseResult.risks.map(item => (
                  <Tag color={riskColor(item.severity)} key={item.code}>
                    {item.code}: {item.message}
                  </Tag>
                ))}
              </Space>
            )}
          </Card>
          <Card size="small" title={`付款条款 (${documentParseResult.paymentTerms.length})`}>
            <Table
              size="small"
              pagination={false}
              dataSource={documentParseResult.paymentTerms}
              rowKey={(_, index) => `payment-${index}`}
              columns={[
                { title: '来源', dataIndex: 'source', key: 'source', width: 120 },
                { title: '金额', dataIndex: 'amount', key: 'amount', width: 120, render: (value: number | null) => value ?? '-' },
                { title: '日期', dataIndex: 'date', key: 'date', width: 160, render: (value: string[]) => value?.join(', ') || '-' },
                { title: '文本', dataIndex: 'text', key: 'text' },
              ]}
            />
          </Card>
          <Card size="small" title={`条款结构 (${documentParseResult.clauses.length})`}>
            <Table
              size="small"
              dataSource={documentParseResult.clauses}
              rowKey={(_, index) => `clause-${index}`}
              columns={[
                { title: '条款', dataIndex: 'title', key: 'title', width: 260 },
                { title: '内容摘要', dataIndex: 'content', key: 'content', ellipsis: true },
              ]}
            />
          </Card>
          <Card size="small" title="本体映射提示">
            <Input.TextArea rows={8} value={JSON.stringify(documentParseResult.ontologyHints, null, 2)} readOnly />
          </Card>
          <Card size="small" title="提取文本">
            <Input.TextArea rows={12} value={documentParseResult.text} readOnly />
          </Card>
        </>
      )}
    </Space>
  );

  const renderSemanticCoverage = () => {
    if (!semanticCoverage) return null;
    return (
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <div style={{ padding: 16, border: '1px solid #f0f0f0', borderRadius: 6 }}>
          <Space align="start" size="large" style={{ width: '100%', justifyContent: 'space-between' }}>
            <div style={{ minWidth: 220 }}>
              <Progress
                type="circle"
                percent={semanticCoverage.score}
                strokeColor={coverageColor(semanticCoverage.status)}
              />
            </div>
            <Descriptions column={4} style={{ flex: 1 }}>
              <Descriptions.Item label="状态">
                <Tag color={coverageColor(semanticCoverage.status)}>{semanticCoverage.status}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="业务对象">{semanticCoverage.summary.businessObjects}</Descriptions.Item>
              <Descriptions.Item label="闭环对象">{semanticCoverage.summary.fullyCoveredObjects}</Descriptions.Item>
              <Descriptions.Item label="受阻对象">{semanticCoverage.summary.blockedObjects}</Descriptions.Item>
              <Descriptions.Item label="属性">{semanticCoverage.summary.attributes}</Descriptions.Item>
              <Descriptions.Item label="确认映射">{semanticCoverage.summary.confirmedMappings}</Descriptions.Item>
              <Descriptions.Item label="待审映射">{semanticCoverage.summary.pendingMappings}</Descriptions.Item>
              <Descriptions.Item label="规则">{semanticCoverage.summary.rules}</Descriptions.Item>
              <Descriptions.Item label="语义 API">{semanticCoverage.summary.semanticOperations}</Descriptions.Item>
              <Descriptions.Item label="可执行操作">{semanticCoverage.summary.executableOperations}</Descriptions.Item>
            </Descriptions>
          </Space>
          {semanticCoverage.nextActions.length > 0 && (
            <Alert
              style={{ marginTop: 16 }}
              type={semanticCoverage.status === 'ready' ? 'success' : semanticCoverage.status === 'blocked' ? 'error' : 'warning'}
              message="治理建议"
              description={semanticCoverage.nextActions.join('；')}
            />
          )}
        </div>
        <Table
          columns={coverageColumns}
          dataSource={semanticCoverage.objects}
          rowKey={(record) => `${record.ontologyId}-${record.objectCode}`}
          expandable={{
            expandedRowRender: (record) => (
              <Space direction="vertical" style={{ width: '100%' }}>
                {record.gaps.length > 0 && <Alert type="warning" message="缺口" description={record.gaps.join('；')} />}
                <Table
                  size="small"
                  columns={apiColumns}
                  dataSource={record.operations}
                  rowKey="operationCode"
                  pagination={false}
                />
              </Space>
            ),
          }}
        />
      </Space>
    );
  };

  const renderSchemaDrift = () => {
    if (!schemaDrift) return null;
    const summary = schemaDrift.summary;
    const changeRows = [
      ...schemaDrift.changedTables,
      ...schemaDrift.addedTables.map(table => ({
        tableName: table.tableName,
        primaryKeyChanged: false,
        oldPrimaryKey: null,
        newPrimaryKey: table.primaryKey,
        rowCountChanged: false,
        oldRowCount: 0,
        newRowCount: table.rowCount,
        addedColumns: table.columns,
        removedColumns: [],
        changedColumns: [],
      })),
      ...schemaDrift.removedTables.map(table => ({
        tableName: table.tableName,
        primaryKeyChanged: false,
        oldPrimaryKey: table.primaryKey,
        newPrimaryKey: null,
        rowCountChanged: false,
        oldRowCount: table.rowCount,
        newRowCount: 0,
        addedColumns: [],
        removedColumns: table.columns,
        changedColumns: [],
      })),
    ];

    return (
      <div style={{ marginBottom: 16, padding: 16, border: '1px solid #f0f0f0', borderRadius: 6 }}>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Typography.Text strong>结构漂移影响分析</Typography.Text>
          <Descriptions column={4}>
            <Descriptions.Item label="状态">
              <Tag color={driftStatusColor(schemaDrift.status)}>{schemaDrift.status}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="新增表">{summary.addedTables}</Descriptions.Item>
            <Descriptions.Item label="删除表">{summary.removedTables}</Descriptions.Item>
            <Descriptions.Item label="变更表">{summary.changedTables}</Descriptions.Item>
            <Descriptions.Item label="新增字段">{summary.addedColumns}</Descriptions.Item>
            <Descriptions.Item label="删除字段">{summary.removedColumns}</Descriptions.Item>
            <Descriptions.Item label="变更字段">{summary.changedColumns}</Descriptions.Item>
            <Descriptions.Item label="影响对象">{summary.impactedObjects}</Descriptions.Item>
            <Descriptions.Item label="影响映射">{summary.impactedMappings}</Descriptions.Item>
            <Descriptions.Item label="影响规则">{summary.impactedRules}</Descriptions.Item>
          </Descriptions>
          {schemaDrift.nextActions.length > 0 && (
            <Alert
              type={schemaDrift.status === 'drift_detected' ? 'warning' : schemaDrift.status === 'no_drift' ? 'success' : 'info'}
              message="建议动作"
              description={schemaDrift.nextActions.join('；')}
            />
          )}
          <Table
            size="small"
            columns={driftTableColumns}
            dataSource={changeRows}
            rowKey="tableName"
            pagination={false}
          />
        </Space>
      </div>
    );
  };

  if (loading) {
    return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  }

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/datasource')}>
          返回
        </Button>
        <Title level={3} style={{ margin: 0 }}>数据源详情</Title>
        {id && (
          <Button
            icon={<DownloadOutlined />}
            onClick={() => window.open(dataSourceApi.kernelPackageUrl(parseInt(id)), '_blank')}
          >
            下载语义内核包
          </Button>
        )}
        {id && (
          <Button
            icon={<BulbOutlined />}
            loading={blueprintDraftLoading}
            onClick={handleGenerateBlueprintDraft}
          >
            生成蓝图草案
          </Button>
        )}
        {id && (
          <Button
            icon={<ApiOutlined />}
            loading={gatewayTesting}
            onClick={handleTestApiGateway}
          >
            测试业务网关
          </Button>
        )}
      </Space>

      {dataSource && (
        <Card style={{ marginBottom: 16 }}>
          <Descriptions column={2}>
            <Descriptions.Item label="ID">{dataSource.id}</Descriptions.Item>
            <Descriptions.Item label="名称">{dataSource.name}</Descriptions.Item>
            <Descriptions.Item label="类型">
              <Tag color="blue">{dataSource.sourceType}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="领域">{dataSource.domain || '-'}</Descriptions.Item>
            <Descriptions.Item label="系统分类">
              <Tag>{dataSource.systemCategory}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="连接地址">
              <code>{dataSource.connectionUri}</code>
            </Descriptions.Item>
            <Descriptions.Item label="业务 API 基址">
              {dataSource.apiBaseUrl ? <code>{dataSource.apiBaseUrl}</code> : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="业务 API 请求头">
              {dataSource.apiHeadersConfigured ? dataSource.apiHeaderNames.join(', ') : '-'}
            </Descriptions.Item>
          </Descriptions>
        </Card>
      )}

      {readiness && (
        <Card style={{ marginBottom: 16 }} title="接入准备度">
          <Space align="start" size="large" style={{ width: '100%', justifyContent: 'space-between' }}>
            <div style={{ minWidth: 220 }}>
              <Progress
                type="circle"
                percent={readiness.score}
                strokeColor={readinessColor(readiness.status)}
              />
            </div>
            <Descriptions column={4} style={{ flex: 1 }}>
              <Descriptions.Item label="状态">
                <Tag color={readinessColor(readiness.status)}>{readiness.status}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="表">{readiness.summary.tables}</Descriptions.Item>
              <Descriptions.Item label="字段">{readiness.summary.columns}</Descriptions.Item>
              <Descriptions.Item label="外键">{readiness.summary.foreignKeys}</Descriptions.Item>
              <Descriptions.Item label="API">{readiness.summary.apis}</Descriptions.Item>
              <Descriptions.Item label="本体">{readiness.summary.ontologies}</Descriptions.Item>
              <Descriptions.Item label="已确认映射">{readiness.summary.confirmedMappings}</Descriptions.Item>
              <Descriptions.Item label="待审核映射">{readiness.summary.pendingMappings}</Descriptions.Item>
            </Descriptions>
          </Space>
          {readiness.nextActions.length > 0 && (
            <Alert
              style={{ marginTop: 16 }}
              type={readiness.status === 'blocked' ? 'error' : 'warning'}
              message="下一步动作"
              description={readiness.nextActions.join('；')}
            />
          )}
        </Card>
      )}

      <Card>
        <Tabs defaultActiveKey="tables">
          <TabPane tab={`已扫描表 (${tables.length})`} key="tables">
            <div style={{ marginBottom: 16 }}>
              <Space>
                <Button
                  type="primary"
                  icon={<ScanOutlined />}
                  loading={scanLoading}
                  onClick={handleScan}
                >
                  重新扫描
                </Button>
                <Button
                  icon={<BranchesOutlined />}
                  loading={driftLoading}
                  onClick={handleAnalyzeDrift}
                >
                  分析结构漂移
                </Button>
              </Space>
            </div>
            {renderSchemaDrift()}
            <Table
              columns={tableColumns}
              dataSource={tables}
              rowKey="id"
            />
          </TabPane>
          <TabPane tab={`已登记API (${apis.length})`} key="apis">
            <div style={{ marginBottom: 16 }}>
              <Button icon={<PlusOutlined />}>
                新增API
              </Button>
              <Button
                icon={<ImportOutlined />}
                style={{ marginLeft: 8 }}
                onClick={() => setOpenApiModalVisible(true)}
              >
                导入 OpenAPI
              </Button>
            </div>
            {operationBindings && (
              <div style={{ marginBottom: 16, padding: 16, border: '1px solid #f0f0f0', borderRadius: 6 }}>
                <Descriptions column={4}>
                  <Descriptions.Item label="状态">
                    <Tag color={bindingColor(operationBindings.status)}>{operationBindings.status}</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="API">{operationBindings.summary.operations}</Descriptions.Item>
                  <Descriptions.Item label="已绑定">{operationBindings.summary.boundOperations}</Descriptions.Item>
                  <Descriptions.Item label="自动化就绪">{operationBindings.summary.readyOperations}</Descriptions.Item>
                  <Descriptions.Item label="未绑定">{operationBindings.summary.unboundOperations}</Descriptions.Item>
                  <Descriptions.Item label="格式错误">{operationBindings.summary.invalidActions}</Descriptions.Item>
                  <Descriptions.Item label="阻断">{operationBindings.summary.blockedOperations}</Descriptions.Item>
                </Descriptions>
                {operationBindings.nextActions.length > 0 && (
                  <Alert
                    style={{ marginTop: 16 }}
                    type={operationBindings.status === 'ready' ? 'success' : operationBindings.status === 'blocked' ? 'error' : 'warning'}
                    message="绑定建议"
                    description={operationBindings.nextActions.join('；')}
                  />
                )}
              </div>
            )}
            <Table
              columns={operationBindingColumns}
              dataSource={operationBindings?.items || []}
              rowKey="operationCode"
            />
          </TabPane>
          <TabPane tab="语义覆盖" key="coverage">
            {renderSemanticCoverage()}
          </TabPane>
          <TabPane tab={`业务规则 (${businessRules.length})`} key="rules">
            <Alert
              style={{ marginBottom: 16 }}
              type="info"
              message="当前数据源关联本体中已定义的规则"
              description="这些规则会被本体语义内核用于合规研判、操作预检、决策一致性评估和自动化拦截。"
            />
            <Card size="small" title="通过 Word 自定义规则" style={{ marginBottom: 16 }}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Alert
                  type="success"
                  message="支持上传 Word 规则定义表"
                  description="建议表头：规则编码、规则名称、适用对象、规则类型、规则表达式、严重程度、自然语言说明。导入会写入当前数据源关联的本体草案。"
                />
                <Upload.Dragger
                  accept=".docx"
                  maxCount={1}
                  beforeUpload={(file) => {
                    handleImportRulesFromWord(file);
                    return false;
                  }}
                  showUploadList={false}
                  disabled={ruleImporting}
                >
                  <p className="ant-upload-drag-icon"><UploadOutlined /></p>
                  <p className="ant-upload-text">点击或拖拽 Word 规则文档到这里导入</p>
                  <p className="ant-upload-hint">支持表格和“规则编码：...”分段文本。已发布本体仍需先派生草案版本。</p>
                </Upload.Dragger>
                {ruleImporting && <Spin tip="正在解析并导入规则..." />}
                {ruleImportResult && (
                  <Alert
                    type={ruleImportResult.errorCount > 0 ? 'warning' : 'success'}
                    message={`识别 ${ruleImportResult.rules.length} 条规则，成功导入 ${ruleImportResult.importedCount} 条`}
                    description={[
                      ...ruleImportResult.warnings,
                      ...ruleImportResult.errors.map(item => `${item.code}: ${item.error}`),
                    ].join('；') || `来源文件：${ruleImportResult.file.name}`}
                  />
                )}
              </Space>
            </Card>
            <Table
              columns={ruleColumns}
              dataSource={businessRules}
              rowKey={(record) => `${record.ontologyId}-${record.id}`}
              expandable={{
                expandedRowRender: (record) => (
                  <Descriptions column={1} size="small">
                    <Descriptions.Item label="所属本体ID">{record.ontologyId}</Descriptions.Item>
                    <Descriptions.Item label="规则表达式"><code>{record.expression}</code></Descriptions.Item>
                    <Descriptions.Item label="自然语言说明">{record.natural_language}</Descriptions.Item>
                  </Descriptions>
                ),
              }}
            />
          </TabPane>
          <TabPane tab="Word解析" key="document-parser">
            {renderDocumentParser()}
          </TabPane>
          <TabPane tab="接入检查" key="readiness">
            <Table
              columns={readinessColumns}
              dataSource={readiness?.checks || []}
              rowKey="code"
              pagination={false}
            />
          </TabPane>
        </Tabs>
      </Card>

      <Modal
        title="导入 OpenAPI"
        open={openApiModalVisible}
        onCancel={() => {
          setOpenApiModalVisible(false);
          openApiForm.resetFields();
        }}
        onOk={() => openApiForm.submit()}
        confirmLoading={importLoading}
        width={760}
      >
        <Form form={openApiForm} layout="vertical" onFinish={handleImportOpenApi}>
          <Form.Item name="specUrl" label="OpenAPI URL">
            <Input placeholder="例如：https://legacy.example/openapi.json" />
          </Form.Item>
          <Form.Item
            name="specJson"
            label="OpenAPI JSON"
            rules={[
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (getFieldValue('specUrl')?.trim() || value?.trim()) return Promise.resolve();
                  return Promise.reject(new Error('请填写 OpenAPI URL 或粘贴 OpenAPI JSON 文档'));
                },
              }),
            ]}
          >
            <Input.TextArea
              rows={12}
              placeholder='{"openapi":"3.0.0","paths":{"/contracts/{id}/submit":{"post":{"operationId":"submit_contract","summary":"提交合同审批"}}}}'
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="行业蓝图草案"
        open={blueprintDraftVisible}
        onCancel={() => setBlueprintDraftVisible(false)}
        footer={null}
        width={760}
      >
        <Input.TextArea
          rows={16}
          value={blueprintDraft ? JSON.stringify(blueprintDraft, null, 2) : ''}
          readOnly
        />
      </Modal>
    </div>
  );
};

export default DataSourceDetail;
