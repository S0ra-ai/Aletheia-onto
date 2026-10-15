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
      setError(requestErrorMessage(caught, '生成审计报表失败'));
    } finally {
      setLoading(false);
    }
  }, []);

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
    { title: '编码', dataIndex: 'code', key: 'code', width: 340, render: (code: string) => <Text style={{ whiteSpace: 'nowrap' }}>{code}</Text> },
    { title: '名称', dataIndex: 'name', key: 'name', ellipsis: true },
    {
      title: '严重级',
      dataIndex: 'severity',
      key: 'severity',
      width: 100,
      render: (severity: string) => <Tag color={severity === 'blocking' ? 'red' : 'orange'}>{severity}</Tag>,
    },
    { title: '求值次数', dataIndex: 'evaluations', key: 'evaluations', width: 100 },
  ];

  const eventColumns = [
    { title: '操作者', dataIndex: 'actor', key: 'actor' },
    { title: '操作', dataIndex: 'action', key: 'action', render: (action: string) => <Tag color="blue">{action}</Tag> },
    { title: '目标类型', dataIndex: 'target_type', key: 'target_type' },
    { title: '目标ID', dataIndex: 'target_id', key: 'target_id' },
    { title: '详情', dataIndex: 'detail', key: 'detail', ellipsis: true },
    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 170 },
  ];

  const blockedColumns = [
    { title: '判定编号', dataIndex: 'decision_id', key: 'decision_id' },
    { title: '类型', dataIndex: 'decision_type', key: 'decision_type' },
    { title: '业务对象', dataIndex: 'object_code', key: 'object_code' },
    { title: '实例ID', dataIndex: 'instance_id', key: 'instance_id' },
    { title: '操作者', dataIndex: 'actor', key: 'actor' },
    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 170 },
  ];

  return (
    <>
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap align="end">
          <Space direction="vertical" size={0}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              审计区间
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
            placeholder="全部本体"
            style={{ width: 220 }}
            value={ontologyId}
            onChange={setOntologyId}
            options={ontologies}
          />
          <Button type="primary" loading={loading} onClick={() => run(range[0], range[1], ontologyId)}>
            生成报表
          </Button>
        </Space>
        <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 8, marginBottom: 0 }}>
          不提供「全部时间」：覆盖范围不明的报表会被当作对某个区间的陈述，
          <Text strong>挂错区间的发现就是错的发现</Text>。区间为半开区间，起点闭、终点开。
        </Paragraph>
      </Card>

      {error && <Alert type="error" showIcon style={{ marginBottom: 16 }} message="生成失败" description={error} />}

      {report && (
        <>
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message={`报表区间：${report.period.start} → ${report.period.end}`}
            description={`作用范围：${report.ontologyId ? `本体 #${report.ontologyId}` : '全部本体'} · ${report.period.boundary}`}
          />

          {report.findings.length === 0 ? (
            <Alert
              type="success"
              showIcon
              style={{ marginBottom: 16 }}
              message="本期没有需要立刻跟进的发现"
              description="这不等于「一切正常」，只等于以下几类没有触发：从未求值的已发布规则、被覆盖的发布门禁、无解释链的求值、失败的模型调用。"
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
                <Statistic title="判定总数" value={report.decisions.total} />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card size="small">
                <Statistic
                  title="规则求值"
                  value={report.coverage.evaluations}
                  suffix={report.model.failed ? `（模型失败 ${report.model.failed}）` : ''}
                />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card size="small">
                <Statistic
                  title="可复核比例"
                  value={report.coverage.ratio === null ? '—' : `${Math.round(report.coverage.ratio * 100)}%`}
                />
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {report.coverage.ratio === null
                    ? '本期没有规则求值，比例无从谈起'
                    : `${report.coverage.withTrace} / ${report.coverage.evaluations} 次求值带解释链`}
                </Text>
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card size="small">
                <Statistic
                  title="从未求值的已发布规则"
                  value={report.rules.neverTriggered.length}
                  valueStyle={report.rules.neverTriggered.length ? { color: '#d4380d' } : undefined}
                />
              </Card>
            </Col>
          </Row>

          <Card size="small" title="规则触发情况" style={{ marginBottom: 16 }}>
            {sectionAnswer('rules') && (
              <Paragraph type="secondary" style={{ fontSize: 12 }}>
                {sectionAnswer('rules')}
              </Paragraph>
            )}
            {report.rules.note && (
              <Alert type="info" showIcon style={{ marginBottom: 12 }} message={report.rules.note} />
            )}
            <Text strong>从未求值（{report.rules.neverTriggered.length}）</Text>
            <Table<AuditRuleEntry>
              size="small"
              rowKey="code"
              style={{ marginTop: 8, marginBottom: 16 }}
              dataSource={report.rules.neverTriggered}
              columns={ruleColumns}
              pagination={false}
              locale={{ emptyText: <Empty description="本期所有已发布规则都参与过求值" /> }}
            />
            <Text strong>已求值（{report.rules.triggered.length}）</Text>
            <Table<AuditRuleEntry>
              size="small"
              rowKey="code"
              style={{ marginTop: 8 }}
              dataSource={report.rules.triggered}
              columns={ruleColumns}
              pagination={{ pageSize: 10, hideOnSinglePage: true }}
              locale={{ emptyText: <Empty description="本期没有规则参与过求值" /> }}
            />
          </Card>

          {report.governance.forcedPublications.length > 0 && (
            <Card size="small" title="覆盖发布门禁的发布" style={{ marginBottom: 16 }}>
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 12 }}
                message="覆盖门禁可以是正当的业务例外，但它不该需要审计去翻找"
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
            <Card size="small" title="被阻断的判定" style={{ marginBottom: 16 }}>
              <Paragraph type="secondary" style={{ fontSize: 12 }}>
                逐条列出而不是只给计数：一屏「40 条被阻断」回答不了「其中有没有被冤枉的」。
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

          <Card size="small" title={`治理事件（${report.governance.events.length}）`} style={{ marginBottom: 16 }}>
            {sectionAnswer('governance') && (
              <Paragraph type="secondary" style={{ fontSize: 12 }}>
                {sectionAnswer('governance')}
              </Paragraph>
            )}
            {report.governance.events.length === 0 ? (
              // Rendered even when empty, so "no governance events this period" is a claim
              // the reader can see. A card that disappears is indistinguishable from a
              // section that was never computed.
              <Empty description="本期没有发布、派生、门禁覆盖或配额调整" />
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
              <Card size="small" title="按状态统计判定">
                {Object.keys(report.decisions.byStatus).length === 0 ? (
                  <Empty description="本期没有判定" />
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
              <Card size="small" title="操作者活动">
                {Object.keys(report.actors.byActor).length === 0 ? (
                  <Empty description="本期没有审计事件" />
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
