import { adviceTexts, codedText, joinSentences, scanReport } from '../../i18n/text';
import React, { useCallback, useEffect, useState } from 'react';
import { DRIFT_STATUS, ONTOLOGY_STATUS, READINESS_STATUS, RELATION_KIND, RULE_SEVERITY, RULE_TYPE } from '../../i18n/labels';
import { useLabel, useLocale, useT } from '../../i18n/locale';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Table, Button, Space, Typography, Tag, Tabs, Descriptions, message, Spin, Progress, Alert, Modal, Form, Input, Upload, Steps } from 'antd';
import { ApiOutlined, ArrowLeftOutlined, ScanOutlined, PlusOutlined, ImportOutlined, DownloadOutlined, BulbOutlined, BranchesOutlined, UploadOutlined } from '@ant-design/icons';
import { aiApi, dataSourceApi, ontologyApi, requestErrorMessage } from '../../api';
import type {
  BusinessRule,
  DataSource,
  DataSourceReadiness,
  IndustryBlueprint,
  OperationBindingResult,
  ReadinessCheck,
  ReasoningChain,
  RuleWordImportResult,
  SchemaDriftResult,
  SchemaDriftTableChange,
  SemanticCoverageObject,
  SemanticCoverageResult,
  SourceApi,
  SourceTable,
  SourceTableRows,
} from '../../types';
import { useTabParam } from '../../hooks/useTabParam';

const { Title } = Typography;
const { TabPane } = Tabs;

/**
 * A rule as this page renders it: the rule list's own shape, plus the ontology it came from.
 *
 * The columns below used to ask for the wire spellings (`rule_type`, `scope_object_code`,
 * `natural_language`) because the endpoint sent them; it now sends camelCase as well
 * (`ontology.business_rule_row` emits both, and says why). Reading the camelCase half here
 * rather than the compatibility half means one fewer place relying on the dual emission --
 * which exists for older clients, not for new code.
 */
type DataSourceRule = BusinessRule & { ontologyId: number };

const DataSourceDetail: React.FC = () => {
  const label = useLabel();
  const t = useT();
  const { locale } = useLocale();
  const [tab, setTab] = useTabParam('tables');
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
  const [ruleImporting, setRuleImporting] = useState(false);
  const [ruleImportResult, setRuleImportResult] = useState<RuleWordImportResult | null>(null);
  const [tableBrowser, setTableBrowser] = useState<SourceTableRows | null>(null);
  const [tableBrowserLoading, setTableBrowserLoading] = useState(false);
  const [reasoningChain, setReasoningChain] = useState<ReasoningChain | null>(null);
  const [openApiForm] = Form.useForm();

  const fetchData = useCallback(async () => {
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
      setApis(apisData.items);
      setReadiness(readinessData);
      setSemanticCoverage(coverageData);
      setOperationBindings(bindingData);
      const ontologyIds = Array.from(new Set(coverageData.objects.map(item => item.ontologyId)));
      const ruleGroups = await Promise.all(
        ontologyIds.map(async ontologyId => {
          // No limit: this list is "every rule of every ontology this source feeds", which is
          // a summary rather than a screen with a pager, so it wants all of them.
          const { items } = await ontologyApi.getRules(ontologyId);
          return items.map((rule) => ({ ...rule, ontologyId }));
        })
      );
      setBusinessRules(ruleGroups.flat());
      // 获取数据源基本信息（从列表中获取）
      const sources = await dataSourceApi.list();
      const source = sources.find(s => s.id === parseInt(id));
      if (source) setDataSource(source);
    } catch (error) {
      message.error(requestErrorMessage(error, t('datasource.loadDetailFailed')));
    } finally {
      setLoading(false);
    }
  }, [id, t]);

  // Through the API client: this button used to hand a URL to `window.open`, which the
  // browser fetches without the bearer token the endpoint requires.
  const handleDownloadKernel = async () => {
    if (!id) return;
    try {
      await dataSourceApi.downloadKernelPackage(parseInt(id));
    } catch (error) {
      message.error(requestErrorMessage(error, t('datasource.downloadKernelFailed')));
    }
  };

  const handleScan = async () => {
    if (!id) return;
    setScanLoading(true);
    try {
      const report = scanReport(await dataSourceApi.scan(parseInt(id)), t);
      // Same words as the list page: both scan, and the one that was fixed first said
      // 「扫描完成」 while the other reported the tables. `scanReport` is where that lives now.
      if (report.level === 'warning') message.warning(report.text, 8);
      else message.success(report.text);
      setSchemaDrift(null);
      fetchData();
    } catch (error) {
      message.error(requestErrorMessage(error, t('datasource.scanFailed')));
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
      message.success(t('datasource.importedApis', { count: result.count }));
      setOpenApiModalVisible(false);
      openApiForm.resetFields();
      fetchData();
    } catch (error) {
      message.error(error instanceof SyntaxError ? t('datasource.openApiJsonInvalid') : t('datasource.openApiImportFailed'));
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
        message.warning(t('datasource.driftDetected'));
      } else if (result.status === 'not_scanned') {
        message.info(t('datasource.noScanBaseline'));
      } else {
        message.success(t('datasource.noDrift'));
      }
    } catch (error) {
      message.error(requestErrorMessage(error, t('datasource.driftAnalysisFailed')));
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
      message.success(result.usedRemoteModel ? t('datasource.blueprintRemoteDone') : t('datasource.blueprintLocalDone'));
    } catch (error) {
      message.error(requestErrorMessage(error, t('datasource.blueprintGenerateFailed')));
    } finally {
      setBlueprintDraftLoading(false);
    }
  };

  const handleBrowseTable = async (tableName: string, offset = 0) => {
    if (!id) return;
    setTableBrowserLoading(true);
    try {
      setTableBrowser(await dataSourceApi.browseTable(parseInt(id), tableName, 50, offset));
    } catch (error) {
      message.error(requestErrorMessage(error, t('datasource.browseTableFailed')));
    } finally {
      setTableBrowserLoading(false);
    }
  };

  const loadReasoningChain = useCallback(async () => {
    if (!id) return;
    try {
      setReasoningChain(await dataSourceApi.getReasoningChain(parseInt(id)));
    } catch (error) {
      // The server's reason was discarded here (the catch had no binding), so a permission
      // or server failure read as a generic "加载…失败".
      message.error(requestErrorMessage(error, t('datasource.reasoningLoadFailed')));
    }
  }, [id, t]);

  // Declared after both loaders: reading a `const` callback from an effect above its
  // declaration is what the initialisation-order warning was about, and listing the real
  // dependencies is what the stale-closure warning was about.
  useEffect(() => {
    fetchData();
    loadReasoningChain();
  }, [fetchData, loadReasoningChain]);


  const handleImportRulesFromWord = async (file: File) => {
    const ontologyId = Array.from(new Set(semanticCoverage?.objects.map(item => item.ontologyId) || []))[0];
    if (!ontologyId) {
      message.warning(t('datasource.noOntologyForRules'));
      return;
    }
    setRuleImporting(true);
    try {
      const result = await ontologyApi.importRulesFromWord(ontologyId, file, true);
      setRuleImportResult(result);
      if (result.errorCount > 0) {
        message.warning(t('datasource.ruleImportPartial', { recognized: result.rules.length, imported: result.importedCount, failed: result.errorCount }));
      } else {
        message.success(t('datasource.ruleImportSuccess', { count: result.importedCount }));
      }
      await fetchData();
      await loadReasoningChain();
    } catch (error) {
      message.error(requestErrorMessage(error, t('datasource.ruleImportFailed')));
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
    } catch (error) {
      message.error(requestErrorMessage(error, t('datasource.gatewayTestFailed')));
    } finally {
      setGatewayTesting(false);
    }
  };

  const tableColumns = [
    {
      title: t('datasource.tableName'),
      dataIndex: 'tableName',
      key: 'tableName',
    },
    {
      title: t('datasource.rowCount'),
      dataIndex: 'rowCount',
      key: 'rowCount',
    },
    {
      title: t('datasource.primaryKey'),
      dataIndex: 'primaryKey',
      key: 'primaryKey',
      render: (pk: string) => <Tag>{pk}</Tag>,
    },
    {
      title: t('datasource.scannedAt'),
      dataIndex: 'scannedAt',
      key: 'scannedAt',
    },
    {
      title: t('datasource.dataBrowse'),
      key: 'browse',
      render: (_: unknown, record: SourceTable) => <Button type="link" onClick={() => handleBrowseTable(record.tableName)}>{t('datasource.browseButton')}</Button>,
    },
  ];

  function bindingColor(status?: string) {
    if (status === 'ready') return 'green';
    if (status === 'partial' || status === 'incomplete' || status === 'bound') return 'orange';
    return 'red';
  }

  const apiColumns = [
    {
      title: t('datasource.operationCode'),
      dataIndex: 'operationCode',
      key: 'operationCode',
    },
    {
      title: t('datasource.name'),
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: t('datasource.method'),
      dataIndex: 'method',
      key: 'method',
      render: (method: string) => (
        <Tag color={method === 'GET' ? 'green' : method === 'POST' ? 'blue' : 'orange'}>
          {method}
        </Tag>
      ),
    },
    {
      title: t('datasource.path'),
      dataIndex: 'path',
      key: 'path',
    },
    {
      title: t('datasource.semanticAction'),
      dataIndex: 'semanticAction',
      key: 'semanticAction',
      render: (action: string) => action || '-',
    },
  ];

  const operationBindingColumns = [
    ...apiColumns,
    {
      title: t('datasource.boundObject'),
      dataIndex: 'objectCode',
      key: 'objectCode',
      render: (objectCode: string) => objectCode || '-',
    },
    {
      title: t('datasource.bindingStatus'),
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => <Tag color={bindingColor(status)}>{label(READINESS_STATUS, status)}</Tag>,
    },
    {
      title: t('datasource.automation'),
      dataIndex: 'automationReady',
      key: 'automationReady',
      render: (ready: boolean) => <Tag color={ready ? 'green' : 'orange'}>{ready ? t('datasource.automationReady') : t('datasource.automationPending')}</Tag>,
    },
    {
      title: t('datasource.gaps'),
      dataIndex: 'gaps',
      key: 'gaps',
      render: (gaps: string[]) => gaps.length ? joinSentences(gaps, locale) : '-',
    },
  ];

  /**
   * One onboarding check's sentence, in the reader's language.
   *
   * Same shape as the release gate: the server sends the code, whether it passed, and the
   * facts (`numbers`, `status`, `text`) beside its own Chinese. The remediation column is the
   * check's advice, so it reads `advice.<code>` -- one sentence per check, said once, and the
   * same one the panel above shows.
   */
  const checkText = (check: ReadinessCheck, field: 'name' | 'evidence'): string => {
    const params = {
      ...(check.numbers ?? {}),
      url: check.text ?? '',
      tables: check.numbers?.tables ?? 0,
      columns: check.numbers?.columns ?? 0,
    };
    const key =
      field === 'evidence' && check.status
        ? `datasource.check.${check.code}.evidence.${check.status}`
        : `datasource.check.${check.code}.${field}`;
    return codedText(t, key, check[field], params);
  };

  const readinessColumns = [
    {
      title: t('datasource.checkItem'),
      dataIndex: 'name',
      key: 'name',
      render: (_: string, check: ReadinessCheck) => checkText(check, 'name'),
    },
    {
      title: t('datasource.status'),
      dataIndex: 'passed',
      key: 'passed',
      render: (passed: boolean) => <Tag color={passed ? 'green' : 'orange'}>{passed ? t('datasource.passed') : t('datasource.pending')}</Tag>,
    },
    {
      title: t('datasource.evidence'),
      dataIndex: 'evidence',
      key: 'evidence',
      render: (_: string, check: ReadinessCheck) => checkText(check, 'evidence'),
    },
    {
      title: t('datasource.remediation'),
      dataIndex: 'remediation',
      key: 'remediation',
      render: (_: string, check: ReadinessCheck) => {
        return codedText(t, `datasource.advice.${check.code}`, check.remediation);
      },
    },
    {
      title: t('datasource.weight'),
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
      title: t('datasource.tableName'),
      dataIndex: 'tableName',
      key: 'tableName',
    },
    {
      title: t('datasource.rowCount'),
      key: 'rowCount',
      render: (_: unknown, record: SchemaDriftTableChange) => (
        record.rowCountChanged ? `${record.oldRowCount} -> ${record.newRowCount}` : record.newRowCount
      ),
    },
    {
      title: t('datasource.primaryKey'),
      key: 'primaryKey',
      render: (_: unknown, record: SchemaDriftTableChange) => (
        record.primaryKeyChanged ? `${record.oldPrimaryKey || '-'} -> ${record.newPrimaryKey || '-'}` : (record.newPrimaryKey || '-')
      ),
    },
    {
      title: t('datasource.addedColumns'),
      key: 'addedColumns',
      render: (_: unknown, record: SchemaDriftTableChange) => record.addedColumns.map(item => <Tag color="green" key={item.columnName}>{item.columnName}</Tag>),
    },
    {
      title: t('datasource.removedColumns'),
      key: 'removedColumns',
      render: (_: unknown, record: SchemaDriftTableChange) => record.removedColumns.map(item => <Tag color="red" key={item.columnName}>{item.columnName}</Tag>),
    },
    {
      title: t('datasource.changedColumns'),
      key: 'changedColumns',
      render: (_: unknown, record: SchemaDriftTableChange) => record.changedColumns.map(item => <Tag color="orange" key={item.columnName}>{item.columnName}</Tag>),
    },
  ];

  const coverageColumns = [
    {
      title: t('datasource.businessObjects'),
      key: 'object',
      render: (_: unknown, record: SemanticCoverageObject) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{record.objectName}</Typography.Text>
          <Typography.Text type="secondary">{record.objectCode}</Typography.Text>
        </Space>
      ),
    },
    {
      title: t('datasource.sourceTable'),
      dataIndex: 'sourceTable',
      key: 'sourceTable',
      render: (table: string) => <Tag>{table}</Tag>,
    },
    {
      title: t('datasource.ontologyVersion'),
      key: 'ontology',
      render: (_: unknown, record: SemanticCoverageObject) => `${record.ontologyName} ${record.ontologyVersion}`,
    },
    {
      title: t('datasource.mappings'),
      key: 'mappings',
      render: (_: unknown, record: SemanticCoverageObject) => t('datasource.mappingCounts', { confirmed: record.confirmedMappings, pending: record.pendingMappings }),
    },
    {
      title: t('datasource.rules'),
      dataIndex: 'ruleCount',
      key: 'ruleCount',
    },
    {
      title: 'API',
      dataIndex: 'operationCount',
      key: 'operationCount',
    },
    {
      title: t('datasource.status'),
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => <Tag color={coverageColor(status)}>{label(READINESS_STATUS, status)}</Tag>,
    },
    {
      title: t('datasource.automation'),
      dataIndex: 'automationReady',
      key: 'automationReady',
      render: (ready: boolean) => <Tag color={ready ? 'green' : 'orange'}>{ready ? t('datasource.automationReady') : t('datasource.automationPending')}</Tag>,
    },
  ];

  const ruleSeverityColor = (severity: string) => {
    if (severity === 'blocking') return 'red';
    if (severity === 'warning') return 'orange';
    return 'blue';
  };

  const ruleColumns = [
    {
      title: t('datasource.ruleCode'),
      dataIndex: 'code',
      key: 'code',
      width: 220,
      render: (code: string) => <Typography.Text code>{code}</Typography.Text>,
    },
    {
      title: t('datasource.name'),
      dataIndex: 'name',
      key: 'name',
      width: 220,
    },
    {
      title: t('datasource.object'),
      dataIndex: 'scopeObjectCode',
      key: 'scope_object_code',
      width: 130,
      render: (objectCode: string) => <Tag>{objectCode}</Tag>,
    },
    {
      title: t('datasource.type'),
      dataIndex: 'ruleType',
      key: 'ruleType',
      width: 120,
      // Through `labels.ts` like every other vocabulary column. Renaming the key from the wire
      // spelling to the camelCase one made the enum-rendering check see this column for the
      // first time -- the value it was printing raw (`validation`, `compliance`) is the same
      // either way; the name was what hid it.
      render: (ruleType: string) => <Tag>{label(RULE_TYPE, ruleType)}</Tag>,
    },
    {
      title: t('datasource.severity'),
      dataIndex: 'severity',
      key: 'severity',
      width: 120,
      render: (severity: string) => <Tag color={ruleSeverityColor(severity)}>{label(RULE_SEVERITY, severity)}</Tag>,
    },
    {
      title: t('datasource.status'),
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (status: string) => <Tag color={status === 'published' ? 'green' : 'orange'}>{label(ONTOLOGY_STATUS, status)}</Tag>,
    },
    {
      title: t('datasource.ruleExpression'),
      dataIndex: 'expression',
      key: 'expression',
      render: (expression: string) => (
        <code style={{ background: '#f5f5f5', padding: '2px 6px', borderRadius: 4 }}>
          {expression}
        </code>
      ),
    },
    {
      title: t('datasource.businessNote'),
      dataIndex: 'natural_language',
      key: 'natural_language',
      ellipsis: true,
    },
  ];

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
              <Descriptions.Item label={t('datasource.status')}>
                <Tag color={coverageColor(semanticCoverage.status)}>{label(READINESS_STATUS, semanticCoverage.status)}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('datasource.businessObjects')}>{semanticCoverage.summary.businessObjects}</Descriptions.Item>
              <Descriptions.Item label={t('datasource.fullyCoveredObjects')}>{semanticCoverage.summary.fullyCoveredObjects}</Descriptions.Item>
              <Descriptions.Item label={t('datasource.blockedObjects')}>{semanticCoverage.summary.blockedObjects}</Descriptions.Item>
              <Descriptions.Item label={t('datasource.attributes')}>{semanticCoverage.summary.attributes}</Descriptions.Item>
              <Descriptions.Item label={t('datasource.coverageConfirmed')}>{semanticCoverage.summary.confirmedMappings}</Descriptions.Item>
              <Descriptions.Item label={t('datasource.coveragePending')}>{semanticCoverage.summary.pendingMappings}</Descriptions.Item>
              <Descriptions.Item label={t('datasource.rules')}>{semanticCoverage.summary.rules}</Descriptions.Item>
              <Descriptions.Item label={t('datasource.semanticApis')}>{semanticCoverage.summary.semanticOperations}</Descriptions.Item>
              <Descriptions.Item label={t('datasource.executableOperations')}>{semanticCoverage.summary.executableOperations}</Descriptions.Item>
            </Descriptions>
          </Space>
          {semanticCoverage.nextActions.length > 0 && (
            <Alert
              style={{ marginTop: 16 }}
              type={semanticCoverage.status === 'ready' ? 'success' : semanticCoverage.status === 'blocked' ? 'error' : 'warning'}
              message={t('datasource.governanceAdvice')}
              description={joinSentences(adviceTexts(semanticCoverage.nextActions, semanticCoverage.nextActionCodes, t), locale)}
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
                {record.gaps.length > 0 && <Alert type="warning" message={t('datasource.gaps')} description={joinSentences(record.gaps, locale)} />}
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
          <Typography.Text strong>{t('datasource.driftTitle')}</Typography.Text>
          <Descriptions column={4}>
            <Descriptions.Item label={t('datasource.status')}>
              <Tag color={driftStatusColor(schemaDrift.status)}>{label(DRIFT_STATUS, schemaDrift.status)}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label={t('datasource.addedTables')}>{summary.addedTables}</Descriptions.Item>
            <Descriptions.Item label={t('datasource.removedTables')}>{summary.removedTables}</Descriptions.Item>
            <Descriptions.Item label={t('datasource.changedTables')}>{summary.changedTables}</Descriptions.Item>
            <Descriptions.Item label={t('datasource.addedColumns')}>{summary.addedColumns}</Descriptions.Item>
            <Descriptions.Item label={t('datasource.removedColumns')}>{summary.removedColumns}</Descriptions.Item>
            <Descriptions.Item label={t('datasource.changedColumns')}>{summary.changedColumns}</Descriptions.Item>
            <Descriptions.Item label={t('datasource.impactedObjects')}>{summary.impactedObjects}</Descriptions.Item>
            <Descriptions.Item label={t('datasource.impactedMappings')}>{summary.impactedMappings}</Descriptions.Item>
            <Descriptions.Item label={t('datasource.impactedRules')}>{summary.impactedRules}</Descriptions.Item>
          </Descriptions>
          {schemaDrift.nextActions.length > 0 && (
            <Alert
              type={schemaDrift.status === 'drift_detected' ? 'warning' : schemaDrift.status === 'no_drift' ? 'success' : 'info'}
              message={t('datasource.suggestedActions')}
              description={joinSentences(adviceTexts(schemaDrift.nextActions, schemaDrift.nextActionCodes, t), locale)}
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
          {t('datasource.back')}
        </Button>
        <Title level={3} style={{ margin: 0 }}>{t('datasource.detailTitle')}</Title>
        {id && (
          <Button
            icon={<DownloadOutlined />}
            onClick={() => void handleDownloadKernel()}
          >
            {t('datasource.downloadKernel')}
          </Button>
        )}
        {id && (
          <Button
            icon={<BulbOutlined />}
            loading={blueprintDraftLoading}
            onClick={handleGenerateBlueprintDraft}
          >
            {t('datasource.blueprintButton')}
          </Button>
        )}
        {id && (
          <Button
            icon={<ApiOutlined />}
            loading={gatewayTesting}
            onClick={handleTestApiGateway}
          >
            {t('datasource.gatewayButton')}
          </Button>
        )}
      </Space>

      {dataSource && (
        <Card style={{ marginBottom: 16 }}>
          <Descriptions column={2}>
            <Descriptions.Item label="ID">{dataSource.id}</Descriptions.Item>
            <Descriptions.Item label={t('datasource.name')}>{dataSource.name}</Descriptions.Item>
            <Descriptions.Item label={t('datasource.type')}>
              <Tag color="blue">{dataSource.sourceType}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label={t('datasource.domain')}>{dataSource.domain || '-'}</Descriptions.Item>
            <Descriptions.Item label={t('datasource.systemCategory')}>
              <Tag>{dataSource.systemCategory}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label={t('datasource.connectionUri')}>
              <code>{dataSource.connectionUri}</code>
            </Descriptions.Item>
            <Descriptions.Item label={t('datasource.apiBaseUrlLabel')}>
              {dataSource.apiBaseUrl ? <code>{dataSource.apiBaseUrl}</code> : '-'}
            </Descriptions.Item>
            <Descriptions.Item label={t('datasource.apiHeadersLabel')}>
              {dataSource.apiHeadersConfigured ? dataSource.apiHeaderNames.join(', ') : '-'}
            </Descriptions.Item>
          </Descriptions>
        </Card>
      )}

      {readiness && (
        <Card style={{ marginBottom: 16 }} title={t('datasource.readinessTitle')}>
          <Space align="start" size="large" style={{ width: '100%', justifyContent: 'space-between' }}>
            <div style={{ minWidth: 220 }}>
              <Progress
                type="circle"
                percent={readiness.score}
                strokeColor={readinessColor(readiness.status)}
              />
            </div>
            <Descriptions column={4} style={{ flex: 1 }}>
              <Descriptions.Item label={t('datasource.status')}>
                <Tag color={readinessColor(readiness.status)}>{label(READINESS_STATUS, readiness.status)}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('datasource.tables')}>{readiness.summary.tables}</Descriptions.Item>
              <Descriptions.Item label={t('datasource.columns')}>{readiness.summary.columns}</Descriptions.Item>
              <Descriptions.Item label={t('datasource.foreignKeys')}>{readiness.summary.foreignKeys}</Descriptions.Item>
              <Descriptions.Item label="API">{readiness.summary.apis}</Descriptions.Item>
              <Descriptions.Item label={t('datasource.ontologies')}>{readiness.summary.ontologies}</Descriptions.Item>
              <Descriptions.Item label={t('datasource.confirmedMappings')}>{readiness.summary.confirmedMappings}</Descriptions.Item>
              <Descriptions.Item label={t('datasource.pendingMappings')}>{readiness.summary.pendingMappings}</Descriptions.Item>
            </Descriptions>
          </Space>
          {readiness.nextActions.length > 0 && (
            <Alert
              style={{ marginTop: 16 }}
              type={readiness.status === 'blocked' ? 'error' : 'warning'}
              message={t('datasource.nextActions')}
              description={joinSentences(adviceTexts(readiness.nextActions, readiness.nextActionCodes, t), locale)}
            />
          )}
        </Card>
      )}

      <Card>
        <Tabs activeKey={tab} onChange={setTab}>
          <TabPane tab={t('datasource.scannedTablesTab', { count: tables.length })} key="tables">
            <div style={{ marginBottom: 16 }}>
              <Space>
                <Button
                  type="primary"
                  icon={<ScanOutlined />}
                  loading={scanLoading}
                  onClick={handleScan}
                >
                  {t('datasource.rescanButton')}
                </Button>
                <Button
                  icon={<BranchesOutlined />}
                  loading={driftLoading}
                  onClick={handleAnalyzeDrift}
                >
                  {t('datasource.driftButton')}
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
          <TabPane tab={t('datasource.registeredApisTab', { count: apis.length })} key="apis">
            <div style={{ marginBottom: 16 }}>
              <Button icon={<PlusOutlined />}>
                {t('datasource.addApiButton')}
              </Button>
              <Button
                icon={<ImportOutlined />}
                style={{ marginLeft: 8 }}
                onClick={() => setOpenApiModalVisible(true)}
              >
                {t('datasource.importOpenApiButton')}
              </Button>
            </div>
            {operationBindings && (
              <div style={{ marginBottom: 16, padding: 16, border: '1px solid #f0f0f0', borderRadius: 6 }}>
                <Descriptions column={4}>
                  <Descriptions.Item label={t('datasource.status')}>
                    <Tag color={bindingColor(operationBindings.status)}>{label(READINESS_STATUS, operationBindings.status)}</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="API">{operationBindings.summary.operations}</Descriptions.Item>
                  <Descriptions.Item label={t('datasource.boundOperations')}>{operationBindings.summary.boundOperations}</Descriptions.Item>
                  <Descriptions.Item label={t('datasource.readyOperations')}>{operationBindings.summary.readyOperations}</Descriptions.Item>
                  <Descriptions.Item label={t('datasource.unboundOperations')}>{operationBindings.summary.unboundOperations}</Descriptions.Item>
                  <Descriptions.Item label={t('datasource.invalidActions')}>{operationBindings.summary.invalidActions}</Descriptions.Item>
                  <Descriptions.Item label={t('datasource.blockedOperations')}>{operationBindings.summary.blockedOperations}</Descriptions.Item>
                </Descriptions>
                {operationBindings.nextActions.length > 0 && (
                  <Alert
                    style={{ marginTop: 16 }}
                    type={operationBindings.status === 'ready' ? 'success' : operationBindings.status === 'blocked' ? 'error' : 'warning'}
                    message={t('datasource.bindingAdvice')}
                    description={joinSentences(adviceTexts(operationBindings.nextActions, operationBindings.nextActionCodes, t), locale)}
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
          <TabPane tab={t('datasource.coverageTab')} key="coverage">
            {renderSemanticCoverage()}
          </TabPane>
          <TabPane tab={t('datasource.rulesTab', { count: businessRules.length })} key="rules">
            <Alert
              style={{ marginBottom: 16 }}
              type="info"
              message={t('datasource.rulesInfoTitle')}
              description={t('datasource.rulesInfoBody')}
            />
            <Card size="small" title={t('datasource.wordRulesTitle')} style={{ marginBottom: 16 }}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Alert
                  type="success"
                  message={t('datasource.wordRulesInfoTitle')}
                  description={t('datasource.wordRulesInfoBody')}
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
                  <p className="ant-upload-text">{t('datasource.uploadText')}</p>
                  <p className="ant-upload-hint">{t('datasource.uploadHint')}</p>
                </Upload.Dragger>
                {ruleImporting && <Spin tip={t('datasource.importingRules')} />}
                {ruleImportResult && (
                  <Alert
                    type={ruleImportResult.errorCount > 0 ? 'warning' : 'success'}
                    message={t('datasource.ruleImportRecognized', { recognized: ruleImportResult.rules.length, imported: ruleImportResult.importedCount })}
                    description={joinSentences([
                      ...ruleImportResult.warnings,
                      ...ruleImportResult.errors.map(item => `${item.code}: ${item.error}`),
                    ], locale) || t('datasource.sourceFile', { file: ruleImportResult.file.name })}
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
                    <Descriptions.Item label={t('datasource.ontologyId')}>{record.ontologyId}</Descriptions.Item>
                    <Descriptions.Item label={t('datasource.ruleExpression')}><code>{record.expression}</code></Descriptions.Item>
                    <Descriptions.Item label={t('datasource.naturalLanguageNote')}>{record.naturalLanguage}</Descriptions.Item>
                  </Descriptions>
                ),
              }}
            />
          </TabPane>
          <TabPane tab={t('datasource.reasoningTitle')} key="reasoning-chain">
            {!reasoningChain?.initialized ? (
              <Alert type="warning" message={t('datasource.notInitialized')} description={t('datasource.notInitializedHint')} />
            ) : (
              <Space direction="vertical" style={{ width: '100%' }} size="middle">
                <Descriptions column={4}>
                  <Descriptions.Item label={t('datasource.ontology')}>{reasoningChain.ontologyName}</Descriptions.Item>
                  <Descriptions.Item label={t('datasource.version')}>{reasoningChain.version}</Descriptions.Item>
                  <Descriptions.Item label={t('datasource.objects')}>{reasoningChain.objects.length}</Descriptions.Item>
                  <Descriptions.Item label={t('datasource.relations')}>{reasoningChain.relations.length}</Descriptions.Item>
                  <Descriptions.Item label={t('datasource.rules')}>{reasoningChain.rules.length}</Descriptions.Item>
                </Descriptions>
                <Tabs
                  items={[
                    { key: 'steps', label: t('datasource.reasoningSteps'), children: <Steps direction="vertical" items={reasoningChain.steps.map(step => ({ title: step.label, description: step.type }))} /> },
                    { key: 'relations', label: t('datasource.ontologyRelations'), children: <Table size="small" pagination={false} rowKey="code" dataSource={reasoningChain.relations} columns={[{ title: t('datasource.sourceObject'), dataIndex: 'sourceObject' }, { title: t('datasource.relation'), dataIndex: 'name' }, { title: t('datasource.targetObject'), dataIndex: 'targetObject' }, { title: t('datasource.type'), dataIndex: 'relationType', render: (v: string) => label(RELATION_KIND, v) }]} /> },
                    { key: 'chain-rules', label: t('datasource.reasoningRules'), children: <Table size="small" rowKey="code" dataSource={reasoningChain.rules} columns={[{ title: t('datasource.rules'), dataIndex: 'name' }, { title: t('datasource.object'), dataIndex: 'scopeObjectCode' }, { title: t('datasource.expression'), dataIndex: 'expression' }, { title: t('datasource.severity'), dataIndex: 'severity', render: (v: string) => label(RULE_SEVERITY, v) }]} /> },
                  ]}
                />
              </Space>
            )}
          </TabPane>
          <TabPane tab={t('datasource.readinessTab')} key="readiness">
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
        title={tableBrowser ? t('datasource.dataBrowseWithTable', { table: tableBrowser.tableName }) : t('datasource.dataBrowse')}
        open={Boolean(tableBrowser) || tableBrowserLoading}
        onCancel={() => setTableBrowser(null)}
        footer={null}
        width="90vw"
      >
        <Spin spinning={tableBrowserLoading}>
          {tableBrowser && <>
            <Alert style={{ marginBottom: 12 }} type="info" message={t('datasource.browseRange', { total: tableBrowser.page.total, from: tableBrowser.page.offset + 1, to: tableBrowser.page.offset + tableBrowser.rows.length })} />
            <Table
              size="small"
              scroll={{ x: 'max-content' }}
              pagination={false}
              rowKey={(_, index) => `${tableBrowser.page.offset}-${index}`}
              dataSource={tableBrowser.rows}
              columns={tableBrowser.columns.map(column => ({ title: column, dataIndex: column, key: column, render: (value: unknown) => typeof value === 'object' ? JSON.stringify(value) : String(value ?? '') }))}
            />
            <Space style={{ marginTop: 12 }}>
              <Button disabled={tableBrowser.page.offset === 0} onClick={() => handleBrowseTable(tableBrowser.tableName, Math.max(0, tableBrowser.page.offset - tableBrowser.page.limit))}>{t('datasource.previousPage')}</Button>
              <Button disabled={!tableBrowser.page.hasMore} onClick={() => handleBrowseTable(tableBrowser.tableName, tableBrowser.page.offset + tableBrowser.page.limit)}>{t('datasource.nextPage')}</Button>
            </Space>
          </>}
        </Spin>
      </Modal>

      <Modal
        title={t('datasource.importOpenApiButton')}
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
            <Input placeholder={t('datasource.openApiUrlPlaceholder')} />
          </Form.Item>
          <Form.Item
            name="specJson"
            label="OpenAPI JSON"
            rules={[
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (getFieldValue('specUrl')?.trim() || value?.trim()) return Promise.resolve();
                  return Promise.reject(new Error(t('datasource.openApiSourceRequired')));
                },
              }),
            ]}
          >
            <Input.TextArea
              rows={12}
              placeholder={t('datasource.openApiSpecExample')}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t('datasource.blueprintDraftTitle')}
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
