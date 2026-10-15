import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Empty, Form, Input, Modal, Select, Space, Table, Tag, Typography, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { ontologyApi, requestErrorMessage } from '../../api';
import { EVENT_CATEGORY, label } from '../../i18n/labels';
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
      setError(requestErrorMessage(caught, '读取事件类型失败'));
    } finally {
      setLoading(false);
    }
  }, [ontologyId]);

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
      message.success('事件类型已声明');
      setOpen(false);
      form.resetFields();
      await load();
    } catch (caught) {
      message.error(requestErrorMessage(caught, '声明事件类型失败'));
    } finally {
      setSaving(false);
    }
  };

  const objectEventTypes = eventTypes.filter((item) => !objectCode || item.objectCode === objectCode);

  return (
    <Card
      size="small"
      title="事件类型"
      extra={
        <Button type="primary" icon={<PlusOutlined />} disabled={readOnly || !objectCode} onClick={() => setOpen(true)}>
          声明事件类型
        </Button>
      }
    >
      <Paragraph type="secondary" style={{ fontSize: 12 }}>
        事件必须声明类型后才能记录：不存在「先记下来，以后再分类」——
        «驳回»、«拒绝» 与 «rejected» 一旦各记各的，历史就不再可检索。
        记录某个实例的事件在「对象浏览」的实例解释里做。
      </Paragraph>

      {readOnly && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="本体已发布或正在审核，不能修改事件定义"
          description="这是刻意设计：已发布的模型不应在无人察觉时改变含义。要改请先派生新版本。"
        />
      )}
      {error && <Alert type="error" showIcon style={{ marginBottom: 12 }} message="读取事件类型失败" description={error} />}

      <Space style={{ marginBottom: 12 }}>
        <Select
          style={{ width: 240 }}
          placeholder="选择业务对象"
          value={objectCode}
          onChange={setObjectCode}
          options={objects.map((item) => ({ value: item.code, label: `${item.name}（${item.code}）` }))}
        />
        <Text type="secondary" style={{ fontSize: 12 }}>
          共声明 {eventTypes.length} 种，其中本对象 {objectEventTypes.length} 种
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
            title: '事件',
            key: 'event',
            render: (_: unknown, row) => (
              <Space direction="vertical" size={0}>
                <Text strong>{row.name}</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {row.code}
                </Text>
              </Space>
            ),
          },
          { title: '业务对象', dataIndex: 'objectCode', key: 'objectCode', width: 140 },
          {
            title: '类别',
            dataIndex: 'category',
            key: 'category',
            width: 110,
            render: (category: string) => <Tag>{label(EVENT_CATEGORY, category)}</Tag>,
          },
          {
            title: '载荷字段',
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
                <Text type="secondary">未声明预期字段</Text>
              ),
          },
          { title: '说明', dataIndex: 'description', key: 'description', ellipsis: true },
        ]}
        locale={{ emptyText: <Empty description="该对象尚未声明任何事件类型，因此无法记录事件" /> }}
      />

      <Modal
        title={`为 ${objectCode ?? ''} 声明事件类型`}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={saving}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={handleDeclare} initialValues={{ category: 'interaction' }}>
          <Form.Item
            name="code"
            label="事件编码"
            rules={[
              { required: true, message: '请填写事件编码' },
              { pattern: /^[A-Za-z_][A-Za-z0-9_]*$/, message: '需为合法标识符：字母或下划线开头，只含字母、数字、下划线' },
            ]}
            extra="会进入规则表达式与查询条件，因此限制为标识符。已存在的编码会被更新而非重复创建。"
          >
            <Input placeholder="signed" autoFocus />
          </Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请填写名称' }]}>
            <Input placeholder="合同签订" />
          </Form.Item>
          <Form.Item name="category" label="类别" rules={[{ required: true }]}>
            <Select options={Object.entries(EVENT_CATEGORY).map(([value, text]) => ({ value, label: text }))} />
          </Form.Item>
          <Form.Item
            name="payloadFields"
            label="载荷字段"
            extra="可选，逗号分隔。它是对生产方的期望而非校验：载荷缺少这些字段时平台会在事件上标注，而不是拒绝写入。"
          >
            <Input placeholder="party, signedAt" />
          </Form.Item>
          <Form.Item name="description" label="说明">
            <Input.TextArea rows={2} placeholder="这个事件代表业务上发生了什么" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
};

export default ModellingExtensions;
