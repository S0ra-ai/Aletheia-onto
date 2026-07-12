import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Typography, Tag, Empty, Select, Space, message, Switch, Button,
  Modal, Form, Input, Upload, Descriptions, Popconfirm, Tooltip, Row, Col,
} from 'antd';
import {
  EditOutlined, DeleteOutlined, PlusOutlined, UploadOutlined, InboxOutlined,
  ReloadOutlined, EyeOutlined,
} from '@ant-design/icons';
import { ontologyApi } from '../../api';
import type { Ontology, BusinessRule, RuleWordImportResult } from '../../types';

const { Title, Text } = Typography;
const { Option } = Select;
const { TextArea } = Input;
const { Dragger } = Upload;

const RULE_TYPES = ['validation', 'derivation', 'transition', 'risk', 'recommendation', 'permission'];
const SEVERITIES = ['info', 'warning', 'blocking'];
const STATUSES = ['draft', 'published', 'disabled'];

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
  const [ontologies, setOntologies] = useState<Ontology[]>([]);
  const [rules, setRules] = useState<BusinessRule[]>([]);
  const [selectedOntology, setSelectedOntology] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  const [modalVisible, setModalVisible] = useState(false);
  const [modalTitle, setModalTitle] = useState('新建规则');
  const [editingRule, setEditingRule] = useState<BusinessRule | null>(null);
  const [form] = Form.useForm();

  const [importResult, setImportResult] = useState<RuleWordImportResult | null>(null);
  const [importModalVisible, setImportModalVisible] = useState(false);
  const [ruleImporting, setRuleImporting] = useState(false);

  const [detailVisible, setDetailVisible] = useState(false);
  const [detailRule, setDetailRule] = useState<BusinessRule | null>(null);

  const fetchOntologies = useCallback(async () => {
    try {
      const items = await ontologyApi.list();
      setOntologies(items as Ontology[]);
    } catch {
      message.error('获取本体列表失败');
    }
  }, []);

  const fetchRules = useCallback(async (ontologyId: number) => {
    setLoading(true);
    try {
      const items = await ontologyApi.getRules(ontologyId);
      setRules(items as BusinessRule[]);
    } catch {
      console.error('Failed to fetch rules');
      setRules([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchOntologies(); }, [fetchOntologies]);

  useEffect(() => {
    if (selectedOntology) {
      fetchRules(selectedOntology);
    }
  }, [selectedOntology, fetchRules]);

  const handleCreate = () => {
    setEditingRule(null);
    setModalTitle('新建规则');
    form.resetFields();
    form.setFieldsValue({ severity: 'warning', ruleType: 'validation', status: 'published' });
    setModalVisible(true);
  };

  const handleEdit = (rule: BusinessRule) => {
    setEditingRule(rule);
    setModalTitle('编辑规则');
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
      message.success(`规则 ${rule.code} 已删除`);
      fetchRules(selectedOntology);
    } catch {
      message.error('删除规则失败');
    }
  };

  const handleToggleStatus = async (rule: BusinessRule) => {
    if (!selectedOntology) return;
    const newStatus = rule.status === 'published' ? 'disabled' : 'published';
    try {
      await ontologyApi.toggleRuleStatus(selectedOntology, rule.id, newStatus);
      message.success(`规则已${newStatus === 'published' ? '启用' : '停用'}`);
      fetchRules(selectedOntology);
    } catch {
      message.error('切换规则状态失败');
    }
  };

  const handleFormSubmit = async () => {
    if (!selectedOntology) {
      message.warning('请先选择本体');
      return;
    }
    try {
      const values = await form.validateFields();
      if (editingRule) {
        await ontologyApi.updateRule(selectedOntology, editingRule.id, values);
        message.success('规则已更新');
      } else {
        await ontologyApi.createRule(selectedOntology, values);
        message.success('规则已创建');
      }
      setModalVisible(false);
      fetchRules(selectedOntology);
    } catch (error: any) {
      if (error?.errorFields) return;
      message.error(editingRule ? '更新规则失败' : '创建规则失败');
    }
  };

  const handleImportRulesFromWord = async (file: File) => {
    if (!selectedOntology) {
      message.warning('请先选择本体');
      return false;
    }
    setRuleImporting(true);
    try {
      const result = await ontologyApi.importRulesFromWord(selectedOntology, file, true);
      setImportResult(result);
      if (result.errorCount > 0) {
        message.warning(`识别 ${result.rules.length} 条规则，成功导入 ${result.importedCount} 条，失败 ${result.errorCount} 条`);
      } else {
        message.success(`已从 Word 导入 ${result.importedCount} 条自定义规则`);
      }
      fetchRules(selectedOntology);
    } catch {
      message.error('规则 Word 导入失败，请确认文件格式和规则字段');
    } finally {
      setRuleImporting(false);
    }
    return false;
  };

  const columns = [
    {
      title: '编码',
      dataIndex: 'code',
      key: 'code',
      width: 140,
    },
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
      width: 160,
    },
    {
      title: '类型',
      dataIndex: 'ruleType',
      key: 'ruleType',
      width: 100,
      render: (type: string) => <Tag>{type}</Tag>,
    },
    {
      title: '适用对象',
      dataIndex: 'scopeObjectCode',
      key: 'scopeObjectCode',
      width: 110,
    },
    {
      title: '表达式',
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
      title: '严重程度',
      dataIndex: 'severity',
      key: 'severity',
      width: 100,
      render: (severity: string) => (
        <Tag color={severityColor[severity] || 'blue'}>{severity}</Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status: string) => (
        <Tag color={statusColor[status] || 'default'}>{status}</Tag>
      ),
    },
    {
      title: '业务说明',
      dataIndex: 'naturalLanguage',
      key: 'naturalLanguage',
      ellipsis: true,
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: unknown, record: BusinessRule) => (
        <Space>
          <Tooltip title="查看详情">
            <Button type="link" icon={<EyeOutlined />} size="small" onClick={() => handleDetail(record)} />
          </Tooltip>
          <Tooltip title="编辑">
            <Button type="link" icon={<EditOutlined />} size="small" onClick={() => handleEdit(record)} />
          </Tooltip>
          <Tooltip title={record.status === 'published' ? '停用' : '启用'}>
            <Switch
              checked={record.status === 'published'}
              size="small"
              onChange={() => handleToggleStatus(record)}
            />
          </Tooltip>
          <Popconfirm
            title="确定删除这条规则吗？"
            onConfirm={() => handleDelete(record)}
            okText="删除"
            cancelText="取消"
          >
            <Tooltip title="删除">
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
        <Col><Title level={3}>规则管理</Title></Col>
        <Col>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => selectedOntology && fetchRules(selectedOntology)}>
              刷新
            </Button>
          </Space>
        </Col>
      </Row>

      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <span>选择本体：</span>
          <Select
            style={{ width: 300 }}
            placeholder="请选择本体"
            onChange={(value) => setSelectedOntology(value)}
            allowClear
            value={selectedOntology}
          >
            {ontologies.map(ontology => (
              <Option key={ontology.id} value={ontology.id}>
                {ontology.name} v{ontology.version} ({ontology.status})
              </Option>
            ))}
          </Select>
          {selectedOntology && (
            <>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
                新建规则
              </Button>
              <Button icon={<UploadOutlined />} onClick={() => setImportModalVisible(true)}>
                Word 导入规则
              </Button>
            </>
          )}
        </Space>
      </Card>

      <Card>
        {rules.length === 0 && !loading ? (
          <Empty description={selectedOntology ? '该本体暂无规则，点击上方按钮创建或导入' : '请选择本体查看业务规则'} />
        ) : (
          <Table
            columns={columns}
            dataSource={rules}
            rowKey="id"
            loading={loading}
            pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (total) => `共 ${total} 条规则` }}
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
              <Form.Item name="code" label="规则编码" rules={[{ required: true, message: '请输入规则编码' }]}>
                <Input placeholder="e.g. contract_amount_check" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="name" label="规则名称">
                <Input placeholder="规则名称" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="ruleType" label="规则类型" rules={[{ required: true }]}>
                <Select>
                  {RULE_TYPES.map(t => <Option key={t} value={t}>{t}</Option>)}
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="scopeObjectCode" label="适用对象" rules={[{ required: true, message: '请输入业务对象编码' }]}>
                <Input placeholder="e.g. contract" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="severity" label="严重程度" rules={[{ required: true }]}>
                <Select>
                  {SEVERITIES.map(s => <Option key={s} value={s}>{s}</Option>)}
                </Select>
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="expression" label="规则表达式" rules={[{ required: true, message: '请输入规则表达式' }]}>
            <TextArea rows={3} placeholder="e.g. amount > 0 and status != 'invalid'" />
          </Form.Item>
          <Form.Item name="naturalLanguage" label="自然语言说明">
            <TextArea rows={2} placeholder="业务描述" />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select>
              {STATUSES.map(s => <Option key={s} value={s}>{s}</Option>)}
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="Word 导入规则"
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
          <p className="ant-upload-text">点击或拖拽 Word 文件到此处</p>
          <p className="ant-upload-hint">
            支持 .docx 和 .doc 格式。
            {ruleImporting && <><br /><ReloadOutlined spin /> 正在导入...</>}
          </p>
        </Dragger>
        {importResult && (
          <Card size="small" style={{ marginTop: 16 }} title={`导入结果 (${importResult.file.name})`}>
            <p>识别规则: {importResult.rules.length} 条</p>
            <p>成功导入: {importResult.importedCount} 条</p>
            {importResult.errorCount > 0 && (
              <p style={{ color: 'red' }}>失败: {importResult.errorCount} 条</p>
            )}
            {importResult.warnings.length > 0 && (
              <div>
                <Text type="warning">警告:</Text>
                {importResult.warnings.map((w, i) => (
                  <p key={i} style={{ fontSize: 12, color: '#faad14' }}>{w}</p>
                ))}
              </div>
            )}
            {importResult.errors.length > 0 && (
              <div>
                <Text type="danger">错误:</Text>
                {importResult.errors.map((e, i) => (
                  <p key={i} style={{ fontSize: 12, color: 'red' }}>{e.code}: {e.error}</p>
                ))}
              </div>
            )}
          </Card>
        )}
      </Modal>

      <Modal
        title="规则详情"
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        footer={<Button onClick={() => setDetailVisible(false)}>关闭</Button>}
        width={600}
      >
        {detailRule && (
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="编码">{detailRule.code}</Descriptions.Item>
            <Descriptions.Item label="名称">{detailRule.name}</Descriptions.Item>
            <Descriptions.Item label="类型"><Tag>{detailRule.ruleType}</Tag></Descriptions.Item>
            <Descriptions.Item label="适用对象">{detailRule.scopeObjectCode}</Descriptions.Item>
            <Descriptions.Item label="严重程度">
              <Tag color={severityColor[detailRule.severity]}>{detailRule.severity}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="状态">
              <Tag color={statusColor[detailRule.status]}>{detailRule.status}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="表达式" span={2}>
              <code style={{ background: '#f5f5f5', padding: '4px 8px', borderRadius: 4 }}>{detailRule.expression}</code>
            </Descriptions.Item>
            <Descriptions.Item label="业务说明" span={2}>
              {detailRule.naturalLanguage || '-'}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  );
};

export default RuleList;
