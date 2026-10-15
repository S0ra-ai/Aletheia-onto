import React, { useEffect, useState } from 'react';
import { Alert, Descriptions, Drawer, Empty, Space, Table, Tag, Typography } from 'antd';
import { requestErrorMessage, semanticApi } from '../../api';
import type {
  InstanceAttributeVersion,
  InstanceEvent,
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
  const [explainError, setExplainError] = useState('');
  const [eventsError, setEventsError] = useState('');
  const [versionsError, setVersionsError] = useState('');
  const [loading, setLoading] = useState(true);

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

    return () => {
      cancelled = true;
    };
  }, [ontologyId, objectCode, instanceId]);

  const attributeColumns = [
    {
      title: '属性',
      key: 'attribute',
      render: (_: unknown, row: InstanceExplainAttribute) => (
        <Space direction="vertical" size={0}>
          <Text strong>{row.attributeName || row.attributeCode}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {row.attributeCode}
          </Text>
        </Space>
      ),
    },
    {
      title: '来源列',
      dataIndex: 'sourceColumn',
      key: 'sourceColumn',
      width: 200,
      // Named per attribute rather than per object: the whole claim is that a value can be
      // traced to where it was read, and "the object maps to table contract" does not
      // answer which column a number came from.
      render: (column: string) => (column ? <Text code>{column}</Text> : <Text type="secondary">—</Text>),
    },
    {
      title: '当前值',
      dataIndex: 'value',
      key: 'value',
      render: (value: unknown) =>
        value === null || value === undefined || value === '' ? (
          <Text type="secondary">空值</Text>
        ) : (
          String(value)
        ),
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
        </>
      )}

      <Text strong>事件历史</Text>
      <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
        解释里只带最近 20 条：解释是交互阅读的，而完整历史在这里。
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
    </Drawer>
  );
};

export default InstanceDrawer;
