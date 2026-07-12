import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Avatar, Button, Card, Input, Select, Space, Spin, Tag, Typography, message } from 'antd';
import { RobotOutlined, SendOutlined, UserOutlined, ClearOutlined } from '@ant-design/icons';
import { dataSourceApi, semanticApi } from '../../api';
import type { DataSource, NaturalLanguageQueryResult } from '../../types';

const { Paragraph, Text, Title } = Typography;

type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  result?: NaturalLanguageQueryResult;
};

const quickPrompts = [
  '合同是否合规？',
  'HT-2024-006 能提交审批吗？',
  '解释合同 1 的业务语义',
  '合同整体决策是否一致？',
];

const OntologyChat: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: '你好，我是业务语义内核助手。你可以直接问合同是否合规、某份合同能否提交审批、某个实例为什么被复核，或让模型基于已接入数据源解释本体推理链。',
    },
  ]);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [dataSources, setDataSources] = useState<DataSource[]>([]);
  const [dataSourceId, setDataSourceId] = useState<number | undefined>();
  const [objectCode, setObjectCode] = useState('contract');
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    dataSourceApi.list()
      .then(items => {
        setDataSources(items);
        if (items.length > 0) {
          setDataSourceId(Math.max(...items.map(item => item.id)));
        }
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, loading]);

  const history = useMemo(
    () =>
      messages
        .filter(item => item.id !== 'welcome')
        .slice(-8)
        .map(item => ({ role: item.role, content: item.content })),
    [messages],
  );

  const ask = async (text?: string) => {
    const content = (text ?? question).trim();
    if (!content) return;

    const userMessage: ChatMessage = { id: `u-${Date.now()}`, role: 'user', content };
    setMessages(prev => [...prev, userMessage]);
    setQuestion('');
    setLoading(true);

    try {
      const result = await semanticApi.query({
        question: content,
        dataSourceId,
        objectCode: objectCode || undefined,
        history,
        useModel: true,
      });
      setMessages(prev => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: 'assistant',
          content: result.answer,
          result,
        },
      ]);
    } catch (error) {
      message.error('对话失败，请检查模型配置或数据源本体是否已生成');
      setMessages(prev => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: 'assistant',
          content: '我暂时无法完成这次语义研判。请确认已接入数据源并生成本体，或在模型配置中测试 OpenRouter 连接。',
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ height: 'calc(100vh - 150px)', minHeight: 620, display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', marginBottom: 12 }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>本体对话</Title>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            大模型负责理解和表达，本体规则引擎负责合规结论、操作放行和治理证据。
          </Paragraph>
        </div>
        <Space wrap>
          <Select
            allowClear
            placeholder="数据源"
            value={dataSourceId}
            onChange={setDataSourceId}
            style={{ width: 220 }}
            options={dataSources.map(item => ({ value: item.id, label: `${item.name} #${item.id}` }))}
          />
          <Input
            value={objectCode}
            onChange={event => setObjectCode(event.target.value)}
            placeholder="业务对象，如 contract"
            style={{ width: 190 }}
          />
          <Button icon={<ClearOutlined />} onClick={() => setMessages(messages.slice(0, 1))}>
            清空
          </Button>
        </Space>
      </div>

      <Card
        styles={{ body: { padding: 0, height: '100%', display: 'flex', flexDirection: 'column' } }}
        style={{ flex: 1, overflow: 'hidden' }}
      >
        <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: '24px 24px 12px' }}>
          {messages.map(item => (
            <div
              key={item.id}
              style={{
                display: 'flex',
                justifyContent: item.role === 'user' ? 'flex-end' : 'flex-start',
                marginBottom: 18,
              }}
            >
              <div style={{ display: 'flex', gap: 12, maxWidth: '78%', flexDirection: item.role === 'user' ? 'row-reverse' : 'row' }}>
                <Avatar icon={item.role === 'user' ? <UserOutlined /> : <RobotOutlined />} style={{ flex: '0 0 auto', background: item.role === 'user' ? '#1677ff' : '#111827' }} />
                <div>
                  <div
                    style={{
                      padding: '12px 14px',
                      borderRadius: 8,
                      background: item.role === 'user' ? '#1677ff' : '#f5f7fb',
                      color: item.role === 'user' ? '#fff' : '#111827',
                      whiteSpace: 'pre-wrap',
                      lineHeight: 1.7,
                    }}
                  >
                    {item.content}
                  </div>
                  {item.result && (
                    <div style={{ marginTop: 8 }}>
                      <Space wrap size={[6, 6]}>
                        <Tag color="blue">{item.result.intent}</Tag>
                        <Tag>本体 #{item.result.resolved.ontologyId}</Tag>
                        {item.result.resolved.dataSourceId && <Tag>数据源 #{item.result.resolved.dataSourceId}</Tag>}
                        <Tag>{item.result.resolved.objectCode}</Tag>
                        {item.result.resolved.instanceId && <Tag>实例 {item.result.resolved.instanceId}</Tag>}
                        {item.result.model?.usedForUnderstanding && <Tag color="green">模型理解</Tag>}
                        {item.result.model?.usedForSummary && <Tag color="green">模型总结</Tag>}
                      </Space>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
          {loading && (
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 18 }}>
              <Avatar icon={<RobotOutlined />} style={{ background: '#111827' }} />
              <Alert message={<Spin size="small" />} description="正在理解问题、调用本体内核并整理证据..." type="info" />
            </div>
          )}
        </div>

        <div style={{ borderTop: '1px solid #edf0f5', padding: 16 }}>
          <Space wrap style={{ marginBottom: 10 }}>
            {quickPrompts.map(prompt => (
              <Button key={prompt} size="small" onClick={() => ask(prompt)}>
                {prompt}
              </Button>
            ))}
          </Space>
          <Input.TextArea
            value={question}
            onChange={event => setQuestion(event.target.value)}
            onPressEnter={event => {
              if (!event.shiftKey) {
                event.preventDefault();
                ask();
              }
            }}
            autoSize={{ minRows: 2, maxRows: 5 }}
            placeholder="输入业务问题，例如：合同是否合规？HT-2024-006 能提交审批吗？"
            disabled={loading}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 10 }}>
            <Text type="secondary">Enter 发送，Shift + Enter 换行</Text>
            <Button type="primary" icon={<SendOutlined />} onClick={() => ask()} loading={loading}>
              发送
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default OntologyChat;
