import { describe, expect, it } from 'vitest';

import {
  filenameFromDisposition,
  normalizeDataSource,
  normalizePolicy,
  normalizeRole,
  normalizeSourceApi,
  normalizeSourceTable,
  normalizeTool,
  normalizeToolExecution,
  normalizeWorkflow,
  normalizeWorkflowTransition,
} from './normalise';

/**
 * The wire, held to the shape the screens read.
 *
 * Four times a table drew nothing for every row because the endpoint sent `snake_case` and the
 * TypeScript type declared `camelCase`. The type checked out, the linter saw a valid string,
 * antd drew an empty cell for a `dataIndex` that was `undefined`, and the only thing that ever
 * noticed was somebody looking at a real screen with real rows on it.
 *
 * These tests are the cheapest substitute for that: for each normaliser, the wire payload the
 * endpoint actually sends in, and the field names the screens actually read out. The payloads
 * below are transcripts, not inventions -- they are the spellings `dict(row)` produces, which is
 * why every key is `snake_case`.
 *
 * What they cannot check is whether the *screen* reads the field. That is `CHARTED_RESPONSES` in
 * `tests/test_frontend_type_agreement.py`, and it is still the half that catches an endpoint
 * that stops sending one.
 */

describe('normalizeDataSource', () => {
  // `/data-sources` sends both spellings; `public_dict()` emits camelCase and the row carries
  // snake_case. The normaliser has to accept either, because both have been seen.
  it('reads the snake_case spelling', () => {
    const row = normalizeDataSource({
      id: 1,
      name: '合同库',
      source_type: 'sqlite',
      connection_uri: '/tmp/x.sqlite3',
      api_base_url: 'http://127.0.0.1:8001',
      system_category: 'database+api',
      created_at: '2026-01-01 00:00:00',
    });
    expect(row.sourceType).toBe('sqlite');
    expect(row.connectionUri).toBe('/tmp/x.sqlite3');
    expect(row.apiBaseUrl).toBe('http://127.0.0.1:8001');
    expect(row.systemCategory).toBe('database+api');
  });

  it('reads the camelCase spelling the same way', () => {
    const row = normalizeDataSource({
      id: 1,
      name: '合同库',
      sourceType: 'sqlite',
      connectionUri: '/tmp/x.sqlite3',
    });
    expect(row.sourceType).toBe('sqlite');
    expect(row.connectionUri).toBe('/tmp/x.sqlite3');
  });

  it('keeps the id and name the row keys depend on', () => {
    // `rowKey="id"` and the create-then-select path both need these; a normaliser that lost
    // them would make every row unkeyed and every post-create lookup fail.
    const row = normalizeDataSource({ id: 7, name: 'x', sourceType: 'csv', connectionUri: '/' });
    expect(row.id).toBe(7);
    expect(row.name).toBe('x');
  });
});

describe('normalizeWorkflow', () => {
  // The defect: `/workflows` sends `object_code`, `ontology_id`, `initial_state`, and the list
  // table's 业务对象 / 本体 / 初始状态 columns were blank for every row.
  it('maps the definition fields the workflow list renders', () => {
    const workflow = normalizeWorkflow({
      id: 3,
      ontology_id: 1,
      object_code: 'contract',
      name: '合同审批',
      initial_state: 'draft',
      status: 'active',
      created_at: '2026-01-01 00:00:00',
    });
    expect(workflow.ontologyId).toBe(1);
    expect(workflow.objectCode).toBe('contract');
    expect(workflow.initialState).toBe('draft');
    expect(workflow.createdAt).toBe('2026-01-01 00:00:00');
  });

  it('normalises the nested rows through their own normalisers', () => {
    // The second half of the same defect: the definition above the table was translated while
    // the transition table's 动作 / 来源 / 目标 / 需审核 columns stayed blank, because
    // `...item` passed `states` and `transitions` through in wire spelling.
    const workflow = normalizeWorkflow({
      id: 3,
      ontology_id: 1,
      object_code: 'contract',
      name: '合同审批',
      initial_state: 'draft',
      states: [{ code: 'draft', name: '草稿', is_terminal: 0, sort_order: 1 }],
      transitions: [
        {
          action_code: 'submit',
          from_state: 'draft',
          to_state: 'reviewing',
          name: '提交',
          requires_review: 1,
          guard_expression: 'amount > 0',
        },
      ],
    });
    expect(workflow.states?.[0].isTerminal).toBe(0);
    expect(workflow.states?.[0].sortOrder).toBe(1);
    expect(workflow.transitions?.[0].actionCode).toBe('submit');
    expect(workflow.transitions?.[0].toState).toBe('reviewing');
    expect(workflow.transitions?.[0].requiresReview).toBe(1);
  });

  it('survives a definition with no states or transitions yet', () => {
    // `states` is absent on a freshly created workflow, and `.map` on `undefined` is a page
    // that renders nothing at all rather than a page with an empty table.
    const workflow = normalizeWorkflow({ id: 1, name: 'x' });
    expect(workflow.states).toEqual([]);
    expect(workflow.transitions).toEqual([]);
  });
});

describe('normalizeWorkflowTransition', () => {
  it('names every column of the transition table', () => {
    const transition = normalizeWorkflowTransition({
      action_code: 'approve',
      from_state: 'reviewing',
      to_state: 'approved',
      name: '批准',
      guard_expression: 'amount <= 100000',
      requires_review: 0,
      review_role: 'legal',
      sort_order: 2,
    });
    expect(transition).toMatchObject({
      actionCode: 'approve',
      fromState: 'reviewing',
      toState: 'approved',
      guardExpression: 'amount <= 100000',
      requiresReview: 0,
      reviewRole: 'legal',
      sortOrder: 2,
    });
  });
});

describe('normalizePolicy', () => {
  // The worst of the four: all seven columns blank, twenty rows, on the screen that answers
  // "who may do what".
  it('names all seven fields the policy table reads', () => {
    const policy = normalizePolicy({
      id: 1,
      role_id: 2,
      role_name: '审核员',
      object_code: 'contract',
      can_read: 1,
      can_write: 0,
      can_execute: 1,
      can_delete: 0,
      description: '只读加执行',
    });
    expect(policy).toMatchObject({
      roleId: 2,
      roleName: '审核员',
      objectCode: 'contract',
      canRead: 1,
      canWrite: 0,
      canExecute: 1,
      canDelete: 0,
      description: '只读加执行',
    });
  });

  it('keeps a zero as a zero rather than folding it into a default', () => {
    // `?? 0` and a falsy check are indistinguishable on this payload, and only one of them is
    // right: a permission that reads "not allowed" must not become "allowed".
    const policy = normalizePolicy({ id: 1, role_id: 1, object_code: 'x', can_read: 0, can_write: 0, can_execute: 0, can_delete: 0 });
    expect(policy.canRead).toBe(0);
    expect(policy.canDelete).toBe(0);
  });
});

describe('normalizeRole / normalizeTool', () => {
  it('maps the role columns, including the system flag', () => {
    const role = normalizeRole({ id: 1, code: 'admin', name: '管理员', is_system: 1, created_at: '2026-01-01' });
    expect(role).toMatchObject({ code: 'admin', name: '管理员', isSystem: 1, createdAt: '2026-01-01' });
  });

  it('maps the tool columns the review queue reads', () => {
    const tool = normalizeTool({
      id: 4,
      code: 'submit',
      name: '提交',
      tool_type: 'mutation',
      risk_level: 'high',
      requires_review: 1,
      status: 'active',
      created_at: '2026-01-01',
    });
    expect(tool).toMatchObject({
      toolType: 'mutation',
      riskLevel: 'high',
      requiresReview: 1,
      status: 'active',
    });
  });

  it('maps a held tool execution, whose eight columns were all blank', () => {
    // `/tools/pending-reviews` returns `dict(row)` and the console reads camelCase. Eight blank
    // columns nobody saw, because on every deployment this table was empty.
    const execution = normalizeToolExecution({
      id: 9,
      tool_code: 'submit',
      agent_role: 'reviewer',
      object_code: 'contract',
      instance_id: '1',
      status: 'success',
      duration_ms: 12,
      requires_review: 1,
      created_at: '2026-01-01',
    });
    expect(execution).toMatchObject({
      toolCode: 'submit',
      agentRole: 'reviewer',
      objectCode: 'contract',
      instanceId: '1',
      durationMs: 12,
      requiresReview: 1,
    });
  });
});

describe('normalizeSourceTable / normalizeSourceApi', () => {
  it('maps the table browser columns', () => {
    const table = normalizeSourceTable({ table_name: 'contract', row_count: 42, primary_key: 'id', scanned_at: '2026-01-01' });
    expect(table).toMatchObject({ tableName: 'contract', rowCount: 42, primaryKey: 'id', scannedAt: '2026-01-01' });
  });

  it('maps the operation list columns', () => {
    const api = normalizeSourceApi({
      operation_code: 'submit_contract',
      name: '提交合同',
      method: 'POST',
      path: '/contracts/{id}/submit',
      semantic_action: 'contract.submit_for_approval',
    });
    expect(api).toMatchObject({
      operationCode: 'submit_contract',
      method: 'POST',
      path: '/contracts/{id}/submit',
      semanticAction: 'contract.submit_for_approval',
    });
  });
});

describe('filenameFromDisposition', () => {
  it('reads the plain form the export endpoint sends', () => {
    // Measured from the running server: `attachment; filename=ontology-1-v0.1.0.jsonld`.
    expect(filenameFromDisposition('attachment; filename=ontology-1-v0.1.0.jsonld')).toBe(
      'ontology-1-v0.1.0.jsonld',
    );
  });

  it('reads a quoted name', () => {
    expect(filenameFromDisposition('attachment; filename="a b.tar.gz"')).toBe('a b.tar.gz');
  });

  it('decodes the encoded form, which is how a Chinese name arrives', () => {
    expect(filenameFromDisposition("attachment; filename*=UTF-8''%E5%90%88%E5%90%8C.jsonld")).toBe(
      '合同.jsonld',
    );
  });

  it('returns null rather than a guess when there is no header', () => {
    // The caller falls back to a name it invented, which is strictly better than a file called
    // `null` or an empty download.
    expect(filenameFromDisposition(undefined)).toBeNull();
    expect(filenameFromDisposition('')).toBeNull();
    expect(filenameFromDisposition('attachment')).toBeNull();
    expect(filenameFromDisposition(12345)).toBeNull();
  });
});
