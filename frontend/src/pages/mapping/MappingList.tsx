import React, { useCallback, useEffect, useState } from 'react';
import { MAPPING_STATUS, MAPPING_TYPE, ONTOLOGY_STATUS } from '../../i18n/labels';
import { useLabel, useT } from '../../i18n/locale';
import { Alert, Button, Card, Table, Typography, Tag, Empty, Select, Space, message } from 'antd';
import { CheckOutlined, CloseOutlined } from '@ant-design/icons';
import { ontologyApi, requestErrorMessage } from '../../api';
import type { Ontology, SemanticMapping } from '../../types';

const { Text, Title } = Typography;
const { Option } = Select;

// Rows per request. Larger than antd's default of 10 because this is a review queue -- a
// reviewer reads through pending mappings rather than hunting for one -- and small enough that
// a page is a page. `ONTOLOGY_MAX_PAGE_SIZE` on the server is 200 and clamps anything larger.
const PAGE_SIZE = 50;

const MappingList: React.FC = () => {
  const label = useLabel();
  const t = useT();
  const [ontologies, setOntologies] = useState<Ontology[]>([]);
  const [mappings, setMappings] = useState<SemanticMapping[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [selectedOntology, setSelectedOntology] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  // Kept apart from an empty list: both leave `mappings` empty.
  const [loadError, setLoadError] = useState('');

  const fetchOntologies = useCallback(async () => {
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
  }, [t]);

  const fetchMappings = useCallback(async (ontologyId: number, page = 1) => {
    setLoading(true);
    setLoadError('');
    try {
      // Server-side paging. The queue is one row per mapped column -- a legacy schema with
      // hundreds of tables produces thousands -- and the page used to fetch all of them and
      // let antd paginate in the browser.
      const { items, pagination } = await ontologyApi.getMappings(ontologyId, {
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      });
      setMappings(items);
      setTotal(pagination.total);
      setPage(page);
    } catch (error) {
      // This used to `console.error` and then set the list to empty, so a failed request
      // rendered the same "请选择本体查看映射关系" as an ontology that genuinely has none.
      // On the mapping review queue -- the governance surface -- reporting a fetch failure
      // as "nothing to review" is a false statement about what has been reviewed.
      setMappings([]);
      setTotal(0);
      setLoadError(requestErrorMessage(error, t('mapping.loadMappingsFailed')));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void fetchOntologies();
  }, [fetchOntologies]);

  useEffect(() => {
    if (selectedOntology) {
      void fetchMappings(selectedOntology);
    }
  }, [selectedOntology, fetchMappings]);

  const handleBulkReview = async (status: string) => {
    if (!selectedOntology) return;
    try {
      // `status` alone. This used to send `reviewer: '前端用户'` -- a name the server does
      // not accept (it credits the authenticated principal) so it was dropped, and a
      // `note: '工作台批量审核'` that the server *did* accept and wrote into
      // `semantic_mapping.evidence`. A canned note is stored in whatever language the
      // console was in, and no later language switch can reach it; the bulk action is
      // already recorded structurally in `audit_log` as `bulk_review_semantic_mappings`
      // with its status and count, which is the provenance this note was standing in for.
      const result = await ontologyApi.reviewMappings(selectedOntology, { status });
      // The count, because paging made the button ambiguous: it reviews every *pending*
      // mapping of the ontology, not the rows on the visible page, and a reader looking at
      // page one of nine has no way to tell that from the label alone.
      message.success(
        t(status === 'confirmed' ? 'mapping.bulkConfirmDone' : 'mapping.bulkRejectDone', {
          count: result?.reviewedCount ?? 0,
        }),
      );
      void fetchMappings(selectedOntology, 1);
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
            pagination={{
              current: page,
              pageSize: PAGE_SIZE,
              total,
              showSizeChanger: false,
              // `total` comes from the server's count, not from `mappings.length`: this table
              // holds one page, and a pager built from the rows it is holding would always say
              // it is on the last one.
              showTotal: (count) => t('mapping.totalRows', { count }),
              onChange: (next) => void fetchMappings(selectedOntology as number, next),
            }}
          />
        )}
      </Card>
    </div>
  );
};

export default MappingList;
