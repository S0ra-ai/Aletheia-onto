import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Table, Button, Space, Typography, Tag, Tabs, Descriptions, message, Spin, Progress, Alert, Modal, Form, Input } from 'antd';
import { ArrowLeftOutlined, ScanOutlined, PlusOutlined, ImportOutlined } from '@ant-design/icons';
import { dataSourceApi } from '../../api';
import type { DataSource, SourceTable, SourceApi, DataSourceReadiness } from '../../types';

const { Title } = Typography;
const { TabPane } = Tabs;

const DataSourceDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [dataSource, setDataSource] = useState<DataSource | null>(null);
  const [tables, setTables] = useState<SourceTable[]>([]);
  const [apis, setApis] = useState<SourceApi[]>([]);
  const [readiness, setReadiness] = useState<DataSourceReadiness | null>(null);
  const [loading, setLoading] = useState(false);
  const [scanLoading, setScanLoading] = useState(false);
  const [openApiModalVisible, setOpenApiModalVisible] = useState(false);
  const [importLoading, setImportLoading] = useState(false);
  const [openApiForm] = Form.useForm();

  const fetchData = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [tablesData, apisData, readinessData] = await Promise.all([
        dataSourceApi.getTables(parseInt(id)),
        dataSourceApi.getApis(parseInt(id)),
        dataSourceApi.getReadiness(parseInt(id)),
      ]);
      setTables(tablesData);
      setApis(apisData);
      setReadiness(readinessData);
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
      fetchData();
    } catch (error) {
      message.error('扫描失败');
    } finally {
      setScanLoading(false);
    }
  };

  const handleImportOpenApi = async (values: { specJson: string }) => {
    if (!id) return;
    setImportLoading(true);
    try {
      const spec = JSON.parse(values.specJson);
      const result = await dataSourceApi.importOpenApi(parseInt(id), spec);
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
              <Button
                type="primary"
                icon={<ScanOutlined />}
                loading={scanLoading}
                onClick={handleScan}
              >
                重新扫描
              </Button>
            </div>
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
            <Table
              columns={apiColumns}
              dataSource={apis}
              rowKey="id"
            />
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
          <Form.Item
            name="specJson"
            label="OpenAPI JSON"
            rules={[{ required: true, message: '请粘贴 OpenAPI JSON 文档' }]}
          >
            <Input.TextArea
              rows={14}
              placeholder='{"openapi":"3.0.0","paths":{"/contracts/{id}/submit":{"post":{"operationId":"submit_contract","summary":"提交合同审批"}}}}'
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default DataSourceDetail;
