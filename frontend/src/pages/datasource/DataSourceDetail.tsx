import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, Table, Button, Space, Typography, Tag, Tabs, Descriptions, message, Spin } from 'antd';
import { ArrowLeftOutlined, ScanOutlined, PlusOutlined } from '@ant-design/icons';
import { dataSourceApi } from '../../api';
import type { DataSource, SourceTable, SourceApi } from '../../types';

const { Title } = Typography;
const { TabPane } = Tabs;

const DataSourceDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [dataSource, setDataSource] = useState<DataSource | null>(null);
  const [tables, setTables] = useState<SourceTable[]>([]);
  const [apis, setApis] = useState<SourceApi[]>([]);
  const [loading, setLoading] = useState(false);
  const [scanLoading, setScanLoading] = useState(false);

  const fetchData = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [tablesData, apisData] = await Promise.all([
        dataSourceApi.getTables(parseInt(id)),
        dataSourceApi.getApis(parseInt(id)),
      ]);
      setTables(tablesData);
      setApis(apisData);
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
            </div>
            <Table
              columns={apiColumns}
              dataSource={apis}
              rowKey="id"
            />
          </TabPane>
        </Tabs>
      </Card>
    </div>
  );
};

export default DataSourceDetail;
