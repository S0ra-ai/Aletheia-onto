import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { tenancyApi, requestErrorMessage } from '../../api';
import type {
  QuotaResource,
  QuotaState,
  TenantList,
  TenantStatistics,
  TenantSummary,
  TenantQuotas,
} from '../../types';

const { Title, Paragraph, Text } = Typography;

/**
 * Tenants, their usage and their declared limits.
 *
 * Multi-tenancy is a headline capability of this platform and had no screen: seven endpoints,
 * no consumer. Provisioning, quota declaration and the isolation check after provisioning all
 * required curl.
 *
 * Two facts the page leads with, because both are easy to misread as faults:
 * multi-tenancy is **opt-in**, so an empty list on a single-tenant deployment is the expected
 * answer; and a resource with no declared limit is **unlimited**, which is why `remaining` is
 * absent rather than a large number.
 */
const TenancyManager: React.FC = () => {
  const [tenants, setTenants] = useState<TenantList | null>(null);
  const [selected, setSelected] = useState<string | undefined>();
  const [statistics, setStatistics] = useState<TenantStatistics | null>(null);
  const [quotas, setQuotas] = useState<TenantQuotas | null>(null);
  const [resources, setResources] = useState<QuotaResource[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [quotaOpen, setQuotaOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [createForm] = Form.useForm();
  const [quotaForm] = Form.useForm();

  const loadTenants = useCallback(async () => {
    setLoadError('');
    try {
      const result = await tenancyApi.list();
      setTenants(result);
      setSelected((current) =>
        current && result.items.some((item) => item.tenant === current) ? current : result.items[0]?.tenant,
      );
    } catch (error) {
      setTenants(null);
      setLoadError(requestErrorMessage(error, '获取租户列表失败'));
    }
  }, []);

  const loadDetail = useCallback(async (tenant: string) => {
    setLoading(true);
    setLoadError('');
    try {
      const [stats, quotaReport] = await Promise.all([
        tenancyApi.statistics(tenant),
        tenancyApi.quotas(tenant),
      ]);
      setStatistics(stats);
      setQuotas(quotaReport);
    } catch (error) {
      setStatistics(null);
      setQuotas(null);
      setLoadError(requestErrorMessage(error, '读取租户信息失败'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTenants();
    tenancyApi
      .quotaResources()
      .then(setResources)
      .catch(() => undefined);
  }, [loadTenants]);

  useEffect(() => {
    if (selected) void loadDetail(selected);
  }, [selected, loadDetail]);

  const handleCreate = async (values: { tenant: string }) => {
    setBusy(true);
    try {
      const created = await tenancyApi.create(values.tenant.trim());
      message.success(`租户 ${created.tenant} 已开通，schema：${created.schema}`);
      setCreateOpen(false);
      createForm.resetFields();
      await loadTenants();
      setSelected(created.tenant);
    } catch (error) {
      message.error(requestErrorMessage(error, '开通租户失败'));
    } finally {
      setBusy(false);
    }
  };

  const handleSetQuota = async (values: { resource: string; limit: number | null; note?: string }) => {
    if (!selected || values.limit === null || values.limit === undefined) return;
    setBusy(true);
    try {
      await tenancyApi.setQuota(selected, values.resource, values.limit, values.note || '');
      message.success('配额已声明。配额存放在基础库，租户无法自行修改。');
      setQuotaOpen(false);
      quotaForm.resetFields();
      await loadDetail(selected);
    } catch (error) {
      message.error(requestErrorMessage(error, '声明配额失败'));
    } finally {
      setBusy(false);
    }
  };

  const quotaRows = quotas
    ? Object.entries(quotas.resources).map(([resource, state]) => ({ resource, ...state }))
    : [];

  return (
    <div>
      <Title level={3}>租户管理</Title>
      <Paragraph type="secondary">
        多租户为<Text strong>可选</Text>能力：单租户部署下这里为空是预期结果，不是故障。
        每租户独立 schema，关键表另带 tenant_id 作为双保险；配额存放在基础库而非租户库——
        存在租户库里的配额是租户可以自己改的配额。
      </Paragraph>

      {loadError && <Alert type="error" showIcon style={{ marginBottom: 16 }} message="读取失败" description={loadError} />}

      {tenants && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={`隔离模型：${tenants.isolationModel}（平台库：${tenants.dbType}）`}
        />
      )}

      <Card
        title="租户列表"
        style={{ marginBottom: 16 }}
        extra={
          <Button type="primary" onClick={() => setCreateOpen(true)}>
            开通租户
          </Button>
        }
      >
        {tenants && tenants.items.length === 0 ? (
          <Empty description="当前部署未开通任何租户（单租户模式）" />
        ) : (
          <Table
            size="small"
            rowKey="tenant"
            loading={!tenants && !loadError}
            dataSource={tenants?.items ?? []}
            columns={[
              { title: '租户', dataIndex: 'tenant', key: 'tenant' },
              { title: 'schema', dataIndex: 'schema', key: 'schema' },
              {
                title: '操作',
                key: 'actions',
                width: 140,
                render: (_: unknown, row: TenantSummary) => (
                  <Button type="link" onClick={() => setSelected(row.tenant)}>
                    {row.tenant === selected ? '已选中' : '查看用量与配额'}
                  </Button>
                ),
              },
            ]}
            pagination={false}
          />
        )}
      </Card>

      {selected && (
        <>
          <Card title={`资源用量：${selected}`} style={{ marginBottom: 16 }} loading={loading}>
            {statistics ? (
              <Descriptions size="small" column={2} bordered>
                <Descriptions.Item label="schema">{statistics.schema}</Descriptions.Item>
                <Descriptions.Item label="总行数">{statistics.totalRows}</Descriptions.Item>
                {Object.entries(statistics.tables).map(([table, count]) => (
                  <Descriptions.Item key={table} label={table}>
                    {count}
                  </Descriptions.Item>
                ))}
              </Descriptions>
            ) : (
              <Empty description="暂无用量数据" />
            )}
          </Card>

          <Card
            title="配额"
            loading={loading}
            extra={
              <Button onClick={() => setQuotaOpen(true)} disabled={resources.length === 0}>
                声明配额
              </Button>
            }
          >
            <Paragraph type="secondary" style={{ fontSize: 12 }}>
              未声明配额的资源为<Text strong>不限量</Text>（而不是 0）——后者会让既有部署在这个特性上线的瞬间停止接受写入。
              用量按真实行数统计，不维护计数器。
            </Paragraph>
            <Table
              size="small"
              rowKey="resource"
              dataSource={quotaRows}
              pagination={false}
              columns={[
                {
                  title: '资源',
                  dataIndex: 'resource',
                  key: 'resource',
                  render: (resource: string, row: QuotaState & { resource: string }) => (
                    <Space direction="vertical" size={0}>
                      <Text strong>{resource}</Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {row.description}
                      </Text>
                    </Space>
                  ),
                },
                { title: '计数表', dataIndex: 'table', key: 'table', width: 160 },
                { title: '当前', dataIndex: 'current', key: 'current', width: 90 },
                {
                  title: '上限',
                  dataIndex: 'limit',
                  key: 'limit',
                  width: 110,
                  render: (limit: number | null) =>
                    limit === null ? <Text type="secondary">不限量</Text> : limit,
                },
                {
                  title: '剩余',
                  dataIndex: 'remaining',
                  key: 'remaining',
                  width: 110,
                  render: (remaining: number | null, row: QuotaState & { resource: string }) =>
                    remaining === null ? (
                      <Text type="secondary">—</Text>
                    ) : row.exceeded ? (
                      <Tag color="red">已超出</Tag>
                    ) : (
                      remaining
                    ),
                },
              ]}
            />
          </Card>
        </>
      )}

      <Modal
        title="开通租户"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => createForm.submit()}
        confirmLoading={busy}
        destroyOnClose
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="开通是幂等的"
          description="重复执行不会破坏已有数据，因此可以放心地把它写进部署流程。"
        />
        <Form form={createForm} layout="vertical" onFinish={handleCreate}>
          <Form.Item
            name="tenant"
            label="租户标识"
            rules={[{ required: true, message: '请填写租户标识' }]}
            extra="用作 schema 名，请使用字母、数字与下划线。"
          >
            <Input placeholder="acme" autoFocus />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`为 ${selected} 声明配额`}
        open={quotaOpen}
        onCancel={() => setQuotaOpen(false)}
        onOk={() => quotaForm.submit()}
        confirmLoading={busy}
        destroyOnClose
      >
        <Form form={quotaForm} layout="vertical" onFinish={handleSetQuota}>
          <Form.Item name="resource" label="资源" rules={[{ required: true, message: '请选择资源' }]}>
            <Select
              options={resources.map((item) => ({
                value: item.resource,
                label: `${item.resource}（计数表 ${item.table}）`,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="limit"
            label="上限"
            rules={[{ required: true, message: '请填写上限' }]}
            extra="设置为 0 表示不允许创建该类数据；留空不适用于本表单——不限量是「不声明」的结果。"
          >
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input.TextArea rows={2} placeholder="为什么是这个数字" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default TenancyManager;
