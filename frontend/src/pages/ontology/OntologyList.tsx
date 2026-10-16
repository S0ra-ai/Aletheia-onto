import React, { useEffect, useState } from 'react';
import { label, ONTOLOGY_STATUS } from '../../i18n/labels';
import { useT } from '../../i18n/locale';
import { Alert, Card, Table, Button, Space, Typography, Tag, Modal, Form, Input, Select, message, Empty } from 'antd';
import { PlusOutlined, EditOutlined, EyeOutlined, ImportOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { dataSourceApi, industryBlueprintApi, ontologyApi, requestErrorMessage } from '../../api';
import type { Ontology, DataSource, OntologyDraftCreate, IndustryBlueprint } from '../../types';

const { Title } = Typography;
const { Option } = Select;

const OntologyList: React.FC = () => {
  const navigate = useNavigate();
  const t = useT();
  const [ontologies, setOntologies] = useState<Ontology[]>([]);
  const [dataSources, setDataSources] = useState<DataSource[]>([]);
  const [blueprints, setBlueprints] = useState<IndustryBlueprint[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [blueprintModalVisible, setBlueprintModalVisible] = useState(false);
  const [form] = Form.useForm();
  const [blueprintForm] = Form.useForm();

  const fetchData = async () => {
    setLoading(true);
    try {
      const sources = await dataSourceApi.list();
      setDataSources(sources);
      setBlueprints(await industryBlueprintApi.list());
      const allOntologies = await ontologyApi.list();
      setOntologies(allOntologies as Ontology[]);
    } catch (error) {
      message.error(requestErrorMessage(error, t('ontology.listLoadFailed')));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [t]);

  const handleCreateDraft = async (values: OntologyDraftCreate) => {
    try {
      const draft = await ontologyApi.createDraft(values);
      // Say what the rebuild cost. 「本体草案生成成功」 was the whole message while a draft's
      // hand-written rules and workflows were being deleted: the operation is destructive by
      // design, and a user who asked for a rebuild still deserves to know what it took.
      if (draft?.discardedSummary) {
        message.warning(t('ontology.draftRebuilt', { summary: draft.discardedSummary }), 6);
      } else {
        message.success(t('ontology.draftCreated'));
      }
      setModalVisible(false);
      form.resetFields();
      fetchData();
    } catch (error) {
      message.error(requestErrorMessage(error, t('ontology.createFailed')));
    }
  };

  const handleImportBlueprint = async (values: { blueprintJson: string }) => {
    try {
      const payload = JSON.parse(values.blueprintJson) as IndustryBlueprint;
      await industryBlueprintApi.upsert(payload);
      message.success(t('ontology.blueprintImported'));
      setBlueprintModalVisible(false);
      blueprintForm.resetFields();
      fetchData();
    } catch (error) {
      message.error(error instanceof SyntaxError ? t('ontology.blueprintJsonInvalid') : t('ontology.blueprintImportFailed'));
    }
  };

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
    },
    {
      title: t('ontology.name'),
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: t('ontology.version'),
      dataIndex: 'version',
      key: 'version',
      render: (version: string) => <Tag>v{version}</Tag>,
    },
    {
      title: t('ontology.status'),
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={status === 'published' ? 'green' : status === 'draft' ? 'orange' : 'default'}>
          {label(ONTOLOGY_STATUS, status)}
        </Tag>
      ),
    },
    {
      title: t('ontology.domain'),
      dataIndex: 'domain',
      key: 'domain',
      render: (domain: string) => domain || '-',
    },
    {
      title: t('shell.common.actions'),
      key: 'action',
      render: (_: unknown, record: Ontology) => (
        <Space>
          <Button
            type="link"
            icon={<EyeOutlined />}
            onClick={() => navigate(`/ontology/${record.id}`)}
          >
            {t('ontology.view')}
          </Button>
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => navigate(`/ontology/${record.id}/edit`)}
          >
            {t('ontology.edit')}
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={3}>{t('ontology.title')}</Title>
        <Space>
          <Button
            icon={<ImportOutlined />}
            onClick={() => setBlueprintModalVisible(true)}
          >
            {t('ontology.importBlueprint')}
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setModalVisible(true)}
          >
            {t('ontology.createDraft')}
          </Button>
        </Space>
      </div>

      <Card>
        {ontologies.length === 0 && !loading ? (
          <Empty
            description={
              dataSources.length === 0
                ? t('ontology.emptyNoSource')
                : t('ontology.emptyData')
            }
          >
            {/* The button generates from a data source. Offering it with none registered
                leads straight to an empty dropdown and a disabled confirm. */}
            {dataSources.length === 0 ? (
              <Button type="primary" onClick={() => navigate('/datasource')}>
                {t('ontology.goToDataSource')}
              </Button>
            ) : (
              <Button type="primary" onClick={() => setModalVisible(true)}>
                {t('ontology.createFirst')}
              </Button>
            )}
          </Empty>
        ) : (
          <Table
            columns={columns}
            dataSource={ontologies}
            rowKey="id"
            loading={loading}
          />
        )}
      </Card>

      <Modal
        title={t('ontology.createDraft')}
        open={modalVisible}
        onCancel={() => {
          setModalVisible(false);
          form.resetFields();
        }}
        onOk={() => form.submit()}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleCreateDraft}
        >
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message={t('ontology.rebuildWarning')}
            description={t('ontology.rebuildDetail')}
          />
          <Form.Item
            name="dataSourceId"
            label={t('ontology.selectDataSource')}
            rules={[{ required: true, message: t('ontology.dataSourceRequired') }]}
          >
            <Select placeholder={t('ontology.dataSourcePlaceholder')}>
              {dataSources.map(source => (
                <Option key={source.id} value={source.id}>
                  {source.name} ({source.sourceType})
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item
            name="blueprintId"
            label={t('ontology.blueprint')}
          >
            <Select placeholder={t('ontology.blueprintPlaceholder')} allowClear>
              {blueprints.map(blueprint => (
                <Option key={blueprint.id} value={blueprint.id}>
                  {blueprint.name} ({blueprint.domain})
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item
            name="name"
            label={t('ontology.ontologyName')}
          >
            <Input placeholder={t('ontology.namePlaceholder')} />
          </Form.Item>
          <Form.Item
            name="domain"
            label={t('ontology.domain')}
          >
            <Input placeholder={t('ontology.domainPlaceholder')} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t('ontology.importBlueprint')}
        open={blueprintModalVisible}
        onCancel={() => {
          setBlueprintModalVisible(false);
          blueprintForm.resetFields();
        }}
        onOk={() => blueprintForm.submit()}
        width={760}
      >
        <Form form={blueprintForm} layout="vertical" onFinish={handleImportBlueprint}>
          <Form.Item
            name="blueprintJson"
            label={t('ontology.blueprintJson')}
            rules={[{ required: true, message: t('ontology.blueprintJsonRequired') }]}
          >
            <Input.TextArea
              rows={14}
              placeholder={t('ontology.blueprintJsonPlaceholder')}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default OntologyList;
