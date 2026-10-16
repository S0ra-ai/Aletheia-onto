import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';
import dayjs, { Dayjs } from 'dayjs';
import { auditApi, ontologyApi, requestErrorMessage } from '../../api';
import type { AuditBlockedDecision, AuditEvent, AuditReport, AuditReportSection, AuditRuleEntry } from '../../types';
import { useT } from '../../i18n/locale';

const { Text, Paragraph } = Typography;
const { RangePicker } = DatePicker;

/**
 * The audit report: the questions an auditor arrives with, over a stated period.
 *
 * Distinct from the raw audit log beside it. A log answers "what happened recently"; this
 * answers "which published controls never fired", "which release gates were overridden" and
 * "how much of this period can be re-examined at all" -- and the last one bounds the other
 * two, since a conclusion with no explanation chain cannot be reviewed by anyone.
 *
 * The period is required, with no "everything" option, because the backend refuses one: a
 * report that does not describe its own coverage gets read as a statement about a period it
 * does not describe, and a finding attached to the wrong period is a wrong finding.
 */
const AuditReportPanel: React.FC = () => {
  const t = useT();
  const [range, setRange] = useState<[Dayjs, Dayjs]>(() => [dayjs().subtract(29, 'day').startOf('day'), dayjs()]);
  const [ontologyId, setOntologyId] = useState<number | undefined>();
  const [ontologies, setOntologies] = useState<{ value: number; label: string }[]>([]);
  const [sections, setSections] = useState<AuditReportSection[]>([]);
  const [report, setReport] = useState<AuditReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    // Both are supporting information; neither failing should hide the report itself.
    auditApi
      .sections()
      .then(setSections)
      .catch(() => undefined);
    ontologyApi
      .list()
      .then((items) =>
        setOntologies((items ?? []).map((item) => ({ value: item.id, label: `${item.name} v${item.version}` }))),
      )
      .catch(() => undefined);
  }, []);

  const run = useCallback(async (start: Dayjs, end: Dayjs, scope: number | undefined) => {
    setLoading(true);
    setError('');
    try {
      setReport(await auditApi.report(start.format('YYYY-MM-DD HH:mm:ss'), end.format('YYYY-MM-DD HH:mm:ss'), scope));
    } catch (caught) {
      setReport(null);
      setError(requestErrorMessage(caught, t('governance.generateFailed')));
    } finally {
      setLoading(false);
    }
  }, [t]);

  // Generate for the default period on open rather than waiting for a click: an empty
  // screen with a button on it tells the reader nothing about what the report contains.
  useEffect(() => {
    void run(dayjs().subtract(29, 'day').startOf('day'), dayjs(), undefined);
  }, [run]);

  const sectionAnswer = (key: string): string => sections.find((item) => item.section === key)?.answers ?? '';

  const ruleColumns = [
    // `whiteSpace: nowrap` rather than a narrow column: rule codes are long and
    // underscore-separated, and letting them wrap breaks them mid-token
    // ("payment_plan_paid_amount_non_ne / gative"), which is unreadable and unsearchable.
    { title: t('governance.column.code'), dataIndex: 'code', key: 'code', width: 340, render: (code: string) => <Text style={{ whiteSpace: 'nowrap' }}>{code}</Text> },
    { title: t('governance.column.name'), dataIndex: 'name', key: 'name', ellipsis: true },
    {
      title: t('governance.column.severity'),
      dataIndex: 'severity',
      key: 'severity',
      width: 100,
      render: (severity: string) => <Tag color={severity === 'blocking' ? 'red' : 'orange'}>{severity}</Tag>,
    },
    { title: t('governance.column.evaluations'), dataIndex: 'evaluations', key: 'evaluations', width: 100 },
  ];

  const eventColumns = [
    { title: t('governance.column.actor'), dataIndex: 'actor', key: 'actor' },
    { title: t('governance.column.action'), dataIndex: 'action', key: 'action', render: (action: string) => <Tag color="blue">{action}</Tag> },
    { title: t('governance.column.targetType'), dataIndex: 'target_type', key: 'target_type' },
    { title: t('governance.column.targetId'), dataIndex: 'target_id', key: 'target_id' },
    { title: t('governance.column.detail'), dataIndex: 'detail', key: 'detail', ellipsis: true },
    { title: t('governance.column.time'), dataIndex: 'created_at', key: 'created_at', width: 170 },
  ];

  const blockedColumns = [
    { title: t('governance.column.blockedDecisionId'), dataIndex: 'decision_id', key: 'decision_id' },
    { title: t('governance.column.type'), dataIndex: 'decision_type', key: 'decision_type' },
    { title: t('governance.column.object'), dataIndex: 'object_code', key: 'object_code' },
    { title: t('governance.column.instanceId'), dataIndex: 'instance_id', key: 'instance_id' },
    { title: t('governance.column.actor'), dataIndex: 'actor', key: 'actor' },
    { title: t('governance.column.time'), dataIndex: 'created_at', key: 'created_at', width: 170 },
  ];

  return (
    <>
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap align="end">
          <Space direction="vertical" size={0}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t('governance.reportRange')}
            </Text>
            <RangePicker
              showTime
              value={range}
              onChange={(value) => {
                if (value?.[0] && value[1]) setRange([value[0], value[1]]);
              }}
            />
          </Space>
          <Select
            allowClear
            placeholder={t('governance.allOntologies')}
            style={{ width: 220 }}
            value={ontologyId}
            onChange={setOntologyId}
            options={ontologies}
          />
          <Button type="primary" loading={loading} onClick={() => run(range[0], range[1], ontologyId)}>
            {t('governance.generateButton')}
          </Button>
        </Space>
        <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 8, marginBottom: 0 }}>
          {t('governance.rangePolicyLead')}
          <Text strong>{t('governance.rangePolicyStrong')}</Text>
          {t('governance.rangePolicyTail')}
        </Paragraph>
      </Card>

      {error && <Alert type="error" showIcon style={{ marginBottom: 16 }} message={t('governance.generateFailedTitle')} description={error} />}

      {report && (
        <>
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message={t('governance.reportPeriod', { start: report.period.start, end: report.period.end })}
            description={t('governance.reportScope', {
              scope: report.ontologyId ? t('governance.ontologyScope', { id: report.ontologyId }) : t('governance.allOntologies'),
              boundary: report.period.boundary,
            })}
          />

          {report.findings.length === 0 ? (
            <Alert
              type="success"
              showIcon
              style={{ marginBottom: 16 }}
              message={t('governance.noFindings')}
              description={t('governance.noFindingsDetail')}
            />
          ) : (
            report.findings.map((finding, index) => (
              <Alert
                key={`${finding.severity}-${index}`}
                type={finding.severity === 'blocker' ? 'error' : 'warning'}
                showIcon
                style={{ marginBottom: 12 }}
                message={finding.finding}
                description={finding.action}
              />
            ))
          )}

          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={12} md={6}>
              <Card size="small">
                <Statistic title={t('governance.statDecisions')} value={report.decisions.total} />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card size="small">
                <Statistic
                  title={t('governance.statEvaluations')}
                  value={report.coverage.evaluations}
                  suffix={report.model.failed ? t('governance.modelFailedSuffix', { count: report.model.failed }) : ''}
                />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card size="small">
                <Statistic
                  title={t('governance.statReviewable')}
                  value={report.coverage.ratio === null ? '—' : `${Math.round(report.coverage.ratio * 100)}%`}
                />
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {report.coverage.ratio === null
                    ? t('governance.ratioNoEvaluations')
                    : t('governance.ratioDetail', { withTrace: report.coverage.withTrace, evaluations: report.coverage.evaluations })}
                </Text>
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card size="small">
                <Statistic
                  title={t('governance.statNeverTriggered')}
                  value={report.rules.neverTriggered.length}
                  valueStyle={report.rules.neverTriggered.length ? { color: '#d4380d' } : undefined}
                />
              </Card>
            </Col>
          </Row>

          <Card size="small" title={t('governance.rulesCard')} style={{ marginBottom: 16 }}>
            {sectionAnswer('rules') && (
              <Paragraph type="secondary" style={{ fontSize: 12 }}>
                {sectionAnswer('rules')}
              </Paragraph>
            )}
            {report.rules.note && (
              <Alert type="info" showIcon style={{ marginBottom: 12 }} message={report.rules.note} />
            )}
            <Text strong>{t('governance.neverTriggered', { count: report.rules.neverTriggered.length })}</Text>
            <Table<AuditRuleEntry>
              size="small"
              rowKey="code"
              style={{ marginTop: 8, marginBottom: 16 }}
              dataSource={report.rules.neverTriggered}
              columns={ruleColumns}
              pagination={false}
              locale={{ emptyText: <Empty description={t('governance.rulesAllEvaluated')} /> }}
            />
            <Text strong>{t('governance.triggered', { count: report.rules.triggered.length })}</Text>
            <Table<AuditRuleEntry>
              size="small"
              rowKey="code"
              style={{ marginTop: 8 }}
              dataSource={report.rules.triggered}
              columns={ruleColumns}
              pagination={{ pageSize: 10, hideOnSinglePage: true }}
              locale={{ emptyText: <Empty description={t('governance.rulesNoneEvaluated')} /> }}
            />
          </Card>

          {report.governance.forcedPublications.length > 0 && (
            <Card size="small" title={t('governance.forcedCard')} style={{ marginBottom: 16 }}>
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 12 }}
                message={t('governance.forcedNote')}
              />
              <Table<AuditEvent>
                size="small"
                rowKey={(row) => `${row.created_at}-${row.action}-${row.target_id}`}
                dataSource={report.governance.forcedPublications}
                columns={eventColumns}
                pagination={false}
              />
            </Card>
          )}

          {report.decisions.blocked.length > 0 && (
            <Card size="small" title={t('governance.blockedCard')} style={{ marginBottom: 16 }}>
              <Paragraph type="secondary" style={{ fontSize: 12 }}>
                {t('governance.blockedNote')}
              </Paragraph>
              <Table<AuditBlockedDecision>
                size="small"
                rowKey="decision_id"
                dataSource={report.decisions.blocked}
                columns={blockedColumns}
                pagination={{ pageSize: 10, hideOnSinglePage: true }}
              />
            </Card>
          )}

          <Card size="small" title={t('governance.eventsCard', { count: report.governance.events.length })} style={{ marginBottom: 16 }}>
            {sectionAnswer('governance') && (
              <Paragraph type="secondary" style={{ fontSize: 12 }}>
                {sectionAnswer('governance')}
              </Paragraph>
            )}
            {report.governance.events.length === 0 ? (
              // Rendered even when empty, so "no governance events this period" is a claim
              // the reader can see. A card that disappears is indistinguishable from a
              // section that was never computed.
              <Empty description={t('governance.eventsEmpty')} />
            ) : (
              <Table<AuditEvent>
                size="small"
                rowKey={(row) => `${row.created_at}-${row.action}-${row.target_id}`}
                dataSource={report.governance.events}
                columns={eventColumns}
                pagination={{ pageSize: 10, hideOnSinglePage: true }}
              />
            )}
          </Card>

          <Row gutter={[16, 16]}>
            <Col xs={24} md={12}>
              <Card size="small" title={t('governance.byStatusCard')}>
                {Object.keys(report.decisions.byStatus).length === 0 ? (
                  <Empty description={t('governance.decisionsEmpty')} />
                ) : (
                  Object.entries(report.decisions.byStatus).map(([status, count]) => (
                    <div key={status} style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
                      <Tag color={status === 'approved' ? 'green' : status === 'blocked' ? 'red' : 'default'}>
                        {status}
                      </Tag>
                      <Text>{count}</Text>
                    </div>
                  ))
                )}
              </Card>
            </Col>
            <Col xs={24} md={12}>
              <Card size="small" title={t('governance.actorsCard')}>
                {Object.keys(report.actors.byActor).length === 0 ? (
                  <Empty description={t('governance.eventsNone')} />
                ) : (
                  // actor → action → count, not actor → count: the question is "who changed
                  // what", and flattening it to a total per actor throws away the "what".
                  Object.entries(report.actors.byActor).map(([actor, actions]) => (
                    <div key={actor} style={{ marginBottom: 8 }}>
                      <Text strong>{actor}</Text>
                      {Object.entries(actions).map(([action, count]) => (
                        <div
                          key={action}
                          style={{ display: 'flex', justifyContent: 'space-between', paddingLeft: 12, fontSize: 12 }}
                        >
                          <Text type="secondary">{action}</Text>
                          <Text type="secondary">{count}</Text>
                        </div>
                      ))}
                    </div>
                  ))
                )}
              </Card>
            </Col>
          </Row>
        </>
      )}
    </>
  );
};

export default AuditReportPanel;
