// @vitest-environment jsdom
//
// Per-file rather than global: a pure test under jsdom is a slower pure test, and most of this
// suite is pure. This one renders components, so it asks for the DOM it needs.
import React from 'react';
import { describe, expect, it, vi, afterEach } from 'vitest';
import { render, cleanup, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { LocaleProvider } from '../i18n/locale';
import MappingList from '../pages/mapping/MappingList';
import RuleList from '../pages/rules/RuleList';
import OntologyList from '../pages/ontology/OntologyList';
import DataSourceList from '../pages/datasource/DataSourceList';
import PermissionManager from '../pages/permission/PermissionManager';
import Governance from '../pages/governance';
import WorkflowManager from '../pages/workflow/WorkflowManager';
import BackupManager from '../pages/backup/BackupManager';
import TenancyManager from '../pages/tenancy/TenancyManager';

/**
 * The cells, rendered and read.
 *
 * **Every "this column is blank in every row" defect this project has had is the same shape**:
 * antd draws nothing for a `dataIndex` the row does not carry. A screen declaring `ruleType`
 * against an endpoint sending `rule_type` renders an empty cell and nothing fails -- the types
 * check out, the linter sees a valid string, and the request succeeded. Seven of them were found
 * by hand, one at a time, by whoever happened to open the right page.
 *
 * `scripts/ui_smoke.py` reports them now, but it drives a real browser against a live instance,
 * which makes it a diagnostic somebody runs rather than a gate on every change. This does the
 * same reading in process. What it cannot see is a page that fails to mount, a route serving the
 * wrong application, or anything about layout -- those stay with the browser sweeps.
 *
 * ## A test is only as good as the payload it is handed
 *
 * The field names below come from `tests/test_frontend_type_agreement.py::CHARTED_RESPONSES`,
 * which is the authority for what each endpoint sends; read it when one of these needs changing.
 * **The first version of this file made both of the mistakes this suite exists to catch**, and
 * in the same direction: the fixtures were written from memory in `snake_case` while
 * `/ontologies/{id}/mappings` sends camelCase, and the mapping-type values were invented
 * (`column` / `table`) rather than read off the vocabulary (`column_to_attribute` /
 * `table_to_object`). That produced three blank-column findings and one raw-enum finding against
 * a page that was correct -- a false report, from a fixture no deployment would ever send.
 */
const WIRE_MAPPINGS = [
  {
    mappingType: 'column_to_attribute',
    sourceTable: 'contract',
    sourceColumn: 'credit_status',
    targetObjectCode: 'contract',
    targetAttributeCode: 'creditStatus',
    confidence: 0.92,
    status: 'pending',
    reviewer: '',
  },
  {
    mappingType: 'table_to_object',
    sourceTable: 'party',
    sourceColumn: '',
    targetObjectCode: 'party',
    targetAttributeCode: '',
    confidence: 0.81,
    status: 'confirmed',
    reviewer: '业务专家',
  },
];

const WIRE_RULES = [
  {
    id: 1,
    code: 'refund_window_check',
    name: '退款窗口检查',
    ruleType: 'validation',
    scopeObjectCode: 'contract',
    expression: 'delivered_days_ago <= 15',
    severity: 'blocking',
    naturalLanguage: '交付超过十五天不得退款。',
    status: 'published',
  },
  {
    id: 2,
    code: 'amount_ceiling',
    name: '金额上限',
    ruleType: 'risk',
    scopeObjectCode: 'contract',
    expression: 'amount <= 1000000',
    severity: 'warning',
    naturalLanguage: '金额超过一百万需人工复核。',
    status: 'draft',
  },
];

const WIRE_ONTOLOGIES = [
  { id: 1, name: '合同管理', domain: '合同管理', version: '0.1.0', status: 'draft', objectCount: 4 },
];

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api');
  const page = (items: unknown[]) => ({
    items,
    pagination: { limit: 50, offset: 0, total: items.length, hasMore: false },
  });
  return {
    ...actual,
    ontologyApi: {
      list: vi.fn(async () => WIRE_ONTOLOGIES),
      getMappings: vi.fn(async () => page(WIRE_MAPPINGS)),
      getRules: vi.fn(async () => page(WIRE_RULES)),
    },
  };
});

afterEach(cleanup);

function renderPage(component: React.ReactElement, route = '/') {
  return render(
    <LocaleProvider>
      <MemoryRouter initialEntries={[route]}>{component}</MemoryRouter>
    </LocaleProvider>,
  );
}

/**
 * Wait until a table holds data rows, and return one table's worth of them.
 *
 * Not `findAllByRole('row')`, which is how the first version of this file passed against
 * nothing: antd renders a header row and a placeholder before the fetch resolves, so the query
 * matches immediately and the assertions then run over an empty tbody -- the same "a scan that
 * saw nothing reported health" failure `scripts/ui_smoke.py` learned about the hard way.
 *
 * **Scoped to one table, and that is not a detail.** The first version read `th` elements and
 * `tr` elements from the whole document, which is right only while a page has exactly one table.
 * On the permission page -- four tabs, each with its own table -- it took the headers of one and
 * the rows of another and reported a column called 描述 as blank that no row had ever been asked
 * for. A cross-table misalignment reads exactly like a real finding.
 */
interface RenderedTable {
  headers: string[];
  rows: Element[];
}

async function waitForRows(): Promise<RenderedTable> {
  await waitFor(() => {
    if (document.querySelectorAll('.ant-table-tbody tr.ant-table-row').length === 0) {
      throw new Error('还没有数据行');
    }
  });
  const table = document.querySelector('.ant-table-wrapper') ?? document;
  return {
    headers: Array.from(table.querySelectorAll('.ant-table-thead th')).map((th) =>
      (th.textContent ?? '').trim(),
    ),
    rows: Array.from(table.querySelectorAll('.ant-table-tbody tr.ant-table-row')),
  };
}

/**
 * Column titles whose every cell is empty, over the rows actually drawn.
 *
 * `:first-child` is deliberately not used to find the first data row: antd's tbody begins with a
 * measurement row, so `tr.ant-table-row:first-child` matches nothing and reports every column as
 * blank. A column holding a control rather than text is excluded by name -- a cell with a button
 * in it legitimately has no text, and counting it would be a standing false positive.
 */
/**
 * What a cell shows when it has no value to show.
 *
 * A column whose every cell is one of these carries exactly as little information as a column
 * that is empty -- and the fallback is what hides it. `render: (domain) => domain || '-'` draws a
 * dash in every row when the field was renamed, and the first version of this file reported
 * nothing: the cell has text. Planting a rename on the ontology list's domain column and watching
 * both this and `scripts/ui_smoke.py` stay green is how the blind spot was found, and both now
 * treat these as empty.
 *
 * `ANTD_SKELETON` is the same idea for the other direction: a cell still showing antd's own
 * placeholder has not finished loading, and counting it as content would hide a column that never
 * gets one.
 */
const PLACEHOLDERS = new Set(['', '-', '—', '–', '‑', '暂无', '暂无数据', 'N/A']);

/**
 * An icon carries meaning without carrying text, and `textContent` cannot see it.
 *
 * `scripts/ui_smoke.py` has treated an icon-only cell as content from the start, with the same
 * reason written beside it: a tick and a cross are the whole content of a permission cell. This
 * file excluded buttons and switches and **not** icons, so the workflow's transitions table --
 * where the `→` column renders a `<RightOutlined />` between 来源 and 目标 -- was reported as a
 * blank column here and as a filled one there.
 *
 * Two checks disagreeing about what "empty" means is worse than either being wrong: whichever
 * one a reader runs decides whether the column is a defect, and the both-green case teaches them
 * the wrong one is right. The sweeps are the authority on what a browser draws, so this follows.
 */
function hasVisibleContent(cell: Element | undefined): boolean {
  if (!cell) return false;
  if (cell.querySelector('button, .ant-switch, .anticon')) return true;
  return !PLACEHOLDERS.has((cell.textContent ?? '').trim());
}

function blankColumns(table: RenderedTable): string[] {
  const { headers, rows } = table;
  const cellCount = rows[0]?.querySelectorAll('td').length ?? 0;
  const blank: string[] = [];
  for (let index = 0; index < cellCount; index += 1) {
    const cells = rows.map((row) => row.querySelectorAll('td')[index]);
    if (cells.some(hasVisibleContent)) continue;
    blank.push(headers[index] ?? `#${index + 1}`);
  }
  return blank;
}

describe('MappingList', () => {
  it('renders a value in every cell of every column', async () => {
    renderPage(<MappingList />);
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_MAPPINGS.length);
    expect(blankColumns(table)).toEqual([]);
  });

  it('names the mapping type rather than printing the backend word', async () => {
    renderPage(<MappingList />);
    const table = await waitForRows();

    const body = table.rows.map((row) => row.textContent ?? '').join(' ');
    // The vocabulary values are identifiers; the console has a word for each of them. Asserting
    // on the rendered body rather than on `.ant-tag` catches the value wherever it lands.
    expect(body).not.toContain('column_to_attribute');
    expect(body).not.toContain('table_to_object');
    expect(body).toContain('列 → 业务属性');
  });
});

describe('RuleList', () => {
  it('renders a value in every cell of every column', async () => {
    renderPage(<RuleList />);
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_RULES.length);
    expect(blankColumns(table)).toEqual([]);
  });

  it('says the rule type and severity in words', async () => {
    renderPage(<RuleList />);
    const table = await waitForRows();

    const body = table.rows.map((row) => row.textContent ?? '').join(' ');
    expect(body).not.toContain('validation');
    expect(body).not.toContain('blocking');
    // The Chinese side of the dictionary, since the provider defaults to it.
    expect(body).toContain('阻断');
  });
});

// -- The rest of the tables that keep breaking -------------------------------------------------

const WIRE_ONTOLOGY_LIST = [
  { id: 1, name: '合同管理', domain: '合同管理', version: '0.1.0', status: 'draft', objectCount: 4 },
  { id: 2, name: '设备台账', domain: '设备管理', version: '0.1.0', status: 'published', objectCount: 6 },
];

const WIRE_DATA_SOURCES = [
  {
    id: 1,
    name: '合同管理样例系统',
    sourceType: 'sqlite',
    connectionUri: '/tmp/legacy_contracts.sqlite3',
    domain: '合同管理',
    systemCategory: 'database+api',
    capabilities: ['database'],
  },
];

const WIRE_ROLES = [
  {
    id: 1,
    code: 'admin',
    name: '管理员',
    // `permission_role.description` is `not null default ''`; the first version of this fixture
    // left it out and the table's 描述 column read as blank -- the third time in this file that
    // a fixture written from memory produced a finding about a page that was correct.
    description: '平台内置，不可删除',
    is_system: 1,
    created_at: '2026-01-01',
  },
];

/**
 * Wire spelling, run through the real `normalizePolicy` by the mock below.
 *
 * This is the table the changelog calls the worst one: **all seven columns blanked on twenty
 * rows**, on the screen that answers "who may do what" -- the one a permission change is made
 * from. The route returns `dict(row)` with `can_read`/`can_write`/`can_execute`/`can_delete`,
 * the table asks for `canRead`/`canWrite`/`canExecute`/`canDelete`, and the normaliser is the
 * only thing between them.
 *
 * So the fixture is the *wire* shape and the mock runs the real function. Writing it already
 * normalised would test the columns and leave the translation -- the half that actually broke --
 * covered by nothing but the fact that it happened to work when the file was written.
 */
const WIRE_POLICIES = [
  {
    id: 1,
    role_id: 1,
    role_code: 'admin',
    role_name: '管理员',
    object_code: 'contract',
    can_read: 1,
    can_write: 1,
    can_execute: 1,
    can_delete: 1,
    filter_expression: '',
    description: '全部权限',
  },
  {
    id: 2,
    role_id: 2,
    role_code: 'analyst',
    role_name: '分析师',
    object_code: 'party',
    can_read: 1,
    can_write: 0,
    can_execute: 0,
    can_delete: 0,
    filter_expression: '',
    description: '只读',
  },
];

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api');
  // The real normalisers, on wire-shaped fixtures. Mocking the API as if the client received
  // the normalised shape would leave the translation itself untested -- rename a key inside
  // `normalizeTool` and every test here would still pass while the column went blank.
  const { normalizeTool, normalizeToolExecution, normalizeWorkflow, normalizePolicy, normalizeRole } =
    await vi.importActual<typeof import('../api/normalise')>('../api/normalise');
  const page = (items: unknown[]) => ({
    items,
    pagination: { limit: 50, offset: 0, total: items.length, hasMore: false },
  });
  return {
    ...actual,
    ontologyApi: {
      list: vi.fn(async () => WIRE_ONTOLOGY_LIST),
      getMappings: vi.fn(async () => page(WIRE_MAPPINGS)),
      getRules: vi.fn(async () => page(WIRE_RULES)),
    },
    dataSourceApi: { list: vi.fn(async () => WIRE_DATA_SOURCES) },
    industryBlueprintApi: { list: vi.fn(async () => []) },
    permissionApi: {
      getRoles: vi.fn(async () => WIRE_ROLES.map(normalizeRole)),
      getPolicies: vi.fn(async () => WIRE_POLICIES.map(normalizePolicy)),
    },
    toolApi: {
      list: vi.fn(async () => WIRE_TOOLS.map(normalizeTool)),
      getPendingReviews: vi.fn(async () => WIRE_PENDING_REVIEWS.map(normalizeToolExecution)),
    },
    ssoApi: { status: vi.fn(async () => null) },
    governanceApi: {
      getAuditLog: vi.fn(async () => WIRE_AUDIT_LOGS),
      getModelInvocations: vi.fn(async () => WIRE_MODEL_INVOCATIONS),
      getDecisions: vi.fn(async () => WIRE_DECISIONS),
    },
    workflowApi: {
      list: vi.fn(async () => WIRE_WORKFLOWS.map(normalizeWorkflow)),
      get: vi.fn(async () => normalizeWorkflow(WIRE_WORKFLOWS[0])),
    },
    backupApi: { list: vi.fn(async () => WIRE_BACKUPS) },
    tenancyApi: {
      list: vi.fn(async () => WIRE_TENANTS),
      // The page asks what quota resources exist so the editor can offer them; it is not part
      // of the table, and an empty list is a deployment with no declared quotas.
      quotaResources: vi.fn(async () => []),
    },
  };
});

describe('OntologyList', () => {
  it('renders a value in every cell of every column', async () => {
    renderPage(<OntologyList />);
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_ONTOLOGY_LIST.length);
    expect(blankColumns(table)).toEqual([]);
  });
});

describe('DataSourceList', () => {
  it('renders a value in every cell of every column', async () => {
    renderPage(<DataSourceList />);
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_DATA_SOURCES.length);
    expect(blankColumns(table)).toEqual([]);
  });
});

describe('PermissionManager', () => {
  it('renders a value in every cell of the roles table', async () => {
    renderPage(<PermissionManager />);
    const table = await waitForRows();
    expect(blankColumns(table)).toEqual([]);
  });

  it('renders a value in every cell of the policies table', async () => {
    // The one that answered "who may do what" with twenty rows of nothing.
    renderPage(<PermissionManager />, '/?tab=policies');
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_POLICIES.length);
    expect(blankColumns(table)).toEqual([]);
  });

  it('shows the grant and the refusal as different values, not two crosses', async () => {
    /** The four permission columns draw a tick or a cross and **no text at all**.
     *
     * `canRead` and the other three fall back to `0`, so a normaliser reading the wrong key
     * produces a table where every cell is a cross: every cell filled, every value wrong, and
     * `blankColumns` satisfied -- the icons are content, which is the rule that keeps this from
     * being a false positive and also the rule that makes it a blind spot.
     *
     * Counting the two icons is the only reading that tells "granted" from "refused". Rows with
     * one grant and one refusal are here on purpose: a payload where everything is permitted
     * would pass a check that only counted ticks.
     */
    renderPage(<PermissionManager />, '/?tab=policies');
    const table = await waitForRows();

    const counts = table.rows.map((row) => ({
      text: row.textContent ?? '',
      granted: row.querySelectorAll('.anticon-check-circle').length,
      refused: row.querySelectorAll('.anticon-close-circle').length,
    }));

    // Found by role *code*: the role column draws `r.roleCode || r.roleId` rather than the
    // name, which is itself worth knowing -- the table says `admin`, not 管理员.
    const admin = counts.find((row) => row.text.includes('admin'));
    const analyst = counts.find((row) => row.text.includes('analyst'));
    expect(admin, '没有找到管理员的策略行').toBeDefined();
    expect(analyst, '没有找到分析师的策略行').toBeDefined();
    expect(admin?.granted).toBe(4);
    expect(admin?.refused).toBe(0);
    expect(analyst?.granted).toBe(1);
    expect(analyst?.refused).toBe(3);
  });
});

// -- The governance page: four tabs, three tables, two wire conventions ------------------------

/**
 * Every field here is snake_case, and that is not a style choice.
 *
 * `/governance/audit-log` and `/governance/model-invocations` return `dict(row)` -- raw column
 * names, no normaliser in between. Three audit columns and four invocation columns asked for
 * camelCase for as long as it took somebody to open the page, and drew nothing for every row
 * while lint, types and the whole suite passed. The spellings below come from
 * `tests/test_frontend_type_agreement.py::CHARTED_RESPONSES`, which is the contract; reading
 * them off the page instead would only confirm that the page agrees with itself.
 */
const WIRE_AUDIT_LOGS = [
  {
    actor: 'admin',
    action: 'ontology.publish',
    target_type: 'ontology',
    target_id: '1',
    detail: '{"version": "0.1.0"}',
    created_at: '2026-01-02 09:15:00',
  },
  {
    actor: 'analyst',
    action: 'mapping.confirm',
    target_type: 'semantic_mapping',
    target_id: '42',
    detail: '{"confidence": 0.92}',
    created_at: '2026-01-02 09:20:00',
  },
];

const WIRE_MODEL_INVOCATIONS = [
  {
    provider: 'openai-compatible',
    model: 'gpt-4o-mini',
    purpose: 'ontology_draft',
    prompt_tokens: 812,
    completion_tokens: 344,
    total_tokens: 1156,
    status: 'success',
    created_at: '2026-01-02 09:16:00',
  },
  {
    provider: 'openai-compatible',
    model: 'gpt-4o-mini',
    purpose: 'natural_language_query',
    prompt_tokens: 511,
    completion_tokens: 90,
    total_tokens: 601,
    status: 'failed',
    created_at: '2026-01-02 09:17:00',
  },
];

/**
 * This table's fields *are* camelCase, because `decisions.py::_decision_row` sends both
 * spellings of each one. Two tables on one screen with two conventions is the reason this page
 * is worth a test: the mistake is invisible, and the page next to it teaches the wrong lesson.
 *
 * `recommendationCode` is the half the renderer reads -- it goes through
 * `codedText(t, 'semantic.recommendation.<code>', ...)`, so a decision whose code is dropped
 * shows the server's Chinese sentence on an English screen. The second row has no code, which
 * is what a record written before that column existed looks like.
 */
const WIRE_DECISIONS = [
  {
    decisionId: '9',
    decisionType: 'operation',
    status: 'approved',
    objectCode: 'contract',
    instanceId: '1',
    operationCode: 'submit_contract',
    recommendation: '未发现阻断或风险规则，允许进入后续自动化流程。',
    recommendationCode: 'recommendation_approved',
    createdAt: '2026-01-02 09:18:00',
  },
  {
    decisionId: '8',
    decisionType: 'consistency',
    status: 'review',
    objectCode: 'party',
    instanceId: '2',
    operationCode: 'verify_party',
    recommendation: '存在风险或警告，应进入人工复核或触发后续治理流程。',
    recommendationCode: '',
    createdAt: '2026-01-02 09:19:00',
  },
];

describe('Governance', () => {
  it('renders a value in every cell of the audit-log table', async () => {
    // The default tab, and the one whose columns asked for camelCase for the longest.
    renderPage(<Governance />);
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_AUDIT_LOGS.length);
    expect(blankColumns(table)).toEqual([]);
  });

  it('renders a value in every cell of the model-invocation table', async () => {
    renderPage(<Governance />, '/?tab=invocations');
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_MODEL_INVOCATIONS.length);
    expect(blankColumns(table)).toEqual([]);
  });

  it('renders a value in every cell of the decisions table', async () => {
    renderPage(<Governance />, '/?tab=decisions');
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_DECISIONS.length);
    expect(blankColumns(table)).toEqual([]);
  });

  it('says the recommendation in the reader’s language when it has a code', async () => {
    renderPage(<Governance />, '/?tab=decisions');
    const table = await waitForRows();

    const body = table.rows.map((row) => row.textContent ?? '').join(' ');
    // The first row carries a code, so its sentence is the console's; the second does not, so
    // it keeps the server's. Asserting both is the point -- a renderer that ignored the code
    // would still show *something*, and this is the only way to see which.
    expect(body).toContain('允许进入后续自动化流程');
    expect(body).not.toContain('semantic.recommendation');
  });
});

// -- The two tables whose fields the client translates on the way in ---------------------------

/**
 * These fixtures are in the **wire** spelling, and the mock runs them through the real
 * normaliser.
 *
 * `/tools` and `/tools/pending-reviews` return `dict(row)` -- `tool_type`, `risk_level`,
 * `duration_ms` -- while the tables ask for `toolType`, `riskLevel`, `durationMs`. The link
 * between the two is a normaliser, so a fixture written in the normalised shape would test the
 * columns and nothing else: rename a key inside `normalizeTool` and this file would still pass
 * while the column went blank.
 *
 * Feeding the wire shape through the real function is the only version that covers both, and it
 * is what the rest of this file cannot do -- `/governance/*` sends camelCase and snake_case
 * side by side, with no translation to get wrong.
 */
const WIRE_TOOLS = [
  {
    id: 1,
    code: 'submit_contract',
    name: '提交合同',
    description: '把一份合同推进到已生效状态。',
    tool_type: 'mutation',
    risk_level: 'high',
    requires_review: 1,
    status: 'published',
    created_at: '2026-01-02 09:00:00',
  },
  {
    id: 2,
    code: 'query_contract',
    name: '查询合同',
    description: '按主键读取一份合同。',
    tool_type: 'query',
    risk_level: 'low',
    requires_review: 0,
    status: 'published',
    created_at: '2026-01-02 09:01:00',
  },
];

const WIRE_PENDING_REVIEWS = [
  {
    id: 7,
    tool_code: 'submit_contract',
    agent_role: 'analyst',
    object_code: 'contract',
    instance_id: '1',
    status: 'pending',
    duration_ms: 42,
    created_at: '2026-01-02 09:30:00',
  },
];

const WIRE_WORKFLOWS = [
  {
    id: 1,
    ontology_id: 1,
    object_code: 'contract',
    name: '合同生命周期',
    initial_state: 'draft',
    status: 'published',
    created_at: '2026-01-02 08:00:00',
    states: [
      { code: 'draft', name: '草稿', is_terminal: 0, color: 'default', sort_order: 1 },
      { code: 'effective', name: '已生效', is_terminal: 1, color: 'green', sort_order: 2 },
    ],
    transitions: [
      {
        action_code: 'submit_contract',
        from_state: 'draft',
        to_state: 'effective',
        name: '提交',
        guard_expression: 'amount > 0',
        requires_review: 1,
      },
    ],
  },
];

describe('PermissionManager, the tools and review tables', () => {
  it('renders a value in every cell of the registered-tools table', async () => {
    // Eight columns, every one of which drew nothing until the normaliser was written.
    renderPage(<PermissionManager />, '/?tab=tools');
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_TOOLS.length);
    expect(blankColumns(table)).toEqual([]);
  });

  it('renders a value in every cell of the pending-executions table', async () => {
    renderPage(<PermissionManager />, '/?tab=reviews');
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_PENDING_REVIEWS.length);
    expect(blankColumns(table)).toEqual([]);
  });

  it('shows the duration the server sent, not the zero a broken normaliser falls back to', async () => {
    /** `normalizeToolExecution` writes `item.durationMs ?? item.duration_ms ?? 0`.
     *
     * The `?? 0` is right -- a row recorded before the column existed has no duration, and a
     * cell reading `0ms` is truer than a blank one. What it also does is **hide the defect that
     * matters**: rename the key the normaliser reads and every row renders `0ms`, which is
     * plausible, non-empty text that `blankColumns` cannot report and that a reader would take
     * for a fast query.
     *
     * Found by planting exactly that rename and watching the blank-cell assertions stay green.
     * So this asserts the value rather than the presence of one -- the same lesson the sweeps
     * learned about a column of dashes, in the one place a dash is a number.
     */
    renderPage(<PermissionManager />, '/?tab=reviews');
    const table = await waitForRows();

    const body = table.rows.map((row) => row.textContent ?? '').join(' ');
    expect(body).toContain(`${WIRE_PENDING_REVIEWS[0].duration_ms}ms`);
    expect(body).not.toContain('0ms');
  });
});

describe('WorkflowManager', () => {
  it('renders a value in every cell of the workflow list', async () => {
    renderPage(<WorkflowManager />);
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_WORKFLOWS.length);
    expect(blankColumns(table)).toEqual([]);
  });

  it('renders a value in every cell of the transitions table the details button opens', async () => {
    // `normalizeWorkflow` spreads `...item` and normalises the nested rows separately. The
    // first version spread and passed `item.transitions` through, so the definition rows above
    // were translated and the transition rows below were blank -- one table's worth of columns
    // hidden behind another table working.
    renderPage(<WorkflowManager />);
    const list = await waitForRows();
    expect(blankColumns(list)).toEqual([]);

    // The transitions are a second table on the same screen, opened by the details action --
    // the first button in the row, and the reason this test does not stop at the list.
    (list.rows[0].querySelector('button') as HTMLElement).click();

    await waitFor(() => {
      if (document.querySelectorAll('.ant-table-wrapper').length < 2) {
        throw new Error('详情还没有渲染出状态转换表');
      }
    });
    const transitions = document.querySelectorAll('.ant-table-wrapper')[1];
    const rendered = {
      headers: Array.from(transitions.querySelectorAll('.ant-table-thead th')).map((th) =>
        (th.textContent ?? '').trim(),
      ),
      rows: Array.from(transitions.querySelectorAll('.ant-table-tbody tr.ant-table-row')),
    };
    expect(rendered.rows.length).toBe(WIRE_WORKFLOWS[0].transitions.length);
    expect(blankColumns(rendered)).toEqual([]);
  });
});

// -- Two more screens whose tables nobody had read --------------------------------------------

/**
 * `/admin/backup/list` returns `dict(row)` -- `name`, `size`, `created_at`, nothing else.
 *
 * The date column is why this table is worth reading. The platform stores instants in UTC with
 * no offset, and `new Date("2026-10-15 19:12:07")` is parsed by a browser as **local** time, so
 * every row was displayed shifted by the reader's offset. That was fixed by appending `Z` before
 * parsing -- and then the archive's own `created_at`, which is written with `isoformat()` and
 * already carries `+00:00`, produced `+00:00Z` and read "Invalid Date". Both shapes are in the
 * fixture because either one alone passes against a renderer that only handles it.
 *
 * `size` is a number formatted into B/KB/MB; a missing value would draw `NaN B`.
 */
const WIRE_BACKUPS = [
  { name: 'nightly-2026-01-02.sqlite3', size: 204800, created_at: '2026-01-02 09:15:00' },
  // The name deliberately does not repeat the timestamp: the assertion below is that the raw
  // `created_at` does not reach the screen, and a name carrying the same characters would make
  // it fail for the wrong reason.
  { name: 'before-restore-0042.sqlite3', size: 512, created_at: '2026-01-02T09:20:00+00:00' },
];

/**
 * `/tenants` sends `{items: [{tenant, schema}]}` and nothing else.
 *
 * Multi-tenancy is opt-in, so an empty list on a single-tenant deployment is the expected
 * answer -- which is exactly why the empty state must not be mistaken for a table that failed
 * to render. Two tenants here so the table has rows to read.
 */
const WIRE_TENANTS = {
  items: [
    { tenant: 'acme', schema: 'tenant_acme' },
    { tenant: 'globex', schema: 'tenant_globex' },
  ],
};

describe('BackupManager', () => {
  it('renders a value in every cell of the backup table', async () => {
    renderPage(<BackupManager />);
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_BACKUPS.length);
    expect(blankColumns(table)).toEqual([]);
  });

  it('reads both timestamp shapes the two writers produce', async () => {
    /** The list endpoint writes `YYYY-MM-DD HH:MM:SS` (UTC, bare) and the archive's own config
     * writes `isoformat()` (`+00:00`). Appending `Z` to the second gives `+00:00Z`, which parses
     * to nothing -- the column read `Invalid Date` for every archive the current release wrote.
     * A blank-cell check cannot see that: `Invalid Date` is text.
     */
    renderPage(<BackupManager />);
    const table = await waitForRows();

    const body = table.rows.map((row) => row.textContent ?? '').join(' ');
    expect(body).not.toContain('Invalid Date');
    // The stronger half: when parsing fails the renderer falls back to the raw value, so the
    // cell still has text and `Invalid Date` never appears -- the ISO string itself is what a
    // regression leaves on screen. `toLocaleString()` cannot produce it.
    expect(body).not.toContain(WIRE_BACKUPS[1].created_at);
    expect(body).toContain('KB'); // 204800 bytes, formatted rather than raw
  });
});

describe('TenancyManager', () => {
  it('renders a value in every cell of the tenant table', async () => {
    renderPage(<TenancyManager />);
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_TENANTS.items.length);
    expect(blankColumns(table)).toEqual([]);
  });
});
