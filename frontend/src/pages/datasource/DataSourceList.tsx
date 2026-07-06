import React, { useEffect, useState } from 'react';
import { Alert, Card, Table, Button, Space, Typography, Tag, Modal, Form, Input, Select, message } from 'antd';
import { PlusOutlined, ScanOutlined, ApiOutlined, LinkOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { dataSourceApi } from '../../api';
import type { DataSource, DataSourceCreate } from '../../types';

const { Title } = Typography;
const { Option } = Select;

const DataSourceList: React.FC = () => {
  const navigate = useNavigate();
  const [dataSources, setDataSources] = useState<DataSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [connectionResult, setConnectionResult] = useState<{ reachable: boolean; status: string; message: string } | null>(null);
  const [testingConnection, setTestingConnection] = useState(false);
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
  }, []);

  const handleCreate = async (values: DataSourceCreate) => {
    try {
      await dataSourceApi.create(values);
      message.success('数据源创建成功');
      setModalVisible(false);
      form.resetFields();
      fetchDataSources();
    } catch (error) {
      message.error('创建失败');
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
        </Form>
      </Modal>
    </div>
  );
};

export default DataSourceList;
