import { joinSentences } from '../../i18n/text';
import React, { useCallback, useEffect, useState } from 'react';
import { MAPPING_STATUS } from '../../i18n/labels';
import { useLabel, useT } from '../../i18n/locale';
import {
  Alert, Button, Card, Col, Empty, Form, Input, Modal, Row, Select, Space,
  Spin, Table, Tag, Typography, Upload, message,
} from 'antd';
import { InboxOutlined, ReloadOutlined } from '@ant-design/icons';
import { useIdParam } from '../../hooks/useIdParam';
import { knowledgeApi, ontologyApi, requestErrorMessage } from '../../api';
import type {
  KnowledgeDocument, KnowledgeEntry, Ontology,
} from '../../types';

const { Title, Text, Paragraph } = Typography;

/**
 * Document knowledge base.
 *
 * This screen exists to make citations *auditable*, which is why it looks like a
 * review queue rather than a file manager. Two rules from ADR-0009 drive the UI:
 *
 * 1. Entries arrive `pending` and are not retrievable until confirmed -- a
 *    mis-split clause that silently became judgement evidence would produce a
 *    verdict that looks sourced but is not.
 * 2. Confirming requires an anchor (business object or rule). Unanchored text
 *    cannot answer "why does this passage support this verdict", so the form
 *    refuses to submit without one.
 */

const STATUS_COLOR: Record<string, string> = {
  confirmed: 'green',
  pending: 'orange',
  rejected: 'red',
};

const KnowledgeBasePage: React.FC = () => {
  const label = useLabel();
  const t = useT();
  const [ontologies, setOntologies] = useState<Ontology[]>([]);
  // The ontology is in the URL: "the documents of this system" is a place somebody can send.
  // Without it a bare `/admin/knowledge` opens whichever ontology the page picks by itself,
  // and a shared link can quietly show a different system's documents than the sender meant.
  const [selected, setSelected] = useIdParam('ontology');
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [entries, setEntries] = useState<KnowledgeEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [reviewing, setReviewing] = useState<KnowledgeEntry | null>(null);
  const [uploadForm] = Form.useForm();
  const [reviewForm] = Form.useForm();

  useEffect(() => {
    (async () => {
      try {
        const items = await ontologyApi.list();
        setOntologies(items);
        // Nothing named in the URL: open the most-modelled ontology, which is the one a
        // fresh deployment has documents for, and *write it into the URL* so the address
        // matches what is on screen from the first second.
        if (items.length && selected == null) {
          const richest = [...items].sort((a, b) => (b.objectCount ?? 0) - (a.objectCount ?? 0))[0];
          setSelected(richest.id);
        }
      } catch (error) {
        message.error(requestErrorMessage(error, t('knowledge.loadOntologiesFailed')));
      }
    })();
    // Once, on arrival: `selected` is the URL's value at that moment, and re-running this
    // when the user switches ontologies would fight their choice.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = useCallback(async (ontologyId: number) => {
    setLoading(true);
    try {
      const [docs, entryList] = await Promise.all([
        knowledgeApi.listDocuments(ontologyId),
        knowledgeApi.listEntries(ontologyId, { limit: 200 }),
      ]);
      setDocuments(docs);
      setEntries(entryList.items);
    } catch (error) {
      message.error(requestErrorMessage(error, t('knowledge.loadFailed')));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (selected != null) void load(selected);
  }, [selected, load]);

  const handleUpload = async () => {
    if (selected == null) return;
    const values = await uploadForm.validateFields();
    if (!pendingFile) {
      message.error(t('knowledge.noFileSelected'));
      return;
    }
    setLoading(true);
    try {
      const result = await knowledgeApi.upload(selected, pendingFile, values);
      Modal.success({
        title: t('knowledge.splitDone', { count: result.chunkCount }),
        content: (
          <div>
            <Paragraph style={{ marginBottom: 8 }}>
              {t('knowledge.citationsLabel')}{result.citations.slice(0, 8).join(t('knowledge.citationSeparator'))}
              {result.citations.length > 8 ? ' …' : ''}
            </Paragraph>
            <Alert type="info" showIcon message={result.note} />
            {result.warnings.length > 0 && (
              <Alert
                type="warning"
                showIcon
                style={{ marginTop: 8 }}
                message={t('knowledge.splitWarnings')}
                description={joinSentences(result.warnings)}
              />
            )}
          </div>
        ),
      });
      setUploadOpen(false);
      setPendingFile(null);
      uploadForm.resetFields();
      await load(selected);
    } catch (error) {
      message.error(requestErrorMessage(error, t('knowledge.uploadFailed')));
    } finally {
      setLoading(false);
    }
  };

  const handleReview = async (status: string) => {
    if (!reviewing || selected == null) return;
    const values = status === 'confirmed' ? await reviewForm.validateFields() : reviewForm.getFieldsValue();
    setLoading(true);
    try {
      await knowledgeApi.review(reviewing.id, { status, ...values });
      message.success(status === 'confirmed' ? t('knowledge.entryConfirmed') : t('knowledge.entryUpdated'));
      setReviewing(null);
      await load(selected);
    } catch (error) {
      message.error(requestErrorMessage(error, t('knowledge.actionFailed')));
    } finally {
      setLoading(false);
    }
  };

  const pendingCount = entries.filter(entry => entry.status === 'pending').length;
  const confirmedCount = entries.filter(entry => entry.status === 'confirmed').length;

  return (
    <div>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap' }}>
        <div>
          <Title level={4} style={{ marginBottom: 4 }}>{t('knowledge.title')}</Title>
          <Text type="secondary">
            {t('knowledge.subtitle')}
          </Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => selected != null && void load(selected)}>{t('knowledge.refresh')}</Button>
          <Button type="primary" onClick={() => setUploadOpen(true)} disabled={selected == null}>
            {t('knowledge.uploadButton')}
          </Button>
          <Select
            style={{ width: 240 }}
            placeholder={t('knowledge.ontologyPlaceholder')}
            value={selected ?? undefined}
            onChange={setSelected}
            options={ontologies.map(item => ({
              value: item.id,
              label: `${item.name} v${item.version}`,
            }))}
          />
        </Space>
      </Space>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message={t('knowledge.confirmedOnly')}
        description={t('knowledge.confirmedOnlyDetail')}
      />

      {loading && !documents.length && <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>}

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={9}>
          <Card size="small" title={t('knowledge.documentsCard', { count: documents.length })}>
            {documents.length === 0 ? (
              <Empty description={t('knowledge.noDocuments')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <Table
                size="small"
                pagination={false}
                rowKey="id"
                dataSource={documents}
                columns={[
                  { title: t('knowledge.colTitle'), dataIndex: 'title', ellipsis: true },
                  {
                    title: t('knowledge.colCounts'),
                    key: 'counts',
                    width: 130,
                    render: (_: unknown, row: KnowledgeDocument) => (
                      <Space size={4}>
                        <Tag color="green">{t('knowledge.confirmedTag', { count: row.confirmedCount })}</Tag>
                        {row.pendingCount > 0 && <Tag color="orange">{t('knowledge.pendingTag', { count: row.pendingCount })}</Tag>}
                      </Space>
                    ),
                  },
                ]}
              />
            )}
          </Card>
        </Col>

        <Col xs={24} lg={15}>
          <Card
            size="small"
            title={
              <Space>
                <span>{t('knowledge.entriesTitle')}</span>
                <Tag color="green">{t('knowledge.confirmedTag', { count: confirmedCount })}</Tag>
                {pendingCount > 0 && <Tag color="orange">{t('knowledge.pendingReviewTag', { count: pendingCount })}</Tag>}
              </Space>
            }
          >
            {entries.length === 0 ? (
              <Empty description={t('knowledge.noEntries')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <Table
                size="small"
                rowKey="id"
                dataSource={entries}
                pagination={{ pageSize: 8, size: 'small' }}
                columns={[
                  { title: t('knowledge.colCitation'), dataIndex: 'citation', width: 96 },
                  { title: t('knowledge.colContent'), dataIndex: 'content', ellipsis: true },
                  {
                    title: t('knowledge.colAnchor'),
                    key: 'anchor',
                    width: 190,
                    render: (_: unknown, row: KnowledgeEntry) => (
                      <Space size={4} wrap>
                        {row.objectCode && <Tag>{row.objectCode}</Tag>}
                        {row.ruleCode && <Tag color="blue"><code>{row.ruleCode}</code></Tag>}
                        {!row.objectCode && !row.ruleCode && <Text type="secondary">{t('knowledge.unanchored')}</Text>}
                      </Space>
                    ),
                  },
                  {
                    title: t('knowledge.colStatus'),
                    dataIndex: 'status',
                    width: 88,
                    render: (status: string) => <Tag color={STATUS_COLOR[status] || 'default'}>{label(MAPPING_STATUS, status)}</Tag>,
                  },
                  {
                    title: '',
                    key: 'action',
                    width: 70,
                    render: (_: unknown, row: KnowledgeEntry) => (
                      <Button
                        type="link"
                        size="small"
                        onClick={() => {
                          setReviewing(row);
                          reviewForm.setFieldsValue({
                            objectCode: row.objectCode,
                            ruleCode: row.ruleCode,
                          });
                        }}
                      >
                        {t('knowledge.review')}
                      </Button>
                    ),
                  },
                ]}
              />
            )}
          </Card>
        </Col>
      </Row>

      <Modal
        title={t('knowledge.uploadTitle')}
        open={uploadOpen}
        onCancel={() => setUploadOpen(false)}
        onOk={handleUpload}
        confirmLoading={loading}
        okText={t('knowledge.uploadAndSplit')}
      >
        <Form form={uploadForm} layout="vertical">
          <Form.Item label={t('knowledge.fileLabel')} required extra={t('knowledge.fileHint')}>
            <Upload.Dragger
              beforeUpload={file => {
                setPendingFile(file as unknown as File);
                return false;
              }}
              maxCount={1}
              onRemove={() => setPendingFile(null)}
            >
              <p className="ant-upload-drag-icon"><InboxOutlined /></p>
              <p className="ant-upload-text">{t('knowledge.draggerText')}</p>
            </Upload.Dragger>
          </Form.Item>
          <Form.Item name="title" label={t('knowledge.documentTitleLabel')} extra={t('knowledge.documentTitleHint')}>
            <Input placeholder={t('knowledge.documentTitlePlaceholder')} />
          </Form.Item>
          <Form.Item name="objectCode" label={t('knowledge.defaultObjectLabel')} extra={t('knowledge.defaultObjectHint')}>
            <Input placeholder="sales_order" />
          </Form.Item>
          <Form.Item name="ruleCode" label={t('knowledge.defaultRuleLabel')}>
            <Input placeholder="refund_window_check" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t('knowledge.reviewTitle', { citation: reviewing?.citation || '' })}
        open={Boolean(reviewing)}
        onCancel={() => setReviewing(null)}
        footer={[
          <Button key="reject" danger onClick={() => void handleReview('rejected')}>{t('knowledge.reject')}</Button>,
          <Button key="cancel" onClick={() => setReviewing(null)}>{t('knowledge.cancel')}</Button>,
          <Button key="confirm" type="primary" loading={loading} onClick={() => void handleReview('confirmed')}>
            {t('knowledge.confirmAsEvidence')}
          </Button>,
        ]}
      >
        {reviewing && (
          <>
            <Card size="small" style={{ marginBottom: 12, background: '#fafcff' }}>
              <Text style={{ whiteSpace: 'pre-wrap' }}>{reviewing.content}</Text>
            </Card>
            <Form form={reviewForm} layout="vertical">
              <Form.Item
                name="objectCode"
                label={t('knowledge.anchorObjectLabel')}
                extra={t('knowledge.anchorObjectHint')}
                rules={[
                  ({ getFieldValue }) => ({
                    validator: () =>
                      getFieldValue('objectCode') || getFieldValue('ruleCode')
                        ? Promise.resolve()
                        : Promise.reject(new Error(t('knowledge.anchorRequired'))),
                  }),
                ]}
              >
                <Input placeholder="sales_order" />
              </Form.Item>
              <Form.Item name="ruleCode" label={t('knowledge.anchorRuleLabel')} extra={t('knowledge.anchorRuleHint')}>
                <Input placeholder="refund_window_check" />
              </Form.Item>
            </Form>
          </>
        )}
      </Modal>
    </div>
  );
};

export default KnowledgeBasePage;
