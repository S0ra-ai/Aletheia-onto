import React, { useEffect, useState } from 'react';
import { Card, Table, Button, Space, Typography, Tag, Modal, Form, Input, Select, message, Empty } from 'antd';
import { PlusOutlined, EditOutlined, EyeOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { ontologyApi, dataSourceApi } from '../../api';
import type { Ontology, DataSource, OntologyDraftCreate } from '../../types';

const { Title } = Typography;
const { Option } = Select;

const OntologyList: React.FC = () => {
  const navigate = useNavigate();
  const [ontologies, setOntologies] = useState<Ontology[]>([]);
  const [dataSources, setDataSources] = useState<DataSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [form] = Form.useForm();

  const fetchData = async () => {
    setLoading(true);
    try {
      const sources = await dataSourceApi.list();
      setDataSources(sources);
      const allOntologies = await ontologyApi.list();
      setOntologies(allOntologies as Ontology[]);
    } catch (error) {
      message.error('获取本体列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleCreateDraft = async (values: OntologyDraftCreate) => {
    try {
      await ontologyApi.createDraft(values);
      message.success('本体草案生成成功');
      setModalVisible(false);
      form.resetFields();
      fetchData();
    } catch (error) {
      message.error('生成失败');
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
      title: '版本',
      dataIndex: 'version',
      key: 'version',
      render: (version: string) => <Tag>v{version}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={status === 'active' ? 'green' : status === 'draft' ? 'orange' : 'default'}>
          {status}
        </Tag>
      ),
    },
    {
      title: '业务领域',
      dataIndex: 'domain',
      key: 'domain',
      render: (domain: string) => domain || '-',
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: Ontology) => (
        <Space>
          <Button
            type="link"
            icon={<EyeOutlined />}
            onClick={() => navigate(`/ontology/${record.id}`)}
          >
            查看
          </Button>
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => navigate(`/ontology/${record.id}/edit`)}
          >
            编辑
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={3}>本体建模</Title>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setModalVisible(true)}
        >
          生成本体草案
        </Button>
      </div>

      <Card>
        {ontologies.length === 0 && !loading ? (
          <Empty description="暂无本体数据">
            <Button type="primary" onClick={() => setModalVisible(true)}>
              生成第一个本体
            </Button>
          </Empty>
        ) : (
          <Table
            columns={columns}
            dataSource={ontologies}
            rowKey="id"
            loading={loading}
          />
        )}
      </Card>

      <Modal
        title="生成本体草案"
        open={modalVisible}
        onCancel={() => {
          setModalVisible(false);
          form.resetFields();
        }}
        onOk={() => form.submit()}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleCreateDraft}
        >
          <Form.Item
            name="dataSourceId"
            label="选择数据源"
            rules={[{ required: true, message: '请选择数据源' }]}
          >
            <Select placeholder="请选择要生成本体的数据源">
              {dataSources.map(source => (
                <Option key={source.id} value={source.id}>
                  {source.name} ({source.sourceType})
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item
            name="name"
            label="本体名称"
          >
            <Input placeholder="留空将自动生成" />
          </Form.Item>
          <Form.Item
            name="domain"
            label="业务领域"
          >
            <Input placeholder="例如：合同管理" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default OntologyList;
