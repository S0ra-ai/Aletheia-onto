// @vitest-environment jsdom
//
// Per-file rather than global: a pure test under jsdom is a slower pure test, and most of this
// suite is pure. This one renders components, so it asks for the DOM it needs.
import React from 'react';
import { describe, expect, it, vi, afterEach } from 'vitest';
import { render, cleanup, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

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
import OntologyDetail from '../pages/ontology/OntologyDetail';
import KnowledgeBase from '../pages/knowledge/KnowledgeBase';
import FeedbackConsole from '../pages/feedback/FeedbackConsole';
import AuditReportPanel from '../pages/governance/AuditReportPanel';
import DataSourceDetail from '../pages/datasource/DataSourceDetail';
import ModellingExtensions from '../pages/ontology/ModellingExtensions';
import SemanticService from '../pages/semantic';
import InstanceDrawer from '../pages/objects/InstanceDrawer';
import Workbench from '../pages/workbench';

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

// `WIRE_ONTOLOGIES` lived here, used only by the first of the two duplicate `vi.mock` blocks.
// Removing the duplicate left it unused, and `tsc` said so -- which is the compiler doing the
// job the duplicate had quietly prevented.

// **One `vi.mock('../api')` in this file, and the second one used to be here.**
//
// The file was grown in two rounds -- first the mapping and rule queues, then everything else --
// and each round added its own mock. Two factories for one module path is not "both apply":
// which one wins is undefined, and it changed with the module graph. In CI the first won, so
// `dataSourceApi`, `permissionApi`, `backupApi`, `tenancyApi` and the rest fell through to the
// real client, every page's fetch rejected, and 23 of 27 tests failed with 「还没有数据行」 and an
// antd error toast. Locally the second won and everything passed.
//
// The tell was that the first four tests passed: they are the ones that need only `ontologyApi`,
// which both factories provided. A suite whose failures line up with which mock block won is
// reporting the duplicate, not the pages.

afterEach(cleanup);

function renderPage(component: React.ReactElement, route = '/') {
  return render(
    <LocaleProvider>
      <MemoryRouter initialEntries={[route]}>{component}</MemoryRouter>
    </LocaleProvider>,
  );
}

/**
 * The same, under a matching `<Route>`, for a page that reads `useParams`.
 *
 * `MemoryRouter initialEntries` alone does not populate `useParams`: the parameter comes from a
 * route *match*, not from the address bar. `OntologyDetail` reads `:id` that way, so rendering
 * it without a Route leaves `id` undefined and the page short-circuits to `notFound` -- which is
 * a table that renders nothing, and the assertions would then pass on an empty document.
 */
function renderRouted(component: React.ReactElement, entry: string, path: string) {
  return render(
    <LocaleProvider>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path={path} element={component} />
        </Routes>
      </MemoryRouter>
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

/**
 * Wait until the page has drawn `count` tables, then read each one on its own.
 *
 * `waitForRows` takes the first `.ant-table-wrapper` in the document, which is right only while
 * a page has one table. The knowledge page has two side by side, and the workflow page opens a
 * second when its details action is used -- reading "the first table" there would silently check
 * one and ignore the other.
 */
async function waitForTables(count: number): Promise<RenderedTable[]> {
  await waitFor(() => {
    if (document.querySelectorAll('.ant-table-wrapper').length < count) {
      throw new Error(`只渲染了 ${document.querySelectorAll('.ant-table-wrapper').length} 张表，期望 ${count}`);
    }
    if (document.querySelectorAll('.ant-table-tbody tr.ant-table-row').length === 0) {
      throw new Error('还没有数据行');
    }
  });
  return Array.from(document.querySelectorAll('.ant-table-wrapper'))
    .slice(0, count)
    .map((table) => ({
      headers: Array.from(table.querySelectorAll('.ant-table-thead th')).map((th) => (th.textContent ?? '').trim()),
      rows: Array.from(table.querySelectorAll('.ant-table-tbody tr.ant-table-row')),
    }));
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
  const {
    normalizeTool,
    normalizeToolExecution,
    normalizeWorkflow,
    normalizePolicy,
    normalizeRole,
    normalizeSourceTable,
    normalizeSourceApi,
  } =
    await vi.importActual<typeof import('../api/normalise')>('../api/normalise');
  const page = (items: unknown[]) => ({
    items,
    pagination: { limit: 50, offset: 0, total: items.length, hasMore: false },
  });
  return {
    ...actual,
    ontologyApi: {
      list: vi.fn(async () => WIRE_ONTOLOGY_LIST),
      eventTypes: vi.fn(async () => WIRE_EVENT_TYPES),
      get: vi.fn(async () => WIRE_ONTOLOGY_DETAIL),
      getReleaseReadiness: vi.fn(async () => WIRE_RELEASE_READINESS),
      getMappings: vi.fn(async () => page(WIRE_MAPPINGS)),
      getRules: vi.fn(async () => page(WIRE_RULES)),
    },
    dataSourceApi: {
      list: vi.fn(async () => WIRE_DATA_SOURCES),
      getTables: vi.fn(async () => WIRE_SOURCE_TABLES.map(normalizeSourceTable)),
      getApis: vi.fn(async () => ({ items: WIRE_SOURCE_APIS.apis.map(normalizeSourceApi) })),
      getReadiness: vi.fn(async () => WIRE_READINESS),
      getSemanticCoverage: vi.fn(async () => WIRE_COVERAGE),
      getOperationBindings: vi.fn(async () => WIRE_BINDINGS),
    },
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
    workbenchApi: { get: vi.fn(async () => WIRE_WORKBENCH) },
    semanticApi: {
      explain: vi.fn(async () => WIRE_DRAWER_EXPLAIN),
      assess: vi.fn(async () => WIRE_ASSESS),
      consistency: vi.fn(async () => WIRE_CONSISTENCY),
      instanceEvents: vi.fn(async () => ({ items: WIRE_INSTANCE_EVENTS })),
      instanceVersions: vi.fn(async () => ({ versions: WIRE_INSTANCE_VERSIONS })),
    },
    auditApi: {
      sections: vi.fn(async () => []),
      report: vi.fn(async () => WIRE_AUDIT_REPORT),
    },
    feedbackApi: {
      list: vi.fn(async () => WIRE_FEEDBACK),
      resolve: vi.fn(async () => ({})),
    },
    conversationApi: { list: vi.fn(async () => WIRE_ESCALATED) },
    knowledgeApi: {
      listDocuments: vi.fn(async () => WIRE_KNOWLEDGE_DOCUMENTS),
      listEntries: vi.fn(async () => WIRE_KNOWLEDGE_ENTRIES),
    },
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

// -- The ontology detail page: six tables behind six tabs ------------------------------------

/**
 * `/ontologies/{id}` returns five lists beside the summary, and the page renders one table per
 * tab. Nothing read any of them, and one had a column that could never hold a value: the
 * attributes table asked for `description`, `business_attribute` has no such column in the
 * schema, and `_business_attribute_row` hardcodes `"description": ""`. Every cell was blank in
 * every ontology. Both sides were internally consistent; only a test that renders the table and
 * reads the cells can see the seam between them.
 *
 * Field names come from the row shapers in `backend/ontology_platform/ontology.py`
 * (`_business_object_row`, `_business_attribute_row`, `_business_relation_row`,
 * `business_rule_row`), not from this page.
 */
const WIRE_ONTOLOGY_DETAIL = {
  id: 1,
  name: '合同管理',
  domain: '合同管理',
  version: '0.1.0',
  status: 'draft',
  // `summarize_ontology` returns the summary row twice: spread at the top level *and* under
  // `ontology`. The header renders `ontology.ontology.*`, so a fixture with only the flat form
  // throws on `undefined.status` -- which is how this shape was found.
  ontology: {
    id: 1,
    name: '合同管理',
    domain: '合同管理',
    version: '0.1.0',
    status: 'draft',
    createdAt: '2026-01-02 08:00:00',
  },
  objects: [
    { id: 1, code: 'contract', name: '合同', sourceTable: 'contract', description: '一份已签署的合同。' },
    { id: 2, code: 'party', name: '签约方', sourceTable: 'party', description: '合同的一方。' },
  ],
  attributes: [
    { id: 1, objectCode: 'contract', code: 'amount', name: '金额', dataType: 'number', sourceColumn: 'amount', required: true },
    { id: 2, objectCode: 'contract', code: 'credit_status', name: '信用状态', dataType: 'string', sourceColumn: 'credit_status', required: false },
  ],
  relations: [
    { id: 1, code: 'contract_party', name: '签约方', type: 'many_to_one', sourceForeignKey: 'party_id' },
  ],
  mappings: [
    {
      id: 1,
      mappingType: 'column_to_attribute',
      sourceTable: 'contract',
      sourceColumn: 'credit_status',
      targetObjectCode: 'contract',
      targetAttributeCode: 'creditStatus',
      confidence: 0.92,
      status: 'confirmed',
    },
  ],
  rules: [
    { id: 1, code: 'amount_positive', name: '金额必须为正', severity: 'blocking', enabled: true, expression: 'amount > 0' },
  ],
};

const WIRE_RELEASE_READINESS = {
  ontologyId: 1,
  name: '合同管理',
  version: '0.1.0',
  status: 'blocked',
  summary: {
    objects: 2,
    dataSources: 1,
    confirmedMappings: 1,
    pendingMappings: 0,
    rejectedMappings: 0,
    publishedRules: 1,
    passedGates: 1,
    totalGates: 2,
    blockers: 1,
    warnings: 0,
  },
  gates: [
    {
      code: 'business_objects',
      name: '业务对象',
      passed: true,
      severity: 'blocker',
      numbers: { objects: 2 },
      status: 'draft',
      evidence: '识别到 2 个业务对象。',
      remediation: '',
    },
    {
      code: 'ontology_status',
      name: '本体状态',
      passed: false,
      severity: 'blocker',
      numbers: {},
      status: 'draft',
      evidence: '当前状态 draft。',
      remediation: '确认映射后发布。',
    },
  ],
  dataSources: [],
  nextActions: [],
};

describe('OntologyDetail', () => {
  it('renders a value in every cell of the objects table', async () => {
    renderRouted(<OntologyDetail />, '/ontologies/1', '/ontologies/:id');
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_ONTOLOGY_DETAIL.objects.length);
    expect(blankColumns(table)).toEqual([]);
  });

  it('renders a value in every cell of the attributes table', async () => {
    renderRouted(<OntologyDetail />, '/ontologies/1?tab=attributes', '/ontologies/:id');
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_ONTOLOGY_DETAIL.attributes.length);
    expect(blankColumns(table)).toEqual([]);
  });

  it('renders a value in every cell of the relations table', async () => {
    renderRouted(<OntologyDetail />, '/ontologies/1?tab=relations', '/ontologies/:id');
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_ONTOLOGY_DETAIL.relations.length);
    expect(blankColumns(table)).toEqual([]);
  });

  it('renders a value in every cell of the mappings table', async () => {
    renderRouted(<OntologyDetail />, '/ontologies/1?tab=mappings', '/ontologies/:id');
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_ONTOLOGY_DETAIL.mappings.length);
    expect(blankColumns(table)).toEqual([]);
  });

  it('renders a value in every cell of the rules table', async () => {
    renderRouted(<OntologyDetail />, '/ontologies/1?tab=rules', '/ontologies/:id');
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_ONTOLOGY_DETAIL.rules.length);
    expect(blankColumns(table)).toEqual([]);
  });

  it('renders a value in every cell of the release-gate table', async () => {
    renderRouted(<OntologyDetail />, '/ontologies/1?tab=release', '/ontologies/:id');
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_RELEASE_READINESS.gates.length);
    expect(blankColumns(table)).toEqual([]);
  });
});

// -- The knowledge base: two tables side by side ---------------------------------------------

/**
 * `/ontologies/{id}/knowledge/documents` and `/knowledge/entries`, both `dict(row)`.
 *
 * The counts column is a render rather than a field: `confirmedCount` and `pendingCount` are
 * separate keys and the cell composes them into two tags. A fixture with a `counts` string would
 * render `undefined` into the tag and still look populated, so the fixture carries the two
 * numbers the renderer reads.
 *
 * The entry's anchor column is composed the same way from `objectCode` and `ruleCode`, and draws
 * 「未锚定」 when both are empty -- which is why one row here is anchored and one is not: a
 * fixture where everything is anchored would never exercise the branch that says so.
 */
const WIRE_KNOWLEDGE_DOCUMENTS = [
  {
    id: 1,
    title: '合同审批制度',
    sourceName: 'policy.txt',
    chunkCount: 3,
    confirmedCount: 2,
    pendingCount: 1,
    status: 'confirmed',
    createdAt: '2026-01-02 09:00:00',
  },
];

const WIRE_KNOWLEDGE_ENTRIES = {
  items: [
    {
      id: 1,
      citation: '第一条',
      content: '合同金额超过一百万元的，应经部门负责人审批。',
      heading: '审批',
      objectCode: 'contract',
      ruleCode: 'amount_ceiling',
      status: 'confirmed',
    },
    {
      id: 2,
      citation: '附则',
      content: '本制度自发布之日起施行。',
      heading: '附则',
      objectCode: '',
      ruleCode: '',
      status: 'pending',
    },
  ],
  retrievalBackends: ['bm25'],
  embeddingModels: ['hashed-ngram'],
};

describe('KnowledgeBase', () => {
  // One case per table, because the maturity page's count of covered tables is counted from
  // these titles -- a case that reads two tables would make the number smaller than the truth.
  it('renders a value in every cell of the documents table', async () => {
    renderPage(<KnowledgeBase />);
    const [documents] = await waitForTables(2);
    expect(documents.rows.length).toBe(WIRE_KNOWLEDGE_DOCUMENTS.length);
    expect(blankColumns(documents)).toEqual([]);
  });

  it('renders a value in every cell of the knowledge-entries table', async () => {
    renderPage(<KnowledgeBase />);
    const [, entries] = await waitForTables(2);
    expect(entries.rows.length).toBe(WIRE_KNOWLEDGE_ENTRIES.items.length);
    expect(blankColumns(entries)).toEqual([]);
  });

  it('says an unanchored entry is unanchored rather than leaving the cell empty', async () => {
    // The anchor column is the one place this page states a negative. `blankColumns` would
    // accept either an empty cell or the word, so the word is asserted.
    renderPage(<KnowledgeBase />);
    const [, entries] = await waitForTables(2);
    const body = entries.rows.map((row) => row.textContent ?? '').join(' ');
    expect(body).toContain('未锚定');
    expect(body).toContain('amount_ceiling');
  });
});

// -- The feedback console: what a reader said, and what was escalated -------------------------

/**
 * `/feedback` returns `{items, summary}`, and the summary is rendered as statistics above the
 * table -- so a fixture with only `items` throws on `summary.incorrect` rather than drawing an
 * empty card.
 *
 * The 纠正 column is a `render`, not a field: it reads `row.correction` and draws a tag or an
 * em dash. One row with a correction and one without, because a fixture where every row has one
 * never exercises the dash, and a fixture where none does is a column of dashes -- which the
 * blank-cell check rightly reports.
 */
const WIRE_FEEDBACK = {
  items: [
    {
      id: 1,
      messageId: 10,
      conversationId: 3,
      rating: 'incorrect',
      comment: '金额判错了。',
      correction: '金额上限应为两百万元。',
      decisionId: '7',
      objectCode: 'contract',
      ruleCode: 'amount_ceiling',
      status: 'resolved',
      actor: 'alice',
      resolvedBy: 'admin',
      createdAt: '2026-01-02 09:30:00',
    },
    {
      id: 2,
      messageId: 11,
      conversationId: 4,
      rating: 'helpful',
      comment: '',
      correction: '',
      decisionId: '8',
      objectCode: 'contract',
      ruleCode: '',
      status: 'open',
      actor: '',
      resolvedBy: '',
      createdAt: '2026-01-02 09:31:00',
    },
  ],
  summary: { incorrect: 1, unhelpful: 0, helpful: 1, corrections: 1 },
};

/** `/conversations?status=escalated` returns `{items}`; the page renders the list directly. */
const WIRE_ESCALATED = [
  {
    sessionId: 'abc123',
    title: '合同金额判定有疑问',
    escalatedTo: '业务专家',
    escalationReason: '模型给出的结论与制度不符',
    status: 'escalated',
  },
];

describe('FeedbackConsole', () => {
  // Escalations render above the feedback table, and that order is the page's rather than a
  // detail to be guessed: reading them the other way round reported a correct page as wrong.
  it('renders a value in every cell of the escalation table', async () => {
    renderPage(<FeedbackConsole />);
    const [escalated] = await waitForTables(2);
    expect(escalated.rows.length).toBe(WIRE_ESCALATED.length);
    expect(blankColumns(escalated)).toEqual([]);
  });

  it('renders a value in every cell of the feedback table', async () => {
    renderPage(<FeedbackConsole />);
    const [, feedback] = await waitForTables(2);
    expect(feedback.rows.length).toBe(WIRE_FEEDBACK.items.length);
    expect(blankColumns(feedback)).toEqual([]);
  });

  it('says an anonymous reporter is anonymous rather than leaving the cell empty', async () => {
    // `actor` has a fallback to 「匿名」, and a fallback is exactly what hides a rename -- so the
    // word is asserted rather than merely the presence of text.
    renderPage(<FeedbackConsole />);
    const [, feedback] = await waitForTables(2);
    const body = feedback.rows.map((row) => row.textContent ?? '').join(' ');
    expect(body).toContain('匿名');
    expect(body).toContain('alice');
  });
});

// -- The audit report: five tables behind one tab --------------------------------------------

/**
 * `POST /governance/audit-report` returns the whole report in one object, and the panel renders
 * a table per section: rules that never fired, rules that did, forced publications, blocked
 * decisions, and the governance event log.
 *
 * Every list is populated on purpose. Four of the five sections render only when their list is
 * non-empty (`forcedPublications.length > 0`, and so on), so a fixture with one row in each is
 * the only version that reads all five tables -- and the version that would have caught a column
 * wired to the wrong key in any of them.
 *
 * The shape is `AuditReport` in `types/index.ts`, which is the contract this panel reads.
 */
const WIRE_AUDIT_REPORT = {
  period: { start: '2026-01-01 00:00:00', end: '2026-01-31 23:59:59', boundary: 'closed' },
  ontologyId: null,
  decisions: {
    total: 2,
    byStatus: { approved: 1, review: 1 },
    blocked: [
      {
        decision_id: '9',
        decision_type: 'operation',
        object_code: 'contract',
        instance_id: '1',
        actor: 'analyst',
        created_at: '2026-01-02 09:00:00',
      },
    ],
  },
  rules: {
    note: '',
    triggered: [
      { code: 'amount_ceiling', name: '金额上限', severity: 'blocking', evaluations: 12 },
    ],
    neverTriggered: [
      { code: 'refund_window_check', name: '退款窗口检查', severity: 'warning', evaluations: 0 },
    ],
  },
  actors: { byActor: { admin: { publish: 1 } } },
  governance: {
    events: [
      {
        actor: 'admin',
        action: 'ontology.publish',
        target_type: 'ontology',
        target_id: '1',
        detail: '{}',
        created_at: '2026-01-02 09:10:00',
      },
    ],
    forcedPublications: [
      {
        actor: 'admin',
        action: 'ontology.publish.force',
        target_type: 'ontology',
        target_id: '2',
        detail: '{"blockers": 1}',
        created_at: '2026-01-02 09:11:00',
      },
    ],
  },
  model: { total: 3, byPurpose: { ontology_draft: 3 }, failed: 0 },
  coverage: { evaluations: 12, withTrace: 12, ratio: 1 },
  findings: [],
};

describe('AuditReportPanel', () => {
  it('renders a value in every cell of the never-triggered rules table', async () => {
    renderPage(<AuditReportPanel />);
    const [neverTriggered] = await waitForTables(5);
    expect(neverTriggered.rows.length).toBe(WIRE_AUDIT_REPORT.rules.neverTriggered.length);
    expect(blankColumns(neverTriggered)).toEqual([]);
  });

  it('renders a value in every cell of the triggered rules table', async () => {
    renderPage(<AuditReportPanel />);
    const [, triggered] = await waitForTables(5);
    expect(triggered.rows.length).toBe(WIRE_AUDIT_REPORT.rules.triggered.length);
    expect(blankColumns(triggered)).toEqual([]);
  });

  it('renders a value in every cell of the forced-publications table', async () => {
    renderPage(<AuditReportPanel />);
    const [, , forced] = await waitForTables(5);
    expect(forced.rows.length).toBe(WIRE_AUDIT_REPORT.governance.forcedPublications.length);
    expect(blankColumns(forced)).toEqual([]);
  });

  it('renders a value in every cell of the blocked-decisions table', async () => {
    renderPage(<AuditReportPanel />);
    const [, , , blocked] = await waitForTables(5);
    expect(blocked.rows.length).toBe(WIRE_AUDIT_REPORT.decisions.blocked.length);
    expect(blankColumns(blocked)).toEqual([]);
  });

  it('renders a value in every cell of the audit-event table', async () => {
    renderPage(<AuditReportPanel />);
    const [, , , , events] = await waitForTables(5);
    expect(events.rows.length).toBe(WIRE_AUDIT_REPORT.governance.events.length);
    expect(blankColumns(events)).toEqual([]);
  });
});

// -- The data source detail: what was scanned, and what was registered ------------------------

/**
 * `/data-sources/{id}/tables` and `/apis` are `dict(row)`, and the client normalises both --
 * `normalizeSourceTable` and `normalizeSourceApi`. The fixtures here are the wire spellings and
 * the mock runs the real normalisers, so a rename inside either one fails this test rather than
 * blanking a column in production.
 *
 * The other three calls on this page are only read by tabs the test does not open; they are
 * answered with empty results so the page mounts, and deliberately not with plausible-looking
 * data -- a fixture for a screen nobody asserts on is a fixture that will be wrong and never
 * noticed.
 */
const WIRE_SOURCE_TABLES = [
  {
    id: 1,
    table_name: 'contract',
    row_count: 120,
    primary_key: 'id',
    scanned_at: '2026-01-02 09:00:00',
  },
  {
    id: 2,
    table_name: 'party',
    row_count: 8,
    primary_key: 'id',
    scanned_at: '2026-01-02 09:00:00',
  },
];

const WIRE_SOURCE_APIS = {
  apis: [
    {
      id: 1,
      operation_code: 'submit_contract',
      name: '提交合同',
      method: 'POST',
      path: '/contracts/{id}/submit',
      semantic_action: 'submit',
    },
  ],
};

const WIRE_READINESS = {
  dataSourceId: 1,
  name: '合同管理样例系统',
  domain: '合同管理',
  score: 80,
  status: 'partial',
  summary: {
    tables: 2,
    columns: 9,
    foreignKeys: 1,
    apis: 1,
    ontologies: 1,
    confirmedMappings: 1,
    pendingMappings: 0,
  },
  checks: [],
  nextActions: [],
};

const WIRE_COVERAGE = {
  dataSourceId: 1,
  name: '合同管理样例系统',
  domain: '合同管理',
  status: 'ready',
  score: 90,
  summary: {},
  objects: [],
  operations: [],
  nextActions: [],
};

/**
 * The tab labelled 「已注册 API」 renders **operation bindings**, not the API list: `apis` feeds
 * the tab's count and this table reads `operationBindings.items`. The distinction is the point
 * of the screen -- an operation can be imported and still not be bound to an object -- so the
 * fixture is a bound one with a gap, because `gaps` renders `-` when empty and a column of
 * dashes is exactly what this file treats as blank.
 */
const WIRE_BINDINGS = {
  dataSourceId: 1,
  status: 'partial',
  summary: {
    operations: 1,
    boundOperations: 1,
    readyOperations: 1,
    unboundOperations: 0,
    invalidActions: 0,
    blockedOperations: 0,
  },
  // The item carries the API's own fields *and* its binding: `/operation-bindings` returns
  // `operationCode, name, method, path, semanticAction` (charted in
  // `test_frontend_type_agreement.py`) beside `objectCode`, `status`, `automationReady`, `gaps`.
  // A fixture with only the binding half leaves four columns blank -- which is what this test
  // said the first time, and the page was right.
  items: [
    {
      operationCode: 'submit_contract',
      name: '提交合同',
      method: 'POST',
      path: '/contracts/{id}/submit',
      semanticAction: 'submit',
      objectCode: 'contract',
      status: 'ready',
      automationReady: true,
      gaps: ['该操作没有对应的业务规则'],
    },
  ],
  nextActions: [],
  nextActionCodes: [],
};

describe('DataSourceDetail', () => {
  it('renders a value in every cell of the scanned-tables table', async () => {
    renderRouted(<DataSourceDetail />, '/datasource/1', '/datasource/:id');
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_SOURCE_TABLES.length);
    expect(blankColumns(table)).toEqual([]);
  });

  it('renders a value in every cell of the operations table', async () => {
    // One table, not two: the tab labelled 「已登记 API」 draws the operation list and its
    // binding together -- nine columns, from one row shape. `apis` feeds the tab's count.
    renderRouted(<DataSourceDetail />, '/datasource/1?tab=apis', '/datasource/:id');
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_BINDINGS.items.length);
    expect(blankColumns(table)).toEqual([]);
  });
});

// -- Modelling extensions: the event types declared for an object -----------------------------

/**
 * `/ontologies/{id}/event-types` returns `{items}`, and the component keeps only the rows whose
 * `objectCode` matches the object selected in the dropdown -- which defaults to the first object
 * it is given. So the fixture's `objectCode` has to be that one, or the table filters itself
 * empty and the test reports "no rows" about a correct page.
 *
 * Two rows: one with payload fields and one without, because the column renders a different
 * thing in each case (tags, or 「没有预期字段」) and only one of them is a list.
 */
const WIRE_EVENT_TYPES = [
  {
    code: 'signed',
    name: '已签署',
    objectCode: 'contract',
    category: 'state_change',
    payloadFields: ['effectiveAt', 'signedBy'],
    description: '合同签署时发出。',
  },
  {
    code: 'archived',
    name: '已归档',
    objectCode: 'contract',
    category: 'state_change',
    payloadFields: [],
    description: '合同归档时发出，不带载荷。',
  },
];

describe('ModellingExtensions', () => {
  it('renders a value in every cell of the event-types table', async () => {
    renderPage(
      <ModellingExtensions
        ontologyId={1}
        objects={[{ id: 1, ontologyId: 1, code: 'contract', name: '合同', description: '', sourceTable: 'contract' }]}
        readOnly={false}
      />,
    );
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_EVENT_TYPES.length);
    expect(blankColumns(table)).toEqual([]);
  });

  it('shows the declared payload fields rather than saying there are none', async () => {
    /** The payload column renders tags when it has fields and 「未声明预期字段」 when it does not.
     *
     * That fallback is right for a declaration that genuinely has no payload, and it is exactly
     * what hides a rename: point `dataIndex` at a key the row does not carry and every cell says
     * 「未声明预期字段」 -- filled, plausible, and false. `blankColumns` cannot see it. Found by
     * planting `payloadFields -> payloadFieldz` and watching the blank-cell case stay green.
     */
    renderPage(
      <ModellingExtensions
        ontologyId={1}
        objects={[{ id: 1, ontologyId: 1, code: 'contract', name: '合同', description: '', sourceTable: 'contract' }]}
        readOnly={false}
      />,
    );
    const table = await waitForRows();

    const body = table.rows.map((row) => row.textContent ?? '').join(' ');
    expect(body).toContain('effectiveAt');
    expect(body).toContain('signedBy');
    // The second row has no fields on purpose: its cell must say so, not be empty.
    expect(body).toContain('未声明预期字段');
  });
});

// -- The semantic screen: explain and consistency ---------------------------------------------

/**
 * Both tables are reached through a **deep link**, not by driving the form.
 *
 * `?tab=explain&object=…&instance=…` is a documented feature -- the parameters are
 * `object`/`instance`/`ontology`, not the form fields' names, which is itself worth writing down -- "an instance's
 * explanation is a link you can paste into a ticket" -- and it is the same code path the form's
 * submit button takes (`handleExplain`). Driving it this way tests the link as well as the
 * table, and avoids a test that only passes because it clicked the button the way the author did.
 *
 * One attribute is derived and one is plain: the source column draws the derived expression for
 * the first and the source column for the second, and a fixture with only one kind would leave
 * half that renderer unexercised.
 */
const WIRE_EXPLAIN = {
  // `InstanceExplainResult`, in full. The first version had `source` as a string -- the semantic
  // page never reads it, so that page's test passed on a fixture the type says is wrong. The
  // drawer reads `source.table` and threw. A fixture only has to be right enough for the page
  // under test, which is exactly why it should be built from the type instead.
  ontology: { id: 1, name: '合同管理', version: '0.1.0' },
  object: { code: 'contract', name: '合同' },
  objectCode: 'contract',
  instanceId: '1',
  source: { table: 'contract', primaryKey: 'id', instanceId: '1' },
  explanation: '合同 1 的金额为 500。',
  explanationParts: [],
  aggregates: [],
  ancestors: [],
  timeline: [],
  asOf: '',
  attributes: [
    {
      attributeCode: 'amount',
      attributeName: '金额',
      sourceColumn: 'amount',
      unit: 'cny',
      unitName: '元',
      derived: false,
      derivedExpression: '',
      value: 500,
    },
    {
      attributeCode: 'effectiveDays',
      attributeName: '生效天数',
      sourceColumn: '',
      unit: '',
      unitName: '',
      derived: true,
      derivedExpression: 'days_between(effective_at, today)',
      value: 12,
    },
  ],
};

const WIRE_ASSESS = { objectCode: 'contract', instanceId: '1', decision: 'approved', failedRules: [], rules: [] };
/**
 * The consistency table renders `failedRules` as tags and `-` when the list is empty -- and a
 * column of hyphens is what this file treats as blank. The single row here failed a rule, so the
 * cell has real content; a fixture of clean instances would have made the column permanently
 * empty-looking and the test would have reported a correct page.
 */
const WIRE_CONSISTENCY = {
  objectCode: 'contract',
  sampleSize: 3,
  assessed: 1,
  status: 'inconsistent',
  summary: { approved: 0, review: 0, blocked: 1, errors: 0 },
  nextActions: [],
  nextActionCodes: [],
  ruleFailures: [],
  errors: [],
  items: [
    {
      instanceId: '1',
      decision: 'blocked',
      failedRuleCount: 1,
      failedRules: ['amount_ceiling'],
      decisionId: '9',
    },
  ],
};

describe('SemanticService', () => {
  it('renders a value in every cell of the consistency table', async () => {
    renderRouted(<SemanticService />, '/semantic?tab=consistency&object=contract&ontology=1', '/semantic');
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_CONSISTENCY.items.length);
    expect(blankColumns(table)).toEqual([]);
  });

  it('renders a value in every cell of the explain table', async () => {
    renderRouted(
      <SemanticService />,
      '/semantic?tab=explain&object=contract&instance=1&ontology=1',
      '/semantic',
    );
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_EXPLAIN.attributes.length);
    expect(blankColumns(table)).toEqual([]);
  });
});

// -- The instance drawer: four tables behind one click ----------------------------------------

/**
 * The drawer takes its data from three calls that fail independently -- the explanation, the
 * event stream and the value history -- and renders one table per section. It also reads
 * `explain.object.name` for its title, which is why the fixture carries an `object` block the
 * semantic page's fixture does not need: a missing one throws on render rather than drawing an
 * empty title.
 *
 * The aggregate row is populated because the aggregates table renders unconditionally, and an
 * empty one would still be *drawn* -- a table with no rows is not the same finding as a column
 * with no values, and only the second is what this file looks for.
 */
const WIRE_DRAWER_EXPLAIN = {
  ...WIRE_EXPLAIN,
  aggregates: [
    { name: 'orderTotal', definition: 'sum(orders.amount)', rowCount: 12 },
  ],
};

const WIRE_INSTANCE_EVENTS = [
  {
    id: 1,
    eventCode: 'signed',
    eventName: '已签署',
    category: 'state_change',
    actor: 'alice',
    occurredAt: '2026-01-02 09:00:00',
    payload: { effectiveAt: '2026-01-03' },
  },
];

const WIRE_INSTANCE_VERSIONS = [
  {
    attributeCode: 'amount',
    value: 500,
    validFrom: '2026-01-01',
    validTo: '',
    recordedAt: '2026-01-02 09:00:00',
    actor: 'alice',
  },
];

describe('InstanceDrawer', () => {
  it('renders a value in every cell of the attributes table', async () => {
    renderPage(
      <InstanceDrawer ontologyId={1} objectCode="contract" instanceId="1" onClose={() => undefined} />,
    );
    const [attributes] = await waitForTables(4);
    expect(attributes.rows.length).toBe(WIRE_EXPLAIN.attributes.length);
    expect(blankColumns(attributes)).toEqual([]);
  });

  it('renders a value in every cell of the aggregates table', async () => {
    renderPage(
      <InstanceDrawer ontologyId={1} objectCode="contract" instanceId="1" onClose={() => undefined} />,
    );
    const [, aggregates] = await waitForTables(4);
    expect(aggregates.rows.length).toBe(WIRE_DRAWER_EXPLAIN.aggregates.length);
    expect(blankColumns(aggregates)).toEqual([]);
  });

  it('renders a value in every cell of the event table', async () => {
    renderPage(
      <InstanceDrawer ontologyId={1} objectCode="contract" instanceId="1" onClose={() => undefined} />,
    );
    const [, , events] = await waitForTables(4);
    expect(events.rows.length).toBe(WIRE_INSTANCE_EVENTS.length);
    expect(blankColumns(events)).toEqual([]);
  });

  it('renders a value in every cell of the value-history table', async () => {
    renderPage(
      <InstanceDrawer ontologyId={1} objectCode="contract" instanceId="1" onClose={() => undefined} />,
    );
    const [, , , versions] = await waitForTables(4);
    expect(versions.rows.length).toBe(WIRE_INSTANCE_VERSIONS.length);
    expect(blankColumns(versions)).toEqual([]);
  });
});

// -- The workbench: what to do next -----------------------------------------------------------

/**
 * `Workbench`, in full. The page destructures every section at the top of its render, so a
 * fixture missing one throws before any table is drawn -- `summary` and `knowledge` in
 * particular are read for the header statistics, not for the table this test reads.
 *
 * The action items are a `<List>`, not a `<Table>`; the recent decisions are the table.
 */
const WIRE_WORKBENCH = {
  generatedAt: '2026-01-02 09:00:00',
  dataSources: { total: 1, scanned: 1, unscanned: 0, withBusinessApi: 0, tables: 2, columns: 9 },
  ontologies: {
    total: 1,
    draft: 1,
    published: 0,
    byStatus: { draft: 1 },
    objects: 2,
    attributes: 4,
    relations: 1,
    unboundObjects: 0,
  },
  governance: {
    pendingMappings: 0,
    confirmedMappings: 1,
    rejectedMappings: 0,
    mappingsByStatus: { confirmed: 1 },
    reviewableTransitions: 0,
    auditEntries: 1,
  },
  rules: {
    total: 1,
    blocking: 1,
    warning: 0,
    info: 0,
    bySeverity: { blocking: 1 },
    byStatus: { published: 1 },
    objectsWithoutRules: 1,
  },
  decisions: {
    total: 1,
    byStatus: { approved: 1 },
    blocked: 0,
    review: 0,
    approved: 1,
    recent: [
      {
        decisionId: '9',
        decisionType: 'operation',
        objectCode: 'contract',
        instanceId: '1',
        status: 'approved',
        actor: 'analyst',
        createdAt: '2026-01-02 09:00:00',
      },
    ],
  },
  knowledge: { valueMappings: 0, confirmedValueMappings: 0, pendingValueMappings: 0 },
  actionItems: [],
  summary: { blockers: 0, warnings: 0, totalActionItems: 0 },
};

describe('Workbench', () => {
  it('renders a value in every cell of the recent-decisions table', async () => {
    renderPage(<Workbench />);
    const table = await waitForRows();
    expect(table.rows.length).toBe(WIRE_WORKBENCH.decisions.recent.length);
    expect(blankColumns(table)).toEqual([]);
  });
});
