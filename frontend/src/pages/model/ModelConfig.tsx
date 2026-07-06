import React, { useEffect, useState } from 'react';
import { Card, Form, Input, Button, Typography, Space, Alert, Descriptions, Tag, Divider, message, InputNumber, Spin } from 'antd';
import { SaveOutlined, UndoOutlined, ApiOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import { modelApi } from '../../api';
import type { ModelConfig, ModelConfigUpdate } from '../../types';

const { Title, Paragraph } = Typography;

const ModelConfigPage: React.FC = () => {
  const [config, setConfig] = useState<ModelConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [testLoading, setTestLoading] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string; model?: string } | null>(null);
  const [form] = Form.useForm();

  const fetchConfig = async () => {
    setLoading(true);
    try {
      const data = await modelApi.getConfig();
      setConfig(data);
      form.setFieldsValue({
        apiKey: '', // 不回显完整 key
        model: data.model,
        baseUrl: data.baseUrl,
        httpReferer: data.httpReferer,
        appTitle: data.appTitle,
        serviceTier: data.serviceTier,
        timeoutSeconds: data.timeoutSeconds,
      });
    } catch (error) {
      message.error('获取配置失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  const handleSave = async (values: ModelConfigUpdate) => {
    setLoading(true);
    try {
      // 如果 apiKey 为空，则不更新
      const payload: ModelConfigUpdate = { ...values };
      if (!payload.apiKey) {
        delete payload.apiKey;
      }
      await modelApi.updateConfig(payload);
      message.success('配置保存成功');
      fetchConfig();
    } catch (error) {
      message.error('保存失败');
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
      fetchConfig();
    } catch (error) {
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
      if (result.success) {
        message.success('连接测试成功');
      } else {
        message.error(result.message);
      }
    } catch (error) {
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
        配置 OpenRouter API 以启用 AI 辅助建模功能
      </Paragraph>

      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={2}>
          <Descriptions.Item label="配置状态">
            <Tag color={config?.configured ? 'green' : 'red'} icon={config?.configured ? <CheckCircleOutlined /> : <CloseCircleOutlined />}>
              {config?.configured ? '已配置' : '未配置'}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="当前模型">{config?.model || '-'}</Descriptions.Item>
          <Descriptions.Item label="API Key">
            {config?.hasApiKey ? (
              <Tag color="green">{config.apiKey}</Tag>
            ) : (
              <Tag color="red">未设置</Tag>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="服务层级">{config?.serviceTier || '-'}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="配置 OpenRouter API">
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSave}
          initialValues={{
            baseUrl: 'https://openrouter.ai/api/v1',
            serviceTier: 'auto',
            timeoutSeconds: 30,
          }}
        >
          <Form.Item
            name="apiKey"
            label="API Key"
            extra={config?.hasApiKey ? '留空则保持现有 Key 不变' : '请输入您的 OpenRouter API Key'}
          >
            <Input.Password placeholder="sk-or-v1-..." />
          </Form.Item>

          <Form.Item
            name="model"
            label="模型"
            rules={[{ required: true, message: '请输入模型名称' }]}
          >
            <Input placeholder="例如：openai/gpt-4o-mini" />
          </Form.Item>

          <Form.Item
            name="baseUrl"
            label="API Base URL"
          >
            <Input placeholder="https://openrouter.ai/api/v1" />
          </Form.Item>

          <Form.Item
            name="httpReferer"
            label="HTTP Referer (可选)"
          >
            <Input placeholder="您的网站 URL" />
          </Form.Item>

          <Form.Item
            name="appTitle"
            label="应用标题 (可选)"
          >
            <Input placeholder="Ontology Transformation Platform" />
          </Form.Item>

          <Form.Item
            name="serviceTier"
            label="服务层级"
          >
            <Input placeholder="auto" />
          </Form.Item>

          <Form.Item
            name="timeoutSeconds"
            label="超时时间 (秒)"
          >
            <InputNumber min={5} max={120} style={{ width: '100%' }} />
          </Form.Item>

          <Divider />

          <Space>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              htmlType="submit"
              loading={loading}
            >
              保存配置
            </Button>
            <Button
              icon={<ApiOutlined />}
              onClick={handleTest}
              loading={testLoading}
            >
              测试连接
            </Button>
            <Button
              icon={<UndoOutlined />}
              onClick={handleReset}
              loading={loading}
            >
              重置配置
            </Button>
          </Space>
        </Form>
      </Card>

      {testResult && (
        <Card style={{ marginTop: 16 }}>
          <Alert
            type={testResult.success ? 'success' : 'error'}
            message={testResult.success ? '连接成功' : '连接失败'}
            description={
              <div>
                <p>{testResult.message}</p>
                {testResult.model && <p>模型: {testResult.model}</p>}
              </div>
            }
            showIcon
          />
        </Card>
      )}

      <Card title="使用说明" style={{ marginTop: 16 }}>
        <Paragraph>
          <ol>
            <li>访问 <a href="https://openrouter.ai/keys" target="_blank" rel="noopener noreferrer">OpenRouter Keys</a> 获取 API Key</li>
            <li>在上方输入 API Key 和模型名称</li>
            <li>点击"保存配置"保存设置</li>
            <li>点击"测试连接"验证配置是否正确</li>
          </ol>
        </Paragraph>
        <Paragraph type="secondary">
          注意：API Key 会安全存储在本地数据库中，不会泄露给第三方。
        </Paragraph>
      </Card>
    </div>
  );
};

export default ModelConfigPage;
