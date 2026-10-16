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

function renderPage(component: React.ReactElement) {
  return render(
    <LocaleProvider>
      <MemoryRouter>{component}</MemoryRouter>
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
function blankColumns(table: RenderedTable): string[] {
  const { headers, rows } = table;
  const cellCount = rows[0]?.querySelectorAll('td').length ?? 0;
  const blank: string[] = [];
  for (let index = 0; index < cellCount; index += 1) {
    const cells = rows.map((row) => row.querySelectorAll('td')[index]);
    if (cells.some((cell) => cell?.querySelector('button, .ant-switch'))) continue;
    if (cells.every((cell) => (cell?.textContent ?? '').trim() === '')) {
      blank.push(headers[index] ?? `#${index + 1}`);
    }
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
    isSystem: 1,
    createdAt: '2026-01-01',
  },
];
const WIRE_POLICIES = [
  {
    id: 1,
    roleId: 1,
    roleName: '管理员',
    objectCode: 'contract',
    canRead: 1,
    canWrite: 1,
    canExecute: 1,
    canDelete: 1,
    description: '全部权限',
  },
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
      list: vi.fn(async () => WIRE_ONTOLOGY_LIST),
      getMappings: vi.fn(async () => page(WIRE_MAPPINGS)),
      getRules: vi.fn(async () => page(WIRE_RULES)),
    },
    dataSourceApi: { list: vi.fn(async () => WIRE_DATA_SOURCES) },
    industryBlueprintApi: { list: vi.fn(async () => []) },
    permissionApi: {
      getRoles: vi.fn(async () => WIRE_ROLES),
      getPolicies: vi.fn(async () => WIRE_POLICIES),
    },
    toolApi: { list: vi.fn(async () => []), getPendingReviews: vi.fn(async () => []) },
    ssoApi: { status: vi.fn(async () => null) },
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
});
