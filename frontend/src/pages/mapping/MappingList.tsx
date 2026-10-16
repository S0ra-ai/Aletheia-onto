import React, { useEffect, useState } from 'react';
import { MAPPING_STATUS, MAPPING_TYPE, ONTOLOGY_STATUS } from '../../i18n/labels';
import { useLabel, useT } from '../../i18n/locale';
import { Alert, Button, Card, Table, Typography, Tag, Empty, Select, Space, message } from 'antd';
import { CheckOutlined, CloseOutlined } from '@ant-design/icons';
import { ontologyApi, requestErrorMessage } from '../../api';
import type { Ontology, SemanticMapping } from '../../types';

const { Text, Title } = Typography;
const { Option } = Select;

const MappingList: React.FC = () => {
  const label = useLabel();
  const t = useT();
  const [ontologies, setOntologies] = useState<Ontology[]>([]);
  const [mappings, setMappings] = useState<SemanticMapping[]>([]);
  const [selectedOntology, setSelectedOntology] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  // Kept apart from an empty list: both leave `mappings` empty.
  const [loadError, setLoadError] = useState('');

  const fetchOntologies = async () => {
    try {
      const items = (await ontologyApi.list()) as Ontology[];
      setOntologies(items);
      // Selected rather than left for the reader to choose. Reviewing mappings is the
      // blocking gate before publishing, and a page that opens by asking "which ontology"
      // -- on a deployment that usually has one -- puts the work behind a guess. It also
      // meant the screen rendered no table at all until somebody clicked, so the smoke
      // check that reports empty columns had nothing to look at.
      setSelectedOntology((current) => current ?? items[0]?.id ?? null);
    } catch (error) {
      message.error(requestErrorMessage(error, t('mapping.loadOntologiesFailed')));
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
      setLoadError(requestErrorMessage(error, t('mapping.loadMappingsFailed')));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOntologies();
  }, [t]);

  useEffect(() => {
    if (selectedOntology) {
      fetchMappings(selectedOntology);
    }
  }, [selectedOntology, t]);

  const handleBulkReview = async (status: string) => {
    if (!selectedOntology) return;
    try {
      await ontologyApi.reviewMappings(selectedOntology, { status, reviewer: '前端用户', note: '工作台批量审核' });
      message.success(status === 'confirmed' ? t('mapping.bulkConfirmDone') : t('mapping.bulkRejectDone'));
      fetchMappings(selectedOntology);
    } catch (error) {
      message.error(requestErrorMessage(error, t('mapping.reviewFailed')));
    }
  };

  const columns = [
    {
      title: t('mapping.colMappingType'),
      dataIndex: 'mappingType',
      key: 'mappingType',
      render: (type: string) => <Tag>{label(MAPPING_TYPE, type)}</Tag>,
    },
    {
      title: t('mapping.colSourceTable'),
      dataIndex: 'sourceTable',
      key: 'sourceTable',
    },
    {
      title: t('mapping.colSourceColumn'),
      dataIndex: 'sourceColumn',
      key: 'sourceColumn',
      render: (column: string) => column || '-',
    },
    {
      title: t('mapping.colTargetObject'),
      dataIndex: 'targetObjectCode',
      key: 'targetObjectCode',
      render: (code: string) => <Tag color="blue">{code}</Tag>,
    },
    {
      title: t('mapping.colTargetAttribute'),
      dataIndex: 'targetAttributeCode',
      key: 'targetAttributeCode',
      render: (code: string) => code || '-',
    },
    {
      title: t('mapping.colConfidence'),
      dataIndex: 'confidence',
      key: 'confidence',
      render: (confidence: number) => (
        <span style={{ color: confidence >= 0.8 ? '#52c41a' : confidence >= 0.5 ? '#faad14' : '#ff4d4f' }}>
          {(confidence * 100).toFixed(0)}%
        </span>
      ),
    },
    {
      title: t('mapping.colStatus'),
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={status === 'confirmed' ? 'green' : status === 'pending' ? 'orange' : 'default'}>
          {label(MAPPING_STATUS, status)}
        </Tag>
      ),
    },
    {
      title: t('mapping.colReviewer'),
      dataIndex: 'reviewer',
      key: 'reviewer',
      render: (reviewer: string) => reviewer || '-',
    },
  ];

  return (
    <div>
      <Title level={3}>{t('mapping.title')}</Title>

      <Card style={{ marginBottom: 16 }}>
        <Space>
          <span>{t('mapping.ontologyLabel')}</span>
          <Select
            style={{ width: 300 }}
            placeholder={t('mapping.ontologyPlaceholder')}
            value={selectedOntology ?? undefined}
            onChange={setSelectedOntology}
            allowClear
          >
            {ontologies.map(ontology => (
              <Option key={ontology.id} value={ontology.id}>
                {t('mapping.ontologyOption', {
                  name: ontology.name,
                  version: ontology.version,
                  status: label(ONTOLOGY_STATUS, ontology.status),
                })}
              </Option>
            ))}
          </Select>
          <Button icon={<CheckOutlined />} disabled={!selectedOntology} onClick={() => handleBulkReview('confirmed')}>
            {t('mapping.bulkConfirm')}
          </Button>
          <Button icon={<CloseOutlined />} disabled={!selectedOntology} onClick={() => handleBulkReview('rejected')}>
            {t('mapping.bulkReject')}
          </Button>
        </Space>
      </Card>

      <Card>
        {loadError ? (
          <Alert
            type="error"
            showIcon
            message={t('mapping.loadMappingsFailed')}
            description={loadError}
            action={<Button onClick={() => selectedOntology && fetchMappings(selectedOntology)}>{t('mapping.retry')}</Button>}
          />
        ) : !selectedOntology ? (
          <Empty
            description={
              <Space direction="vertical" size={4} style={{ maxWidth: 620 }}>
                <Text strong>{t('mapping.noOntologies')}</Text>
                <Text type="secondary">{t('mapping.noOntologiesHint')}</Text>
              </Space>
            }
          />
        ) : mappings.length === 0 && !loading ? (
          <Empty description={t('mapping.noMappings')} />
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
