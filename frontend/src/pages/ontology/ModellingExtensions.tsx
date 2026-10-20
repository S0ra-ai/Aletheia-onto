import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Empty, Form, Input, Modal, Select, Space, Table, Tag, Typography, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { ontologyApi, requestErrorMessage } from '../../api';
import { EVENT_CATEGORY } from '../../i18n/labels';
import { useLabel, useT } from '../../i18n/locale';
import type { BusinessObject, EventTypeDeclaration } from '../../types';

const { Text, Paragraph } = Typography;

interface Props {
  ontologyId: number;
  objects: BusinessObject[];
  /** A published or reviewing ontology refuses these declarations server-side. */
  readOnly: boolean;
}

/**
 * Declarations that describe how instances behave over time.
 *
 * Event types are the one this screen exists for. Recording an event whose code was never
 * declared is refused -- deliberately, so that «驳回», «拒绝» and «rejected» cannot become
 * three unrelated facts -- which means an instance's timeline stays empty on a fresh
 * deployment and there was no way from the console to change that. The instance drawer says
 * "declare an event type first"; this is where that happens.
 *
 * The split with the drawer is deliberate: declaring a *kind* of event is a modelling act
 * and belongs here, while recording that *this* instance was signed is an operational fact
 * and belongs beside the instance.
 */
const ModellingExtensions: React.FC<Props> = ({ ontologyId, objects, readOnly }) => {
  const label = useLabel();
  const t = useT();
  const [objectCode, setObjectCode] = useState<string | undefined>(objects[0]?.code);
  const [eventTypes, setEventTypes] = useState<EventTypeDeclaration[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setEventTypes(await ontologyApi.eventTypes(ontologyId));
    } catch (caught) {
      setEventTypes([]);
      setError(requestErrorMessage(caught, t('ontology.eventTypesLoadFailed')));
    } finally {
      setLoading(false);
    }
  }, [ontologyId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setObjectCode((current) => (objects.some((item) => item.code === current) ? current : objects[0]?.code));
  }, [objects]);

  const handleDeclare = async (values: {
    code: string;
    name: string;
    category: string;
    payloadFields?: string;
    description?: string;
  }) => {
    if (!objectCode) return;
    setSaving(true);
    try {
      await ontologyApi.declareEventType(ontologyId, objectCode, {
        code: values.code.trim(),
        name: values.name.trim(),
        category: values.category,
        // A comma-separated string in the form, an array on the wire. The server treats the
        // list as advisory and reports a payload that omits a declared field, so an empty
        // list is a legitimate answer meaning "no expectation stated".
        payloadFields: (values.payloadFields || '')
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
        description: values.description?.trim() || '',
      });
      message.success(t('ontology.eventTypeDeclared'));
      setOpen(false);
      form.resetFields();
      await load();
    } catch (caught) {
      message.error(requestErrorMessage(caught, t('ontology.declareFailed')));
    } finally {
      setSaving(false);
    }
  };

  const objectEventTypes = eventTypes.filter((item) => !objectCode || item.objectCode === objectCode);

  return (
    <Card
      size="small"
      title={t('ontology.eventTypes')}
      extra={
        <Button type="primary" icon={<PlusOutlined />} disabled={readOnly || !objectCode} onClick={() => setOpen(true)}>
          {t('ontology.declareEventType')}
        </Button>
      }
    >
      <Paragraph type="secondary" style={{ fontSize: 12 }}>
        {t('ontology.eventTypesIntro')}
      </Paragraph>

      {readOnly && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          title={t('ontology.readOnlyTitle')}
          description={t('ontology.readOnlyDetail')}
        />
      )}
      {error && <Alert type="error" showIcon style={{ marginBottom: 12 }} title={t('ontology.eventTypesLoadFailed')} description={error} />}

      <Space style={{ marginBottom: 12 }}>
        <Select
          style={{ width: 240 }}
          placeholder={t('ontology.selectObject')}
          value={objectCode}
          onChange={setObjectCode}
          options={objects.map((item) => ({ value: item.code, label: `${item.name}（${item.code}）` }))}
        />
        <Text type="secondary" style={{ fontSize: 12 }}>
          {t('ontology.declaredCount', { total: eventTypes.length, here: objectEventTypes.length })}
        </Text>
      </Space>

      <Table<EventTypeDeclaration>
        size="small"
        rowKey={(row) => `${row.objectCode}.${row.code}`}
        loading={loading}
        dataSource={objectEventTypes}
        pagination={false}
        columns={[
          {
            title: t('ontology.event'),
            key: 'event',
            render: (_: unknown, row) => (
              <Space orientation="vertical" size={0}>
                <Text strong>{row.name}</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {row.code}
                </Text>
              </Space>
            ),
          },
          { title: t('ontology.objects'), dataIndex: 'objectCode', key: 'objectCode', width: 140 },
          {
            // No fixed width, and that is a fix rather than a preference: at 110px the English
            // 「Business interaction」 tag was wider than its column and spilled over the next
            // one. A column sized for the shortest label in one language is a column that
            // breaks in the other -- the tag decides its own width and the table lays out
            // around it.
            title: t('ontology.category'),
            dataIndex: 'category',
            key: 'category',
            render: (category: string) => <Tag>{label(EVENT_CATEGORY, category)}</Tag>,
          },
          {
            title: t('ontology.payloadFields'),
            dataIndex: 'payloadFields',
            key: 'payloadFields',
            render: (fields: string[]) =>
              fields?.length ? (
                <Space wrap size={4}>
                  {fields.map((field) => (
                    <Tag key={field}>{field}</Tag>
                  ))}
                </Space>
              ) : (
                <Text type="secondary">{t('ontology.noExpectedFields')}</Text>
              ),
          },
          { title: t('ontology.note'), dataIndex: 'description', key: 'description', ellipsis: true },
        ]}
        locale={{ emptyText: <Empty description={t('ontology.noEventTypes')} /> }}
      />

      <Modal
        title={t('ontology.declareFor', { code: objectCode ?? '' })}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={saving}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={handleDeclare} initialValues={{ category: 'interaction' }}>
          <Form.Item
            name="code"
            label={t('ontology.eventCode')}
            rules={[
              { required: true, message: t('ontology.eventCodeRequired') },
              { pattern: /^[A-Za-z_][A-Za-z0-9_]*$/, message: t('ontology.identifierRule') },
            ]}
            extra={t('ontology.identifierHint')}
          >
            <Input placeholder="signed" autoFocus />
          </Form.Item>
          <Form.Item name="name" label={t('ontology.name')} rules={[{ required: true, message: t('ontology.nameRequired') }]}>
            <Input placeholder={t('ontology.eventNamePlaceholder')} />
          </Form.Item>
          <Form.Item name="category" label={t('ontology.category')} rules={[{ required: true }]}>
            <Select options={Object.entries(EVENT_CATEGORY).map(([value]) => ({ value, label: label(EVENT_CATEGORY, value) }))} />
          </Form.Item>
          <Form.Item
            name="payloadFields"
            label={t('ontology.payloadFields')}
            extra={t('ontology.payloadHint')}
          >
            <Input placeholder="party, signedAt" />
          </Form.Item>
          <Form.Item name="description" label={t('ontology.note')}>
            <Input.TextArea rows={2} placeholder={t('ontology.eventDescriptionPlaceholder')} />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
};

export default ModellingExtensions;
