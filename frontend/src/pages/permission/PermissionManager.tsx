import React, { useEffect, useState } from 'react';
import { ONTOLOGY_STATUS } from '../../i18n/labels';
import { useLabel, useT } from '../../i18n/locale';
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
  const label = useLabel();
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
  const t = useT();

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
      message.error(requestErrorMessage(error, t('permission.loadFailed')));
    }
    setLoading(false);
  };

  useEffect(() => { loadAll(); }, []);

  const handleCreateRole = async (values: any) => {
    try {
      await permissionApi.createRole(values);
      message.success(t('permission.roleCreated'));
      setRoleModalOpen(false);
      roleForm.resetFields();
      loadAll();
    } catch (e: any) {
      message.error(requestErrorMessage(e, t('permission.createFailed')));
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
      message.success(t('permission.policySaved'));
      setPolicyModalOpen(false);
      policyForm.resetFields();
      loadAll();
    } catch (e: any) {
      message.error(requestErrorMessage(e, t('permission.saveFailed')));
    }
  };

  const handleReview = async (logId: number, decision: string) => {
    try {
      await toolApi.reviewExecution(logId, { reviewer: 'admin', decision });
      message.success(decision === 'approved' ? t('permission.reviewApproved') : t('permission.reviewRejected'));
      loadAll();
    } catch (error) {
      message.error(requestErrorMessage(error, t('permission.reviewFailed')));
    }
  };

  const roleColumns = [
    { title: t('permission.code'), dataIndex: 'code', key: 'code', render: (v: string) => <Tag>{v}</Tag> },
    { title: t('permission.name'), dataIndex: 'name', key: 'name' },
    { title: t('permission.description'), dataIndex: 'description', key: 'description' },
    { title: t('permission.systemRole'), dataIndex: 'isSystem', key: 'isSystem', render: (v: number) => v ? <Tag color="blue">{t('permission.yes')}</Tag> : '-' },
  ];

  const policyColumns = [
    { title: t('permission.role'), dataIndex: 'roleName', key: 'roleName', render: (_: string, r: PermissionPolicy) => <Tag>{r.roleCode || r.roleId}</Tag> },
    { title: t('permission.object'), dataIndex: 'objectCode', key: 'objectCode', render: (v: string) => <Tag color="purple">{v}</Tag> },
    {
      title: t('permission.read'), dataIndex: 'canRead', key: 'canRead',
      render: (v: number) => v ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : <CloseCircleOutlined style={{ color: '#ccc' }} />,
    },
    {
      title: t('permission.write'), dataIndex: 'canWrite', key: 'canWrite',
      render: (v: number) => v ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : <CloseCircleOutlined style={{ color: '#ccc' }} />,
    },
    {
      title: t('permission.execute'), dataIndex: 'canExecute', key: 'canExecute',
      render: (v: number) => v ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : <CloseCircleOutlined style={{ color: '#ccc' }} />,
    },
    {
      title: t('permission.delete'), dataIndex: 'canDelete', key: 'canDelete',
      render: (v: number) => v ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : <CloseCircleOutlined style={{ color: '#ccc' }} />,
    },
    { title: t('permission.description'), dataIndex: 'description', key: 'description' },
  ];

  const toolColumns = [
    { title: t('permission.code'), dataIndex: 'code', key: 'code', render: (v: string) => <Tag>{v}</Tag> },
    { title: t('permission.name'), dataIndex: 'name', key: 'name' },
    { title: t('permission.type'), dataIndex: 'toolType', key: 'toolType', render: (v: string) => <Tag color={v === 'mutation' ? 'red' : 'blue'}>{v}</Tag> },
    { title: t('permission.riskLevel'), dataIndex: 'riskLevel', key: 'riskLevel', render: (v: string) => {
      const color = v === 'high' ? 'red' : v === 'medium' ? 'orange' : 'green';
      return <Tag color={color}>{v}</Tag>;
    }},
    { title: t('permission.requiresReview'), dataIndex: 'requiresReview', key: 'requiresReview', render: (v: number) => v ? <Tag color="warning">{t('permission.yes')}</Tag> : '-' },
    { title: t('permission.status'), dataIndex: 'status', key: 'status', render: (v: string) => label(ONTOLOGY_STATUS, v) },
  ];

  const reviewColumns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: t('permission.tool'), dataIndex: 'toolCode', key: 'toolCode', render: (v: string) => <Tag>{v}</Tag> },
    { title: t('permission.role'), dataIndex: 'agentRole', key: 'agentRole' },
    { title: t('permission.object'), dataIndex: 'objectCode', key: 'objectCode' },
    { title: t('permission.instance'), dataIndex: 'instanceId', key: 'instanceId' },
    { title: t('permission.status'), dataIndex: 'status', key: 'status', render: (v: string) => <Tag color={v === 'success' ? 'green' : 'red'}>{v}</Tag> },
    { title: t('permission.duration'), dataIndex: 'durationMs', key: 'durationMs', render: (v: number) => `${v}ms` },
    { title: t('permission.createdAt'), dataIndex: 'createdAt', key: 'createdAt' },
    {
      title: t('permission.actions'), key: 'action', width: 160,
      render: (_: any, record: ToolExecutionLog) => (
        <Space>
          <Button size="small" type="primary" onClick={() => handleReview(record.id, 'approved')}>{t('permission.approve')}</Button>
          <Popconfirm title={t('permission.confirmReject')} onConfirm={() => handleReview(record.id, 'rejected')}>
            <Button size="small" danger>{t('permission.reject')}</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const handleDeclareSso = async (values: { providerGroup: string; roleCode: string; note?: string }) => {
    try {
      await ssoApi.declare(values.providerGroup.trim(), values.roleCode, values.note || '');
      message.success(t('permission.mappingDeclared'));
      setSsoModalOpen(false);
      ssoForm.resetFields();
      await loadAll();
    } catch (error) {
      // The server rejects an unknown role by name; discarding that would leave the admin
      // guessing which role codes exist.
      message.error(requestErrorMessage(error, t('permission.declareFailed')));
    }
  };

  const handleRemoveSso = async (providerGroup: string) => {
    try {
      await ssoApi.remove(providerGroup);
      message.success(t('permission.mappingRemoved'));
      await loadAll();
    } catch (error) {
      message.error(requestErrorMessage(error, t('permission.removeFailed')));
    }
  };

  return (
    <div>
      <Tabs activeKey={tab} onChange={setTab} items={[
        {
          key: 'roles',
          label: t('permission.rolesTab'),
          children: (
            <Card title={t('permission.roleList')} extra={<Button icon={<PlusOutlined />} onClick={() => setRoleModalOpen(true)}>{t('permission.newRole')}</Button>}>
              <Table dataSource={roles} columns={roleColumns} rowKey="id" loading={loading} pagination={false} size="small" />
            </Card>
          ),
        },
        {
          key: 'policies',
          label: t('permission.policiesTab'),
          children: (
            <Card title={t('permission.policiesTab')} extra={<Button icon={<PlusOutlined />} onClick={() => setPolicyModalOpen(true)}>{t('permission.newPolicy')}</Button>}>
              <Table dataSource={policies} columns={policyColumns} rowKey="id" loading={loading} pagination={false} size="small" />
            </Card>
          ),
        },
        {
          key: 'tools',
          label: t('permission.toolsTab'),
          children: (
            <Card title={t('permission.registeredTools')}>
              <Table dataSource={tools} columns={toolColumns} rowKey="id" loading={loading} pagination={false} size="small" />
            </Card>
          ),
        },
        {
          key: 'sso',
          label: t('permission.ssoTab'),
          children: (
            <Card
              title={t('permission.ssoCard')}
              extra={
                <Button icon={<PlusOutlined />} onClick={() => setSsoModalOpen(true)} disabled={!sso?.enabled}>
                  {t('permission.declareMapping')}
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
                  message={t('permission.ssoUnknownTitle')}
                  description={t('permission.ssoUnknownDesc')}
                />
              ) : !sso.enabled ? (
                <Alert
                  type="info"
                  showIcon
                  message={t('permission.ssoDisabledTitle')}
                  description={t('permission.ssoDisabledDesc')}
                />
              ) : (
                <>
                  <Alert
                    type="success"
                    showIcon
                    style={{ marginBottom: 16 }}
                    message={t('permission.ssoEnabledTitle', { count: sso?.mappedGroups ?? 0 })}
                    description={
                      <>
                        <div>{t('permission.ssoIssuerLine', { issuer: sso?.issuer ?? '', audience: sso?.audience ?? '', algorithm: sso?.algorithm ?? '' })}</div>
                        <div>{t('permission.ssoClaimsLine', { group: sso?.groupClaim ?? '', username: sso?.usernameClaim ?? '' })}</div>
                        <div>{sso?.note}</div>
                      </>
                    }
                  />
                  {ssoMappings.length === 0 && (
                    <Alert
                      type="warning"
                      showIcon
                      style={{ marginBottom: 16 }}
                      message={t('permission.noMappingsTitle')}
                      description={t('permission.noMappingsDesc')}
                    />
                  )}
                  <Table
                    dataSource={ssoMappings}
                    rowKey="providerGroup"
                    loading={loading}
                    pagination={false}
                    size="small"
                    columns={[
                      { title: t('permission.providerGroup'), dataIndex: 'providerGroup', key: 'providerGroup' },
                      { title: t('permission.platformRole'), dataIndex: 'roleCode', key: 'roleCode', render: (role: string) => <Tag color="blue">{role}</Tag> },
                      { title: t('permission.note'), dataIndex: 'note', key: 'note' },
                      {
                        title: t('permission.actions'),
                        key: 'actions',
                        width: 100,
                        render: (_: unknown, row: SsoGroupMapping) => (
                          <Popconfirm title={t('permission.confirmRemoveMapping')} onConfirm={() => handleRemoveSso(row.providerGroup)}>
                            <Button type="link" danger>
                              {t('permission.remove')}
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
          label: <Badge count={pendingReviews.length} size="small">{t('permission.pendingReviews')}</Badge>,
          children: (
            <Card title={t('permission.pendingExecutions')}>
              <Table dataSource={pendingReviews} columns={reviewColumns} rowKey="id" loading={loading} pagination={false} size="small" />
            </Card>
          ),
        },
      ]} />

      <Modal
        title={t('permission.declareMapping')}
        open={ssoModalOpen}
        onCancel={() => setSsoModalOpen(false)}
        onOk={() => ssoForm.submit()}
        width={480}
        destroyOnClose
      >
        <Form form={ssoForm} layout="vertical" onFinish={handleDeclareSso}>
          <Form.Item
            name="providerGroup"
            label={t('permission.providerGroup')}
            rules={[{ required: true, message: t('permission.providerGroupRequired') }]}
            extra={t('permission.providerGroupHint')}
          >
            <Input placeholder={t('permission.providerGroupExample')} autoFocus />
          </Form.Item>
          <Form.Item name="roleCode" label={t('permission.platformRole')} rules={[{ required: true, message: t('permission.roleRequired') }]}>
            <Select options={roles.map((role) => ({ value: role.code, label: t('permission.roleOption', { name: role.name, code: role.code }) }))} />
          </Form.Item>
          <Form.Item name="note" label={t('permission.note')}>
            <Input.TextArea rows={2} placeholder={t('permission.notePlaceholder')} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title={t('permission.newRole')} open={roleModalOpen} onCancel={() => setRoleModalOpen(false)} onOk={() => roleForm.submit()} width={450}>
        <Form form={roleForm} layout="vertical" onFinish={handleCreateRole}>
          <Form.Item name="code" label={t('permission.roleCode')} rules={[{ required: true }]}>
            <Input placeholder={t('permission.roleCodeExample')} />
          </Form.Item>
          <Form.Item name="name" label={t('permission.roleName')} rules={[{ required: true }]}>
            <Input placeholder={t('permission.roleNameExample')} />
          </Form.Item>
          <Form.Item name="description" label={t('permission.description')}>
            <Input.TextArea placeholder={t('permission.optional')} />
          </Form.Item>
          <Form.Item name="isSystem" label={t('permission.systemRole')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title={t('permission.newPolicyTitle')} open={policyModalOpen} onCancel={() => setPolicyModalOpen(false)} onOk={() => policyForm.submit()} width={500}>
        <Form form={policyForm} layout="vertical" onFinish={handleUpsertPolicy}>
          <Form.Item name="roleId" label={t('permission.role')} rules={[{ required: true }]}>
            <Select placeholder={t('permission.selectRole')}>
              {roles.map(r => <Select.Option key={r.id} value={r.id}>{r.name} ({r.code})</Select.Option>)}
            </Select>
          </Form.Item>
          <Form.Item name="objectCode" label={t('permission.objectCode')} rules={[{ required: true }]}>
            <Input placeholder={t('permission.objectCodeExample')} />
          </Form.Item>
          <Space>
            <Form.Item name="canRead" label={t('permission.read')} valuePropName="checked" initialValue={true}><Switch /></Form.Item>
            <Form.Item name="canWrite" label={t('permission.write')} valuePropName="checked"><Switch /></Form.Item>
            <Form.Item name="canExecute" label={t('permission.execute')} valuePropName="checked"><Switch /></Form.Item>
            <Form.Item name="canDelete" label={t('permission.delete')} valuePropName="checked"><Switch /></Form.Item>
          </Space>
          <Form.Item name="description" label={t('permission.description')}>
            <Input placeholder={t('permission.optional')} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default PermissionManager;
