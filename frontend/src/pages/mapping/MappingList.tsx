import React, { useEffect, useState } from 'react';
import { Button, Card, Table, Typography, Tag, Empty, Select, Space, message } from 'antd';
import { CheckOutlined, CloseOutlined } from '@ant-design/icons';
import { ontologyApi } from '../../api';
import type { Ontology, SemanticMapping } from '../../types';

const { Title } = Typography;
const { Option } = Select;

const MappingList: React.FC = () => {
  const [ontologies, setOntologies] = useState<Ontology[]>([]);
  const [mappings, setMappings] = useState<SemanticMapping[]>([]);
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

  const fetchMappings = async (ontologyId: number) => {
    setLoading(true);
    try {
      setMappings(await ontologyApi.getMappings(ontologyId) as SemanticMapping[]);
    } catch (error) {
      console.error('Failed to fetch mappings:', error);
      setMappings([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOntologies();
  }, []);

  useEffect(() => {
    if (selectedOntology) {
      fetchMappings(selectedOntology);
    }
  }, [selectedOntology]);

  const handleBulkReview = async (status: string) => {
    if (!selectedOntology) return;
    try {
      await ontologyApi.reviewMappings(selectedOntology, { status, reviewer: '前端用户', note: '工作台批量审核' });
      message.success(status === 'confirmed' ? '已批量确认' : '已批量拒绝');
      fetchMappings(selectedOntology);
    } catch {
      message.error('审核失败');
    }
  };

  const columns = [
    {
      title: '映射类型',
      dataIndex: 'mappingType',
      key: 'mappingType',
      render: (type: string) => <Tag>{type}</Tag>,
    },
    {
      title: '来源表',
      dataIndex: 'sourceTable',
      key: 'sourceTable',
    },
    {
      title: '来源字段',
      dataIndex: 'sourceColumn',
      key: 'sourceColumn',
      render: (column: string) => column || '-',
    },
    {
      title: '目标对象',
      dataIndex: 'targetObjectCode',
      key: 'targetObjectCode',
      render: (code: string) => <Tag color="blue">{code}</Tag>,
    },
    {
      title: '目标属性',
      dataIndex: 'targetAttributeCode',
      key: 'targetAttributeCode',
      render: (code: string) => code || '-',
    },
    {
      title: '置信度',
      dataIndex: 'confidence',
      key: 'confidence',
      render: (confidence: number) => (
        <span style={{ color: confidence >= 0.8 ? '#52c41a' : confidence >= 0.5 ? '#faad14' : '#ff4d4f' }}>
          {(confidence * 100).toFixed(0)}%
        </span>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={status === 'confirmed' ? 'green' : status === 'pending' ? 'orange' : 'default'}>
          {status}
        </Tag>
      ),
    },
    {
      title: '审核人',
      dataIndex: 'reviewer',
      key: 'reviewer',
      render: (reviewer: string) => reviewer || '-',
    },
  ];

  return (
    <div>
      <Title level={3}>语义映射</Title>

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
          <Button icon={<CheckOutlined />} disabled={!selectedOntology} onClick={() => handleBulkReview('confirmed')}>
            批量确认
          </Button>
          <Button icon={<CloseOutlined />} disabled={!selectedOntology} onClick={() => handleBulkReview('rejected')}>
            批量拒绝
          </Button>
        </Space>
      </Card>

      <Card>
        {mappings.length === 0 && !loading ? (
          <Empty description="请选择本体查看映射关系" />
        ) : (
          <Table
            columns={columns}
            dataSource={mappings}
            rowKey="id"
            loading={loading}
          />
        )}
      </Card>
    </div>
  );
};

export default MappingList;
