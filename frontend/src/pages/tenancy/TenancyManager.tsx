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
import { useT } from '../../i18n/locale';
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
  const t = useT();
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
      setLoadError(requestErrorMessage(error, t('tenancy.loadTenantsFailed')));
    }
  }, [t]);

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
      setLoadError(requestErrorMessage(error, t('tenancy.loadDetailFailed')));
    } finally {
      setLoading(false);
    }
  }, [t]);

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

  const resourceText = (resource: string, fallback: string): string => {
    const translated = t(`tenancy.resource.${resource}` as never);
    return translated.startsWith('⟦') ? fallback : translated;
  };

  const handleCreate = async (values: { tenant: string }) => {
    setBusy(true);
    try {
      const created = await tenancyApi.create(values.tenant.trim());
      message.success(t('tenancy.createSuccess', { tenant: created.tenant, schema: created.schema }));
      setCreateOpen(false);
      createForm.resetFields();
      await loadTenants();
      setSelected(created.tenant);
    } catch (error) {
      message.error(requestErrorMessage(error, t('tenancy.createFailed')));
    } finally {
      setBusy(false);
    }
  };

  const handleSetQuota = async (values: { resource: string; limit: number | null; note?: string }) => {
    if (!selected || values.limit === null || values.limit === undefined) return;
    setBusy(true);
    try {
      await tenancyApi.setQuota(selected, values.resource, values.limit, values.note || '');
      message.success(t('tenancy.quotaSuccess'));
      setQuotaOpen(false);
      quotaForm.resetFields();
      await loadDetail(selected);
    } catch (error) {
      message.error(requestErrorMessage(error, t('tenancy.quotaFailed')));
    } finally {
      setBusy(false);
    }
  };

  const quotaRows = quotas
    ? Object.entries(quotas.resources).map(([resource, state]) => ({ resource, ...state }))
    : [];

  return (
    <div>
      <Title level={3}>{t('tenancy.title')}</Title>
      <Paragraph type="secondary">
        {t('tenancy.introBefore')}
        <Text strong>{t('tenancy.introOptional')}</Text>
        {t('tenancy.introAfter')}
      </Paragraph>

      {loadError && <Alert type="error" showIcon style={{ marginBottom: 16 }} message={t('tenancy.loadFailedTitle')} description={loadError} />}

      {tenants && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={t('tenancy.isolationModel', { model: tenants.isolationModel, database: tenants.dbType })}
        />
      )}

      <Card
        title={t('tenancy.tenantList')}
        style={{ marginBottom: 16 }}
        extra={
          <Button type="primary" onClick={() => setCreateOpen(true)}>
            {t('tenancy.createTenant')}
          </Button>
        }
      >
        {tenants && tenants.items.length === 0 ? (
          <Empty description={t('tenancy.emptyTenants')} />
        ) : (
          <Table
            size="small"
            rowKey="tenant"
            loading={!tenants && !loadError}
            dataSource={tenants?.items ?? []}
            columns={[
              { title: t('tenancy.column.tenant'), dataIndex: 'tenant', key: 'tenant' },
              { title: 'schema', dataIndex: 'schema', key: 'schema' },
              {
                title: t('shell.common.actions'),
                key: 'actions',
                width: 140,
                render: (_: unknown, row: TenantSummary) => (
                  <Button type="link" onClick={() => setSelected(row.tenant)}>
                    {row.tenant === selected ? t('tenancy.selected') : t('tenancy.viewUsage')}
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
          <Card title={t('tenancy.usageTitle', { tenant: selected })} style={{ marginBottom: 16 }} loading={loading}>
            {statistics ? (
              <Descriptions size="small" column={2} bordered>
                <Descriptions.Item label="schema">{statistics.schema}</Descriptions.Item>
                <Descriptions.Item label={t('tenancy.totalRows')}>{statistics.totalRows}</Descriptions.Item>
                {Object.entries(statistics.tables).map(([table, count]) => (
                  <Descriptions.Item key={table} label={table}>
                    {count}
                  </Descriptions.Item>
                ))}
              </Descriptions>
            ) : (
              <Empty description={t('tenancy.noUsage')} />
            )}
          </Card>

          <Card
            title={t('tenancy.quotaTitle')}
            loading={loading}
            extra={
              <Button onClick={() => setQuotaOpen(true)} disabled={resources.length === 0}>
                {t('tenancy.declareQuota')}
              </Button>
            }
          >
            <Paragraph type="secondary" style={{ fontSize: 12 }}>
              {t('tenancy.quotaIntroBefore')}
              <Text strong>{t('tenancy.unlimited')}</Text>
              {t('tenancy.quotaIntroAfter')}
            </Paragraph>
            <Table
              size="small"
              rowKey="resource"
              dataSource={quotaRows}
              pagination={false}
              columns={[
                {
                  title: t('tenancy.resource'),
                  dataIndex: 'resource',
                  key: 'resource',
                  render: (resource: string, row: QuotaState & { resource: string }) => (
                    <Space direction="vertical" size={0}>
                      <Text strong>{resource}</Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {/* The resource code is a closed vocabulary; the server's Chinese
                            description is the fallback for one this build does not know. */}
                        {resourceText(row.resource, row.description)}
                      </Text>
                    </Space>
                  ),
                },
                { title: t('tenancy.countTable'), dataIndex: 'table', key: 'table', width: 160 },
                { title: t('tenancy.current'), dataIndex: 'current', key: 'current', width: 90 },
                {
                  title: t('tenancy.limit'),
                  dataIndex: 'limit',
                  key: 'limit',
                  width: 110,
                  render: (limit: number | null) =>
                    limit === null ? <Text type="secondary">{t('tenancy.unlimited')}</Text> : limit,
                },
                {
                  title: t('tenancy.remaining'),
                  dataIndex: 'remaining',
                  key: 'remaining',
                  width: 110,
                  render: (remaining: number | null, row: QuotaState & { resource: string }) =>
                    remaining === null ? (
                      <Text type="secondary">—</Text>
                    ) : row.exceeded ? (
                      <Tag color="red">{t('tenancy.exceeded')}</Tag>
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
        title={t('tenancy.createTenant')}
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
          message={t('tenancy.idempotentTitle')}
          description={t('tenancy.idempotentHint')}
        />
        <Form form={createForm} layout="vertical" onFinish={handleCreate}>
          <Form.Item
            name="tenant"
            label={t('tenancy.tenantIdLabel')}
            rules={[{ required: true, message: t('tenancy.tenantIdRequired') }]}
            extra={t('tenancy.tenantIdHint')}
          >
            <Input placeholder="acme" autoFocus />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t('tenancy.quotaModalTitle', { tenant: selected ?? '' })}
        open={quotaOpen}
        onCancel={() => setQuotaOpen(false)}
        onOk={() => quotaForm.submit()}
        confirmLoading={busy}
        destroyOnClose
      >
        <Form form={quotaForm} layout="vertical" onFinish={handleSetQuota}>
          <Form.Item name="resource" label={t('tenancy.resource')} rules={[{ required: true, message: t('tenancy.resourceRequired') }]}>
            <Select
              options={resources.map((item) => ({
                value: item.resource,
                label: t('tenancy.resourceOption', { resource: item.resource, table: item.table }),
              }))}
            />
          </Form.Item>
          <Form.Item
            name="limit"
            label={t('tenancy.limit')}
            rules={[{ required: true, message: t('tenancy.limitRequired') }]}
            extra={t('tenancy.limitHint')}
          >
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="note" label={t('tenancy.note')}>
            <Input.TextArea rows={2} placeholder={t('tenancy.notePlaceholder')} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default TenancyManager;
