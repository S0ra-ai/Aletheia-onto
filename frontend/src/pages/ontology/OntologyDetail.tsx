import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Alert, Card, Table, Button, Space, Typography, Tag, Tabs, Descriptions, Empty, Spin, Progress } from 'antd';
import { ArrowLeftOutlined, DownloadOutlined } from '@ant-design/icons';
import { ontologyApi } from '../../api';
import type { OntologyDetail, ReleaseReadinessResult } from '../../types';

const { Title } = Typography;
const { TabPane } = Tabs;

const OntologyDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [ontology, setOntology] = useState<OntologyDetail | null>(null);
  const [releaseReadiness, setReleaseReadiness] = useState<ReleaseReadinessResult | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchOntology = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [data, readiness] = await Promise.all([
        ontologyApi.get(parseInt(id)),
        ontologyApi.getReleaseReadiness(parseInt(id)),
      ]);
      setOntology(data);
      setReleaseReadiness(readiness);
    } catch (error) {
      console.error('Failed to fetch ontology:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOntology();
  }, [id]);

  if (loading) {
    return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  }

  if (!ontology) {
    return <Empty description="未找到本体数据" />;
  }

  const objectColumns = [
    { title: '编码', dataIndex: 'code', key: 'code' },
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '来源表', dataIndex: 'sourceTable', key: 'sourceTable' },
    { title: '描述', dataIndex: 'description', key: 'description' },
  ];

  const attributeColumns = [
    { title: '编码', dataIndex: 'code', key: 'code' },
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '数据类型', dataIndex: 'dataType', key: 'dataType', render: (type: string) => <Tag>{type}</Tag> },
    { title: '来源字段', dataIndex: 'sourceColumn', key: 'sourceColumn' },
    { title: '描述', dataIndex: 'description', key: 'description' },
  ];

  const relationColumns = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '类型', dataIndex: 'type', key: 'type', render: (type: string) => <Tag color="blue">{type}</Tag> },
    { title: '外键', dataIndex: 'sourceForeignKey', key: 'sourceForeignKey' },
  ];

  const mappingColumns = [
    { title: '类型', dataIndex: 'mappingType', key: 'mappingType', render: (type: string) => <Tag>{type}</Tag> },
    { title: '来源表', dataIndex: 'sourceTable', key: 'sourceTable' },
    { title: '来源字段', dataIndex: 'sourceColumn', key: 'sourceColumn', render: (col: string) => col || '-' },
    { title: '目标对象', dataIndex: 'targetObjectCode', key: 'targetObjectCode' },
    { title: '目标属性', dataIndex: 'targetAttributeCode', key: 'targetAttributeCode', render: (attr: string) => attr || '-' },
    { title: '置信度', dataIndex: 'confidence', key: 'confidence', render: (conf: number) => `${(conf * 100).toFixed(0)}%` },
    { title: '状态', dataIndex: 'status', key: 'status', render: (status: string) => <Tag color={status === 'confirmed' ? 'green' : 'orange'}>{status}</Tag> },
  ];

  const ruleColumns = [
    { title: '编码', dataIndex: 'code', key: 'code' },
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '严重程度', dataIndex: 'severity', key: 'severity', render: (sev: string) => <Tag color={sev === 'error' ? 'red' : sev === 'warning' ? 'orange' : 'blue'}>{sev}</Tag> },
    { title: '启用', dataIndex: 'enabled', key: 'enabled', render: (enabled: boolean) => <Tag color={enabled ? 'green' : 'default'}>{enabled ? '是' : '否'}</Tag> },
    { title: '表达式', dataIndex: 'expression', key: 'expression', render: (expr: string) => <code>{expr}</code> },
  ];

  const releaseGateColumns = [
    { title: '门禁', dataIndex: 'name', key: 'name' },
    {
      title: '状态',
      dataIndex: 'passed',
      key: 'passed',
      render: (passed: boolean) => <Tag color={passed ? 'green' : 'red'}>{passed ? '通过' : '未通过'}</Tag>,
    },
    {
      title: '级别',
      dataIndex: 'severity',
      key: 'severity',
      render: (severity: string) => <Tag color={severity === 'blocker' ? 'red' : 'orange'}>{severity}</Tag>,
    },
    { title: '证据', dataIndex: 'evidence', key: 'evidence' },
    { title: '修复动作', dataIndex: 'remediation', key: 'remediation' },
  ];

  const releaseColor = (status?: string) => {
    if (status === 'ready') return 'green';
    if (status === 'review') return 'orange';
    return 'red';
  };

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/ontology')}>
          返回
        </Button>
        <Title level={3} style={{ margin: 0 }}>本体详情</Title>
        <Button
          icon={<DownloadOutlined />}
          onClick={() => window.open(ontologyApi.exportUrl(ontology.ontology.id, 'jsonld'), '_blank')}
        >
          JSON-LD
        </Button>
        <Button
          icon={<DownloadOutlined />}
          onClick={() => window.open(ontologyApi.exportUrl(ontology.ontology.id, 'turtle'), '_blank')}
        >
          Turtle
        </Button>
      </Space>

      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={2}>
          <Descriptions.Item label="ID">{ontology.ontology.id}</Descriptions.Item>
          <Descriptions.Item label="名称">{ontology.ontology.name}</Descriptions.Item>
          <Descriptions.Item label="版本">
            <Tag>v{ontology.ontology.version}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="状态">
            <Tag color={ontology.ontology.status === 'active' ? 'green' : 'orange'}>
              {ontology.ontology.status}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="数据源ID">{ontology.ontology.dataSourceId}</Descriptions.Item>
        </Descriptions>
      </Card>

      {releaseReadiness && (
        <Card style={{ marginBottom: 16 }} title="发布就绪度">
          <Space align="start" size="large" style={{ width: '100%', justifyContent: 'space-between' }}>
            <div style={{ minWidth: 220 }}>
              <Progress
                type="circle"
                percent={Math.round((releaseReadiness.summary.passedGates / Math.max(releaseReadiness.summary.totalGates, 1)) * 100)}
                strokeColor={releaseColor(releaseReadiness.status)}
              />
            </div>
            <Descriptions column={4} style={{ flex: 1 }}>
              <Descriptions.Item label="状态">
                <Tag color={releaseColor(releaseReadiness.status)}>{releaseReadiness.status}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="业务对象">{releaseReadiness.summary.objects}</Descriptions.Item>
              <Descriptions.Item label="数据源">{releaseReadiness.summary.dataSources}</Descriptions.Item>
              <Descriptions.Item label="门禁">{releaseReadiness.summary.passedGates}/{releaseReadiness.summary.totalGates}</Descriptions.Item>
              <Descriptions.Item label="阻断">{releaseReadiness.summary.blockers}</Descriptions.Item>
              <Descriptions.Item label="预警">{releaseReadiness.summary.warnings}</Descriptions.Item>
              <Descriptions.Item label="确认映射">{releaseReadiness.summary.confirmedMappings}</Descriptions.Item>
              <Descriptions.Item label="待审映射">{releaseReadiness.summary.pendingMappings}</Descriptions.Item>
              <Descriptions.Item label="发布规则">{releaseReadiness.summary.publishedRules}</Descriptions.Item>
            </Descriptions>
          </Space>
          {releaseReadiness.nextActions.length > 0 && (
            <Alert
              style={{ marginTop: 16 }}
              type={releaseReadiness.status === 'ready' ? 'success' : releaseReadiness.status === 'blocked' ? 'error' : 'warning'}
              message="下一步动作"
              description={releaseReadiness.nextActions.join('；')}
            />
          )}
        </Card>
      )}

      <Card>
        <Tabs defaultActiveKey="objects">
          <TabPane tab={`业务对象 (${ontology.objects.length})`} key="objects">
            <Table
              columns={objectColumns}
              dataSource={ontology.objects}
              rowKey="id"
            />
          </TabPane>
          <TabPane tab={`业务属性 (${ontology.attributes.length})`} key="attributes">
            <Table
              columns={attributeColumns}
              dataSource={ontology.attributes}
              rowKey="id"
            />
          </TabPane>
          <TabPane tab={`业务关系 (${ontology.relations.length})`} key="relations">
            <Table
              columns={relationColumns}
              dataSource={ontology.relations}
              rowKey="id"
            />
          </TabPane>
          <TabPane tab={`语义映射 (${ontology.mappings.length})`} key="mappings">
            <Table
              columns={mappingColumns}
              dataSource={ontology.mappings}
              rowKey="id"
            />
          </TabPane>
          <TabPane tab={`业务规则 (${ontology.rules.length})`} key="rules">
            <Table
              columns={ruleColumns}
              dataSource={ontology.rules}
              rowKey="id"
            />
          </TabPane>
          <TabPane tab="发布门禁" key="release">
            <Table
              columns={releaseGateColumns}
              dataSource={releaseReadiness?.gates || []}
              rowKey="code"
              pagination={false}
            />
          </TabPane>
        </Tabs>
      </Card>
    </div>
  );
};

export default OntologyDetailPage;
