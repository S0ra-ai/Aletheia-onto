import React, { useEffect, useState } from 'react';
import { label, ONTOLOGY_STATUS } from '../../i18n/labels';
import { Alert, Badge, Button, Card, Form, Input, Modal, Popconfirm, Select, Space, Switch, Table, Tabs, Tag, message } from 'antd';
import { PlusOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import { permissionApi, requestErrorMessage, ssoApi, toolApi } from '../../api';
import { useTabParam } from '../../hooks/useTabParam';
import type {
  PermissionRole,
  PermissionPolicy,
  SsoGroupMapping,
  SsoStatus,
  ToolDefinition,
  ToolExecutionLog,
} from '../../types';

const PermissionManager: React.FC = () => {
  const [tab, setTab] = useTabParam('roles');
  const [roles, setRoles] = useState<PermissionRole[]>([]);
  const [policies, setPolicies] = useState<PermissionPolicy[]>([]);
  const [tools, setTools] = useState<ToolDefinition[]>([]);
  const [pendingReviews, setPendingReviews] = useState<ToolExecutionLog[]>([]);
  const [loading, setLoading] = useState(false);
  // SSO lives on this page because a group mapping *is* a role assignment: it is where a
  // provider group becomes a platform capability. It had no screen at all, so an SSO
  // deployment had to declare it with curl -- and until one mapping existed every SSO login
  // was refused, by design, with nothing in the product to resolve it.
  const [sso, setSso] = useState<SsoStatus | null>(null);
  const [ssoMappings, setSsoMappings] = useState<SsoGroupMapping[]>([]);
  const [ssoModalOpen, setSsoModalOpen] = useState(false);
  const [ssoForm] = Form.useForm();
  const [roleModalOpen, setRoleModalOpen] = useState(false);
  const [policyModalOpen, setPolicyModalOpen] = useState(false);
  const [roleForm] = Form.useForm();
  const [policyForm] = Form.useForm();

  const loadAll = async () => {
    setLoading(true);
    try {
      const [r, p, t, pr, ssoStatus] = await Promise.all([
        permissionApi.getRoles(),
        permissionApi.getPolicies(),
        toolApi.list(),
        toolApi.getPendingReviews(),
        ssoApi.status().catch(() => null),
      ]);
      setRoles(r);
      setPolicies(p);
      setTools(t);
      setPendingReviews(pr);
      setSso(ssoStatus);
      setSsoMappings(ssoStatus?.mappings ?? []);
    } catch (error) {
      // A failure here left roles, policies, tools and pending reviews all empty with
      // nothing shown -- the whole page rendered as "there is nothing configured".
      message.error(requestErrorMessage(error, '加载权限配置失败'));
    }
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
    } catch (error) {
      message.error(requestErrorMessage(error, '审核失败'));
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
    { title: '状态', dataIndex: 'status', key: 'status', render: (v: string) => label(ONTOLOGY_STATUS, v) },
  ];

  const reviewColumns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '工具', dataIndex: 'toolCode', key: 'toolCode', render: (v: string) => <Tag>{v}</Tag> },
    { title: '角色', dataIndex: 'agentRole', key: 'agentRole' },
    { title: '对象', dataIndex: 'objectCode', key: 'objectCode' },
    { title: '实例', dataIndex: 'instanceId', key: 'instanceId' },
    { title: '状态', dataIndex: 'status', key: 'status', render: (v: string) => <Tag color={v === 'success' ? 'green' : 'red'}>{v}</Tag> },
    { title: '耗时', dataIndex: 'durationMs', key: 'durationMs', render: (v: number) => `${v}ms` },
    { title: '创建时间（UTC）', dataIndex: 'createdAt', key: 'createdAt' },
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

  const handleDeclareSso = async (values: { providerGroup: string; roleCode: string; note?: string }) => {
    try {
      await ssoApi.declare(values.providerGroup.trim(), values.roleCode, values.note || '');
      message.success('组映射已声明。未映射的身份会被拒绝，而不是给一个默认角色。');
      setSsoModalOpen(false);
      ssoForm.resetFields();
      await loadAll();
    } catch (error) {
      // The server rejects an unknown role by name; discarding that would leave the admin
      // guessing which role codes exist.
      message.error(requestErrorMessage(error, '声明组映射失败'));
    }
  };

  const handleRemoveSso = async (providerGroup: string) => {
    try {
      await ssoApi.remove(providerGroup);
      message.success('组映射已移除');
      await loadAll();
    } catch (error) {
      message.error(requestErrorMessage(error, '移除组映射失败'));
    }
  };

  return (
    <div>
      <Tabs activeKey={tab} onChange={setTab} items={[
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
          key: 'sso',
          label: 'SSO 组映射',
          children: (
            <Card
              title="单点登录"
              extra={
                <Button icon={<PlusOutlined />} onClick={() => setSsoModalOpen(true)} disabled={!sso?.enabled}>
                  声明组映射
                </Button>
              }
            >
              {sso === null ? (
                // Unknown is not "enabled". Falling through to the panel below would state
                // that SSO is on with empty fields whenever the status request failed --
                // the most misleading possible rendering of "we could not ask".
                <Alert
                  type="warning"
                  showIcon
                  message="无法读取 SSO 状态"
                  description="这不表示 SSO 已启用或已关闭，只表示这次读取失败。请刷新重试；若持续失败，查看服务端日志。"
                />
              ) : !sso.enabled ? (
                <Alert
                  type="info"
                  showIcon
                  message="未启用 SSO"
                  description="SSO 由环境变量配置（ONTOLOGY_SSO_ISSUER／ONTOLOGY_SSO_AUDIENCE／ONTOLOGY_SSO_SECRET），三项缺一即视为关闭。启用后在这里声明组到角色的映射。"
                />
              ) : (
                <>
                  <Alert
                    type="success"
                    showIcon
                    style={{ marginBottom: 16 }}
                    message={`SSO 已启用：身份由提供方断言，权限由平台决定（已映射 ${sso?.mappedGroups ?? 0} 个组）`}
                    description={
                      <>
                        <div>签发方：{sso?.issuer}　受众：{sso?.audience}　算法：{sso?.algorithm}（取自配置，绝不取自令牌头）</div>
                        <div>组声明：{sso?.groupClaim}　用户标识声明：{sso?.usernameClaim}</div>
                        <div>{sso?.note}</div>
                      </>
                    }
                  />
                  {ssoMappings.length === 0 && (
                    <Alert
                      type="warning"
                      showIcon
                      style={{ marginBottom: 16 }}
                      message="尚未声明任何组映射：所有 SSO 登录都会被拒绝"
                      description="这是刻意设计——未映射的身份不给默认角色，否则目录里的每位员工都会被静默授予「读取平台可达的全部业务对象」。"
                    />
                  )}
                  <Table
                    dataSource={ssoMappings}
                    rowKey="providerGroup"
                    loading={loading}
                    pagination={false}
                    size="small"
                    columns={[
                      { title: '提供方组', dataIndex: 'providerGroup', key: 'providerGroup' },
                      { title: '平台角色', dataIndex: 'roleCode', key: 'roleCode', render: (role: string) => <Tag color="blue">{role}</Tag> },
                      { title: '备注', dataIndex: 'note', key: 'note' },
                      {
                        title: '操作',
                        key: 'actions',
                        width: 100,
                        render: (_: unknown, row: SsoGroupMapping) => (
                          <Popconfirm title="移除该组映射？未映射的组将无法登录。" onConfirm={() => handleRemoveSso(row.providerGroup)}>
                            <Button type="link" danger>
                              移除
                            </Button>
                          </Popconfirm>
                        ),
                      },
                    ]}
                  />
                </>
              )}
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

      <Modal
        title="声明组映射"
        open={ssoModalOpen}
        onCancel={() => setSsoModalOpen(false)}
        onOk={() => ssoForm.submit()}
        width={480}
        destroyOnClose
      >
        <Form form={ssoForm} layout="vertical" onFinish={handleDeclareSso}>
          <Form.Item
            name="providerGroup"
            label="提供方组"
            rules={[{ required: true, message: '请填写提供方组名' }]}
            extra="取自令牌里的组声明，需与提供方完全一致。"
          >
            <Input placeholder="如 engineering" autoFocus />
          </Form.Item>
          <Form.Item name="roleCode" label="平台角色" rules={[{ required: true, message: '请选择角色' }]}>
            <Select options={roles.map((role) => ({ value: role.code, label: `${role.name}（${role.code}）` }))} />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input.TextArea rows={2} placeholder="为什么这个组对应这个角色" />
          </Form.Item>
        </Form>
      </Modal>

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
