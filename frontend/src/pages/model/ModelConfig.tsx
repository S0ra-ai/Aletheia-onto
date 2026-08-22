import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert, Button, Card, Descriptions, Divider, Form, Input, InputNumber, Select,
  Space, Spin, Switch, Tag, Tooltip, Typography, message,
} from 'antd';
import {
  ApiOutlined, CheckCircleOutlined, CloseCircleOutlined, SaveOutlined, UndoOutlined,
} from '@ant-design/icons';
import { modelApi } from '../../api';
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
  label: string;
  baseUrl: string;
  model: string;
  authStyle: string;
  authHeader?: string;
  sendProviderExtras: boolean;
  note: string;
}

/** Starting points for the shapes we have actually had to support. */
const PRESETS: Record<string, Preset> = {
  openrouter: {
    label: 'OpenRouter',
    baseUrl: 'https://openrouter.ai/api/v1',
    model: 'openai/gpt-4o-mini',
    authStyle: 'bearer',
    sendProviderExtras: true,
    note: '支持 service_tier 与 session_id 等扩展字段。',
  },
  openai: {
    label: 'OpenAI 官方',
    baseUrl: 'https://api.openai.com/v1',
    model: 'gpt-4o-mini',
    authStyle: 'bearer',
    sendProviderExtras: false,
    note: '官方接口不接受 OpenRouter 扩展字段，已默认关闭。',
  },
  relay: {
    label: '中转站 / 自定义订阅',
    baseUrl: 'https://your-relay.example.com/v1',
    model: 'gpt-4o-mini',
    authStyle: 'bearer',
    sendProviderExtras: false,
    note: '多数中转站兼容 OpenAI 协议；若返回 400，先关闭扩展字段。',
  },
  azure: {
    label: 'Azure OpenAI',
    baseUrl: 'https://<资源名>.openai.azure.com/openai/deployments/<部署名>/chat/completions?api-version=2024-02-01',
    model: '<部署名>',
    authStyle: 'api-key',
    sendProviderExtras: false,
    note: 'Azure 使用 api-key 请求头，且 Base URL 需含完整路径与 api-version。',
  },
  vllm: {
    label: '自建 vLLM / Ollama',
    baseUrl: 'http://127.0.0.1:8000/v1',
    model: 'qwen2.5-7b-instruct',
    authStyle: 'none',
    sendProviderExtras: false,
    note: '本地服务通常无需密钥，且对未知字段严格返回 400。',
  },
  dashscope: {
    label: '阿里云百炼 / 通义',
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    model: 'qwen-max',
    authStyle: 'bearer',
    sendProviderExtras: false,
    note: '使用 OpenAI 兼容模式端点。',
  },
};

const AUTH_STYLE_LABELS: Record<string, string> = {
  bearer: 'Bearer Token（多数服务）',
  'api-key': 'api-key 请求头（Azure）',
  custom: '自定义请求头',
  none: '不发送密钥（本地服务）',
};

const ModelConfigPage: React.FC = () => {
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
    } catch {
      message.error('获取配置失败');
    } finally {
      setLoading(false);
    }
  }, [form]);

  useEffect(() => {
    void fetchConfig();
  }, [fetchConfig]);

  const applyPreset = (key: string) => {
    const preset = PRESETS[key];
    if (!preset) return;
    form.setFieldsValue({
      baseUrl: preset.baseUrl,
      model: preset.model,
      authStyle: preset.authStyle,
      authHeader: preset.authHeader || '',
      sendProviderExtras: preset.sendProviderExtras,
    });
    setAuthStyle(preset.authStyle);
    message.info(`已套用「${preset.label}」预设，请补齐密钥后保存`);
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
          message.error('附加请求头必须是 JSON 对象');
          return;
        }
        payload.extraHeaders = parsed as Record<string, string>;
      } catch {
        message.error('附加请求头不是合法 JSON');
        return;
      }
    } else {
      payload.extraHeaders = {};
    }

    setLoading(true);
    try {
      await modelApi.updateConfig(payload);
      message.success('配置保存成功');
      setTestResult(null);
      await fetchConfig();
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || '保存失败');
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async () => {
    setLoading(true);
    try {
      await modelApi.resetConfig();
      message.success('配置已重置');
      setTestResult(null);
      await fetchConfig();
    } catch {
      message.error('重置失败');
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
      if (result.success) message.success('连接测试成功');
      else message.error(result.message);
    } catch {
      message.error('测试失败');
    } finally {
      setTestLoading(false);
    }
  };

  if (loading && !config) {
    return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  }

  return (
    <div>
      <Title level={3}>模型配置</Title>
      <Paragraph type="secondary">
        平台使用 OpenAI 兼容的 chat/completions 协议，因此任何实现该协议的服务都可接入：
        官方 API、中转站与自定义订阅、自建 vLLM / Ollama、Azure OpenAI、国内厂商兼容端点。
        <br />
        <Text type="secondary" style={{ fontSize: 12 }}>
          未配置密钥时，问答与建模会回退到本地启发式，功能不中断。
        </Text>
      </Paragraph>

      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="配置状态">
            <Tag color={config?.configured ? 'green' : 'red'} icon={config?.configured ? <CheckCircleOutlined /> : <CloseCircleOutlined />}>
              {config?.configured ? '已配置' : '未配置'}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="当前模型">{config?.model || '-'}</Descriptions.Item>
          <Descriptions.Item label="API Key">
            {config?.hasApiKey ? <Tag color="green">{config.apiKey}</Tag> : <Tag color="red">未设置</Tag>}
          </Descriptions.Item>
          <Descriptions.Item label="鉴权方式">
            <Tag>{AUTH_STYLE_LABELS[config?.authStyle || 'bearer'] || config?.authStyle}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="实际调用地址" span={2}>
            <Text code copyable style={{ fontSize: 12 }}>{config?.resolvedEndpoint || '-'}</Text>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card
        title="接入配置"
        extra={
          <Space>
            <Text type="secondary" style={{ fontSize: 12 }}>快速预设</Text>
            <Select
              style={{ width: 200 }}
              placeholder="选择服务商"
              onChange={applyPreset}
              options={Object.entries(PRESETS).map(([key, preset]) => ({ value: key, label: preset.label }))}
            />
          </Space>
        }
      >
        <Form form={form} layout="vertical" onFinish={handleSave}>
          <Form.Item
            name="baseUrl"
            label="API Base URL"
            rules={[{ required: true, message: '请输入 API 地址' }]}
            extra="通常以 /v1 结尾。若你的网关直接提供完整的 /chat/completions 地址（如 Azure），可整段填入，平台不会重复拼接。"
          >
            <Input placeholder="https://your-relay.example.com/v1" />
          </Form.Item>

          <Form.Item
            name="model"
            label="模型名称"
            rules={[{ required: true, message: '请输入模型名称' }]}
            extra="填写你的服务商所使用的模型标识；Azure 填部署名。"
          >
            <Input placeholder="gpt-4o-mini / qwen-max / deepseek-chat" />
          </Form.Item>

          <Form.Item
            name="apiKey"
            label="API Key"
            extra={config?.hasApiKey ? '留空则保持现有 Key 不变' : '本地服务若无需鉴权，可将鉴权方式设为「不发送密钥」'}
          >
            <Input.Password placeholder="sk-..." autoComplete="new-password" />
          </Form.Item>

          <Divider titlePlacement="start" plain>兼容性设置</Divider>

          <Form.Item
            name="authStyle"
            label="鉴权方式"
            extra="不同服务商传递密钥的方式不同，选错会得到 401。"
          >
            <Select
              onChange={setAuthStyle}
              options={(config?.authStyleOptions || ['bearer', 'api-key', 'custom', 'none']).map(value => ({
                value,
                label: AUTH_STYLE_LABELS[value] || value,
              }))}
            />
          </Form.Item>

          {authStyle === 'custom' && (
            <Form.Item
              name="authHeader"
              label="自定义鉴权请求头名称"
              rules={[{ required: true, message: '请填写请求头名称' }]}
              extra="密钥将以该请求头原样发送，例如 X-Api-Token。"
            >
              <Input placeholder="X-Api-Token" />
            </Form.Item>
          )}

          <Form.Item
            name="sendProviderExtras"
            label={
              <Tooltip title="service_tier 与 session_id 是 OpenRouter 扩展字段。严格的 OpenAI 兼容服务（vLLM、LM Studio、部分中转站）会因未知字段直接返回 400。">
                <span>发送 OpenRouter 扩展字段</span>
              </Tooltip>
            }
            valuePropName="checked"
            extra="接入非 OpenRouter 服务且遇到 400 错误时，请关闭此项。"
          >
            <Switch />
          </Form.Item>

          <Form.Item
            name="extraHeadersText"
            label="附加请求头（可选，JSON）"
            extra='部分网关需要额外标识，例如 {"X-Tenant-Id": "acme"}。此处的键会覆盖上面自动生成的同名请求头。'
          >
            <Input.TextArea rows={3} placeholder='{"X-Tenant-Id": "acme"}' />
          </Form.Item>

          <Divider titlePlacement="start" plain>其他</Divider>

          <Space size={16} style={{ display: 'flex', flexWrap: 'wrap' }}>
            <Form.Item name="serviceTier" label="服务层级" style={{ minWidth: 160 }} extra="仅 OpenRouter">
              <Input placeholder="auto" />
            </Form.Item>
            <Form.Item name="timeoutSeconds" label="超时（秒）" style={{ minWidth: 160 }}>
              <InputNumber min={5} max={600} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="appTitle" label="应用标题" style={{ minWidth: 220 }} extra="作为 X-Title 发送">
              <Input placeholder="Aletheia" />
            </Form.Item>
            <Form.Item name="httpReferer" label="HTTP Referer" style={{ minWidth: 220 }} extra="可选，用于服务商归因">
              <Input placeholder="https://example.com" />
            </Form.Item>
          </Space>

          <Space>
            <Button type="primary" icon={<SaveOutlined />} htmlType="submit" loading={loading}>
              保存配置
            </Button>
            <Button icon={<ApiOutlined />} onClick={handleTest} loading={testLoading}>
              测试连接
            </Button>
            <Button icon={<UndoOutlined />} onClick={handleReset} danger>
              重置为默认
            </Button>
          </Space>
        </Form>

        {testResult && (
          <Alert
            style={{ marginTop: 16 }}
            type={testResult.success ? 'success' : 'error'}
            showIcon
            message={testResult.success ? '连接成功' : '连接失败'}
            description={
              <>
                <div>{testResult.message}</div>
                {testResult.model && <div>返回模型：{testResult.model}</div>}
                {!testResult.success && (
                  <div style={{ marginTop: 8 }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      401 通常是鉴权方式不匹配；400 常见于未知字段，可尝试关闭「发送 OpenRouter 扩展字段」；
                      404 多为 Base URL 路径不正确。
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
