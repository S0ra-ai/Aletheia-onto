import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Card, Empty, Select, Space, Table, Tag, Typography } from 'antd';
import { useSearchParams } from 'react-router-dom';
import { ontologyApi, requestErrorMessage, semanticApi } from '../../api';
import { useT } from '../../i18n/locale';
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
  const t = useT();
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
      setListError(requestErrorMessage(error, t('objects.loadOntologiesFailed')));
    }
  }, [t]);

  const loadObjects = useCallback(async (id: number) => {
    try {
      const detail = await ontologyApi.get(id);
      setObjects(detail.objects ?? []);
      setAttributes(detail.attributes ?? []);
      setObjectCode((current) =>
        detail.objects?.some((item) => item.code === current) ? current : detail.objects?.[0]?.code,
      );
    } catch (error) {
      setListError(requestErrorMessage(error, t('objects.loadOntologyDetailFailed')));
    }
  }, [t]);

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
        setListError(requestErrorMessage(error, t('objects.loadInstancesFailed')));
      } finally {
        setLoading(false);
      }
    },
    [t],
  );

  useEffect(() => {
    void loadOntologies();
  }, [loadOntologies, t]);

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
  // **Only the selected object's attributes.** `/ontologies/{id}` returns every attribute of
  // every object, and rendering all of them put a dash in every cell of every column belonging
  // to another table: fourteen columns of dashes on the demo schema, with no way for a reader to
  // tell which ones belonged to the row in front of them. `docs/limitations.md` named the fix --
  // "rendering only the columns of the tables an instance actually came from" -- and this is it.
  //
  // The filter runs at render rather than in `loadObjects` because the object selector changes
  // without refetching the ontology.
  const visibleAttributes = attributes.filter((attribute) => !objectCode || attribute.objectCode === objectCode);
  const columns = [
    { title: t('objects.instanceColumn'), dataIndex: 'instanceId', key: 'instanceId', width: 100, fixed: 'left' as const },
    ...visibleAttributes.map((attribute) => ({
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
      title: t('objects.actionsColumn'),
      key: 'actions',
      width: 110,
      fixed: 'right' as const,
      render: (_: unknown, row: InstanceRow) => (
        // A row that does nothing when clicked is a dead end: the reader can see the values
        // and cannot ask where any of them came from, which is the question this platform
        // exists to answer.
        <Typography.Link onClick={() => showInstance(row.instanceId)}>{t('objects.explainAction')}</Typography.Link>
      ),
    },
  ];

  return (
    <div>
      <Title level={3}>{t('objects.title')}</Title>
      <Paragraph type="secondary">
        {t('objects.subtitle')}
      </Paragraph>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Select
            style={{ width: 260 }}
            placeholder={t('objects.selectOntology')}
            value={ontologyId}
            onChange={(value) => {
              setOntologyId(value);
              setOffset(0);
            }}
            options={ontologies.map((item) => ({ value: item.id, label: `${item.name} v${item.version}` }))}
          />
          <Select
            style={{ width: 220 }}
            placeholder={t('objects.selectObject')}
            value={objectCode}
            onChange={(value) => {
              setObjectCode(value);
              setOffset(0);
            }}
            options={objects.map((item) => ({ value: item.code, label: t('objects.nameWithCode', { name: item.name, code: item.code }) }))}
          />
          {sourceType && <Tag color="blue">{sourceType}</Tag>}
          {resolver && typeof resolver.tables !== 'undefined' ? (
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t('objects.sourceLine', {
                tables: String((resolver.tables as string[])?.join(t('objects.listSeparator')) || resolver.primaryKey || ''),
              })}
            </Text>
          ) : null}
        </Space>
      </Card>

      {rowFilterApplied && !rowFilterError && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          title={t('objects.rowFilterApplied')}
          description={t('objects.rowFilterAppliedDescription')}
        />
      )}

      {rowFilterError && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          title={t('objects.rowFilterError')}
          description={
            <>
              {rowFilterError}
              <br />
              {t('objects.rowFilterErrorDescription')}
            </>
          }
        />
      )}

      {listError && (
        <Alert type="error" showIcon style={{ marginBottom: 16 }} title={t('objects.loadFailed')} description={listError} />
      )}

      <Card>
        {ontologies.length === 0 ? (
          // "请选择本体与业务对象" is unanswerable when there are none, and this is the page a
          // reader reaches straight from the navigation.
          <Empty description={t('objects.emptyNoOntologies')} />
        ) : !ontologyId || !objectCode ? (
          <Empty description={t('objects.emptySelectOntologyAndObject')} />
        ) : !rowFilterError && rows.length === 0 && !loading ? (
          <Empty description={rowFilterApplied ? t('objects.emptyNoVisibleInstances') : t('objects.emptyNoInstances')} />
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
