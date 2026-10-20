import { codedText, joinSentences } from '../../i18n/text';
import React, { useCallback, useEffect, useState } from 'react';
import { GATE_SEVERITY, MAPPING_TYPE, ONTOLOGY_STATUS, READINESS_STATUS, RULE_SEVERITY } from '../../i18n/labels';
import { useLabel, useLocale, useT } from '../../i18n/locale';
import { useParams, useNavigate } from 'react-router-dom';
import { Alert, Card, Table, Button, Space, Typography, Tag, Tabs, Descriptions, Empty, Spin, Progress, Popconfirm, message } from 'antd';
import { ArrowLeftOutlined, CloudUploadOutlined, DownloadOutlined } from '@ant-design/icons';
import { ontologyApi, requestErrorMessage } from '../../api';
import type { OntologyDetail, ReleaseReadinessGate, ReleaseReadinessResult } from '../../types';
import { useTabParam } from '../../hooks/useTabParam';
import ModellingExtensions from './ModellingExtensions';

const { Title } = Typography;
const { TabPane } = Tabs;

const OntologyDetailPage: React.FC = () => {
  const label = useLabel();
  const [tab, setTab] = useTabParam('objects');
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const t = useT();
  const { locale } = useLocale();
  const [ontology, setOntology] = useState<OntologyDetail | null>(null);
  const [releaseReadiness, setReleaseReadiness] = useState<ReleaseReadinessResult | null>(null);
  const [loading, setLoading] = useState(false);
  // Kept apart from "loaded and there is nothing": both leave `ontology` null, and showing
  // the same "未找到本体数据" for a failed read told the user the data does not exist when
  // the real cause was a permission or a server failure.
  const [loadError, setLoadError] = useState('');
  const [publishing, setPublishing] = useState(false);

  // `useCallback` so the effect below can list its real dependency instead of capturing the
  // first render's closure and warning about it.
  const fetchOntology = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setLoadError('');
    try {
      const [data, readiness] = await Promise.all([
        ontologyApi.get(parseInt(id)),
        ontologyApi.getReleaseReadiness(parseInt(id)),
      ]);
      setOntology(data);
      setReleaseReadiness(readiness);
    } catch (error) {
      // Was `console.error` only, so a failed read was indistinguishable from an empty one
      // to anyone not holding the developer console.
      setLoadError(requestErrorMessage(error, t('ontology.loadFailed')));
    } finally {
      setLoading(false);
    }
  }, [id, t]);

  useEffect(() => {
    fetchOntology();
  }, [fetchOntology]);

  const blockers = (releaseReadiness?.gates ?? []).filter((gate) => gate.severity === 'blocker' && !gate.passed);

  // Only the plain path is offered here. `aletheia publish --force` exists for a deliberate
  // override and records it in the audit log; a button labelled 强行发布 in a web console
  // would make an override look like an ordinary action -- and the refusal names every
  // blocker, so the button being disabled is never the end of the story.
  const canPublish =
    !!ontology && ontology.ontology.status !== 'published' && blockers.length === 0;

  // The download goes through the API client, so a failure is a message rather than a blank
  // tab: these four buttons used to hand a URL to `window.open`, and the API authenticates
  // with a bearer header a browser does not attach on its own.
  const handleExport = async (format: 'jsonld' | 'turtle' | 'owl' | 'shacl') => {
    if (!id) return;
    try {
      await ontologyApi.downloadExport(parseInt(id), format);
    } catch (error) {
      message.error(requestErrorMessage(error, t('ontology.exportFailed')));
    }
  };

  const handlePublish = async () => {
    if (!id) return;
    setPublishing(true);
    try {
      const result = await ontologyApi.publish(parseInt(id));
      message.success(t('ontology.published', { name: result.name, version: result.version }));
      await fetchOntology();
    } catch (error) {
      // The server's refusal names the blockers, and that message is the useful one -- the
      // gate list on this tab shows the same thing in detail.
      message.error(requestErrorMessage(error, t('ontology.publishFailed')));
    } finally {
      setPublishing(false);
    }
  };

  if (loading) {
    return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  }

  if (loadError) {
    return (
      <Alert
        type="error"
        showIcon
        title={t('ontology.loadFailed')}
        description={loadError}
        action={<Button onClick={fetchOntology}>{t('ontology.retry')}</Button>}
      />
    );
  }

  if (!ontology) {
    return <Empty description={t('ontology.notFound')} />;
  }

  const objectColumns = [
    { title: t('ontology.code'), dataIndex: 'code', key: 'code' },
    { title: t('ontology.name'), dataIndex: 'name', key: 'name' },
    { title: t('ontology.sourceTable'), dataIndex: 'sourceTable', key: 'sourceTable' },
    { title: t('ontology.description'), dataIndex: 'description', key: 'description' },
  ];

  const attributeColumns = [
    { title: t('ontology.code'), dataIndex: 'code', key: 'code' },
    { title: t('ontology.name'), dataIndex: 'name', key: 'name' },
    { title: t('ontology.dataType'), dataIndex: 'dataType', key: 'dataType', render: (type: string) => <Tag>{type}</Tag> },
    { title: t('ontology.sourceColumn'), dataIndex: 'sourceColumn', key: 'sourceColumn' },
    // There is deliberately no 描述 column here. `business_attribute` has no description
    // column in the schema, and `_business_attribute_row` hardcodes `"description": ""` -- so
    // the column rendered blank for every row of every ontology. It was found by writing the
    // component test that reads this table, which is the only place it could have been seen:
    // the backend was consistent with itself and the frontend was consistent with itself.
  ];

  const relationColumns = [
    { title: t('ontology.name'), dataIndex: 'name', key: 'name' },
    { title: t('ontology.type'), dataIndex: 'type', key: 'type', render: (type: string) => <Tag color="blue">{type}</Tag> },
    { title: t('ontology.foreignKey'), dataIndex: 'sourceForeignKey', key: 'sourceForeignKey' },
  ];

  const mappingColumns = [
    { title: t('ontology.type'), dataIndex: 'mappingType', key: 'mappingType', render: (type: string) => <Tag>{label(MAPPING_TYPE, type)}</Tag> },
    { title: t('ontology.sourceTable'), dataIndex: 'sourceTable', key: 'sourceTable' },
    { title: t('ontology.sourceColumn'), dataIndex: 'sourceColumn', key: 'sourceColumn', render: (col: string) => col || '-' },
    { title: t('ontology.targetObject'), dataIndex: 'targetObjectCode', key: 'targetObjectCode' },
    { title: t('ontology.targetAttribute'), dataIndex: 'targetAttributeCode', key: 'targetAttributeCode', render: (attr: string) => attr || '-' },
    { title: t('ontology.confidence'), dataIndex: 'confidence', key: 'confidence', render: (conf: number) => `${(conf * 100).toFixed(0)}%` },
    { title: t('ontology.status'), dataIndex: 'status', key: 'status', render: (status: string) => <Tag color={status === 'confirmed' ? 'green' : 'orange'}>{label(ONTOLOGY_STATUS, status)}</Tag> },
  ];

  const ruleColumns = [
    { title: t('ontology.code'), dataIndex: 'code', key: 'code' },
    { title: t('ontology.name'), dataIndex: 'name', key: 'name' },
    { title: t('ontology.severity'), dataIndex: 'severity', key: 'severity', render: (sev: string) => <Tag color={sev === 'blocking' ? 'red' : sev === 'warning' ? 'orange' : 'blue'}>{label(RULE_SEVERITY, sev)}</Tag> },
    { title: t('ontology.enabled'), dataIndex: 'enabled', key: 'enabled', render: (enabled: boolean) => <Tag color={enabled ? 'green' : 'default'}>{enabled ? t('ontology.yes') : t('ontology.no')}</Tag> },
    { title: t('ontology.expression'), dataIndex: 'expression', key: 'expression', render: (expr: string) => <code>{expr}</code> },
  ];

  const releaseGateColumns = [
    {
      title: t('ontology.gate'),
      dataIndex: 'name',
      key: 'name',
      render: (_: string, gate: ReleaseReadinessGate) => gateText(gate, 'label'),
    },
    {
      title: t('ontology.status'),
      dataIndex: 'passed',
      key: 'passed',
      render: (passed: boolean) => <Tag color={passed ? 'green' : 'red'}>{passed ? t('ontology.passed') : t('ontology.notPassed')}</Tag>,
    },
    {
      title: t('ontology.gateLevel'),
      dataIndex: 'severity',
      key: 'severity',
      render: (severity: string) => (
        <Tag color={severity === 'blocker' ? 'red' : 'orange'}>{label(GATE_SEVERITY, severity)}</Tag>
      ),
    },
    {
      title: t('ontology.evidence'),
      dataIndex: 'evidence',
      key: 'evidence',
      render: (_: string, gate: ReleaseReadinessGate) => gateText(gate, 'evidence'),
    },
    {
      title: t('ontology.remediation'),
      dataIndex: 'remediation',
      key: 'remediation',
      render: (_: string, gate: ReleaseReadinessGate) => gateText(gate, 'remediation'),
    },
  ];

  /**
   * A gate's sentence, in the reader's language.
   *
   * The server sends the code, whether the gate passed, and the facts it is about --
   * `numbers` and `status` -- beside its own Chinese wording. Composing here rather than
   * quoting is what makes the release gate bilingual; the server's wording is the fallback
   * for a code this build does not know, including the axioms gate when it *fails*, whose
   * evidence carries the offending declarations themselves.
   */
  const gateText = (gate: ReleaseReadinessGate, field: 'label' | 'evidence' | 'remediation'): string => {
    const dynamic = /^data_source_(\d+)_(readiness|coverage|schema_drift)$/.exec(gate.code ?? '');
    const subject = dynamic ? `data_source.${dynamic[2]}` : (gate.code ?? '');
    const numbers = gate.numbers ?? {};
    const params = {
      ...numbers,
      id: dynamic ? dynamic[1] : '',
      // The status is a vocabulary of its own, and the server's own sentence prints the raw
      // word -- 「当前状态 draft。」 The reader gets 「当前状态 草案。」 instead.
      status: label(ONTOLOGY_STATUS, gate.status),
    };
    // `t()` renders ⟦key⟧ for a key it does not have, which is how a message that may or may not
    // exist is asked for -- `codedText` turns that into the empty string this caller wants rather
    // than into a fallback sentence. Two of the gates have evidence that reads differently
    // depending on the status (the axioms gate says "all declared axioms hold" or lists the
    // violations), and the rest have one sentence for both -- so the status-specific key is
    // tried first and the plain one is the fallback.
    const known = (key: string): string => codedText(t, key, '', params);
    const candidates =
      field === 'evidence' && gate.status
        ? [`ontology.gate.${subject}.evidence.${gate.status}`, `ontology.gate.${subject}.evidence`]
        : [`ontology.gate.${subject}.${field}`];
    for (const candidate of candidates) {
      const translated = known(candidate);
      if (translated) return translated;
    }
    // A failing axioms gate lists the violated declarations in its evidence; those stay the
    // server's sentence until the console learns to render them, which is a change of its own.
    if (field === 'evidence' && gate.status === 'violated') return gate.evidence;
    // `label` rather than `name`: the column is the gate's name, and the message key is
    // `gate.<code>.label` because `name` already means the ontology's own name in this file.
    const fallback = { label: gate.name, evidence: gate.evidence, remediation: gate.remediation };
    return fallback[field];
  };

  /**
   * What to do next, in the reader's language.
   *
   * Built from the failing gates rather than from the server's `nextActions`, which is the
   * same sentences in Chinese. The selection rule mirrors `release_readiness._next_actions`:
   * blockers first, then warnings, and when nothing failed, the sentence that says so.
   *
   * Declared *after* `gateText`, and that is not style: this expression runs while the
   * component body executes, so naming a `const` that is still in its temporal dead zone is a
   * ReferenceError -- the whole page rendered as the error boundary, which the render sweep
   * caught on five routes at once.
   */
  const releaseActions = (() => {
    const failing = (releaseReadiness?.gates ?? []).filter((gate) => !gate.passed);
    const blocking = failing.filter((gate) => gate.severity === 'blocker');
    const selected = blocking.length ? blocking : failing;
    if (!selected.length) return [t('ontology.gate.allPassed')];
    return selected.map((gate) => gateText(gate, 'remediation'));
  })();

  const releaseColor = (status?: string) => {
    if (status === 'ready') return 'green';
    if (status === 'review') return 'orange';
    return 'red';
  };

  /** The four values `governance.VALID_ONTOLOGY_STATUSES` accepts. */
  const statusColor = (status: string) => {
    if (status === 'published') return 'green';
    if (status === 'deprecated') return 'default';
    if (status === 'reviewing') return 'blue';
    return 'orange';
  };

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/ontology')}>
          {t('ontology.back')}
        </Button>
        <Title level={3} style={{ margin: 0 }}>{t('ontology.detailTitle')}</Title>
        {/* Four formats, because the endpoint takes four. It offered two, so the pair the
            endpoint's own docstring calls the one another tool can *interpret* rather than
            merely read -- OWL/RDFS and SHACL -- was reachable only by composing the URL by
            hand. JSON-LD and Turtle carry this platform's own fields, which standard
            vocabulary has no word for; both are worth having, and a user comparing them
            should not have to discover that two of the four exist. */}
        <Button
          icon={<DownloadOutlined />}
          onClick={() => void handleExport('jsonld')}
        >
          JSON-LD
        </Button>
        <Button
          icon={<DownloadOutlined />}
          onClick={() => void handleExport('turtle')}
        >
          Turtle
        </Button>
        <Button
          icon={<DownloadOutlined />}
          onClick={() => void handleExport('owl')}
        >
          OWL/RDFS
        </Button>
        <Button
          icon={<DownloadOutlined />}
          onClick={() => void handleExport('shacl')}
        >
          SHACL
        </Button>
      </Space>

      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={2}>
          <Descriptions.Item label="ID">{ontology.ontology.id}</Descriptions.Item>
          <Descriptions.Item label={t('ontology.name')}>{ontology.ontology.name}</Descriptions.Item>
          <Descriptions.Item label={t('ontology.version')}>
            <Tag>v{ontology.ontology.version}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t('ontology.status')}>
            {/* This asked `status === 'active'`, a value `VALID_ONTOLOGY_STATUSES` does not
                contain, so the tag was orange for every status including a published one --
                and it printed the raw enum, which the list page beside it already
                translates. A condition that can never be true reads as a working rule. */}
            <Tag color={statusColor(ontology.ontology.status)}>{label(ONTOLOGY_STATUS, ontology.ontology.status)}</Tag>
          </Descriptions.Item>
          {/* The row here read "数据源ID" and bound `ontology.dataSourceId`, a field the
              `ontology` table does not have -- an ontology reaches its data sources through
              its objects, which may be several. The row was therefore blank on every
              deployment, permanently. Replaced with two fields that exist in the payload. */}
          <Descriptions.Item label={t('ontology.domain')}>{ontology.ontology.domain || t('ontology.domainUnset')}</Descriptions.Item>
          <Descriptions.Item label={t('ontology.createdAt')}>{ontology.ontology.createdAt}</Descriptions.Item>
        </Descriptions>
      </Card>

      {releaseReadiness && (
        <Card style={{ marginBottom: 16 }} title={t('ontology.releaseReadiness')}>
          <Space align="start" size="large" style={{ width: '100%', justifyContent: 'space-between' }}>
            <div style={{ minWidth: 220 }}>
              <Progress
                type="circle"
                percent={Math.round((releaseReadiness.summary.passedGates / Math.max(releaseReadiness.summary.totalGates, 1)) * 100)}
                strokeColor={releaseColor(releaseReadiness.status)}
              />
            </div>
            <Descriptions column={4} style={{ flex: 1 }}>
              <Descriptions.Item label={t('ontology.status')}>
                <Tag color={releaseColor(releaseReadiness.status)}>
                  {label(READINESS_STATUS, releaseReadiness.status)}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('ontology.objects')}>{releaseReadiness.summary.objects}</Descriptions.Item>
              <Descriptions.Item label={t('ontology.dataSources')}>{releaseReadiness.summary.dataSources}</Descriptions.Item>
              <Descriptions.Item label={t('ontology.gate')}>{releaseReadiness.summary.passedGates}/{releaseReadiness.summary.totalGates}</Descriptions.Item>
              <Descriptions.Item label={t('ontology.blockers')}>{releaseReadiness.summary.blockers}</Descriptions.Item>
              <Descriptions.Item label={t('ontology.warnings')}>{releaseReadiness.summary.warnings}</Descriptions.Item>
              <Descriptions.Item label={t('ontology.confirmedMappings')}>{releaseReadiness.summary.confirmedMappings}</Descriptions.Item>
              <Descriptions.Item label={t('ontology.pendingMappings')}>{releaseReadiness.summary.pendingMappings}</Descriptions.Item>
              <Descriptions.Item label={t('ontology.publishedRules')}>{releaseReadiness.summary.publishedRules}</Descriptions.Item>
            </Descriptions>
          </Space>
          {releaseReadiness.nextActions.length > 0 && (
            <Alert
              style={{ marginTop: 16 }}
              type={releaseReadiness.status === 'ready' ? 'success' : releaseReadiness.status === 'blocked' ? 'error' : 'warning'}
              title={t('ontology.nextActions')}
              description={joinSentences(releaseActions, locale)}
            />
          )}
        </Card>
      )}

      <Card>
        <Tabs activeKey={tab} onChange={setTab}>
          <TabPane tab={t('ontology.objectsTab', { count: ontology.objects.length })} key="objects">
            <Table
              columns={objectColumns}
              dataSource={ontology.objects}
              rowKey="id"
            />
          </TabPane>
          <TabPane tab={t('ontology.attributesTab', { count: ontology.attributes.length })} key="attributes">
            <Table
              columns={attributeColumns}
              dataSource={ontology.attributes}
              rowKey="id"
            />
          </TabPane>
          <TabPane tab={t('ontology.relationsTab', { count: ontology.relations.length })} key="relations">
            <Table
              columns={relationColumns}
              dataSource={ontology.relations}
              rowKey="id"
            />
          </TabPane>
          <TabPane tab={t('ontology.mappingsTab', { count: ontology.mappings.length })} key="mappings">
            <Table
              columns={mappingColumns}
              dataSource={ontology.mappings}
              rowKey="id"
            />
          </TabPane>
          <TabPane tab={t('ontology.rulesTab', { count: ontology.rules.length })} key="rules">
            <Table
              columns={ruleColumns}
              dataSource={ontology.rules}
              rowKey="id"
            />
          </TabPane>
          <TabPane tab={t('ontology.releaseGatesTab')} key="release">
            {/*
              The gate's verdict had no door: this tab listed what blocks a release, the card
              above listed what is ready, and there was no way to publish from the application
              at all -- while `ontologyApi.publish` sat unused in the client. A screen that
              shows a gate and offers no way through it is a screen that ends in a terminal.
            */}
            <Space style={{ marginBottom: 12 }} orientation="vertical" size={8}>
              <Space>
                <Popconfirm
                  title={t('ontology.publish')}
                  description={t('ontology.publishConfirm')}
                  okText={t('ontology.publishOk')}
                  cancelText={t('shell.common.cancel')}
                  onConfirm={() => void handlePublish()}
                  disabled={!canPublish}
                >
                  <Button
                    type="primary"
                    icon={<CloudUploadOutlined />}
                    loading={publishing}
                    disabled={!canPublish}
                  >
                    {ontology.ontology.status === 'published' ? t('ontology.isPublished') : t('ontology.publish')}
                  </Button>
                </Popconfirm>
                {blockers.length > 0 && (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {t('ontology.blockerHintPrefix', { count: blockers.length })}
                    <Typography.Text code>aletheia publish --force</Typography.Text>
                    {t('ontology.blockerHintSuffix')}
                  </Typography.Text>
                )}
              </Space>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {t('ontology.publishNote')}
              </Typography.Text>
            </Space>
            <Table
              columns={releaseGateColumns}
              dataSource={releaseReadiness?.gates || []}
              rowKey="code"
              pagination={false}
            />
          </TabPane>
          <TabPane tab={t('ontology.extensionsTab')} key="extensions">
            <ModellingExtensions
              ontologyId={ontology.ontology.id}
              objects={ontology.objects ?? []}
              readOnly={['published', 'reviewing'].includes(ontology.ontology.status)}
            />
          </TabPane>
        </Tabs>
      </Card>
    </div>
  );
};

export default OntologyDetailPage;
