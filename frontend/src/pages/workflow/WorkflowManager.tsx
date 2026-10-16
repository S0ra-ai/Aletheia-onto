import React, { useCallback, useEffect, useState } from 'react';
import { Empty, Card, Table, Button, Modal, Form, Input, Select, Space, Tag, message, Popconfirm, Descriptions, Timeline } from 'antd';
import { PlusOutlined, DeleteOutlined, RightOutlined, HistoryOutlined } from '@ant-design/icons';
import { ontologyApi, requestErrorMessage, workflowApi } from '../../api';
import type { WorkflowDefinition, WorkflowHistoryItem } from '../../types';
import { useT } from '../../i18n/locale';

const WorkflowManager: React.FC = () => {
  const t = useT();
  const [workflows, setWorkflows] = useState<WorkflowDefinition[]>([]);
  const [ontologies, setOntologies] = useState<Array<{ id: number; name: string; domain: string }>>([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowDefinition | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyItems, setHistoryItems] = useState<WorkflowHistoryItem[]>([]);
  // Which workflow the history dialog is about, and whether its query has run: an empty
  // timeline means "no history" only after somebody asked for a specific instance.
  const [historyWorkflow, setHistoryWorkflow] = useState<WorkflowDefinition | null>(null);
  const [historyInstanceId, setHistoryInstanceId] = useState('');
  const [historyQueried, setHistoryQueried] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [transitionModalOpen, setTransitionModalOpen] = useState(false);
  const [transitionActions, setTransitionActions] = useState<Array<{ actionCode: string; name: string; toState: string }>>([]);
  const [transitionInstanceId, setTransitionInstanceId] = useState('');
  const [transitionWorkflowId, setTransitionWorkflowId] = useState(0);
  const [form] = Form.useForm();

  const loadWorkflows = useCallback(async () => {
    setLoading(true);
    try {
      const items = await workflowApi.list();
      setWorkflows(items);
    } catch (error) {
      message.error(requestErrorMessage(error, t('workflow.loadFailed')));
    }
    setLoading(false);
  }, [t]);

  const loadOntologies = useCallback(async () => {
    try {
      const items = await ontologyApi.list();
      setOntologies(items.map((o: any) => ({ id: o.id, name: o.name, domain: o.domain || '' })));
    } catch (error) {
      // Ignoring this left the object selector empty with nothing said, so "why can I not
      // pick an ontology" had no answer on screen.
      message.error(requestErrorMessage(error, t('workflow.loadOntologiesFailed')));
    }
  }, [t]);

  useEffect(() => {
    void loadWorkflows();
    void loadOntologies();
  }, [loadWorkflows, loadOntologies]);

  const handleCreate = async (values: any) => {
    try {
      await workflowApi.create({
        ontologyId: values.ontologyId,
        objectCode: values.objectCode,
        name: values.name,
        description: values.description || '',
      });
      message.success(t('workflow.createSuccess'));
      setCreateOpen(false);
      form.resetFields();
      loadWorkflows();
    } catch (e: any) {
      message.error(requestErrorMessage(e, t('workflow.createFailed')));
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await workflowApi.delete(id);
      message.success(t('workflow.deleteSuccess'));
      loadWorkflows();
    } catch (error) {
      message.error(requestErrorMessage(error, t('workflow.deleteFailed')));
    }
  };

  const showDetail = async (wf: WorkflowDefinition) => {
    try {
      const detail = await workflowApi.get(wf.id);
      setSelectedWorkflow(detail);
      setDetailOpen(true);
    } catch (error) {
      message.error(requestErrorMessage(error, t('workflow.loadDetailFailed')));
    }
  };

  const showTransitionModal = async (wf: WorkflowDefinition) => {
    setTransitionWorkflowId(wf.id);
    setTransitionInstanceId('');
    setTransitionActions([]);
    setTransitionModalOpen(true);
  };

  const loadActions = async () => {
    if (!transitionInstanceId || !transitionWorkflowId) return;
    try {
      const actions = await workflowApi.getAvailableActions(transitionWorkflowId, transitionInstanceId);
      setTransitionActions(actions);
    } catch (error) {
      // An empty action list means "this workflow allows nothing from here", which is a
      // statement about the configuration. A failed read is not that statement.
      setTransitionActions([]);
      message.error(requestErrorMessage(error, t('workflow.loadActionsFailed')));
    }
  };

  const doTransition = async (actionCode: string) => {
    try {
      await workflowApi.transition(transitionWorkflowId, {
        instanceId: transitionInstanceId,
        actionCode,
        actor: 'ui_user',
      });
      message.success(t('workflow.transitionSuccess'));
      setTransitionModalOpen(false);
    } catch (e: any) {
      message.error(requestErrorMessage(e, t('workflow.transitionFailed')));
    }
  };

  const showHistory = async (wf: WorkflowDefinition, instanceId: string) => {
    setTransitionWorkflowId(wf.id);
    if (!instanceId.trim()) {
      // It used to pass `transitionInstanceId || 'demo_1'` -- an id that exists nowhere in the
      // repository. The dialog then listed nothing and said 「暂无历史记录」, which is a claim
      // about that instance's audit trail rather than about the query.
      setHistoryItems([]);
      setHistoryQueried(false);
      setHistoryOpen(true);
      return;
    }
    setHistoryLoading(true);
    try {
      setHistoryItems(await workflowApi.getInstanceHistory(wf.id, instanceId.trim()));
      setHistoryQueried(true);
      setHistoryOpen(true);
    } catch (error) {
      // This also opened the history dialog, so a failed read presented an empty dialog as
      // "this instance has no history" -- a statement about the instance's audit trail,
      // which is not what happened.
      setHistoryItems([]);
      setHistoryQueried(true);
      setHistoryOpen(true);
      message.error(requestErrorMessage(error, t('workflow.loadHistoryFailed')));
    } finally {
      setHistoryLoading(false);
    }
  };

  const stateColor = (code: string) => {
    const map: Record<string, string> = {
      draft: '#94a3b8', pending_review: '#f59e0b', approved: '#22c55e',
      rejected: '#ef4444', active: '#3b82f6', completed: '#10b981', cancelled: '#6b7280',
    };
    return map[code] || '#666';
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: t('workflow.name'), dataIndex: 'name', key: 'name' },
    { title: t('workflow.object'), dataIndex: 'objectCode', key: 'objectCode', render: (v: string) => <Tag>{v}</Tag> },
    { title: t('workflow.ontology'), dataIndex: 'ontologyId', key: 'ontologyId' },
    { title: t('workflow.initialState'), dataIndex: 'initialState', key: 'initialState', render: (v: string) => <Tag color={stateColor(v)}>{v}</Tag> },
    // No status column. `workflow_definition.status` is `active` and nothing ever changes
    // it -- deleting a workflow removes the row -- so every cell read the same word, in
    // English, under a heading that promises a lifecycle. Same reasoning as the detail
    // panel's removed row, and the same fix: a field that cannot vary is not a column.
    {
      title: t('shell.common.actions'), key: 'action', width: 280,
      render: (_: any, record: WorkflowDefinition) => (
        <Space>
          <Button size="small" onClick={() => showDetail(record)}>{t('workflow.details')}</Button>
          <Button size="small" icon={<RightOutlined />} onClick={() => showTransitionModal(record)}>{t('workflow.transition')}</Button>
          <Button size="small" icon={<HistoryOutlined />} onClick={() => { setHistoryWorkflow(record); setHistoryInstanceId(transitionInstanceId); void showHistory(record, transitionInstanceId); }}>{t('workflow.history')}</Button>
          <Popconfirm title={t('workflow.deleteConfirm')} onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Card title={t('workflow.title')} extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>{t('workflow.createButton')}</Button>}>
        <Table
          dataSource={workflows}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={false}
          locale={{
            // A bare "暂无数据" leaves the reader to guess whether the feature is missing,
            // the fetch failed, or there is simply nothing yet.
            emptyText: (
              <Empty description={t('workflow.empty')} />
            ),
          }}
        />
      </Card>

      <Modal title={t('workflow.createButton')} open={createOpen} onCancel={() => setCreateOpen(false)} onOk={() => form.submit()} width={500}>
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="ontologyId" label={t('workflow.ontology')} rules={[{ required: true }]}>
            <Select placeholder={t('workflow.selectOntology')}>
              {ontologies.map(o => <Select.Option key={o.id} value={o.id}>{o.name} ({o.domain})</Select.Option>)}
            </Select>
          </Form.Item>
          <Form.Item name="objectCode" label={t('workflow.objectCodeLabel')} rules={[{ required: true }]}>
            <Input placeholder={t('workflow.objectCodePlaceholder')} />
          </Form.Item>
          <Form.Item name="name" label={t('workflow.nameLabel')} rules={[{ required: true }]}>
            <Input placeholder={t('workflow.namePlaceholder')} />
          </Form.Item>
          <Form.Item name="description" label={t('workflow.description')}>
            <Input.TextArea placeholder={t('workflow.optional')} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title={t('workflow.detailTitle')} open={detailOpen} onCancel={() => setDetailOpen(false)} footer={null} width={800}>
        {selectedWorkflow && (
          <div>
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label={t('workflow.name')}>{selectedWorkflow.name}</Descriptions.Item>
              <Descriptions.Item label={t('workflow.object')}><Tag>{selectedWorkflow.objectCode}</Tag></Descriptions.Item>
              <Descriptions.Item label={t('workflow.initialState')}><Tag color={stateColor(selectedWorkflow.initialState)}>{selectedWorkflow.initialState}</Tag></Descriptions.Item>
              {/* No status row. `workflow_definition.status` is `active` and nothing ever
                  changes it -- deleting a workflow removes the row -- so the row showed one
                  value under a heading that promises a lifecycle. A field that cannot vary is
                  a claim about the model, and this one was not true. */}

            </Descriptions>

            <Card title={t('workflow.states')} size="small" style={{ marginTop: 16 }}>
              <Space wrap>
                {(selectedWorkflow.states || []).map(s => (
                  <Tag key={s.code} color={s.color} style={{ fontSize: 13, padding: '4px 12px' }}>
                    {s.name} ({s.code}){s.isTerminal ? t('workflow.terminal') : ''}
                  </Tag>
                ))}
              </Space>
            </Card>

            <Card title={t('workflow.transitions')} size="small" style={{ marginTop: 16 }}>
              <Table
                dataSource={selectedWorkflow.transitions || []}
                rowKey="id"
                size="small"
                pagination={false}
                columns={[
                  { title: t('workflow.action'), dataIndex: 'actionCode', render: (v: string) => <Tag>{v}</Tag> },
                  { title: t('workflow.name'), dataIndex: 'name' },
                  { title: t('workflow.from'), dataIndex: 'fromState', render: (v: string) => <Tag color={stateColor(v)}>{v}</Tag> },
                  { title: '→', width: 40, render: () => <RightOutlined /> },
                  { title: t('workflow.to'), dataIndex: 'toState', render: (v: string) => <Tag color={stateColor(v)}>{v}</Tag> },
                  { title: t('workflow.requiresReview'), dataIndex: 'requiresReview', render: (v: number) => v ? <Tag color="orange">{t('workflow.yes')}</Tag> : '-' },
                ]}
              />
            </Card>
          </div>
        )}
      </Modal>

      <Modal title={t('workflow.transitionTitle')} open={transitionModalOpen} onCancel={() => setTransitionModalOpen(false)} footer={null} width={500}>
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Input placeholder={t('workflow.instanceIdPlaceholder')} value={transitionInstanceId} onChange={e => setTransitionInstanceId(e.target.value)} onPressEnter={loadActions} />
          <Button onClick={loadActions}>{t('workflow.loadActionButton')}</Button>
          {transitionActions.length > 0 ? (
            <Space wrap>
              {transitionActions.map(a => (
                <Button key={a.actionCode} type="primary" onClick={() => doTransition(a.actionCode)}>
                  {a.name} → {a.toState}
                </Button>
              ))}
            </Space>
          ) : transitionInstanceId ? (
            <div style={{ color: '#999' }}>{t('workflow.noActions')}</div>
          ) : null}
        </Space>
      </Modal>

      <Modal title={t('workflow.historyTitle')} open={historyOpen} onCancel={() => setHistoryOpen(false)} footer={null} width={600}>
        <Input
          placeholder={t('workflow.instanceIdPlaceholder')}
          value={historyInstanceId}
          onChange={e => setHistoryInstanceId(e.target.value)}
          onPressEnter={() => historyWorkflow && void showHistory(historyWorkflow, historyInstanceId)}
          style={{ marginBottom: 12 }}
        />
        <Button
          onClick={() => historyWorkflow && void showHistory(historyWorkflow, historyInstanceId)}
          loading={historyLoading}
          style={{ marginBottom: 16 }}
        >
          {t('workflow.queryHistory')}
        </Button>
        {!historyQueried ? (
          <div style={{ color: '#999', textAlign: 'center', padding: 24 }}>
            {t('workflow.historyPrompt')}
          </div>
        ) : historyItems.length > 0 ? (
          <Timeline items={historyItems.map(h => ({
            color: h.fromState === '' ? 'green' : 'blue',
            children: (
              <div>
                <div style={{ fontWeight: 500 }}>
                  {h.fromState || t('workflow.initial')} → {h.toState}
                  <Tag style={{ marginLeft: 8 }}>{h.actionCode}</Tag>
                </div>
                <div style={{ color: '#666', fontSize: 12 }}>
                  {h.actor} | {h.createdAt}
                  {h.reason && ` | ${h.reason}`}
                </div>
              </div>
            ),
          }))} />
        ) : (
          <div style={{ color: '#999', textAlign: 'center', padding: 24 }}>{t('workflow.noHistory')}</div>
        )}
      </Modal>
    </div>
  );
};

export default WorkflowManager;
