import { ONTOLOGY_STATUS, RULE_SEVERITY, RULE_STATUS, RULE_TYPE } from '../../i18n/labels';
import { useLabel, useT } from '../../i18n/locale';
import React, { useEffect, useState, useCallback } from 'react';
import {
  Alert, Card, Table, Typography, Tag, Empty, Select, Space, message, Switch, Button,
  Modal, Form, Input, Upload, Descriptions, Popconfirm, Tooltip, Row, Col,
} from 'antd';
import {
  EditOutlined, DeleteOutlined, PlusOutlined, UploadOutlined, InboxOutlined,
  ReloadOutlined, EyeOutlined,
} from '@ant-design/icons';
import { ontologyApi, requestErrorMessage } from '../../api';
import type { Ontology, BusinessRule, RuleWordImportResult } from '../../types';

const { Title, Text } = Typography;
const { Option } = Select;
const { TextArea } = Input;
const { Dragger } = Upload;


const severityColor: Record<string, string> = {
  blocking: 'red',
  warning: 'orange',
  info: 'blue',
};

const statusColor: Record<string, string> = {
  published: 'green',
  draft: 'default',
  disabled: 'default',
};

const RuleList: React.FC = () => {
  const label = useLabel();
  const t = useT();
  const [ontologies, setOntologies] = useState<Ontology[]>([]);
  const [rules, setRules] = useState<BusinessRule[]>([]);
  // Kept apart from an empty list: both leave `rules` empty.
  const [loadError, setLoadError] = useState('');
  const [selectedOntology, setSelectedOntology] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  const [modalVisible, setModalVisible] = useState(false);
  const [modalTitle, setModalTitle] = useState(t('rules.newRule'));
  const [editingRule, setEditingRule] = useState<BusinessRule | null>(null);
  const [form] = Form.useForm();

  const [importResult, setImportResult] = useState<RuleWordImportResult | null>(null);
  const [importModalVisible, setImportModalVisible] = useState(false);
  const [ruleImporting, setRuleImporting] = useState(false);

  const [detailVisible, setDetailVisible] = useState(false);
  const [detailRule, setDetailRule] = useState<BusinessRule | null>(null);

  const fetchOntologies = useCallback(async () => {
    try {
      const items = (await ontologyApi.list()) as Ontology[];
      setOntologies(items);
      // Selected rather than left for the reader to choose, for the same reason the mapping
      // review page does it: on a deployment with one ontology, asking which one puts the
      // work behind a guess. It also meant the page rendered no table at all until somebody
      // clicked, so the check that reports empty columns had nothing to look at.
      setSelectedOntology((current) => current ?? items[0]?.id ?? null);
    } catch (error) {
      message.error(requestErrorMessage(error, t('rules.ontologyLoadFailed')));
    }
  }, [t]);

  const fetchRules = useCallback(async (ontologyId: number) => {
    setLoading(true);
    setLoadError('');
    try {
      const items = await ontologyApi.getRules(ontologyId);
      setRules(items as BusinessRule[]);
    } catch (error) {
      // A failed read used to render as an empty rule list, which reads as "this ontology
      // has no rules" -- on the page where a reviewer checks that the controls they believe
      // are running actually exist.
      setRules([]);
      setLoadError(requestErrorMessage(error, t('rules.rulesLoadFailed')));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => { fetchOntologies(); }, [fetchOntologies]);

  useEffect(() => {
    if (selectedOntology) {
      fetchRules(selectedOntology);
    }
  }, [selectedOntology, fetchRules]);

  const handleCreate = () => {
    setEditingRule(null);
    setModalTitle(t('rules.newRule'));
    form.resetFields();
    form.setFieldsValue({ severity: 'warning', ruleType: 'validation', status: 'published' });
    setModalVisible(true);
  };

  const handleEdit = (rule: BusinessRule) => {
    setEditingRule(rule);
    setModalTitle(t('rules.editRule'));
    form.setFieldsValue(rule);
    setModalVisible(true);
  };

  const handleDetail = (rule: BusinessRule) => {
    setDetailRule(rule);
    setDetailVisible(true);
  };

  const handleDelete = async (rule: BusinessRule) => {
    if (!selectedOntology) return;
    try {
      await ontologyApi.deleteRule(selectedOntology, rule.id);
      message.success(t('rules.deleted', { code: rule.code }));
      fetchRules(selectedOntology);
    } catch (error) {
      message.error(requestErrorMessage(error, t('rules.deleteFailed')));
    }
  };

  const handleToggleStatus = async (rule: BusinessRule) => {
    if (!selectedOntology) return;
    const newStatus = rule.status === 'published' ? 'disabled' : 'published';
    try {
      await ontologyApi.toggleRuleStatus(selectedOntology, rule.id, newStatus);
      message.success(newStatus === 'published' ? t('rules.enabled') : t('rules.disabled'));
      fetchRules(selectedOntology);
    } catch (error) {
      message.error(requestErrorMessage(error, t('rules.toggleFailed')));
    }
  };

  const handleFormSubmit = async () => {
    if (!selectedOntology) {
      message.warning(t('rules.selectOntologyFirst'));
      return;
    }
    try {
      const values = await form.validateFields();
      if (editingRule) {
        await ontologyApi.updateRule(selectedOntology, editingRule.id, values);
        message.success(t('rules.updated'));
      } else {
        await ontologyApi.createRule(selectedOntology, values);
        message.success(t('rules.created'));
      }
      setModalVisible(false);
      fetchRules(selectedOntology);
    } catch (error: any) {
      if (error?.errorFields) return;
      message.error(editingRule ? t('rules.updateFailed') : t('rules.createFailed'));
    }
  };

  const handleImportRulesFromWord = async (file: File) => {
    if (!selectedOntology) {
      message.warning(t('rules.selectOntologyFirst'));
      return false;
    }
    setRuleImporting(true);
    try {
      const result = await ontologyApi.importRulesFromWord(selectedOntology, file, true);
      setImportResult(result);
      if (result.errorCount > 0) {
        message.warning(t('rules.importPartial', {
          total: result.rules.length,
          imported: result.importedCount,
          failed: result.errorCount,
        }));
      } else {
        message.success(t('rules.importedFromWord', { count: result.importedCount }));
      }
      fetchRules(selectedOntology);
    } catch (error) {
      message.error(requestErrorMessage(error, t('rules.importFailed')));
    } finally {
      setRuleImporting(false);
    }
    return false;
  };

  const columns = [
    {
      title: t('rules.code'),
      dataIndex: 'code',
      key: 'code',
      width: 140,
    },
    {
      title: t('rules.name'),
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
      width: 160,
    },
    {
      title: t('rules.type'),
      dataIndex: 'ruleType',
      key: 'ruleType',
      width: 100,
      render: (type: string) => <Tag>{label(RULE_TYPE, type)}</Tag>,
    },
    {
      title: t('rules.scope'),
      dataIndex: 'scopeObjectCode',
      key: 'scopeObjectCode',
      width: 110,
    },
    {
      title: t('rules.expression'),
      dataIndex: 'expression',
      key: 'expression',
      ellipsis: true,
      render: (expr: string) => (
        <code style={{ background: '#f5f5f5', padding: '2px 6px', borderRadius: 4, fontSize: 12 }}>
          {expr}
        </code>
      ),
    },
    {
      title: t('rules.severity'),
      dataIndex: 'severity',
      key: 'severity',
      width: 100,
      render: (severity: string) => (
        <Tag color={severityColor[severity] || 'blue'}>{label(RULE_SEVERITY, severity)}</Tag>
      ),
    },
    {
      title: t('rules.status'),
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status: string) => (
        <Tag color={statusColor[status] || 'default'}>{label(RULE_STATUS, status)}</Tag>
      ),
    },
    {
      title: t('rules.note'),
      dataIndex: 'naturalLanguage',
      key: 'naturalLanguage',
      ellipsis: true,
    },
    {
      title: t('rules.actions'),
      key: 'action',
      width: 200,
      render: (_: unknown, record: BusinessRule) => (
        <Space>
          <Tooltip title={t('rules.viewDetail')}>
            <Button type="link" icon={<EyeOutlined />} size="small" onClick={() => handleDetail(record)} />
          </Tooltip>
          <Tooltip title={t('rules.edit')}>
            <Button type="link" icon={<EditOutlined />} size="small" onClick={() => handleEdit(record)} />
          </Tooltip>
          <Tooltip title={record.status === 'published' ? t('rules.disable') : t('rules.enable')}>
            <Switch
              checked={record.status === 'published'}
              size="small"
              onChange={() => handleToggleStatus(record)}
            />
          </Tooltip>
          <Popconfirm
            title={t('rules.deleteConfirm')}
            onConfirm={() => handleDelete(record)}
            okText={t('rules.delete')}
            cancelText={t('rules.cancel')}
          >
            <Tooltip title={t('rules.delete')}>
              <Button type="link" icon={<DeleteOutlined />} size="small" danger />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Row justify="space-between" align="middle">
        <Col><Title level={3}>{t('rules.title')}</Title></Col>
        <Col>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => selectedOntology && fetchRules(selectedOntology)}>
              {t('rules.refresh')}
            </Button>
          </Space>
        </Col>
      </Row>

      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <span>{t('rules.chooseOntology')}</span>
          <Select
            style={{ width: 300 }}
            placeholder={t('rules.selectOntologyPlaceholder')}
            onChange={(value) => setSelectedOntology(value)}
            allowClear
            value={selectedOntology}
          >
            {ontologies.map(ontology => (
              <Option key={ontology.id} value={ontology.id}>
                {t('rules.ontologyOption', { name: ontology.name, version: ontology.version, status: label(ONTOLOGY_STATUS, ontology.status) })}
              </Option>
            ))}
          </Select>
          {selectedOntology && (
            <>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
                {t('rules.newRule')}
              </Button>
              <Button icon={<UploadOutlined />} onClick={() => setImportModalVisible(true)}>
                {t('rules.importWord')}
              </Button>
            </>
          )}
        </Space>
      </Card>

      <Card>
        {loadError ? (
          <Alert
            type="error"
            showIcon
            message={t('rules.rulesLoadFailed')}
            description={loadError}
            action={<Button onClick={() => selectedOntology && fetchRules(selectedOntology)}>{t('rules.retry')}</Button>}
          />
        ) : rules.length === 0 && !loading ? (
          // Three different situations, and "请选择本体" told the reader to pick something
          // that may not exist: on a fresh install the list is empty and the instruction is
          // impossible to follow. Naming the next step beats naming the missing selection.
          <Empty
            description={
              ontologies.length === 0
                ? t('rules.emptyNoOntologies')
                : selectedOntology
                  ? t('rules.emptyNoRules')
                  : t('rules.emptySelectOntology')
            }
          />
        ) : (
          <Table
            columns={columns}
            dataSource={rules}
            rowKey="id"
            loading={loading}
            pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (total) => t('rules.totalRules', { total }) }}
            scroll={{ x: 1100 }}
            size="middle"
          />
        )}
      </Card>

      <Modal
        title={modalTitle}
        open={modalVisible}
        onOk={handleFormSubmit}
        onCancel={() => setModalVisible(false)}
        width={640}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="code" label={t('rules.formCode')} rules={[{ required: true, message: t('rules.codeRequired') }]}>
                <Input placeholder="e.g. contract_amount_check" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="name" label={t('rules.formName')}>
                <Input placeholder={t('rules.formName')} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="ruleType" label={t('rules.formType')} rules={[{ required: true }]}>
                <Select
                  options={Object.entries(RULE_TYPE).map(([value]) => ({ value, label: label(RULE_TYPE, value) }))}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="scopeObjectCode" label={t('rules.scope')} rules={[{ required: true, message: t('rules.scopeRequired') }]}>
                <Input placeholder="e.g. contract" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="severity" label={t('rules.severity')} rules={[{ required: true }]}>
                <Select>
                  {Object.entries(RULE_SEVERITY).map(([value]) => <Option key={value} value={value}>{label(RULE_SEVERITY, value)}</Option>)}
                </Select>
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="expression" label={t('rules.formExpression')} rules={[{ required: true, message: t('rules.expressionRequired') }]}>
            <TextArea rows={3} placeholder="e.g. amount > 0 and status != 'invalid'" />
          </Form.Item>
          <Form.Item name="naturalLanguage" label={t('rules.formNaturalLanguage')}>
            <TextArea rows={2} placeholder={t('rules.naturalLanguagePlaceholder')} />
          </Form.Item>
          <Form.Item name="status" label={t('rules.status')}>
            <Select>
              {Object.entries(RULE_STATUS).map(([value]) => <Option key={value} value={value}>{label(RULE_STATUS, value)}</Option>)}
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t('rules.importWord')}
        open={importModalVisible}
        onCancel={() => { setImportModalVisible(false); setImportResult(null); }}
        footer={null}
        width={600}
      >
        <Dragger
          name="file"
          accept=".docx,.doc"
          multiple={false}
          showUploadList={false}
          beforeUpload={handleImportRulesFromWord}
          disabled={ruleImporting}
        >
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p className="ant-upload-text">{t('rules.uploadText')}</p>
          <p className="ant-upload-hint">
            {t('rules.uploadHint')}
            {ruleImporting && <><br /><ReloadOutlined spin /> {t('rules.importing')}</>}
          </p>
        </Dragger>
        {importResult && (
          <Card size="small" style={{ marginTop: 16 }} title={t('rules.importResultTitle', { file: importResult.file.name })}>
            <p>{t('rules.importRecognized', { count: importResult.rules.length })}</p>
            <p>{t('rules.importSucceeded', { count: importResult.importedCount })}</p>
            {importResult.errorCount > 0 && (
              <p style={{ color: 'red' }}>{t('rules.importErrorCount', { count: importResult.errorCount })}</p>
            )}
            {importResult.warnings.length > 0 && (
              <div>
                <Text type="warning">{t('rules.warnings')}</Text>
                {importResult.warnings.map((w, i) => (
                  <p key={i} style={{ fontSize: 12, color: '#faad14' }}>{w}</p>
                ))}
              </div>
            )}
            {importResult.errors.length > 0 && (
              <div>
                <Text type="danger">{t('rules.errors')}</Text>
                {importResult.errors.map((e, i) => (
                  <p key={i} style={{ fontSize: 12, color: 'red' }}>{e.code}: {e.error}</p>
                ))}
              </div>
            )}
          </Card>
        )}
      </Modal>

      <Modal
        title={t('rules.detailTitle')}
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        footer={<Button onClick={() => setDetailVisible(false)}>{t('rules.close')}</Button>}
        width={600}
      >
        {detailRule && (
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label={t('rules.code')}>{detailRule.code}</Descriptions.Item>
            <Descriptions.Item label={t('rules.name')}>{detailRule.name}</Descriptions.Item>
            <Descriptions.Item label={t('rules.type')}>
              <Tag>{label(RULE_TYPE, detailRule.ruleType)}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label={t('rules.scope')}>{detailRule.scopeObjectCode}</Descriptions.Item>
            <Descriptions.Item label={t('rules.severity')}>
              <Tag color={severityColor[detailRule.severity]}>{label(RULE_SEVERITY, detailRule.severity)}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label={t('rules.status')}>
              <Tag color={statusColor[detailRule.status]}>{label(RULE_STATUS, detailRule.status)}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label={t('rules.expression')} span={2}>
              <code style={{ background: '#f5f5f5', padding: '4px 8px', borderRadius: 4 }}>{detailRule.expression}</code>
            </Descriptions.Item>
            <Descriptions.Item label={t('rules.note')} span={2}>
              {detailRule.naturalLanguage || '-'}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  );
};

export default RuleList;
