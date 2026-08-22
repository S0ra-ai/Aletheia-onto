import React, { useEffect, useRef, useState } from 'react';
import { Alert, Avatar, Button, Card, Input, Select, Space, Spin, Tag, Typography, message } from 'antd';
import { SendOutlined, UserOutlined, ClearOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { agentApi, conversationApi, knowledgeBaseApi } from '../../api';
import MarkdownMessage from '../../components/MarkdownMessage';
import type { AgentRole, AgentChatResult, KnowledgeBase } from '../../types';

const { Paragraph, Text, Title } = Typography;

type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  result?: AgentChatResult;
  roleId?: string;
  /** Backend message id, required to attach feedback to this specific answer. */
  messageId?: number;
  feedbackGiven?: string;
};

// Role avatars come from the backend, which derives them from the domain name.
// Colours are assigned deterministically so a role keeps the same colour across
// sessions without maintaining a per-domain palette in the frontend.
const ROLE_PALETTE = ['#1677ff', '#52c41a', '#722ed1', '#fa8c16', '#13c2c2', '#eb2f96'];

const roleColor = (roleId?: string): string => {
  if (!roleId) return ROLE_PALETTE[0];
  let hash = 0;
  for (let index = 0; index < roleId.length; index += 1) {
    hash = (hash * 31 + roleId.charCodeAt(index)) % 100000;
  }
  return ROLE_PALETTE[hash % ROLE_PALETTE.length];
};

const roleAvatar = (roles: AgentRole[], roleId?: string): string => {
  const role = roles.find(item => item.id === roleId);
  return role?.avatar || 'AI';
};

// Prompts are built from the objects actually present in the knowledge base, so
// they reference the user's own business vocabulary.
const buildQuickPrompts = (knowledgeBase?: KnowledgeBase): string[] => {
  const objects = knowledgeBase?.objects || [];
  if (objects.length === 0) {
    return ['查看所有已接入的数据源', '当前知识库有哪些业务对象？'];
  }
  const primary = objects[0];
  const primaryLabel = primary.name || primary.code;
  const prompts = [
    `${primaryLabel}整体是否合规？`,
    `查看${primaryLabel}的业务规则`,
    `${primaryLabel}决策是否一致？`,
  ];
  if (objects[1]) {
    const secondary = objects[1];
    prompts.push(`${secondary.name || secondary.code}有哪些关联关系？`);
  }
  return prompts;
};

const preferredObjectCode = (knowledgeBase?: KnowledgeBase) => knowledgeBase?.objects?.[0]?.code;

const OntologyChat: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [loading, setLoading] = useState(false);
  const [roles, setRoles] = useState<AgentRole[]>([]);
  // Empty until roles load: the available roles depend on which domains have
  // been onboarded, so the frontend cannot assume any particular role id.
  const [selectedRoleId, setSelectedRoleId] = useState<string>('');
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [dataSourceId, setDataSourceId] = useState<number | undefined>();
  const [objectCode, setObjectCode] = useState<string>();
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  const selectedRole = roles.find(r => r.id === selectedRoleId) || roles[0];

  useEffect(() => {
    agentApi.roles().then(items => {
      setRoles(items);
      setSelectedRoleId(current => current || items[0]?.id || '');
    }).catch(() => undefined);
    knowledgeBaseApi.list().then(items => {
      setKnowledgeBases(items);
      if (items.length > 0) {
        setDataSourceId(items[0].dataSourceId);
        setObjectCode(preferredObjectCode(items[0]));
      }
    }).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (messages.length === 0 && selectedRole) {
      setMessages([{
        id: 'welcome',
        role: 'assistant',
        content: `你好，我是${selectedRole.name}。${selectedRole.description}\n\n请先选择已初始化的数据源和业务对象，然后向我提问。`,
        roleId: selectedRole.id,
      }]);
    }
  }, [selectedRole, messages.length]);

  const selectedKnowledgeBase = knowledgeBases.find(item => item.dataSourceId === dataSourceId);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, loading]);

  const handleFeedback = async (item: ChatMessage, rating: string) => {
    if (!item.messageId) return;
    try {
      await conversationApi.submitFeedback(item.messageId, { rating });
      setMessages(prev => prev.map(m => (m.id === item.id ? { ...m, feedbackGiven: rating } : m)));
      message.success(
        rating === 'incorrect' ? '已记录：该结论被标记为错误，将进入复核队列' : '感谢反馈',
      );
    } catch {
      message.error('提交反馈失败');
    }
  };

  const quickPrompts = buildQuickPrompts(selectedKnowledgeBase);

  const ask = async (text?: string) => {
    const content = (text ?? question).trim();
    if (!content) return;

    const userMessage: ChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      content,
    };
    setMessages(prev => [...prev, userMessage]);
    setQuestion('');
    setLoading(true);

    try {
      const result = await agentApi.chat({
        message: content,
        roleId: selectedRoleId,
        dataSourceId,
        objectCode: objectCode || undefined,
        // History now comes from the stored conversation, so a refresh no longer
        // loses the thread. Passing the session id is what links the turns.
        sessionId: sessionId || undefined,
      });
      if (result.sessionId && result.sessionId !== sessionId) {
        setSessionId(result.sessionId);
      }

      setMessages(prev => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: 'assistant',
          content: result.answer,
          result,
          roleId: result.roleId,
          messageId: result.messageId,
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
          roleId: selectedRoleId,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleRoleChange = (roleId: string) => {
    setSelectedRoleId(roleId);
    setMessages([{
      id: 'welcome',
      role: 'assistant',
      content: '',
      roleId,
    }]);
  };

  return (
    <div style={{ height: 'calc(100vh - 150px)', minHeight: 620, display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', marginBottom: 12 }}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            <ThunderboltOutlined style={{ marginRight: 8, color: roleColor(selectedRoleId) }} />
            智能体对话
          </Title>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            选择角色和数据源，像与业务专家对话一样提问；回答基于真实数据和已确认的业务规则。
          </Paragraph>
        </div>
        <Space wrap>
          <Select
            value={selectedRoleId}
            onChange={handleRoleChange}
            style={{ width: 180 }}
            options={roles.map(r => ({ value: r.id, label: r.name }))}
          />
          <Select
            allowClear
            placeholder="数据源"
            value={dataSourceId}
            onChange={(value) => {
              setDataSourceId(value);
              setObjectCode(preferredObjectCode(knowledgeBases.find(item => item.dataSourceId === value)));
            }}
            style={{ width: 220 }}
            options={knowledgeBases.map(item => ({ value: item.dataSourceId, label: `${item.name} · ${item.sourceType}` }))}
          />
          <Select
            value={objectCode}
            onChange={setObjectCode}
            placeholder="业务对象"
            style={{ width: 190 }}
            options={(selectedKnowledgeBase?.objects || []).map(item => ({ value: item.code, label: `${item.name} (${item.code})` }))}
          />
          <Button icon={<ClearOutlined />} onClick={() => {
            setMessages([{
              id: 'welcome',
              role: 'assistant',
              content: `你好，我是${selectedRole?.name || '业务顾问'}。请先选择已初始化的数据源和业务对象，然后向我提问。`,
              roleId: selectedRoleId,
            }]);
          }}>
            清空
          </Button>
        </Space>
      </div>

      {knowledgeBases.length === 0 && (
        <Alert style={{ marginBottom: 12 }} type="warning" showIcon message="暂无可问答的数据源" description="请先在数据源管理中完成连接测试和知识库初始化。" />
      )}

      <Card
        styles={{ body: { padding: 0, height: '100%', display: 'flex', flexDirection: 'column' } }}
        style={{ flex: 1, overflow: 'hidden' }}
      >
        <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: '24px 24px 12px' }}>
          {messages.map(item => {
            const isUser = item.role === 'user';
            const avatarBg = isUser ? '#1677ff' : roleColor(item.roleId || selectedRoleId);
            const avatarLabel = isUser ? <UserOutlined /> : (
              <span style={{ fontSize: 12, fontWeight: 600 }}>
                {roleAvatar(roles, item.roleId || selectedRoleId)}
              </span>
            );

            return (
              <div
                key={item.id}
                style={{
                  display: 'flex',
                  justifyContent: isUser ? 'flex-end' : 'flex-start',
                  marginBottom: 18,
                }}
              >
                <div style={{ display: 'flex', gap: 12, maxWidth: '78%', flexDirection: isUser ? 'row-reverse' : 'row' }}>
                  <Avatar icon={avatarLabel} style={{ flex: '0 0 auto', background: avatarBg }} />
                  <div>
                    {!isUser && item.roleId && (
                      <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
                        {roles.find(r => r.id === item.roleId)?.name || '智能体'}
                      </Text>
                    )}
                    <div
                      style={{
                        padding: '12px 14px',
                        borderRadius: 8,
                        background: isUser ? '#1677ff' : '#f5f7fb',
                        color: isUser ? '#fff' : '#111827',
                        lineHeight: 1.7,
                        overflowWrap: 'anywhere',
                      }}
                    >
                      <MarkdownMessage content={item.content} inverted={isUser} />
                    </div>
                    {!isUser && item.messageId && (
                      <div style={{ marginTop: 6 }}>
                        {item.feedbackGiven ? (
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            已反馈：{item.feedbackGiven === 'helpful' ? '有帮助' : item.feedbackGiven === 'unhelpful' ? '没有帮助' : '结论错误'}
                          </Text>
                        ) : (
                          <Space size={4}>
                            <Button size="small" type="text" onClick={() => void handleFeedback(item, 'helpful')}>
                              有帮助
                            </Button>
                            <Button size="small" type="text" onClick={() => void handleFeedback(item, 'unhelpful')}>
                              没帮助
                            </Button>
                            <Button size="small" type="text" danger onClick={() => void handleFeedback(item, 'incorrect')}>
                              结论错误
                            </Button>
                          </Space>
                        )}
                      </div>
                    )}
                    {item.result && (
                      <div style={{ marginTop: 8 }}>
                        <Space wrap size={[6, 6]}>
                          <Tag color="blue">{item.result.intent}</Tag>
                          {item.result.resolved.dataSourceId && <Tag>数据源 #{item.result.resolved.dataSourceId}</Tag>}
                          {item.result.resolved.objectCode && <Tag>{item.result.resolved.objectCode}</Tag>}
                          {item.result.model?.usedForUnderstanding && <Tag color="green">模型理解</Tag>}
                          {item.result.toolCalls && item.result.toolCalls.length > 0 && (
                            <Tag color="orange">工具调用 x{item.result.toolCalls.length}</Tag>
                          )}
                        </Space>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
          {loading && (
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 18 }}>
              <Avatar
                icon={<span style={{ fontSize: 12, fontWeight: 600 }}>{roleAvatar(roles, selectedRoleId)}</span>}
                style={{ background: roleColor(selectedRoleId) }}
              />
              <Alert message={<Spin size="small" />} description="正在分析问题、调用本体内核并整理回答..." type="info" />
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
            ref={inputRef as any}
            value={question}
            onChange={event => setQuestion(event.target.value)}
            onPressEnter={event => {
              if (!event.shiftKey) {
                event.preventDefault();
                ask();
              }
            }}
            autoSize={{ minRows: 2, maxRows: 5 }}
            placeholder={`向${selectedRole?.name || '智能体'}提问...`}
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
