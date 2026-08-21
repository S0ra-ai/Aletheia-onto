import React, { useEffect, useState } from 'react';
import { Card, Table, Button, Modal, Form, Input, Select, Space, Tag, message, Popconfirm, Descriptions, Timeline } from 'antd';
import { PlusOutlined, DeleteOutlined, RightOutlined, HistoryOutlined } from '@ant-design/icons';
import { workflowApi, ontologyApi } from '../../api';
import type { WorkflowDefinition, WorkflowHistoryItem } from '../../types';

const WorkflowManager: React.FC = () => {
  const [workflows, setWorkflows] = useState<WorkflowDefinition[]>([]);
  const [ontologies, setOntologies] = useState<Array<{ id: number; name: string; domain: string }>>([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowDefinition | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyItems, setHistoryItems] = useState<WorkflowHistoryItem[]>([]);
  const [transitionModalOpen, setTransitionModalOpen] = useState(false);
  const [transitionActions, setTransitionActions] = useState<Array<{ actionCode: string; name: string; toState: string }>>([]);
  const [transitionInstanceId, setTransitionInstanceId] = useState('');
  const [transitionWorkflowId, setTransitionWorkflowId] = useState(0);
  const [form] = Form.useForm();

  const loadWorkflows = async () => {
    setLoading(true);
    try {
      const items = await workflowApi.list();
      setWorkflows(items);
    } catch {
      message.error('加载工作流失败');
    }
    setLoading(false);
  };

  const loadOntologies = async () => {
    try {
      const items = await ontologyApi.list();
      setOntologies(items.map((o: any) => ({ id: o.id, name: o.name, domain: o.domain || '' })));
    } catch { /* ignore */ }
  };

  useEffect(() => { loadWorkflows(); loadOntologies(); }, []);

  const handleCreate = async (values: any) => {
    try {
      await workflowApi.create({
        ontologyId: values.ontologyId,
        objectCode: values.objectCode,
        name: values.name,
        description: values.description || '',
      });
      message.success('工作流创建成功');
      setCreateOpen(false);
      form.resetFields();
      loadWorkflows();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '创建失败');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await workflowApi.delete(id);
      message.success('已删除');
      loadWorkflows();
    } catch {
      message.error('删除失败');
    }
  };

  const showDetail = async (wf: WorkflowDefinition) => {
    try {
      const detail = await workflowApi.get(wf.id);
      setSelectedWorkflow(detail);
      setDetailOpen(true);
    } catch {
      message.error('加载详情失败');
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
    } catch {
      setTransitionActions([]);
    }
  };

  const doTransition = async (actionCode: string) => {
    try {
      await workflowApi.transition(transitionWorkflowId, {
        instanceId: transitionInstanceId,
        actionCode,
        actor: 'ui_user',
      });
      message.success('状态转移成功');
      setTransitionModalOpen(false);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '转移失败');
    }
  };

  const showHistory = async (wf: WorkflowDefinition) => {
    setTransitionWorkflowId(wf.id);
    try {
      const items = await workflowApi.getInstanceHistory(wf.id, transitionInstanceId || 'demo_1');
      setHistoryItems(items);
      setHistoryOpen(true);
    } catch {
      setHistoryItems([]);
      setHistoryOpen(true);
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
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '业务对象', dataIndex: 'objectCode', key: 'objectCode', render: (v: string) => <Tag>{v}</Tag> },
    { title: '本体', dataIndex: 'ontologyId', key: 'ontologyId' },
    { title: '初始状态', dataIndex: 'initialState', key: 'initialState', render: (v: string) => <Tag color={stateColor(v)}>{v}</Tag> },
    { title: '状态', dataIndex: 'status', key: 'status', render: (v: string) => <Tag color={v === 'active' ? 'green' : 'default'}>{v}</Tag> },
    {
      title: '操作', key: 'action', width: 280,
      render: (_: any, record: WorkflowDefinition) => (
        <Space>
          <Button size="small" onClick={() => showDetail(record)}>详情</Button>
          <Button size="small" icon={<RightOutlined />} onClick={() => showTransitionModal(record)}>转移</Button>
          <Button size="small" icon={<HistoryOutlined />} onClick={() => showHistory(record)}>历史</Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Card title="工作流管理" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新建工作流</Button>}>
        <Table dataSource={workflows} columns={columns} rowKey="id" loading={loading} pagination={false} />
      </Card>

      <Modal title="新建工作流" open={createOpen} onCancel={() => setCreateOpen(false)} onOk={() => form.submit()} width={500}>
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="ontologyId" label="本体" rules={[{ required: true }]}>
            <Select placeholder="选择本体">
              {ontologies.map(o => <Select.Option key={o.id} value={o.id}>{o.name} ({o.domain})</Select.Option>)}
            </Select>
          </Form.Item>
          <Form.Item name="objectCode" label="业务对象编码" rules={[{ required: true }]}>
            <Input placeholder="如 contract, equipment" />
          </Form.Item>
          <Form.Item name="name" label="工作流名称" rules={[{ required: true }]}>
            <Input placeholder="合同审批流程" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea placeholder="可选" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="工作流详情" open={detailOpen} onCancel={() => setDetailOpen(false)} footer={null} width={800}>
        {selectedWorkflow && (
          <div>
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="名称">{selectedWorkflow.name}</Descriptions.Item>
              <Descriptions.Item label="业务对象"><Tag>{selectedWorkflow.objectCode}</Tag></Descriptions.Item>
              <Descriptions.Item label="初始状态"><Tag color={stateColor(selectedWorkflow.initialState)}>{selectedWorkflow.initialState}</Tag></Descriptions.Item>
              <Descriptions.Item label="状态"><Tag color={selectedWorkflow.status === 'active' ? 'green' : 'default'}>{selectedWorkflow.status}</Tag></Descriptions.Item>
            </Descriptions>

            <Card title="状态节点" size="small" style={{ marginTop: 16 }}>
              <Space wrap>
                {(selectedWorkflow.states || []).map(s => (
                  <Tag key={s.code} color={s.color} style={{ fontSize: 13, padding: '4px 12px' }}>
                    {s.name} ({s.code}){s.isTerminal ? ' [终态]' : ''}
                  </Tag>
                ))}
              </Space>
            </Card>

            <Card title="转移规则" size="small" style={{ marginTop: 16 }}>
              <Table
                dataSource={selectedWorkflow.transitions || []}
                rowKey="id"
                size="small"
                pagination={false}
                columns={[
                  { title: '动作', dataIndex: 'actionCode', render: (v: string) => <Tag>{v}</Tag> },
                  { title: '名称', dataIndex: 'name' },
                  { title: '来源', dataIndex: 'fromState', render: (v: string) => <Tag color={stateColor(v)}>{v}</Tag> },
                  { title: '→', width: 40, render: () => <RightOutlined /> },
                  { title: '目标', dataIndex: 'toState', render: (v: string) => <Tag color={stateColor(v)}>{v}</Tag> },
                  { title: '需审核', dataIndex: 'requiresReview', render: (v: number) => v ? <Tag color="orange">是</Tag> : '-' },
                ]}
              />
            </Card>
          </div>
        )}
      </Modal>

      <Modal title="实例状态转移" open={transitionModalOpen} onCancel={() => setTransitionModalOpen(false)} footer={null} width={500}>
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Input placeholder="输入实例 ID" value={transitionInstanceId} onChange={e => setTransitionInstanceId(e.target.value)} onPressEnter={loadActions} />
          <Button onClick={loadActions}>查询可用动作</Button>
          {transitionActions.length > 0 ? (
            <Space wrap>
              {transitionActions.map(a => (
                <Button key={a.actionCode} type="primary" onClick={() => doTransition(a.actionCode)}>
                  {a.name} → {a.toState}
                </Button>
              ))}
            </Space>
          ) : transitionInstanceId ? (
            <div style={{ color: '#999' }}>该实例暂无可用动作</div>
          ) : null}
        </Space>
      </Modal>

      <Modal title="工作流历史" open={historyOpen} onCancel={() => setHistoryOpen(false)} footer={null} width={600}>
        {historyItems.length > 0 ? (
          <Timeline items={historyItems.map(h => ({
            color: h.fromState === '' ? 'green' : 'blue',
            children: (
              <div>
                <div style={{ fontWeight: 500 }}>
                  {h.fromState || '初始'} → {h.toState}
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
          <div style={{ color: '#999', textAlign: 'center', padding: 24 }}>暂无历史记录</div>
        )}
      </Modal>
    </div>
  );
};

export default WorkflowManager;
