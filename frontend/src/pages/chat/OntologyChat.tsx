import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Avatar, Button, Card, Input, Select, Space, Spin, Tag, Typography, message } from 'antd';
import { RobotOutlined, SendOutlined, UserOutlined, ClearOutlined } from '@ant-design/icons';
import { knowledgeBaseApi, semanticApi } from '../../api';
import type { KnowledgeBase, NaturalLanguageQueryResult } from '../../types';

const { Paragraph, Text, Title } = Typography;

type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  result?: NaturalLanguageQueryResult;
};

const quickPrompts = [
  '解释实例 1 的业务语义',
  '实例 1 是否合规？',
  '当前业务对象有哪些规则？',
  '整体决策是否一致？',
];

const OntologyChat: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: '你好，我是本体知识库助手。请先选择已初始化的数据源和业务对象，我会基于该数据源的真实记录、本体关系和用户上传规则回答。',
    },
  ]);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [dataSourceId, setDataSourceId] = useState<number | undefined>();
  const [objectCode, setObjectCode] = useState<string>();
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    knowledgeBaseApi.list()
      .then(items => {
        setKnowledgeBases(items);
        if (items.length > 0) {
          setDataSourceId(items[0].dataSourceId);
          setObjectCode(items[0].objects[0]?.code);
        }
      })
      .catch(() => undefined);
  }, []);

  const selectedKnowledgeBase = knowledgeBases.find(item => item.dataSourceId === dataSourceId);

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
            像问业务专家一样直接提问；回答会结合真实数据和已确认的业务规则。
          </Paragraph>
        </div>
        <Space wrap>
          <Select
            allowClear
            placeholder="数据源"
            value={dataSourceId}
            onChange={(value) => {
              setDataSourceId(value);
              setObjectCode(knowledgeBases.find(item => item.dataSourceId === value)?.objects[0]?.code);
            }}
            style={{ width: 220 }}
            options={knowledgeBases.map(item => ({ value: item.dataSourceId, label: `${item.name} · ${item.sourceType}` }))}
          />
          <Select
            value={objectCode}
            onChange={setObjectCode}
            placeholder="本体业务对象"
            style={{ width: 190 }}
            options={(selectedKnowledgeBase?.objects || []).map(item => ({ value: item.code, label: `${item.name} (${item.code})` }))}
          />
          <Button icon={<ClearOutlined />} onClick={() => setMessages(messages.slice(0, 1))}>
            清空
          </Button>
        </Space>
      </div>

      {knowledgeBases.length === 0 && <Alert style={{ marginBottom: 12 }} type="warning" showIcon message="暂无可问答的数据源" description="请先在数据源管理中完成连接测试和知识库初始化。" />}

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
            placeholder="例如：CG-2024-001 这份合同有什么需要注意的？"
            disabled={loading || !dataSourceId || !objectCode}
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
