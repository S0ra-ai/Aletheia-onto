import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert, Button, Card, Descriptions, Divider, Form, Input, InputNumber, Popconfirm, Select,
  Space, Spin, Switch, Tag, Tooltip, Typography, message,
} from 'antd';
import {
  ApiOutlined, CheckCircleOutlined, CloseCircleOutlined, SaveOutlined, UndoOutlined,
} from '@ant-design/icons';
import { modelApi, requestErrorMessage } from '../../api';
import { useT } from '../../i18n/locale';
import type { MessageKey } from '../../i18n/messages';
import type { ModelConfig, ModelConfigUpdate } from '../../types';

const { Title, Paragraph, Text } = Typography;

/**
 * Model configuration.
 *
 * The platform speaks the OpenAI chat-completions protocol, so anything that
 * implements it can be used: official APIs, relay/subscription gateways,
 * self-hosted vLLM or Ollama, Azure OpenAI, and domestic providers. A base URL
 * alone is not enough, because providers differ in how they authenticate and
 * which extra body fields they tolerate -- hence the compatibility section.
 */

interface Preset {
  /**
   * Declared as a `MessageKey` rather than a `string` so a typo is a compile error.
   *
   * Both keys below reach `t()` through a variable, and a variable key cannot be checked the
   * way `t('model.note.azure')` can. The casts that used to sit at those two call sites
   * (`as never`) did not fix that -- they turned the check off, which is how a whole screen's
   * worth of keys can be missing while the type checker stays quiet.
   */
  labelKey: MessageKey;
  provider: string;
  baseUrl: string;
  model: string;
  authStyle: string;
  authHeader?: string;
  sendProviderExtras: boolean;
  /** Dictionary key for what this preset gets right, and what it gets wrong. */
  noteKey: MessageKey;
}

/** Starting points for the shapes we have actually had to support. */
const PRESETS: Record<string, Preset> = {
  openrouter: {
    labelKey: 'model.preset.openrouter',
    noteKey: 'model.note.openrouter',
    provider: 'openrouter',
    baseUrl: 'https://openrouter.ai/api/v1',
    model: 'openai/gpt-4o-mini',
    authStyle: 'bearer',
    sendProviderExtras: true,
  },
  openai: {
    labelKey: 'model.preset.openai',
    noteKey: 'model.note.openai',
    provider: 'openai',
    baseUrl: 'https://api.openai.com/v1',
    model: 'gpt-4o-mini',
    authStyle: 'bearer',
    sendProviderExtras: false,
  },
  relay: {
    labelKey: 'model.preset.relay',
    noteKey: 'model.note.relay',
    provider: 'custom',
    baseUrl: 'https://your-relay.example.com/v1',
    model: 'gpt-4o-mini',
    authStyle: 'bearer',
    sendProviderExtras: false,
  },
  azure: {
    labelKey: 'model.preset.azure',
    noteKey: 'model.note.azure',
    provider: 'azure',
    baseUrl: 'https://<资源名>.openai.azure.com/openai/deployments/<部署名>/chat/completions?api-version=2024-02-01',
    model: '<部署名>',
    authStyle: 'api-key',
    sendProviderExtras: false,
  },
  vllm: {
    labelKey: 'model.preset.vllm',
    noteKey: 'model.note.vllm',
    provider: 'local',
    baseUrl: 'http://127.0.0.1:8000/v1',
    model: 'qwen2.5-7b-instruct',
    authStyle: 'none',
    sendProviderExtras: false,
  },
  dashscope: {
    labelKey: 'model.preset.dashscope',
    noteKey: 'model.note.dashscope',
    provider: 'dashscope',
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    model: 'qwen-max',
    authStyle: 'bearer',
    sendProviderExtras: false,
  },
  deepseek: {
    labelKey: 'model.preset.deepseek',
    noteKey: 'model.note.deepseek',
    provider: 'deepseek',
    baseUrl: 'https://api.deepseek.com',
    model: 'deepseek-flash',
    authStyle: 'bearer',
    sendProviderExtras: false,
  },
};

const AUTH_STYLE_KEYS: Record<string, MessageKey> = {
  bearer: 'model.authStyle.bearer',
  'api-key': 'model.authStyle.apiKey',
  custom: 'model.authStyle.custom',
  none: 'model.authStyle.none',
};

const ModelConfigPage: React.FC = () => {
  const t = useT();
  const [config, setConfig] = useState<ModelConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [testLoading, setTestLoading] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string; model?: string } | null>(null);
  const [authStyle, setAuthStyle] = useState('bearer');
  const [form] = Form.useForm();

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    try {
      const data = await modelApi.getConfig();
      setConfig(data);
      setAuthStyle(data.authStyle || 'bearer');
      form.setFieldsValue({
        apiKey: '', // 从不回显完整 Key
        provider: data.provider || 'openrouter',
        model: data.model,
        baseUrl: data.baseUrl,
        httpReferer: data.httpReferer,
        appTitle: data.appTitle,
        serviceTier: data.serviceTier,
        timeoutSeconds: data.timeoutSeconds,
        authStyle: data.authStyle || 'bearer',
        authHeader: data.authHeader,
        sendProviderExtras: data.sendProviderExtras,
        extraHeadersText: Object.keys(data.extraHeaders || {}).length
          ? JSON.stringify(data.extraHeaders, null, 2)
          : '',
      });
    } catch (error) {
      message.error(requestErrorMessage(error, t('model.loadFailed')));
    } finally {
      setLoading(false);
    }
  }, [form, t]);

  useEffect(() => {
    void fetchConfig();
  }, [fetchConfig]);

  const [appliedPreset, setAppliedPreset] = useState<Preset | null>(null);

  const applyPreset = (key: string) => {
    const preset = PRESETS[key];
    if (!preset) return;
    form.setFieldsValue({
      provider: preset.provider,
      baseUrl: preset.baseUrl,
      model: preset.model,
      authStyle: preset.authStyle,
      authHeader: preset.authHeader || '',
      sendProviderExtras: preset.sendProviderExtras,
    });
    setAuthStyle(preset.authStyle);
    setAppliedPreset(preset);
    message.info(t('model.presetApplied', { name: t(preset.labelKey) }));
  };

  const handleSave = async (values: Record<string, unknown>) => {
    const { extraHeadersText, ...rest } = values;
    const payload: ModelConfigUpdate = { ...(rest as ModelConfigUpdate) };

    // An empty key means "keep the existing one" rather than "clear it".
    if (!payload.apiKey) delete payload.apiKey;

    const raw = String(extraHeadersText ?? '').trim();
    if (raw) {
      try {
        const parsed = JSON.parse(raw);
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
          message.error(t('model.extraHeadersNotObject'));
          return;
        }
        payload.extraHeaders = parsed as Record<string, string>;
      } catch (error) {
        message.error(requestErrorMessage(error, t('model.extraHeadersInvalidJson')));
        return;
      }
    } else {
      payload.extraHeaders = {};
    }

    setLoading(true);
    try {
      await modelApi.updateConfig(payload);
      message.success(t('model.saved'));
      setTestResult(null);
      await fetchConfig();
    } catch (error) {
      message.error(requestErrorMessage(error, t('model.saveFailed')));
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async () => {
    setLoading(true);
    try {
      await modelApi.resetConfig();
      message.success(t('model.resetDone'));
      setTestResult(null);
      await fetchConfig();
    } catch (error) {
      message.error(requestErrorMessage(error, t('model.resetFailed')));
    } finally {
      setLoading(false);
    }
  };

  const handleTest = async () => {
    setTestLoading(true);
    setTestResult(null);
    try {
      const result = await modelApi.testConfig();
      setTestResult(result);
      if (result.success) message.success(t('model.testSucceeded'));
      else message.error(result.message);
    } catch (error) {
      message.error(requestErrorMessage(error, t('model.testFailed')));
    } finally {
      setTestLoading(false);
    }
  };

  if (loading && !config) {
    return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  }

  return (
    <div>
      <Title level={3}>{t('model.title')}</Title>
      <Paragraph type="secondary">
        {t('model.intro')}
        <br />
        <Text type="secondary" style={{ fontSize: 12 }}>
          {t('model.introHint')}
        </Text>
      </Paragraph>

      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label={t('model.configStatus')}>
            <Tag color={config?.configured ? 'green' : 'red'} icon={config?.configured ? <CheckCircleOutlined /> : <CloseCircleOutlined />}>
              {config?.configured ? t('model.configured') : t('model.notConfigured')}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t('model.currentModel')}>{config?.model || '-'}</Descriptions.Item>
          <Descriptions.Item label="API Key">
            {config?.hasApiKey ? <Tag color="green">{config.apiKey}</Tag> : <Tag color="red">{t('model.notSet')}</Tag>}
          </Descriptions.Item>
          <Descriptions.Item label={t('model.authStyleLabel')}>
            <Tag>{AUTH_STYLE_KEYS[config?.authStyle || 'bearer'] ? t(AUTH_STYLE_KEYS[config?.authStyle || 'bearer']) : config?.authStyle}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t('model.resolvedEndpoint')} span={2}>
            <Text code copyable style={{ fontSize: 12 }}>{config?.resolvedEndpoint || '-'}</Text>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card
        title={t('model.connectionCard')}
        extra={
          <Space>
            <Text type="secondary" style={{ fontSize: 12 }}>{t('model.presets')}</Text>
            <Select
              style={{ width: 200 }}
              placeholder={t('model.providerPlaceholder')}
              onChange={applyPreset}
              options={Object.entries(PRESETS).map(([key, preset]) => ({ value: key, label: t(preset.labelKey) }))}
            />
          </Space>
        }
      >
        {appliedPreset && (
          // The preset's note, shown while it is the one that was applied. It is a caveat
          // about the endpoint being configured (Azure's header and full path, vLLM's 400 on
          // unknown fields), which is exactly the thing that goes wrong here -- and the
          // presets carried one for each of the seven all along, rendered nowhere.
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            title={t(appliedPreset.noteKey)}
          />
        )}
        <Form form={form} layout="vertical" onFinish={handleSave}>
          <Form.Item name="provider" label={t('model.providerLabel')} hidden>
            <Input />
          </Form.Item>
          <Form.Item
            name="baseUrl"
            label="API Base URL"
            rules={[{ required: true, message: t('model.baseUrlRequired') }]}
            extra={t('model.baseUrlHint')}
          >
            <Input placeholder="https://your-relay.example.com/v1" />
          </Form.Item>

          <Form.Item
            name="model"
            label={t('model.modelNameLabel')}
            rules={[{ required: true, message: t('model.modelNameRequired') }]}
            extra={t('model.modelNameHint')}
          >
            <Input placeholder="gpt-4o-mini / qwen-max / deepseek-flash" />
          </Form.Item>

          <Form.Item
            name="apiKey"
            label="API Key"
            extra={config?.hasApiKey ? t('model.apiKeyKeepHint') : t('model.apiKeyLocalHint')}
          >
            <Input.Password placeholder="sk-..." autoComplete="new-password" />
          </Form.Item>

          <Divider titlePlacement="start" plain>{t('model.compatibility')}</Divider>

          <Form.Item
            name="authStyle"
            label={t('model.authStyleLabel')}
            extra={t('model.authStyleHint')}
          >
            <Select
              onChange={setAuthStyle}
              options={(config?.authStyleOptions || ['bearer', 'api-key', 'custom', 'none']).map(value => ({
                value,
                label: AUTH_STYLE_KEYS[value] ? t(AUTH_STYLE_KEYS[value]) : value,
              }))}
            />
          </Form.Item>

          {authStyle === 'custom' && (
            <Form.Item
              name="authHeader"
              label={t('model.authHeaderLabel')}
              rules={[{ required: true, message: t('model.authHeaderRequired') }]}
              extra={t('model.authHeaderHint')}
            >
              <Input placeholder="X-Api-Token" />
            </Form.Item>
          )}

          <Form.Item
            name="sendProviderExtras"
            label={
              <Tooltip title={t('model.extrasTooltip')}>
                <span>{t('model.extrasLabel')}</span>
              </Tooltip>
            }
            valuePropName="checked"
            extra={t('model.extrasHint')}
          >
            <Switch />
          </Form.Item>

          <Form.Item
            name="extraHeadersText"
            label={t('model.extraHeadersLabel')}
            extra={t('model.extraHeadersHint')}
          >
            <Input.TextArea rows={3} placeholder='{"X-Tenant-Id": "acme"}' />
          </Form.Item>

          <Divider titlePlacement="start" plain>{t('model.other')}</Divider>

          <Space size={16} style={{ display: 'flex', flexWrap: 'wrap' }}>
            <Form.Item name="serviceTier" label={t('model.serviceTierLabel')} style={{ minWidth: 160 }} extra={t('model.serviceTierHint')}>
              <Input placeholder="auto" />
            </Form.Item>
            <Form.Item name="timeoutSeconds" label={t('model.timeoutLabel')} style={{ minWidth: 160 }}>
              <InputNumber min={5} max={600} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="appTitle" label={t('model.appTitleLabel')} style={{ minWidth: 220 }} extra={t('model.appTitleHint')}>
              <Input placeholder="Aletheia" />
            </Form.Item>
            <Form.Item name="httpReferer" label="HTTP Referer" style={{ minWidth: 220 }} extra={t('model.httpRefererHint')}>
              <Input placeholder="https://example.com" />
            </Form.Item>
          </Space>

          <Space>
            <Button type="primary" icon={<SaveOutlined />} htmlType="submit" loading={loading}>
              {t('model.saveButton')}
            </Button>
            <Button icon={<ApiOutlined />} onClick={handleTest} loading={testLoading}>
              {t('model.testButton')}
            </Button>
            <Popconfirm
              title={t('model.resetConfirmTitle')}
              description={
                <>
                  <div>{t('model.resetConfirmBody')}</div>
                  {/* The warning is only true when there is a key to lose, and a modal that
                      cries wolf on every reset is one people click through. */}
                  {config?.hasApiKey && (
                    <div style={{ marginTop: 8, fontWeight: 500 }}>{t('model.resetNoKeyWarning')}</div>
                  )}
                </>
              }
              okText={t('model.resetConfirmButton')}
              cancelText={t('shell.common.cancel')}
              okButtonProps={{ danger: true }}
              onConfirm={() => void handleReset()}
            >
              <Button icon={<UndoOutlined />} danger>
                {t('model.resetButton')}
              </Button>
            </Popconfirm>
          </Space>
        </Form>

        {testResult && (
          <Alert
            style={{ marginTop: 16 }}
            type={testResult.success ? 'success' : 'error'}
            showIcon
            title={testResult.success ? t('model.connected') : t('model.connectionFailed')}
            description={
              <>
                <div>{testResult.message}</div>
                {testResult.model && <div>{t('model.returnedModel', { model: testResult.model })}</div>}
                {!testResult.success && (
                  <div style={{ marginTop: 8 }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {t('model.testHint')}
                    </Text>
                  </div>
                )}
              </>
            }
          />
        )}
      </Card>
    </div>
  );
};

export default ModelConfigPage;
