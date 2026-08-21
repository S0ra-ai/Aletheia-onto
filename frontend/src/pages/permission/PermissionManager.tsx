import React, { useEffect, useState } from 'react';
import { Card, Table, Button, Modal, Form, Input, Select, Switch, Space, Tag, message, Tabs, Popconfirm, Badge } from 'antd';
import { PlusOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import { permissionApi, toolApi } from '../../api';
import type { PermissionRole, PermissionPolicy, ToolDefinition, ToolExecutionLog } from '../../types';

const PermissionManager: React.FC = () => {
  const [roles, setRoles] = useState<PermissionRole[]>([]);
  const [policies, setPolicies] = useState<PermissionPolicy[]>([]);
  const [tools, setTools] = useState<ToolDefinition[]>([]);
  const [pendingReviews, setPendingReviews] = useState<ToolExecutionLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [roleModalOpen, setRoleModalOpen] = useState(false);
  const [policyModalOpen, setPolicyModalOpen] = useState(false);
  const [roleForm] = Form.useForm();
  const [policyForm] = Form.useForm();

  const loadAll = async () => {
    setLoading(true);
    try {
      const [r, p, t, pr] = await Promise.all([
        permissionApi.getRoles(),
        permissionApi.getPolicies(),
        toolApi.list(),
        toolApi.getPendingReviews(),
      ]);
      setRoles(r);
      setPolicies(p);
      setTools(t);
      setPendingReviews(pr);
    } catch { /* ignore */ }
    setLoading(false);
  };

  useEffect(() => { loadAll(); }, []);

  const handleCreateRole = async (values: any) => {
    try {
      await permissionApi.createRole(values);
      message.success('角色创建成功');
      setRoleModalOpen(false);
      roleForm.resetFields();
      loadAll();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '创建失败');
    }
  };

  const handleUpsertPolicy = async (values: any) => {
    try {
      await permissionApi.upsertPolicy({
        roleId: values.roleId,
        objectCode: values.objectCode,
        canRead: values.canRead ?? true,
        canWrite: values.canWrite ?? false,
        canExecute: values.canExecute ?? false,
        canDelete: values.canDelete ?? false,
        description: values.description || '',
      });
      message.success('策略已保存');
      setPolicyModalOpen(false);
      policyForm.resetFields();
      loadAll();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '保存失败');
    }
  };

  const handleReview = async (logId: number, decision: string) => {
    try {
      await toolApi.reviewExecution(logId, { reviewer: 'admin', decision });
      message.success(decision === 'approved' ? '已通过' : '已拒绝');
      loadAll();
    } catch {
      message.error('审核失败');
    }
  };

  const roleColumns = [
    { title: '编码', dataIndex: 'code', key: 'code', render: (v: string) => <Tag>{v}</Tag> },
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '描述', dataIndex: 'description', key: 'description' },
    { title: '系统角色', dataIndex: 'isSystem', key: 'isSystem', render: (v: number) => v ? <Tag color="blue">是</Tag> : '-' },
  ];

  const policyColumns = [
    { title: '角色', dataIndex: 'roleName', key: 'roleName', render: (_: string, r: PermissionPolicy) => <Tag>{r.roleCode || r.roleId}</Tag> },
    { title: '对象', dataIndex: 'objectCode', key: 'objectCode', render: (v: string) => <Tag color="purple">{v}</Tag> },
    {
      title: '读', dataIndex: 'canRead', key: 'canRead',
      render: (v: number) => v ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : <CloseCircleOutlined style={{ color: '#ccc' }} />,
    },
    {
      title: '写', dataIndex: 'canWrite', key: 'canWrite',
      render: (v: number) => v ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : <CloseCircleOutlined style={{ color: '#ccc' }} />,
    },
    {
      title: '执行', dataIndex: 'canExecute', key: 'canExecute',
      render: (v: number) => v ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : <CloseCircleOutlined style={{ color: '#ccc' }} />,
    },
    {
      title: '删除', dataIndex: 'canDelete', key: 'canDelete',
      render: (v: number) => v ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : <CloseCircleOutlined style={{ color: '#ccc' }} />,
    },
    { title: '描述', dataIndex: 'description', key: 'description' },
  ];

  const toolColumns = [
    { title: '编码', dataIndex: 'code', key: 'code', render: (v: string) => <Tag>{v}</Tag> },
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '类型', dataIndex: 'toolType', key: 'toolType', render: (v: string) => <Tag color={v === 'mutation' ? 'red' : 'blue'}>{v}</Tag> },
    { title: '风险等级', dataIndex: 'riskLevel', key: 'riskLevel', render: (v: string) => {
      const color = v === 'high' ? 'red' : v === 'medium' ? 'orange' : 'green';
      return <Tag color={color}>{v}</Tag>;
    }},
    { title: '需审核', dataIndex: 'requiresReview', key: 'requiresReview', render: (v: number) => v ? <Tag color="warning">是</Tag> : '-' },
    { title: '状态', dataIndex: 'status', key: 'status' },
  ];

  const reviewColumns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '工具', dataIndex: 'toolCode', key: 'toolCode', render: (v: string) => <Tag>{v}</Tag> },
    { title: '角色', dataIndex: 'agentRole', key: 'agentRole' },
    { title: '对象', dataIndex: 'objectCode', key: 'objectCode' },
    { title: '实例', dataIndex: 'instanceId', key: 'instanceId' },
    { title: '状态', dataIndex: 'status', key: 'status', render: (v: string) => <Tag color={v === 'success' ? 'green' : 'red'}>{v}</Tag> },
    { title: '耗时', dataIndex: 'durationMs', key: 'durationMs', render: (v: number) => `${v}ms` },
    { title: '创建时间', dataIndex: 'createdAt', key: 'createdAt' },
    {
      title: '操作', key: 'action', width: 160,
      render: (_: any, record: ToolExecutionLog) => (
        <Space>
          <Button size="small" type="primary" onClick={() => handleReview(record.id, 'approved')}>通过</Button>
          <Popconfirm title="确认拒绝？" onConfirm={() => handleReview(record.id, 'rejected')}>
            <Button size="small" danger>拒绝</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Tabs items={[
        {
          key: 'roles',
          label: '角色管理',
          children: (
            <Card title="角色列表" extra={<Button icon={<PlusOutlined />} onClick={() => setRoleModalOpen(true)}>新建角色</Button>}>
              <Table dataSource={roles} columns={roleColumns} rowKey="id" loading={loading} pagination={false} size="small" />
            </Card>
          ),
        },
        {
          key: 'policies',
          label: '权限策略',
          children: (
            <Card title="权限策略" extra={<Button icon={<PlusOutlined />} onClick={() => setPolicyModalOpen(true)}>新建策略</Button>}>
              <Table dataSource={policies} columns={policyColumns} rowKey="id" loading={loading} pagination={false} size="small" />
            </Card>
          ),
        },
        {
          key: 'tools',
          label: '工具定义',
          children: (
            <Card title="已注册工具">
              <Table dataSource={tools} columns={toolColumns} rowKey="id" loading={loading} pagination={false} size="small" />
            </Card>
          ),
        },
        {
          key: 'reviews',
          label: <Badge count={pendingReviews.length} size="small">待审核</Badge>,
          children: (
            <Card title="待审核工具执行">
              <Table dataSource={pendingReviews} columns={reviewColumns} rowKey="id" loading={loading} pagination={false} size="small" />
            </Card>
          ),
        },
      ]} />

      <Modal title="新建角色" open={roleModalOpen} onCancel={() => setRoleModalOpen(false)} onOk={() => roleForm.submit()} width={450}>
        <Form form={roleForm} layout="vertical" onFinish={handleCreateRole}>
          <Form.Item name="code" label="角色编码" rules={[{ required: true }]}>
            <Input placeholder="如 manager" />
          </Form.Item>
          <Form.Item name="name" label="角色名称" rules={[{ required: true }]}>
            <Input placeholder="部门经理" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea placeholder="可选" />
          </Form.Item>
          <Form.Item name="isSystem" label="系统角色" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="新建权限策略" open={policyModalOpen} onCancel={() => setPolicyModalOpen(false)} onOk={() => policyForm.submit()} width={500}>
        <Form form={policyForm} layout="vertical" onFinish={handleUpsertPolicy}>
          <Form.Item name="roleId" label="角色" rules={[{ required: true }]}>
            <Select placeholder="选择角色">
              {roles.map(r => <Select.Option key={r.id} value={r.id}>{r.name} ({r.code})</Select.Option>)}
            </Select>
          </Form.Item>
          <Form.Item name="objectCode" label="业务对象编码" rules={[{ required: true }]}>
            <Input placeholder="如 contract, equipment" />
          </Form.Item>
          <Space>
            <Form.Item name="canRead" label="读" valuePropName="checked" initialValue={true}><Switch /></Form.Item>
            <Form.Item name="canWrite" label="写" valuePropName="checked"><Switch /></Form.Item>
            <Form.Item name="canExecute" label="执行" valuePropName="checked"><Switch /></Form.Item>
            <Form.Item name="canDelete" label="删除" valuePropName="checked"><Switch /></Form.Item>
          </Space>
          <Form.Item name="description" label="描述">
            <Input placeholder="可选" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default PermissionManager;
