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
 * Wait until the table holds data rows.
 *
 * Not `findAllByRole('row')`, which is how the first version of this file passed against
 * nothing: antd renders a header row and a placeholder before the fetch resolves, so the query
 * matches immediately and the assertions then run over an empty tbody -- the same "a scan that
 * saw nothing reported health" failure `scripts/ui_smoke.py` learned about the hard way.
 */
async function waitForRows(): Promise<Element[]> {
  await waitFor(() => {
    if (document.querySelectorAll('.ant-table-tbody tr.ant-table-row').length === 0) {
      throw new Error('还没有数据行');
    }
  });
  return Array.from(document.querySelectorAll('.ant-table-tbody tr.ant-table-row'));
}

function columnTitles(): string[] {
  return Array.from(document.querySelectorAll('.ant-table-thead th')).map((th) =>
    (th.textContent ?? '').trim(),
  );
}

/**
 * Column titles whose every cell is empty, over the rows actually drawn.
 *
 * `:first-child` is deliberately not used to find the first data row: antd's tbody begins with a
 * measurement row, so `tr.ant-table-row:first-child` matches nothing and reports every column as
 * blank. A column holding a control rather than text is excluded by name -- a cell with a button
 * in it legitimately has no text, and counting it would be a standing false positive.
 */
function blankColumns(rows: Element[]): string[] {
  const titles = columnTitles();
  const cellCount = rows[0]?.querySelectorAll('td').length ?? 0;
  const blank: string[] = [];
  for (let index = 0; index < cellCount; index += 1) {
    const cells = rows.map((row) => row.querySelectorAll('td')[index]);
    if (cells.some((cell) => cell?.querySelector('button, .ant-switch'))) continue;
    if (cells.every((cell) => (cell?.textContent ?? '').trim() === '')) {
      blank.push(titles[index] ?? `#${index + 1}`);
    }
  }
  return blank;
}

describe('MappingList', () => {
  it('renders a value in every cell of every column', async () => {
    renderPage(<MappingList />);
    const rows = await waitForRows();
    expect(rows.length).toBe(WIRE_MAPPINGS.length);
    expect(blankColumns(rows)).toEqual([]);
  });

  it('names the mapping type rather than printing the backend word', async () => {
    renderPage(<MappingList />);
    const rows = await waitForRows();

    const body = rows.map((row) => row.textContent ?? '').join(' ');
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
    const rows = await waitForRows();
    expect(rows.length).toBe(WIRE_RULES.length);
    expect(blankColumns(rows)).toEqual([]);
  });

  it('says the rule type and severity in words', async () => {
    renderPage(<RuleList />);
    const rows = await waitForRows();

    const body = rows.map((row) => row.textContent ?? '').join(' ');
    expect(body).not.toContain('validation');
    expect(body).not.toContain('blocking');
    // The Chinese side of the dictionary, since the provider defaults to it.
    expect(body).toContain('阻断');
  });
});
