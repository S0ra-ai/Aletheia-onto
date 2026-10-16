import React, { useCallback, useEffect, useState } from 'react';
import { Card, Table, Typography, Tabs, Tag, Button, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { governanceApi, requestErrorMessage } from '../../api';
import type { AuditLogItem, ModelInvocationItem, DecisionRecordItem } from '../../types';
import { useTabParam } from '../../hooks/useTabParam';
import { CALL_STATUS, DECISION_STATUS, DECISION_TYPE } from '../../i18n/labels';
import { useLabel, useT } from '../../i18n/locale';
import AuditReportPanel from './AuditReportPanel';
import { codedText } from '../../i18n/text';

const { Title } = Typography;
const { TabPane } = Tabs;

const Governance: React.FC = () => {
  const t = useT();
  const label = useLabel();
  const [tab, setTab] = useTabParam('audit');
  const [auditLogs, setAuditLogs] = useState<AuditLogItem[]>([]);
  const [modelInvocations, setModelInvocations] = useState<ModelInvocationItem[]>([]);
  const [decisions, setDecisions] = useState<DecisionRecordItem[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [logs, invocations, decisionItems] = await Promise.all([
        governanceApi.getAuditLog(),
        governanceApi.getModelInvocations(),
        governanceApi.getDecisions(),
      ]);
      setAuditLogs(logs);
      setModelInvocations(invocations);
      setDecisions(decisionItems);
    } catch (error) {
      message.error(requestErrorMessage(error, t('governance.loadFailed')));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const auditColumns = [
    {
      title: t('governance.column.actor'),
      dataIndex: 'actor',
      key: 'actor',
    },
    {
      title: t('governance.column.action'),
      dataIndex: 'action',
      key: 'action',
      render: (action: string) => <Tag color="blue">{action}</Tag>,
    },
    {
      title: t('governance.column.targetType'),
      // `/governance/audit-log` returns `dict(row)` -- snake_case keys only. Three of
      // these columns asked for camelCase, so 目标类型/目标ID/时间 rendered empty for
      // every row while their siblings worked. Only a browser shows this.
      dataIndex: 'target_type',
      key: 'target_type',
    },
    {
      title: t('governance.column.targetId'),
      dataIndex: 'target_id',
      key: 'target_id',
    },
    {
      title: t('governance.column.detail'),
      dataIndex: 'detail',
      key: 'detail',
      ellipsis: true,
    },
    {
      title: t('governance.column.time'),
      dataIndex: 'created_at',
      key: 'created_at',
    },
  ];

  const invocationColumns = [
    {
      title: t('governance.column.provider'),
      dataIndex: 'provider',
      key: 'provider',
    },
    {
      title: t('governance.column.model'),
      dataIndex: 'model',
      key: 'model',
    },
    {
      title: t('governance.column.purpose'),
      dataIndex: 'purpose',
      key: 'purpose',
    },
    {
      title: t('governance.column.promptTokens'),
      dataIndex: 'prompt_tokens',
      key: 'prompt_tokens',
    },
    {
      title: t('governance.column.completionTokens'),
      dataIndex: 'completion_tokens',
      key: 'completion_tokens',
    },
    {
      title: t('governance.column.totalTokens'),
      dataIndex: 'total_tokens',
      key: 'total_tokens',
    },
    {
      title: t('governance.column.status'),
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={status === 'success' ? 'green' : 'red'}>{label(CALL_STATUS, status)}</Tag>
      ),
    },
    {
      title: t('governance.column.time'),
      dataIndex: 'created_at',
      key: 'created_at',
    },
  ];

  const decisionColumns = [
    {
      title: t('governance.column.decisionId'),
      dataIndex: 'decisionId',
      key: 'decisionId',
    },
    {
      title: t('governance.column.type'),
      dataIndex: 'decisionType',
      key: 'decisionType',
      render: (type: string) => <Tag color="blue">{label(DECISION_TYPE, type)}</Tag>,
    },
    {
      title: t('governance.column.status'),
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={status === 'approved' ? 'green' : status === 'review' ? 'orange' : 'red'}>
          {label(DECISION_STATUS, status)}
        </Tag>
      ),
    },
    {
      title: t('governance.column.object'),
      dataIndex: 'objectCode',
      key: 'objectCode',
      render: (value: string) => value || '-',
    },
    {
      title: t('governance.column.instanceId'),
      dataIndex: 'instanceId',
      key: 'instanceId',
      render: (value: string) => value || '-',
    },
    {
      title: t('governance.column.operationCode'),
      dataIndex: 'operationCode',
      key: 'operationCode',
      render: (value: string) => value || '-',
    },
    {
      title: t('governance.column.recommendation'),
      dataIndex: 'recommendation',
      key: 'recommendation',
      // The kernel's recommendation, in the reader's language: the row carries a code beside
      // the server's sentence -- see `semantic_kernel._decision_from_results`.
      render: (_: string, row: { recommendation: string; recommendationCode?: string }) => {
        const code = row.recommendationCode;
        if (!code) return row.recommendation;
        return codedText(t, `semantic.recommendation.${code}`, row.recommendation);
      },
      ellipsis: true,
    },
    {
      title: t('governance.column.time'),
      dataIndex: 'createdAt',
      key: 'createdAt',
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={3}>{t('governance.title')}</Title>
        <Button icon={<ReloadOutlined />} onClick={fetchData} loading={loading}>
          {t('governance.refresh')}
        </Button>
      </div>

      <Card>
        <Tabs activeKey={tab} onChange={setTab}>
          <TabPane tab={t('governance.tabDecisions', { count: decisions.length })} key="decisions">
            <Table
              columns={decisionColumns}
              dataSource={decisions}
              rowKey="decisionId"
              loading={loading}
            />
          </TabPane>
          <TabPane tab={t('governance.tabAudit', { count: auditLogs.length })} key="audit">
            <Table
              columns={auditColumns}
              dataSource={auditLogs}
              rowKey={(record) => `${record.created_at}-${record.action}`}
              loading={loading}
            />
          </TabPane>
          <TabPane tab={t('governance.tabInvocations', { count: modelInvocations.length })} key="invocations">
            <Table
              columns={invocationColumns}
              dataSource={modelInvocations}
              rowKey={(record) => `${record.created_at}-${record.model}`}
              loading={loading}
            />
          </TabPane>
          <TabPane tab={t('governance.tabReport')} key="report">
            <AuditReportPanel />
          </TabPane>
        </Tabs>
      </Card>
    </div>
  );
};

export default Governance;
