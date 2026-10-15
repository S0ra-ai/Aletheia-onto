import React, { useEffect, useState } from 'react';
import { label, MAPPING_STATUS } from '../../i18n/labels';
import { Alert, Button, Card, Table, Typography, Tag, Empty, Select, Space, message } from 'antd';
import { CheckOutlined, CloseOutlined } from '@ant-design/icons';
import { ontologyApi, requestErrorMessage } from '../../api';
import type { Ontology, SemanticMapping } from '../../types';

const { Title } = Typography;
const { Option } = Select;

const MappingList: React.FC = () => {
  const [ontologies, setOntologies] = useState<Ontology[]>([]);
  const [mappings, setMappings] = useState<SemanticMapping[]>([]);
  const [selectedOntology, setSelectedOntology] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  // Kept apart from an empty list: both leave `mappings` empty.
  const [loadError, setLoadError] = useState('');

  const fetchOntologies = async () => {
    try {
      const items = await ontologyApi.list();
      setOntologies(items as Ontology[]);
    } catch (error) {
      message.error(requestErrorMessage(error, '获取本体列表失败'));
    }
  };

  const fetchMappings = async (ontologyId: number) => {
    setLoading(true);
    setLoadError('');
    try {
      setMappings(await ontologyApi.getMappings(ontologyId) as SemanticMapping[]);
    } catch (error) {
      // This used to `console.error` and then set the list to empty, so a failed request
      // rendered the same "请选择本体查看映射关系" as an ontology that genuinely has none.
      // On the mapping review queue -- the governance surface -- reporting a fetch failure
      // as "nothing to review" is a false statement about what has been reviewed.
      setMappings([]);
      setLoadError(requestErrorMessage(error, '获取语义映射失败'));
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
    } catch (error) {
      message.error(requestErrorMessage(error, '审核失败'));
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
          {label(MAPPING_STATUS, status)}
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
        {loadError ? (
          <Alert
            type="error"
            showIcon
            message="获取语义映射失败"
            description={loadError}
            action={<Button onClick={() => selectedOntology && fetchMappings(selectedOntology)}>重试</Button>}
          />
        ) : mappings.length === 0 && !loading ? (
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
