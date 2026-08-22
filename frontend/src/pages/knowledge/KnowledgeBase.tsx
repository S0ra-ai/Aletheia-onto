import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert, Button, Card, Col, Empty, Form, Input, Modal, Row, Select, Space,
  Spin, Table, Tag, Typography, Upload, message,
} from 'antd';
import { InboxOutlined, ReloadOutlined } from '@ant-design/icons';
import { knowledgeApi, ontologyApi } from '../../api';
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
  const [ontologies, setOntologies] = useState<Ontology[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
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
        if (items.length) {
          const richest = [...items].sort((a, b) => (b.objectCount ?? 0) - (a.objectCount ?? 0))[0];
          setSelected(richest.id);
        }
      } catch {
        message.error('加载本体列表失败');
      }
    })();
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
    } catch {
      message.error('加载知识库失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selected != null) void load(selected);
  }, [selected, load]);

  const handleUpload = async () => {
    if (selected == null) return;
    const values = await uploadForm.validateFields();
    if (!pendingFile) {
      message.error('请选择文件');
      return;
    }
    setLoading(true);
    try {
      const result = await knowledgeApi.upload(selected, pendingFile, values);
      Modal.success({
        title: `已切分 ${result.chunkCount} 个条目`,
        content: (
          <div>
            <Paragraph style={{ marginBottom: 8 }}>
              引用定位：{result.citations.slice(0, 8).join('、')}
              {result.citations.length > 8 ? ' …' : ''}
            </Paragraph>
            <Alert type="info" showIcon message={result.note} />
            {result.warnings.length > 0 && (
              <Alert
                type="warning"
                showIcon
                style={{ marginTop: 8 }}
                message="切分提示"
                description={result.warnings.join('；')}
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
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || '上传失败');
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
      message.success(status === 'confirmed' ? '条目已确认，可作为判定依据' : '条目已更新');
      setReviewing(null);
      await load(selected);
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || '操作失败');
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
          <Title level={4} style={{ marginBottom: 4 }}>文档知识库</Title>
          <Text type="secondary">
            制度与合同条款，锚定到业务对象或规则后可作为判定依据被引用
          </Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => selected != null && void load(selected)}>刷新</Button>
          <Button type="primary" onClick={() => setUploadOpen(true)} disabled={selected == null}>
            上传文档
          </Button>
          <Select
            style={{ width: 240 }}
            placeholder="选择本体"
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
        message="条目须经确认才会被检索"
        description="切分结果默认为待审核状态。确认时必须指定它解释的业务对象或它作为依据的规则——未锚定的文本无法回答「这段话凭什么支持这个结论」，因此不能作为判定依据。"
      />

      {loading && !documents.length && <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>}

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={9}>
          <Card size="small" title={`文档（${documents.length}）`}>
            {documents.length === 0 ? (
              <Empty description="尚未上传文档" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <Table
                size="small"
                pagination={false}
                rowKey="id"
                dataSource={documents}
                columns={[
                  { title: '标题', dataIndex: 'title', ellipsis: true },
                  {
                    title: '条目',
                    key: 'counts',
                    width: 130,
                    render: (_: unknown, row: KnowledgeDocument) => (
                      <Space size={4}>
                        <Tag color="green">{row.confirmedCount} 已确认</Tag>
                        {row.pendingCount > 0 && <Tag color="orange">{row.pendingCount} 待审</Tag>}
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
                <span>知识条目</span>
                <Tag color="green">{confirmedCount} 已确认</Tag>
                {pendingCount > 0 && <Tag color="orange">{pendingCount} 待审核</Tag>}
              </Space>
            }
          >
            {entries.length === 0 ? (
              <Empty description="尚无条目" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <Table
                size="small"
                rowKey="id"
                dataSource={entries}
                pagination={{ pageSize: 8, size: 'small' }}
                columns={[
                  { title: '引用', dataIndex: 'citation', width: 96 },
                  { title: '内容', dataIndex: 'content', ellipsis: true },
                  {
                    title: '锚定',
                    key: 'anchor',
                    width: 190,
                    render: (_: unknown, row: KnowledgeEntry) => (
                      <Space size={4} wrap>
                        {row.objectCode && <Tag>{row.objectCode}</Tag>}
                        {row.ruleCode && <Tag color="blue"><code>{row.ruleCode}</code></Tag>}
                        {!row.objectCode && !row.ruleCode && <Text type="secondary">未锚定</Text>}
                      </Space>
                    ),
                  },
                  {
                    title: '状态',
                    dataIndex: 'status',
                    width: 88,
                    render: (status: string) => <Tag color={STATUS_COLOR[status] || 'default'}>{status}</Tag>,
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
                        审核
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
        title="上传制度或合同文档"
        open={uploadOpen}
        onCancel={() => setUploadOpen(false)}
        onOk={handleUpload}
        confirmLoading={loading}
        okText="上传并切分"
      >
        <Form form={uploadForm} layout="vertical">
          <Form.Item label="文件" required extra="支持 .docx 与 UTF-8 文本；按条款编号切分，保留可引用定位">
            <Upload.Dragger
              beforeUpload={file => {
                setPendingFile(file as unknown as File);
                return false;
              }}
              maxCount={1}
              onRemove={() => setPendingFile(null)}
            >
              <p className="ant-upload-drag-icon"><InboxOutlined /></p>
              <p className="ant-upload-text">点击或拖拽文件到此处</p>
            </Upload.Dragger>
          </Form.Item>
          <Form.Item name="title" label="文档标题" extra="留空则使用文件名；将作为引用出处显示">
            <Input placeholder="售后政策" />
          </Form.Item>
          <Form.Item name="objectCode" label="默认锚定业务对象（可选）" extra="可在逐条审核时修正">
            <Input placeholder="sales_order" />
          </Form.Item>
          <Form.Item name="ruleCode" label="默认锚定规则（可选）">
            <Input placeholder="refund_window_check" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`审核条目 ${reviewing?.citation || ''}`}
        open={Boolean(reviewing)}
        onCancel={() => setReviewing(null)}
        footer={[
          <Button key="reject" danger onClick={() => void handleReview('rejected')}>驳回</Button>,
          <Button key="cancel" onClick={() => setReviewing(null)}>取消</Button>,
          <Button key="confirm" type="primary" loading={loading} onClick={() => void handleReview('confirmed')}>
            确认为判定依据
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
                label="锚定业务对象"
                extra="该条款解释哪个业务对象"
                rules={[
                  ({ getFieldValue }) => ({
                    validator: () =>
                      getFieldValue('objectCode') || getFieldValue('ruleCode')
                        ? Promise.resolve()
                        : Promise.reject(new Error('业务对象与规则至少填写一项')),
                  }),
                ]}
              >
                <Input placeholder="sales_order" />
              </Form.Item>
              <Form.Item name="ruleCode" label="锚定规则" extra="该条款是哪条规则的文字依据">
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
