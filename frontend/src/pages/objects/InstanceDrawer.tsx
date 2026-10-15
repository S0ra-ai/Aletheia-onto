import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Descriptions, Drawer, Empty, Form, Input, Modal, Select, Space, Table, Tag, Typography, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { ontologyApi, requestErrorMessage, semanticApi } from '../../api';
import { EVENT_CATEGORY, label } from '../../i18n/labels';
import type {
  EventTypeDeclaration,
  InstanceAttributeVersion,
  InstanceEvent,
  InstanceExplainAggregate,
  InstanceExplainAttribute,
  InstanceExplainResult,
  InstanceVersionsResult,
} from '../../types';

const { Text, Paragraph } = Typography;

interface Props {
  ontologyId: number;
  objectCode: string;
  instanceId: string;
  onClose: () => void;
}

/**
 * One instance, explained.
 *
 * This is the platform's central claim rendered as a screen: a business object is consumed
 * through one stable interface, and every conclusion about it can be traced back to the
 * column it was read from, the events that produced it, and the values it held before.
 *
 * Three endpoints feed it, and the difference between them is the point:
 *
 * - `explain` answers "what is this, and where did each value come from" -- it names the
 *   source column behind every attribute, which is what makes the mapping inspectable
 *   rather than asserted.
 * - `events` answers "how did it get that way". It is the full history; `explain` embeds
 *   only the twenty most recent, because an explanation is read interactively.
 * - `versions` answers "what did it say last month". Rule verdicts can be produced as of a
 *   past time, so a reader who cannot see the old values cannot check the old verdict.
 *
 * The drawer is deliberately read-only. Every mutation these endpoints support is a
 * declared modelling act -- recording an event type, closing a value's validity -- and
 * belongs on a screen that says what it is doing, not on one a user opens to look.
 */
const InstanceDrawer: React.FC<Props> = ({ ontologyId, objectCode, instanceId, onClose }) => {
  const [explain, setExplain] = useState<InstanceExplainResult | null>(null);
  const [events, setEvents] = useState<InstanceEvent[] | null>(null);
  const [versions, setVersions] = useState<InstanceVersionsResult | null>(null);
  const [eventTypes, setEventTypes] = useState<EventTypeDeclaration[]>([]);
  const [explainError, setExplainError] = useState('');
  const [eventsError, setEventsError] = useState('');
  const [versionsError, setVersionsError] = useState('');
  const [loading, setLoading] = useState(true);
  const [recordOpen, setRecordOpen] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordForm] = Form.useForm();

  const loadEvents = useCallback(async () => {
    try {
      const result = await semanticApi.instanceEvents(ontologyId, objectCode, instanceId);
      setEvents(result.items ?? []);
    } catch (error) {
      setEvents(null);
      setEventsError(requestErrorMessage(error, '读取事件历史失败'));
    }
  }, [ontologyId, objectCode, instanceId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setExplain(null);
    setEvents(null);
    setVersions(null);
    setExplainError('');
    setEventsError('');
    setVersionsError('');

    // Each of the three fails on its own. A failure in one must not blank the other two:
    // "the value history could not be read" and "this instance has no history" are
    // different answers, and only one of them is somebody else's outage.
    semanticApi
      .explain(objectCode, instanceId, ontologyId)
      .then((result) => !cancelled && setExplain(result))
      .catch((error) => !cancelled && setExplainError(requestErrorMessage(error, '读取实例解释失败')))
      .finally(() => !cancelled && setLoading(false));
    semanticApi
      .instanceEvents(ontologyId, objectCode, instanceId)
      .then((result) => !cancelled && setEvents(result.items ?? []))
      .catch((error) => !cancelled && setEventsError(requestErrorMessage(error, '读取事件历史失败')));
    semanticApi
      .instanceVersions(ontologyId, objectCode, instanceId)
      .then((result) => !cancelled && setVersions(result))
      .catch((error) => !cancelled && setVersionsError(requestErrorMessage(error, '读取取值沿革失败')));
    // Declared event codes, so recording offers only what the server will accept: an
    // undeclared code is refused, and a free-text box would turn that refusal into a
    // mysterious failure at submit time.
    ontologyApi
      .eventTypes(ontologyId, objectCode)
      .then((items) => !cancelled && setEventTypes(items ?? []))
      .catch(() => undefined);

    return () => {
      cancelled = true;
    };
  }, [ontologyId, objectCode, instanceId]);

  const handleRecord = async (values: { eventCode: string; occurredAt?: string; payload?: string }) => {
    setRecording(true);
    try {
      let payload: Record<string, unknown> = {};
      if (values.payload?.trim()) {
        try {
          payload = JSON.parse(values.payload);
        } catch {
          message.error('载荷必须是合法 JSON');
          return;
        }
      }
      await semanticApi.recordInstanceEvent(ontologyId, objectCode, instanceId, {
        eventCode: values.eventCode,
        payload,
        occurredAt: values.occurredAt?.trim() || '',
      });
      message.success('事件已记录');
      setRecordOpen(false);
      recordForm.resetFields();
      await loadEvents();
    } catch (error) {
      message.error(requestErrorMessage(error, '记录事件失败'));
    } finally {
      setRecording(false);
    }
  };

  const attributeColumns = [
    {
      title: '属性',
      key: 'attribute',
      render: (_: unknown, row: InstanceExplainAttribute) => (
        <Space direction="vertical" size={0}>
          <Space size={4}>
            <Text strong>{row.attributeName || row.attributeCode}</Text>
            {row.derived && <Tag color="purple">计算</Tag>}
            {row.fromHistory && <Tag color="blue">历史</Tag>}
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {row.attributeCode}
          </Text>
        </Space>
      ),
    },
    {
      title: '来源',
      key: 'source',
      width: 230,
      // A derived attribute has no column, and saying so is the explanation: the value was
      // computed from an expression, not read from anywhere. It used to be dropped from
      // this table entirely, because the query inner-joined the source column.
      render: (_: unknown, row: InstanceExplainAttribute) =>
        row.derived ? (
          <Space direction="vertical" size={0}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              由表达式计算
            </Text>
            <Text code style={{ fontSize: 12 }}>
              {row.derivedExpression}
            </Text>
          </Space>
        ) : row.sourceColumn ? (
          <Text code>{row.sourceColumn}</Text>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: '值',
      key: 'value',
      render: (_: unknown, row: InstanceExplainAttribute) => {
        if (row.error) {
          // A derived attribute that could not be computed makes rules referencing it fail
          // closed. Showing an empty cell here would hide that behind a blank.
          return <Text type="danger">无法计算：{row.error}</Text>;
        }
        if (row.value === null || row.value === undefined || row.value === '') {
          return <Text type="secondary">空值</Text>;
        }
        return (
          <Space size={4}>
            <Text>{String(row.value)}</Text>
            {row.stateName && <Tag color="green">{row.stateName}</Tag>}
          </Space>
        );
      },
    },
    {
      title: '单位',
      key: 'unit',
      width: 90,
      // A magnitude without its unit is not a value: 1200000 万元 and 1200000 元 differ by a
      // factor of ten thousand, and the explanation is where a reader decides which they are
      // looking at.
      render: (_: unknown, row: InstanceExplainAttribute) =>
        row.unitName ? <Tag>{row.unitName}</Tag> : <Text type="secondary">—</Text>,
    },
  ];

  const eventColumns = [
    { title: '时间', dataIndex: 'occurredAt', key: 'occurredAt', width: 180 },
    {
      title: '事件',
      key: 'event',
      render: (_: unknown, row: InstanceEvent) => (
        <Space direction="vertical" size={0}>
          <Text strong>{row.eventName || row.eventCode}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {row.eventCode}
          </Text>
        </Space>
      ),
    },
    {
      title: '类别',
      dataIndex: 'categoryLabel',
      key: 'categoryLabel',
      width: 110,
      render: (label: string) => (label ? <Tag>{label}</Tag> : <Text type="secondary">—</Text>),
    },
    { title: '操作者', dataIndex: 'actor', key: 'actor', width: 140 },
    {
      title: '载荷',
      dataIndex: 'payload',
      key: 'payload',
      render: (payload: Record<string, unknown>, row: InstanceEvent) =>
        Object.keys(payload ?? {}).length === 0 ? (
          <Text type="secondary">—</Text>
        ) : (
          <Space direction="vertical" size={0}>
            <Text code style={{ fontSize: 12 }}>
              {JSON.stringify(payload)}
            </Text>
            {/* The server checks the payload against the declared fields and says so when it
                does not match. Swallowing that would hide a producer that changed shape. */}
            {row.payloadWarning && <Text type="warning">{row.payloadWarning}</Text>}
          </Space>
        ),
    },
  ];

  const versionColumns = [
    {
      title: '属性',
      dataIndex: 'attributeCode',
      key: 'attributeCode',
      width: 200,
      render: (code: string) => <Text code>{code}</Text>,
    },
    { title: '取值', dataIndex: 'value', key: 'value' },
    {
      title: '生效区间',
      key: 'validity',
      width: 320,
      render: (_: unknown, row: InstanceAttributeVersion) => (
        <Text>
          {row.validFrom} → {row.validTo ?? <Text type="secondary">至今</Text>}
        </Text>
      ),
    },
    { title: '记录时间', dataIndex: 'recordedAt', key: 'recordedAt', width: 180 },
    { title: '记录人', dataIndex: 'actor', key: 'actor', width: 120 },
  ];

  return (
    <Drawer
      open
      width={880}
      onClose={onClose}
      title={explain ? `${explain.object.name || objectCode} · ${instanceId}` : `${objectCode} · ${instanceId}`}
    >
      {explainError && (
        <Alert type="error" showIcon style={{ marginBottom: 16 }} message="读取实例解释失败" description={explainError} />
      )}

      {explain && (
        <>
          <Descriptions size="small" column={2} bordered style={{ marginBottom: 16 }}>
            <Descriptions.Item label="本体">
              {explain.ontology.name} v{explain.ontology.version}
            </Descriptions.Item>
            <Descriptions.Item label="业务对象">
              {explain.object.name}（{explain.objectCode}）
            </Descriptions.Item>
            <Descriptions.Item label="来源表">{explain.source.table}</Descriptions.Item>
            <Descriptions.Item label="主键">{explain.source.primaryKey}</Descriptions.Item>
            {explain.ancestors.length > 0 && (
              <Descriptions.Item label="类型层级" span={2}>
                <Space wrap>
                  {explain.ancestors.map((ancestor) => (
                    <Tag key={ancestor}>{ancestor}</Tag>
                  ))}
                </Space>
                <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
                  这些类型的规则同样适用于本实例
                </Text>
              </Descriptions.Item>
            )}
          </Descriptions>

          <Alert type="info" showIcon style={{ marginBottom: 16 }} message={explain.explanation} />

          <Text strong>属性与来源</Text>
          <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
            每个值都列出它读自哪一列。列与属性对不上时，问题出在映射上而不是数据上。
          </Paragraph>
          <Table
            size="small"
            rowKey="attributeCode"
            dataSource={explain.attributes}
            columns={attributeColumns}
            pagination={false}
            loading={loading}
            style={{ marginBottom: 24 }}
          />

          {explain.aggregates.length > 0 && (
            <>
              <Text strong>聚合值</Text>
              <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
                规则可以直接按名称引用这些值。它们不属于本行的任何属性，而是对其他行的一次查询，
                所以单独列出——<Text strong>判定引用了某个聚合值，这里就必须看得到它</Text>。
              </Paragraph>
              <Table<InstanceExplainAggregate>
                size="small"
                rowKey="name"
                dataSource={explain.aggregates}
                pagination={false}
                style={{ marginBottom: 24 }}
                columns={[
                  {
                    title: '名称',
                    dataIndex: 'name',
                    key: 'name',
                    width: 180,
                    render: (name: string) => <Text code>{name}</Text>,
                  },
                  { title: '定义', dataIndex: 'definition', key: 'definition', ellipsis: true },
                  {
                    title: '值',
                    key: 'value',
                    width: 160,
                    render: (_: unknown, row: InstanceExplainAggregate) =>
                      row.error ? (
                        <Text type="danger">无法计算：{row.error}</Text>
                      ) : (
                        <Space size={4}>
                          <Text>{row.value === null || row.value === undefined ? '空值' : String(row.value)}</Text>
                          {/* A truncated aggregate is a partial answer; a verdict resting on
                              it was reached on partial data, and the reader has to know. */}
                          {row.truncated && <Tag color="orange">已达取数上限</Tag>}
                        </Space>
                      ),
                  },
                  { title: '行数', dataIndex: 'rowCount', key: 'rowCount', width: 90 },
                ]}
              />
            </>
          )}
        </>
      )}

      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 4 }}>
        <Text strong>事件历史</Text>
        <Button
          size="small"
          icon={<PlusOutlined />}
          disabled={eventTypes.length === 0}
          onClick={() => setRecordOpen(true)}
        >
          记录事件
        </Button>
      </Space>
      <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
        解释里只带最近 20 条：解释是交互阅读的，而完整历史在这里。
        {eventTypes.length === 0 && ' 该对象尚未声明事件类型，因此无法记录事件——请先到本体详情的「建模扩展」中声明。'}
      </Paragraph>
      {eventsError ? (
        <Alert type="error" showIcon style={{ marginBottom: 24 }} message="读取事件历史失败" description={eventsError} />
      ) : events && events.length === 0 ? (
        <Empty
          style={{ marginBottom: 24 }}
          description="该实例没有已记录事件（事件类型需先声明，否则历史无法按类型检索）"
        />
      ) : (
        <Table
          size="small"
          rowKey="id"
          dataSource={events ?? []}
          columns={eventColumns}
          loading={events === null}
          pagination={{ pageSize: 10, hideOnSinglePage: true }}
          style={{ marginBottom: 24 }}
        />
      )}

      <Text strong>取值沿革</Text>
      <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
        判定可以按过去某一时刻产出，所以「上个月的金额是多少」是复核旧结论时绕不开的问题。
        <Text strong>没记录过取值的属性不会出现在这里</Text>——这不是数据缺失，是沿革从未被记录。
      </Paragraph>
      {versionsError ? (
        <Alert type="error" showIcon message="读取取值沿革失败" description={versionsError} />
      ) : versions && versions.versions.length === 0 ? (
        <Empty description="该实例没有任何已记录的取值版本" />
      ) : (
        <Table
          size="small"
          rowKey="versionId"
          dataSource={versions?.versions ?? []}
          columns={versionColumns}
          loading={versions === null}
          pagination={{ pageSize: 10, hideOnSinglePage: true }}
        />
      )}

      <Modal
        title={`记录事件：${objectCode} / ${instanceId}`}
        open={recordOpen}
        onCancel={() => setRecordOpen(false)}
        onOk={() => recordForm.submit()}
        confirmLoading={recording}
        destroyOnClose
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="记录事件不会触发任何动作"
          description="它只把「发生了什么」写进历史，因此它是可复核的凭据，而不是一条自动化指令。"
        />
        <Form form={recordForm} layout="vertical" onFinish={handleRecord}>
          <Form.Item name="eventCode" label="事件" rules={[{ required: true, message: '请选择事件' }]}>
            <Select
              placeholder="选择已声明的事件类型"
              options={eventTypes.map((item) => ({
                value: item.code,
                label: `${item.name}（${label(EVENT_CATEGORY, item.category)}）`,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="occurredAt"
            label="发生时间"
            extra="留空表示「现在」。历史是补记的常见情形，因此这里可以填过去的时间。"
          >
            <Input placeholder="2026-01-05 10:00:00" />
          </Form.Item>
          <Form.Item
            name="payload"
            label="载荷"
            extra="可选，JSON 对象。与已声明的载荷字段不一致时平台会在事件上标注，而不是拒绝写入。"
          >
            <Input.TextArea rows={3} placeholder='{"party": "甲方"}' />
          </Form.Item>
        </Form>
      </Modal>
    </Drawer>
  );
};

export default InstanceDrawer;
