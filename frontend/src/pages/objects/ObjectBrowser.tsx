import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Card, Empty, Select, Space, Table, Tag, Typography } from 'antd';
import { useSearchParams } from 'react-router-dom';
import { ontologyApi, requestErrorMessage, semanticApi } from '../../api';
import type { BusinessAttribute, BusinessObject, Ontology } from '../../types';
import InstanceDrawer from './InstanceDrawer';

const { Title, Paragraph, Text } = Typography;

type InstanceRow = { instanceId: string; record: Record<string, unknown> };
type Pagination = { limit: number; offset: number; total: number; hasMore: boolean };

/**
 * Business objects and their governed instances.
 *
 * The platform's distinguishing claim is that a business object is consumed through one
 * stable API without the caller knowing which table or resolver backs it -- and until now
 * that view had no screen. The datasource page browses *raw table rows*, which is a
 * different thing: it does not go through the instance resolver, does not apply the
 * caller's row-level filter, and shows columns rather than declared attributes. The
 * endpoint, the client method and the response type all existed; nothing called them.
 */
const ObjectBrowser: React.FC = () => {
  /**
   * Which instance is open is part of the address, like every other selection in this
   * application.
   *
   * `/admin/objects?ontology=1&object=contract&instance=1` opens that instance's drawer --
   * the attributes with the column each value was read from, the events and the value
   * history. It is the screen where a verdict is actually read, so it is the one worth
   * sending to somebody; and it is four tables that no check could see, because they
   * appear only after a click and the render check reads the DOM rather than clicking.
   */
  const [params, setParams] = useSearchParams();
  const requestedOntology = Number(params.get('ontology'));
  const [ontologies, setOntologies] = useState<Ontology[]>([]);
  const [ontologyId, setOntologyId] = useState<number | undefined>(
    Number.isInteger(requestedOntology) && requestedOntology > 0 ? requestedOntology : undefined,
  );
  const [objects, setObjects] = useState<BusinessObject[]>([]);
  const [attributes, setAttributes] = useState<BusinessAttribute[]>([]);
  const [objectCode, setObjectCode] = useState<string | undefined>(params.get('object') ?? undefined);
  const [rows, setRows] = useState<InstanceRow[]>([]);
  const [pagination, setPagination] = useState<Pagination | null>(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState('');
  // Two instructions that must not be confused: `rowFilterApplied` says the result is
  // narrowed by what this role may see, `rowFilterError` says the narrowing could not
  // happen at all -- so an empty table means "nothing is visible" in one case and "your
  // policy is broken" in the other.
  const [rowFilterApplied, setRowFilterApplied] = useState(false);
  const [rowFilterError, setRowFilterError] = useState('');
  const [sourceType, setSourceType] = useState('');
  const [resolver, setResolver] = useState<Record<string, unknown> | null>(null);
  const [openedInstance, setOpenedInstance] = useState<string | undefined>(params.get('instance') ?? undefined);

  /** Keep the address in step with what is open, so the two never disagree. */
  const showInstance = useCallback(
    (instanceId: string | undefined) => {
      setOpenedInstance(instanceId);
      setParams(
        (previous) => {
          const next = new URLSearchParams(previous);
          if (instanceId) next.set('instance', instanceId);
          else next.delete('instance');
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  const loadOntologies = useCallback(async () => {
    try {
      const items = await ontologyApi.list();
      const list = Array.isArray(items) ? items : [];
      setOntologies(list);
      setOntologyId((current) => current ?? list[0]?.id);
    } catch (error) {
      setListError(requestErrorMessage(error, '获取本体列表失败'));
    }
  }, []);

  const loadObjects = useCallback(async (id: number) => {
    try {
      const detail = await ontologyApi.get(id);
      setObjects(detail.objects ?? []);
      setAttributes(detail.attributes ?? []);
      setObjectCode((current) =>
        detail.objects?.some((item) => item.code === current) ? current : detail.objects?.[0]?.code,
      );
    } catch (error) {
      setListError(requestErrorMessage(error, '读取本体详情失败'));
    }
  }, []);

  const loadInstances = useCallback(
    async (code: string, id: number, nextOffset: number) => {
      setLoading(true);
      setListError('');
      try {
        const result = await semanticApi.listInstances(code, id, 20, nextOffset);
        setRows((result.items ?? []) as InstanceRow[]);
        setPagination(result.pagination ?? null);
        setRowFilterApplied(Boolean(result.rowFilterApplied));
        setRowFilterError((result.rowFilterError ?? '') as string);
        setSourceType(result.object?.sourceType ?? '');
        setResolver(result.object?.resolver ?? null);
      } catch (error) {
        setRows([]);
        setPagination(null);
        setListError(requestErrorMessage(error, '读取业务对象实例失败'));
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    void loadOntologies();
  }, [loadOntologies]);

  useEffect(() => {
    if (ontologyId) void loadObjects(ontologyId);
  }, [ontologyId, loadObjects]);

  useEffect(() => {
    if (objectCode && ontologyId) void loadInstances(objectCode, ontologyId, offset);
  }, [objectCode, ontologyId, offset, loadInstances]);

  // One column per declared attribute of the selected object: the object's contract, not
  // whatever columns today's query happened to return.
  // An object has twenty-odd attributes, and antd divides the available width among
  // columns that declare none -- so every header rendered as a single character with an
  // ellipsis ("标…", "合…") and no value was readable. A declared width plus horizontal
  // scrolling keeps each value legible and the whole contract reachable.
  const ATTRIBUTE_WIDTH = 150;
  /**
   * A value from the row, found by the column the attribute was derived from.
   *
   * `record` is the row as the source returned it -- keyed by *column names*. The cells used
   * to be read by `attribute.code`, which is a different string as soon as the source declares
   * anything but an all-lowercase name: a column `ContractNo` yields an attribute code of
   * `contractno` (or a blueprint's own name for it), and every cell in the table then rendered
   * the 「—」 that means "this row has no value here". A table of plausible-looking dashes is
   * the exact failure this platform cannot afford, and the demo schema is all-lowercase, so it
   * never showed.
   */
  const valueFor = (row: InstanceRow, attribute: BusinessAttribute): unknown => {
    const record = row.record ?? {};
    for (const key of [attribute.sourceColumn, attribute.code]) {
      if (key && key in record) return record[key];
    }
    // Adapters differ on identifier case (PostgreSQL folds unquoted names, MySQL keeps them),
    // so a case-insensitive match is the last resort rather than a guess.
    const wanted = [attribute.sourceColumn, attribute.code].filter(Boolean).map((key) => key.toLowerCase());
    for (const [key, value] of Object.entries(record)) {
      if (wanted.includes(key.toLowerCase())) return value;
    }
    return undefined;
  };
  const columns = [
    { title: '实例', dataIndex: 'instanceId', key: 'instanceId', width: 100, fixed: 'left' as const },
    ...attributes.map((attribute) => ({
      title: attribute.name || attribute.code,
      key: attribute.code,
      width: ATTRIBUTE_WIDTH,
      ellipsis: true,
      render: (_: unknown, row: InstanceRow) => {
        const value = valueFor(row, attribute);
        if (value === null || value === undefined || value === '') return <Text type="secondary">—</Text>;
        return String(value);
      },
    })),
    {
      title: '操作',
      key: 'actions',
      width: 110,
      fixed: 'right' as const,
      render: (_: unknown, row: InstanceRow) => (
        // A row that does nothing when clicked is a dead end: the reader can see the values
        // and cannot ask where any of them came from, which is the question this platform
        // exists to answer.
        <Typography.Link onClick={() => showInstance(row.instanceId)}>解释</Typography.Link>
      ),
    },
  ];

  return (
    <div>
      <Title level={3}>业务对象浏览</Title>
      <Paragraph type="secondary">
        按本体中声明的业务对象查看实例。数据经实例解析器读取，并按你的角色做行级过滤，
        与直接浏览来源表不是同一件事。
      </Paragraph>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Select
            style={{ width: 260 }}
            placeholder="选择本体"
            value={ontologyId}
            onChange={(value) => {
              setOntologyId(value);
              setOffset(0);
            }}
            options={ontologies.map((item) => ({ value: item.id, label: `${item.name} v${item.version}` }))}
          />
          <Select
            style={{ width: 220 }}
            placeholder="选择业务对象"
            value={objectCode}
            onChange={(value) => {
              setObjectCode(value);
              setOffset(0);
            }}
            options={objects.map((item) => ({ value: item.code, label: `${item.name}（${item.code}）` }))}
          />
          {sourceType && <Tag color="blue">{sourceType}</Tag>}
          {resolver && typeof resolver.tables !== 'undefined' ? (
            <Text type="secondary" style={{ fontSize: 12 }}>
              来源：{String((resolver.tables as string[])?.join('、') || resolver.primaryKey || '')}
            </Text>
          ) : null}
        </Space>
      </Card>

      {rowFilterApplied && !rowFilterError && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="结果已按你的角色做行级过滤"
          description="没有看到某条实例，可能是它不在你的可见范围内，而不是它不存在。"
        />
      )}

      {rowFilterError && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          message="行级过滤表达式无法求值，因此没有返回任何实例"
          description={
            <>
              {rowFilterError}
              <br />
              这不是「没有数据」：平台为避免越权披露，在过滤条件无法判断时按不可见处理。
              请修正该角色在本对象上的过滤表达式后重试。
            </>
          }
        />
      )}

      {listError && (
        <Alert type="error" showIcon style={{ marginBottom: 16 }} message="读取失败" description={listError} />
      )}

      <Card>
        {ontologies.length === 0 ? (
          // "请选择本体与业务对象" is unanswerable when there are none, and this is the page a
          // reader reaches straight from the navigation.
          <Empty description="还没有可浏览的本体。请先到「数据接入」登记并扫描业务库，再回「本体建模」生成本体草案" />
        ) : !ontologyId || !objectCode ? (
          <Empty description="请选择本体与业务对象" />
        ) : !rowFilterError && rows.length === 0 && !loading ? (
          <Empty description={rowFilterApplied ? '按当前角色的可见范围内没有实例' : '该对象没有实例'} />
        ) : (
          <Table
            size="small"
            columns={columns}
            dataSource={rows}
            rowKey="instanceId"
            loading={loading}
            scroll={{ x: 'max-content' }}
            pagination={
              pagination
                ? {
                    current: Math.floor(pagination.offset / Math.max(1, pagination.limit)) + 1,
                    pageSize: pagination.limit,
                    total: pagination.total,
                    showSizeChanger: false,
                    onChange: (page) => setOffset((page - 1) * pagination.limit),
                  }
                : false
            }
          />
        )}
      </Card>

      {openedInstance && objectCode && ontologyId && (
        <InstanceDrawer
          ontologyId={ontologyId}
          objectCode={objectCode}
          instanceId={openedInstance}
          onClose={() => showInstance(undefined)}
        />
      )}
    </div>
  );
};

export default ObjectBrowser;
