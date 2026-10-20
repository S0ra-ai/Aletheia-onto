import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Descriptions, Drawer, Empty, Form, Input, Modal, Select, Space, Table, Tag, Typography, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { ontologyApi, requestErrorMessage, semanticApi } from '../../api';
import { EVENT_CATEGORY } from '../../i18n/labels';
import { useLabel, useT } from '../../i18n/locale';
import { explanationParts } from '../../i18n/text';
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
  const label = useLabel();
  const t = useT();
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
      setEventsError(requestErrorMessage(error, t('objects.loadEventsFailed')));
    }
  }, [ontologyId, objectCode, instanceId, t]);

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
      .catch((error) => !cancelled && setExplainError(requestErrorMessage(error, t('objects.loadExplainFailed'))))
      .finally(() => !cancelled && setLoading(false));
    semanticApi
      .instanceEvents(ontologyId, objectCode, instanceId)
      .then((result) => !cancelled && setEvents(result.items ?? []))
      .catch((error) => !cancelled && setEventsError(requestErrorMessage(error, t('objects.loadEventsFailed'))));
    semanticApi
      .instanceVersions(ontologyId, objectCode, instanceId)
      .then((result) => !cancelled && setVersions(result))
      .catch((error) => !cancelled && setVersionsError(requestErrorMessage(error, t('objects.loadVersionsFailed'))));
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
  }, [ontologyId, objectCode, instanceId, t]);

  const handleRecord = async (values: { eventCode: string; occurredAt?: string; payload?: string }) => {
    setRecording(true);
    try {
      let payload: Record<string, unknown> = {};
      if (values.payload?.trim()) {
        try {
          payload = JSON.parse(values.payload);
        } catch {
          message.error(t('objects.payloadInvalidJson'));
          return;
        }
      }
      await semanticApi.recordInstanceEvent(ontologyId, objectCode, instanceId, {
        eventCode: values.eventCode,
        payload,
        occurredAt: values.occurredAt?.trim() || '',
      });
      message.success(t('objects.eventRecorded'));
      setRecordOpen(false);
      recordForm.resetFields();
      await loadEvents();
    } catch (error) {
      message.error(requestErrorMessage(error, t('objects.recordEventFailed')));
    } finally {
      setRecording(false);
    }
  };

  const attributeColumns = [
    {
      title: t('objects.attributeColumn'),
      key: 'attribute',
      render: (_: unknown, row: InstanceExplainAttribute) => (
        <Space orientation="vertical" size={0}>
          <Space size={4}>
            <Text strong>{row.attributeName || row.attributeCode}</Text>
            {row.derived && <Tag color="purple">{t('objects.tagDerived')}</Tag>}
            {row.fromHistory && <Tag color="blue">{t('objects.tagFromHistory')}</Tag>}
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {row.attributeCode}
          </Text>
        </Space>
      ),
    },
    {
      title: t('objects.sourceColumn'),
      key: 'source',
      width: 230,
      // A derived attribute has no column, and saying so is the explanation: the value was
      // computed from an expression, not read from anywhere. It used to be dropped from
      // this table entirely, because the query inner-joined the source column.
      render: (_: unknown, row: InstanceExplainAttribute) =>
        row.derived ? (
          <Space orientation="vertical" size={0}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t('objects.derivedFromExpression')}
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
      title: t('objects.valueColumn'),
      key: 'value',
      render: (_: unknown, row: InstanceExplainAttribute) => {
        if (row.error) {
          // A derived attribute that could not be computed makes rules referencing it fail
          // closed. Showing an empty cell here would hide that behind a blank.
          return <Text type="danger">{t('objects.computeFailed', { error: row.error })}</Text>;
        }
        if (row.value === null || row.value === undefined || row.value === '') {
          return <Text type="secondary">{t('objects.emptyValue')}</Text>;
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
      title: t('objects.unitColumn'),
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
    { title: t('objects.occurredAtColumn'), dataIndex: 'occurredAt', key: 'occurredAt', width: 180 },
    {
      title: t('objects.eventColumn'),
      key: 'event',
      render: (_: unknown, row: InstanceEvent) => (
        <Space orientation="vertical" size={0}>
          <Text strong>{row.eventName || row.eventCode}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {row.eventCode}
          </Text>
        </Space>
      ),
    },
    {
      // The code, not the server's `categoryLabel`: the categories are a closed vocabulary
      // (`events.EVENT_CATEGORIES`) with a label map on this side, and rendering the server's
      // Chinese word left 「状态变更」 in the middle of the English drawer. The server's label is
      // the fallback for a category an extension adds.
      title: t('objects.categoryColumn'),
      dataIndex: 'category',
      key: 'category',
      width: 110,
      render: (category: string, row: InstanceEvent) =>
        category ? (
          <Tag>{label(EVENT_CATEGORY, category)}</Tag>
        ) : row.categoryLabel ? (
          <Tag>{row.categoryLabel}</Tag>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    { title: t('objects.actorColumn'), dataIndex: 'actor', key: 'actor', width: 140 },
    {
      title: t('objects.payloadColumn'),
      dataIndex: 'payload',
      key: 'payload',
      render: (payload: Record<string, unknown>, row: InstanceEvent) =>
        Object.keys(payload ?? {}).length === 0 ? (
          <Text type="secondary">—</Text>
        ) : (
          <Space orientation="vertical" size={0}>
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
      title: t('objects.attributeColumn'),
      dataIndex: 'attributeCode',
      key: 'attributeCode',
      width: 200,
      render: (code: string) => <Text code>{code}</Text>,
    },
    { title: t('objects.versionValueColumn'), dataIndex: 'value', key: 'value' },
    {
      title: t('objects.validityColumn'),
      key: 'validity',
      width: 320,
      render: (_: unknown, row: InstanceAttributeVersion) => (
        <Text>
          {row.validFrom} → {row.validTo ?? <Text type="secondary">{t('objects.toPresent')}</Text>}
        </Text>
      ),
    },
    { title: t('objects.recordedAtColumn'), dataIndex: 'recordedAt', key: 'recordedAt', width: 180 },
    { title: t('objects.recordedByColumn'), dataIndex: 'actor', key: 'actor', width: 120 },
  ];

  return (
    <Drawer
      open
      size={880}
      onClose={onClose}
      title={explain ? `${explain.object.name || objectCode} · ${instanceId}` : `${objectCode} · ${instanceId}`}
    >
      {explainError && (
        <Alert type="error" showIcon style={{ marginBottom: 16 }} title={t('objects.loadExplainFailed')} description={explainError} />
      )}

      {explain && (
        <>
          <Descriptions size="small" column={2} bordered style={{ marginBottom: 16 }}>
            <Descriptions.Item label={t('objects.ontologyLabel')}>
              {explain.ontology.name} v{explain.ontology.version}
            </Descriptions.Item>
            <Descriptions.Item label={t('objects.objectLabel')}>
              {t('objects.nameWithCode', { name: explain.object.name, code: explain.objectCode })}
            </Descriptions.Item>
            <Descriptions.Item label={t('objects.sourceTableLabel')}>{explain.source.table}</Descriptions.Item>
            <Descriptions.Item label={t('objects.primaryKeyLabel')}>{explain.source.primaryKey}</Descriptions.Item>
            {explain.ancestors.length > 0 && (
              <Descriptions.Item label={t('objects.typeHierarchyLabel')} span={2}>
                <Space wrap>
                  {explain.ancestors.map((ancestor) => (
                    <Tag key={ancestor}>{ancestor}</Tag>
                  ))}
                </Space>
                <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
                  {t('objects.ancestorNote')}
                </Text>
              </Descriptions.Item>
            )}
          </Descriptions>

          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            title={explanationParts(explain.explanationParts, t, explain.explanation)}
          />

          <Text strong>{t('objects.attributesHeading')}</Text>
          <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
            {t('objects.attributesHint')}
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
              <Text strong>{t('objects.aggregatesHeading')}</Text>
              <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
                {t('objects.aggregatesHint')}
                <Text strong>{t('objects.aggregatesHintEmphasis')}</Text>
                {t('objects.aggregatesHintEnd')}
              </Paragraph>
              <Table<InstanceExplainAggregate>
                size="small"
                rowKey="name"
                dataSource={explain.aggregates}
                pagination={false}
                style={{ marginBottom: 24 }}
                columns={[
                  {
                    title: t('objects.nameColumn'),
                    dataIndex: 'name',
                    key: 'name',
                    width: 180,
                    render: (name: string) => <Text code>{name}</Text>,
                  },
                  { title: t('objects.definitionColumn'), dataIndex: 'definition', key: 'definition', ellipsis: true },
                  {
                    title: t('objects.valueColumn'),
                    key: 'value',
                    width: 160,
                    render: (_: unknown, row: InstanceExplainAggregate) =>
                      row.error ? (
                        <Text type="danger">{t('objects.computeFailed', { error: row.error })}</Text>
                      ) : (
                        <Space size={4}>
                          <Text>{row.value === null || row.value === undefined ? t('objects.emptyValue') : String(row.value)}</Text>
                          {/* A truncated aggregate is a partial answer; a verdict resting on
                              it was reached on partial data, and the reader has to know. */}
                          {row.truncated && <Tag color="orange">{t('objects.truncatedTag')}</Tag>}
                        </Space>
                      ),
                  },
                  { title: t('objects.rowCountColumn'), dataIndex: 'rowCount', key: 'rowCount', width: 90 },
                ]}
              />
            </>
          )}
        </>
      )}

      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 4 }}>
        <Text strong>{t('objects.eventsHeading')}</Text>
        <Button
          size="small"
          icon={<PlusOutlined />}
          disabled={eventTypes.length === 0}
          onClick={() => setRecordOpen(true)}
        >
          {t('objects.recordEventButton')}
        </Button>
      </Space>
      <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
        {t('objects.eventsHint')}
        {eventTypes.length === 0 && t('objects.eventsNoTypesHint')}
      </Paragraph>
      {eventsError ? (
        <Alert type="error" showIcon style={{ marginBottom: 24 }} title={t('objects.loadEventsFailed')} description={eventsError} />
      ) : events && events.length === 0 ? (
        <Empty
          style={{ marginBottom: 24 }}
          description={t('objects.emptyNoEvents')}
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

      <Text strong>{t('objects.versionsHeading')}</Text>
      <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
        {t('objects.versionsHint')}
        <Text strong>{t('objects.versionsHintEmphasis')}</Text>
        {t('objects.versionsHintTail')}
      </Paragraph>
      {versionsError ? (
        <Alert type="error" showIcon title={t('objects.loadVersionsFailed')} description={versionsError} />
      ) : versions && versions.versions.length === 0 ? (
        <Empty description={t('objects.emptyNoVersions')} />
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
        title={t('objects.recordEventTitle', { object: objectCode, instance: instanceId })}
        open={recordOpen}
        onCancel={() => setRecordOpen(false)}
        onOk={() => recordForm.submit()}
        confirmLoading={recording}
        destroyOnHidden
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          title={t('objects.recordEventNote')}
          description={t('objects.recordEventNoteDescription')}
        />
        <Form form={recordForm} layout="vertical" onFinish={handleRecord}>
          <Form.Item name="eventCode" label={t('objects.eventColumn')} rules={[{ required: true, message: t('objects.selectEventRequired') }]}>
            <Select
              placeholder={t('objects.selectEventType')}
              options={eventTypes.map((item) => ({
                value: item.code,
                label: t('objects.eventTypeOption', { name: item.name, category: label(EVENT_CATEGORY, item.category) }),
              }))}
            />
          </Form.Item>
          <Form.Item
            name="occurredAt"
            label={t('objects.occurredAtLabel')}
            extra={t('objects.occurredAtHint')}
          >
            <Input placeholder="2026-01-05 10:00:00" />
          </Form.Item>
          <Form.Item
            name="payload"
            label={t('objects.payloadColumn')}
            extra={t('objects.payloadHint')}
          >
            <Input.TextArea rows={3} placeholder={t('objects.payloadPlaceholder')} />
          </Form.Item>
        </Form>
      </Modal>
    </Drawer>
  );
};

export default InstanceDrawer;
