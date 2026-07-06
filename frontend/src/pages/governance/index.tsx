import React, { useEffect, useState } from 'react';
import { Card, Table, Typography, Tabs, Tag, Button, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { governanceApi } from '../../api';
import type { AuditLogItem, ModelInvocationItem, DecisionRecordItem } from '../../types';

const { Title } = Typography;
const { TabPane } = Tabs;

const Governance: React.FC = () => {
  const [auditLogs, setAuditLogs] = useState<AuditLogItem[]>([]);
  const [modelInvocations, setModelInvocations] = useState<ModelInvocationItem[]>([]);
  const [decisions, setDecisions] = useState<DecisionRecordItem[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchData = async () => {
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
      message.error('获取审计数据失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const auditColumns = [
    {
      title: '操作者',
      dataIndex: 'actor',
      key: 'actor',
    },
    {
      title: '操作',
      dataIndex: 'action',
      key: 'action',
      render: (action: string) => <Tag color="blue">{action}</Tag>,
    },
    {
      title: '目标类型',
      dataIndex: 'targetType',
      key: 'targetType',
    },
    {
      title: '目标ID',
      dataIndex: 'targetId',
      key: 'targetId',
    },
    {
      title: '详情',
      dataIndex: 'detail',
      key: 'detail',
      ellipsis: true,
    },
    {
      title: '时间',
      dataIndex: 'createdAt',
      key: 'createdAt',
    },
  ];

  const invocationColumns = [
    {
      title: '提供商',
      dataIndex: 'provider',
      key: 'provider',
    },
    {
      title: '模型',
      dataIndex: 'model',
      key: 'model',
    },
    {
      title: '用途',
      dataIndex: 'purpose',
      key: 'purpose',
    },
    {
      title: '提示词Token',
      dataIndex: 'promptTokens',
      key: 'promptTokens',
    },
    {
      title: '完成Token',
      dataIndex: 'completionTokens',
      key: 'completionTokens',
    },
    {
      title: '总Token',
      dataIndex: 'totalTokens',
      key: 'totalTokens',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={status === 'success' ? 'green' : 'red'}>{status}</Tag>
      ),
    },
    {
      title: '时间',
      dataIndex: 'createdAt',
      key: 'createdAt',
    },
  ];

  const decisionColumns = [
    {
      title: '决策编号',
      dataIndex: 'decisionId',
      key: 'decisionId',
    },
    {
      title: '类型',
      dataIndex: 'decisionType',
      key: 'decisionType',
      render: (type: string) => <Tag color="blue">{type}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={status === 'approved' || status === 'ready_for_execution' || status === 'executed' ? 'green' : status === 'review' ? 'orange' : 'red'}>
          {status}
        </Tag>
      ),
    },
    {
      title: '业务对象',
      dataIndex: 'objectCode',
      key: 'objectCode',
      render: (value: string) => value || '-',
    },
    {
      title: '实例ID',
      dataIndex: 'instanceId',
      key: 'instanceId',
      render: (value: string) => value || '-',
    },
    {
      title: '操作码',
      dataIndex: 'operationCode',
      key: 'operationCode',
      render: (value: string) => value || '-',
    },
    {
      title: '建议',
      dataIndex: 'recommendation',
      key: 'recommendation',
      ellipsis: true,
    },
    {
      title: '时间',
      dataIndex: 'createdAt',
      key: 'createdAt',
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={3}>治理审计</Title>
        <Button icon={<ReloadOutlined />} onClick={fetchData} loading={loading}>
          刷新
        </Button>
      </div>

      <Card>
        <Tabs defaultActiveKey="audit">
          <TabPane tab={`决策记录 (${decisions.length})`} key="decisions">
            <Table
              columns={decisionColumns}
              dataSource={decisions}
              rowKey="decisionId"
              loading={loading}
            />
          </TabPane>
          <TabPane tab={`审计日志 (${auditLogs.length})`} key="audit">
            <Table
              columns={auditColumns}
              dataSource={auditLogs}
              rowKey={(record) => `${record.createdAt}-${record.action}`}
              loading={loading}
            />
          </TabPane>
          <TabPane tab={`模型调用记录 (${modelInvocations.length})`} key="invocations">
            <Table
              columns={invocationColumns}
              dataSource={modelInvocations}
              rowKey={(record) => `${record.createdAt}-${record.model}`}
              loading={loading}
            />
          </TabPane>
        </Tabs>
      </Card>
    </div>
  );
};

export default Governance;
