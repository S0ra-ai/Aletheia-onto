import React, { useEffect, useState } from 'react';
import { Card, Table, Typography, Tag, Empty, Select, Space, message, Switch, Button } from 'antd';
import { EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { ontologyApi } from '../../api';
import type { Ontology, BusinessRule } from '../../types';

const { Title } = Typography;
const { Option } = Select;

const RuleList: React.FC = () => {
  const [ontologies, setOntologies] = useState<Ontology[]>([]);
  const [rules, setRules] = useState<BusinessRule[]>([]);
  const [selectedOntology, setSelectedOntology] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchOntologies = async () => {
    try {
      const items = await ontologyApi.list();
      setOntologies(items as Ontology[]);
    } catch (error) {
      message.error('获取本体列表失败');
    }
  };

  const fetchRules = async (ontologyId: number) => {
    setLoading(true);
    try {
      setRules(await ontologyApi.getRules(ontologyId) as BusinessRule[]);
    } catch (error) {
      console.error('Failed to fetch rules:', error);
      setRules([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOntologies();
  }, []);

  useEffect(() => {
    if (selectedOntology) {
      fetchRules(selectedOntology);
    }
  }, [selectedOntology]);

  const columns = [
    {
      title: '编码',
      dataIndex: 'code',
      key: 'code',
    },
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '严重程度',
      dataIndex: 'severity',
      key: 'severity',
      render: (severity: string) => (
        <Tag color={severity === 'error' ? 'red' : severity === 'warning' ? 'orange' : 'blue'}>
          {severity}
        </Tag>
      ),
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      key: 'enabled',
      render: (enabled: boolean) => (
        <Switch checked={enabled} disabled size="small" />
      ),
    },
    {
      title: '表达式',
      dataIndex: 'expression',
      key: 'expression',
      render: (expression: string) => (
        <code style={{ background: '#f5f5f5', padding: '2px 6px', borderRadius: 4 }}>
          {expression}
        </code>
      ),
    },
    {
      title: '操作',
      key: 'action',
      render: () => (
        <Space>
          <Button type="link" icon={<EditOutlined />} size="small">
            编辑
          </Button>
          <Button type="link" icon={<DeleteOutlined />} size="small" danger>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Title level={3}>规则管理</Title>

      <Card style={{ marginBottom: 16 }}>
        <Space>
          <span>选择本体：</span>
          <Select
            style={{ width: 300 }}
            placeholder="请选择本体"
            onChange={setSelectedOntology}
            allowClear
          >
            {ontologies.map(ontology => (
              <Option key={ontology.id} value={ontology.id}>
                {ontology.name} v{ontology.version} ({ontology.status})
              </Option>
            ))}
          </Select>
        </Space>
      </Card>

      <Card>
        {rules.length === 0 && !loading ? (
          <Empty description="请选择本体查看业务规则" />
        ) : (
          <Table
            columns={columns}
            dataSource={rules}
            rowKey="id"
            loading={loading}
          />
        )}
      </Card>
    </div>
  );
};

export default RuleList;
