import React, { useState } from 'react';
import { Alert, Button, Card, Divider, message, Result, Typography } from 'antd';
import { RocketOutlined, FileTextOutlined, SettingOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { DECISION_STATUS } from '../../i18n/labels';
import { useLabel, useT } from '../../i18n/locale';
import { discardedReport } from '../../i18n/text';
import { demoApi, requestErrorMessage } from '../../api';
import type { DemoBootstrapResult } from '../../types';

const { Title, Paragraph } = Typography;

const DemoCenter: React.FC = () => {
  const label = useLabel();
  const navigate = useNavigate();
  const t = useT();
  const [loading, setLoading] = useState<'contract' | 'equipment' | null>(null);
  const [result, setResult] = useState<DemoBootstrapResult | null>(null);

  // One handler for both demonstrations: they differ only in which endpoint they call, and
  // two copies is how the failure handling drifted apart in the first place.
  const bootstrap = async (kind: 'contract' | 'equipment') => {
    setLoading(kind);
    try {
      const data = kind === 'contract' ? await demoApi.bootstrapContract() : await demoApi.bootstrapEquipment();
      setResult(data);
    } catch (error) {
      // This is the first button a new user presses. It used to `console.error` and stop,
      // so on any environment where the bootstrap fails the spinner vanished and nothing
      // else happened -- no message, no state change, nothing to report.
      message.error(requestErrorMessage(error, t('demo.loadFailed')));
    } finally {
      setLoading(null);
    }
  };

  // Computed once, above the JSX: the warning's text and its condition are the same value,
  // and a composition this cheap is still not one to run twice per render.
  const lost = result ? discardedReport(result.ontology.discarded, t, result.ontology.discardedSummary || '') : '';

  return (
    <div>
      <Title level={3}>{t('demo.title')}</Title>
      <Paragraph type="secondary">
        {t('demo.subtitle')}
      </Paragraph>

      <Alert
        message={t('demo.notice.title')}
        description={t('demo.notice.body')}
        type="info"
        showIcon
        style={{ marginBottom: 24 }}
      />

      <div style={{ display: 'flex', gap: 24 }}>
        <Card
          title={t('demo.contract.title')}
          style={{ flex: 1 }}
          extra={<FileTextOutlined style={{ fontSize: 24, color: '#1890ff' }} />}
        >
          <Paragraph>
            {t('demo.contract.intro')}
          </Paragraph>
          <ul>
            <li>{t('demo.contract.objects')}</li>
            <li>{t('demo.contract.risks')}</li>
            <li>{t('demo.contract.rules')}</li>
          </ul>
          <Button
            type="primary"
            icon={<RocketOutlined />}
            loading={loading === 'contract'}
            onClick={() => bootstrap('contract')}
            block
          >
            {t('demo.contract.start')}
          </Button>
        </Card>

        <Card
          title={t('demo.equipment.title')}
          style={{ flex: 1 }}
          extra={<SettingOutlined style={{ fontSize: 24, color: '#52c41a' }} />}
        >
          <Paragraph>
            {t('demo.equipment.intro')}
          </Paragraph>
          <ul>
            <li>{t('demo.equipment.objects')}</li>
            <li>{t('demo.equipment.risks')}</li>
            <li>{t('demo.equipment.rules')}</li>
          </ul>
          <Button
            type="primary"
            icon={<RocketOutlined />}
            loading={loading === 'equipment'}
            onClick={() => bootstrap('equipment')}
            block
            style={{ background: '#52c41a', borderColor: '#52c41a' }}
          >
            {t('demo.equipment.start')}
          </Button>
        </Card>
      </div>

      {result && (
        <>
          <Divider />
          {/* Pressing the button a second time re-drafts a source that already has a draft, and
              a rebuild clears the rules, mappings and workflows attached to the old one. The
              backend has reported that since the rebuild landed; this screen answered with a
              green tick, which is a silent loss wearing a success message. */}
          {lost && (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 16 }}
              message={t('ontology.draftRebuilt', { summary: lost })}
            />
          )}
          <Result
            status="success"
            title={t('demo.successTitle')}
            subTitle={
              result.decision
                ? t('demo.resultWithDecision', { id: result.dataSource.id, decision: label(DECISION_STATUS, result.decision) })
                : t('demo.resultWithoutDecision', { id: result.dataSource.id })
            }
            extra={[
              <Button
                type="primary"
                key="datasource"
                onClick={() => navigate(`/datasource/${result.dataSource.id}`)}
              >
                {t('demo.viewDatasource')}
              </Button>,
              <Button
                key="ontology"
                onClick={() => navigate(`/ontology/${result.ontology.id}`)}
              >
                {t('demo.viewOntology')}
              </Button>,
              <Button
                key="semantic"
                onClick={() => navigate('/semantic')}
              >
                {t('demo.trySemantic')}
              </Button>,
            ]}
          />
        </>
      )}
    </div>
  );
};

export default DemoCenter;
