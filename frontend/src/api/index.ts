import axios from 'axios';
import type {
  DataSource,
  DataSourceCreate,
  SourceApi,
  SourceApiCreate,
  SourceTable,
  OntologyDraftCreate,
  OntologyDetail,
  DemoBootstrapResult,
  InstanceExplainResult,
  InstanceAssessResult,
  OperationPreflightResult,
  AuditLogItem,
  ModelInvocationItem,
  ModelStatus,
  ModelConfig,
  ModelConfigUpdate,
} from '../types';

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

const normalizeDataSource = (item: any): DataSource => ({
  id: item.id,
  name: item.name,
  sourceType: item.sourceType ?? item.source_type,
  connectionUri: item.connectionUri ?? item.connection_uri,
  domain: item.domain ?? '',
  systemCategory: item.systemCategory ?? item.system_category ?? 'database',
  capabilities: item.capabilities ?? [],
  createdAt: item.createdAt ?? item.created_at,
});

const normalizeSourceApi = (item: any): SourceApi => ({
  id: item.id,
  dataSourceId: item.dataSourceId ?? item.data_source_id,
  operationCode: item.operationCode ?? item.operation_code,
  name: item.name,
  method: item.method,
  path: item.path,
  semanticAction: item.semanticAction ?? item.semantic_action ?? '',
  requestSchema: item.requestSchema ?? item.request_schema ?? {},
  responseSchema: item.responseSchema ?? item.response_schema ?? {},
});

const normalizeSourceTable = (item: any): SourceTable => ({
  id: item.id,
  tableName: item.tableName ?? item.table_name,
  rowCount: item.rowCount ?? item.row_count,
  primaryKey: item.primaryKey ?? item.primary_key,
  scannedAt: item.scannedAt ?? item.scanned_at,
});

// 数据源 API
export const dataSourceApi = {
  list: async (): Promise<DataSource[]> => {
    const { data } = await api.get('/data-sources');
    const items = (data as { dataSources?: unknown[]; data_sources?: unknown[] }).dataSources
      || (data as { data_sources?: unknown[] }).data_sources
      || [];
    return items.map(normalizeDataSource);
  },

  create: async (payload: DataSourceCreate): Promise<DataSource> => {
    const { data } = await api.post('/data-sources', payload);
    return normalizeDataSource(data);
  },

  testConnection: async (payload: { sourceType: string; connectionUri: string }): Promise<{ reachable: boolean; status: string; message: string; sourceType: string }> => {
    const { data } = await api.post('/data-sources/test-connection', payload);
    return data;
  },

  testRegisteredConnection: async (id: number): Promise<{ reachable: boolean; status: string; message: string; sourceType: string }> => {
    const { data } = await api.post(`/data-sources/${id}/test-connection`);
    return data;
  },

  getTables: async (id: number): Promise<SourceTable[]> => {
    const { data } = await api.get(`/data-sources/${id}/tables`);
    return ((data as { tables: unknown[] }).tables || []).map(normalizeSourceTable);
  },

  scan: async (id: number): Promise<{ tables: number; columns: number; foreignKeys: number }> => {
    const { data } = await api.post(`/data-sources/${id}/scan`);
    return data as { tables: number; columns: number; foreignKeys: number };
  },

  getApis: async (id: number): Promise<SourceApi[]> => {
    const { data } = await api.get(`/data-sources/${id}/apis`);
    return ((data as { apis: unknown[] }).apis || []).map(normalizeSourceApi);
  },

  createApi: async (dataSourceId: number, payload: SourceApiCreate): Promise<SourceApi> => {
    const { data } = await api.post(`/data-sources/${dataSourceId}/apis`, payload);
    return normalizeSourceApi(data);
  },
};

// 本体 API
export const ontologyApi = {
  list: async (): Promise<any[]> => {
    const { data } = await api.get('/ontologies');
    return (data.items || data.ontologies || []) as any[];
  },

  get: async (id: number): Promise<OntologyDetail> => {
    const { data } = await api.get(`/ontologies/${id}`);
    return data as OntologyDetail;
  },

  createDraft: async (payload: OntologyDraftCreate): Promise<OntologyDetail> => {
    const { data } = await api.post('/ontologies/draft', payload);
    return data as OntologyDetail;
  },

  getMappings: async (ontologyId: number, status?: string): Promise<any[]> => {
    const { data } = await api.get(`/ontologies/${ontologyId}/mappings`, { params: status ? { status } : {} });
    return data.items || [];
  },

  reviewMappings: async (ontologyId: number, payload: { status: string; reviewer?: string; note?: string }): Promise<any> => {
    const { data } = await api.post(`/ontologies/${ontologyId}/mappings/review`, payload);
    return data;
  },

  publish: async (ontologyId: number, publisher = 'system'): Promise<any> => {
    const { data } = await api.post(`/ontologies/${ontologyId}/publish`, { publisher });
    return data;
  },

  derive: async (ontologyId: number, version: string, actor = 'system'): Promise<any> => {
    const { data } = await api.post(`/ontologies/${ontologyId}/derive`, { version, actor });
    return data;
  },

  getRules: async (ontologyId: number): Promise<any[]> => {
    const { data } = await api.get(`/ontologies/${ontologyId}/rules`);
    return data.items || [];
  },
};

// 语义服务 API
export const semanticApi = {
  explain: async (objectCode: string, instanceId: string, ontologyId?: number): Promise<InstanceExplainResult> => {
    const params = ontologyId ? { ontologyId } : {};
    const { data } = await api.get(`/semantic/objects/${objectCode}/instances/${instanceId}/explain`, { params });
    return data as InstanceExplainResult;
  },

  assess: async (objectCode: string, instanceId: string, ontologyId?: number): Promise<InstanceAssessResult> => {
    const params = ontologyId ? { ontologyId } : {};
    const { data } = await api.post(`/semantic/objects/${objectCode}/instances/${instanceId}/assess`, {}, { params });
    return {
      objectCode: data.semanticKernel?.objectCode ?? objectCode,
      instanceId: data.semanticKernel?.instanceId ?? instanceId,
      decision: (data.decision?.status ?? 'review') as 'approved' | 'review' | 'blocked',
      rulesHit: (data.ruleResults || []).map((rule: any) => ({
        ruleCode: rule.ruleCode,
        ruleName: rule.ruleName,
        passed: rule.passed,
        message: rule.explanation,
      })),
      explanation: data.decision?.recommendation ?? '',
    };
  },
};

// 自动化 API
export const automationApi = {
  preflight: async (
    operationCode: string,
    payload: {
      ontologyId: number;
      dataSourceId: number;
      instanceId: string;
      objectCode?: string;
    }
  ): Promise<OperationPreflightResult> => {
    const { data } = await api.post(`/automation/operations/${operationCode}/preflight`, payload);
    return {
      operationCode: data.operation?.operationCode ?? operationCode,
      instanceId: data.target?.instanceId ?? payload.instanceId,
      decision: (data.decision?.status ?? 'review') as 'approved' | 'review' | 'blocked',
      rulesHit: (data.ruleResults || []).map((rule: any) => ({
        ruleCode: rule.ruleCode,
        ruleName: rule.ruleName,
        passed: rule.passed,
        message: rule.explanation,
      })),
      explanation: data.decision?.recommendation ?? '',
      recommendation: data.nextAction ?? data.decision?.recommendation ?? '',
    };
  },
};

// 演示 API
export const demoApi = {
  bootstrapContract: async (): Promise<DemoBootstrapResult> => {
    const { data } = await api.post('/demo/bootstrap');
    return data as DemoBootstrapResult;
  },

  bootstrapEquipment: async (): Promise<DemoBootstrapResult> => {
    const { data } = await api.post('/demo/bootstrap/equipment');
    return data as DemoBootstrapResult;
  },
};

// 治理审计 API
export const governanceApi = {
  getAuditLog: async (limit?: number): Promise<AuditLogItem[]> => {
    const params = limit ? { limit } : {};
    const { data } = await api.get('/governance/audit-log', { params });
    return (data as { items: AuditLogItem[] }).items || [];
  },

  getModelInvocations: async (limit?: number): Promise<ModelInvocationItem[]> => {
    const params = limit ? { limit } : {};
    const { data } = await api.get('/governance/model-invocations', { params });
    return (data as { items: ModelInvocationItem[] }).items || [];
  },
};

// 模型 API
export const modelApi = {
  getStatus: async (): Promise<ModelStatus> => {
    const { data } = await api.get('/model/status');
    return data as ModelStatus;
  },

  getConfig: async (): Promise<ModelConfig> => {
    const { data } = await api.get('/model/config');
    return data as ModelConfig;
  },

  updateConfig: async (config: ModelConfigUpdate): Promise<{ success: boolean; message: string }> => {
    const { data } = await api.post('/model/config', config);
    return data as { success: boolean; message: string };
  },

  resetConfig: async (): Promise<{ success: boolean; message: string }> => {
    const { data } = await api.delete('/model/config');
    return data as { success: boolean; message: string };
  },

  testConfig: async (): Promise<{ success: boolean; message: string; model?: string; status: ModelStatus }> => {
    const { data } = await api.get('/model/config/test');
    return data as { success: boolean; message: string; model?: string; status: ModelStatus };
  },
};

// AI 建议 API
export const aiApi = {
  getOntologySuggestions: async (dataSourceId: number): Promise<unknown> => {
    const { data } = await api.post(`/ai/data-sources/${dataSourceId}/ontology-suggestions`);
    return data;
  },
};

export default api;
