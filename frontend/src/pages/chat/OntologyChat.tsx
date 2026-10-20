import React, { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Alert, Avatar, Button, Card, Input, Select, Space, Spin, Tag, Typography, message } from 'antd';
import { SendOutlined, UserOutlined, ClearOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { agentApi, conversationApi, knowledgeBaseApi, requestErrorMessage } from '../../api';
import MarkdownMessage from '../../components/MarkdownMessage';
import { useT } from '../../i18n/locale';
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

// `t` is passed in rather than imported: these helpers build a sentence for a screen, and a
// module-level function cannot call `useT` itself -- a hook only runs inside a component.
type Translate = ReturnType<typeof useT>;

// Prompts are built from the objects actually present in the knowledge base, so
// they reference the user's own business vocabulary.
const buildQuickPrompts = (t: Translate, knowledgeBase?: KnowledgeBase): string[] => {
  const objects = knowledgeBase?.objects || [];
  if (objects.length === 0) {
    return [t('chat.promptAllSources'), t('chat.promptObjects')];
  }
  const primary = objects[0];
  const primaryLabel = primary.name || primary.code;
  const prompts = [
    t('chat.promptCompliance', { name: primaryLabel }),
    t('chat.promptRules', { name: primaryLabel }),
    t('chat.promptConsistency', { name: primaryLabel }),
  ];
  if (objects[1]) {
    const secondary = objects[1];
    prompts.push(t('chat.promptRelations', { name: secondary.name || secondary.code }));
  }
  return prompts;
};

const preferredObjectCode = (knowledgeBase?: KnowledgeBase) => knowledgeBase?.objects?.[0]?.code;

/**
 * The opening line, which says what is actually left to do.
 *
 * It used to end with "请先选择已初始化的数据源和业务对象，然后向我提问。" unconditionally --
 * including on a page where both selectors are already filled in, so the first thing the
 * agent said was an instruction the user had no way to follow. It now names the objects it
 * can answer about when they are chosen, and asks for a selection only when there is none.
 *
 * One function for both call sites: the two copies had already drifted (one carried the
 * role's description, the other did not).
 */
const welcomeMessage = (t: Translate, roleName: string, roleDescription: string, hasTarget: boolean) =>
  t('chat.welcomeIntro', { roleName, roleDescription }) +
  (hasTarget ? t('chat.welcomeReady') : t('chat.welcomeSelectFirst'));

const OntologyChat: React.FC = () => {
  const t = useT();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState('');
  /**
   * The conversation is a place: `/chat?session=<id>` opens it, and the id is written back
   * when it is created. Two affordances already linked to a conversation -- the feedback
   * console's 查看 and the workbench's 「N 个会话已转人工」 -- and both pointed at
   * `/conversations`, a path this application does not serve, so the only way into an
   * escalated conversation ended on 页面不存在.
   */
  const [params, setParams] = useSearchParams();
  const [sessionId, setSessionId] = useState(() => params.get('session') ?? '');
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

  // Arriving with an id opens that conversation: its turns are the page's content, and an
  // empty chat with the right id is not the conversation the link named.
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    conversationApi
      .get(sessionId)
      .then(conversation => {
        if (cancelled) return;
        const turns = (conversation.messages ?? [])
          .filter(message => message.role !== 'system')
          .map<ChatMessage>(message => ({
            id: `stored-${message.id}`,
            role: message.role === 'user' ? 'user' : 'assistant',
            content: message.content,
            roleId: conversation.roleId,
            messageId: message.id,
            feedbackGiven: message.feedback?.[0]?.rating,
          }));
        if (turns.length) setMessages(turns);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
    // Once, for the id the page arrived with: a reply's own id is written back below, and
    // re-loading on that would replace the transcript the reader just made.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
        content: welcomeMessage(t, selectedRole.name, selectedRole.description, Boolean(objectCode)),
        roleId: selectedRole.id,
      }]);
    }
    // `objectCode` is read here, so it is listed: while the conversation is empty the
    // greeting should follow the selection instead of describing the state it loaded with.
  }, [selectedRole, objectCode, messages.length, t]);

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
        rating === 'incorrect' ? t('chat.feedbackRecordedIncorrect') : t('chat.feedbackThanks'),
      );
    } catch (error) {
      message.error(requestErrorMessage(error, t('chat.feedbackFailed')));
    }
  };

  const quickPrompts = buildQuickPrompts(t, selectedKnowledgeBase);

  /**
   * A question can arrive in the URL: `/chat?q=合同 1 是否合规？` asks it once on mount.
   *
   * The same reason the conversation itself is a place (`?session=`) and the explanation tab
   * takes its instance from the query: an answer worth reading is worth sending, and a link
   * that opens on an empty box makes the sender do the typing twice. It is also the only way
   * `scripts/capture_screenshots.py` can reach a *answered* conversation -- a screenshot tool
   * cannot type into a composer.
   *
   * Asked once, guarded by a ref: a re-render must not re-ask, or the conversation fills with
   * the same question every time the page re-renders for any reason at all.
   */
  const askedFromUrl = useRef(false);
  useEffect(() => {
    const fromUrl = params.get('q') ?? '';
    if (!fromUrl || askedFromUrl.current) return;
    askedFromUrl.current = true;
    void ask(fromUrl);
    // `ask` reads the role and knowledge base from state that loads asynchronously, so it is
    // called again below once those arrive -- asking against an empty picker would send the
    // question to whichever role happened to be first.
    //
    // `ask` is deliberately not in this list, and the rule is what is wrong here rather than
    // the code: naming it would mean declaring it above this effect, and a `useCallback`'s
    // dependency array is read *during* the render that defines it -- so the const below would
    // be in its temporal dead zone and the whole page would fail to render. The effect's own
    // dependencies are the state `ask` reads, which is what it needs to re-run for; the ref
    // above then makes the second and later runs do nothing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params, roles, knowledgeBases]);

  // Message ids come from a counter rather than `Date.now()`. The id is both the React key
  // and the key the feedback update matches on, so two messages created within one
  // millisecond would collide: React would merge the rows, and a rating could be written to
  // the wrong message. A clock is the wrong source for an identity.
  const nextMessageId = useRef(0);
  const localMessageId = (prefix: string) => `${prefix}-local-${(nextMessageId.current += 1)}`;

  const ask = async (text?: string) => {
    const content = (text ?? question).trim();
    if (!content) return;

    const userMessage: ChatMessage = {
      id: localMessageId('u'),
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
        setParams(
          previous => {
            const next = new URLSearchParams(previous);
            next.set('session', String(result.sessionId));
            return next;
          },
          { replace: true },
        );
      }

      setMessages(prev => [
        ...prev,
        {
          id: localMessageId('a'),
          role: 'assistant',
          content: result.answer,
          result,
          roleId: result.roleId,
          messageId: result.messageId,
        },
      ]);
    } catch (error) {
      message.error(requestErrorMessage(error, t('chat.requestFailed')));
      setMessages(prev => [
        ...prev,
        {
          id: localMessageId('a'),
          role: 'assistant',
          content: t('chat.assistantUnavailable'),
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
            {t('chat.title')}
          </Title>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            {t('chat.subtitle')}
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
            placeholder={t('chat.dataSourcePlaceholder')}
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
            placeholder={t('chat.objectPlaceholder')}
            style={{ width: 190 }}
            options={(selectedKnowledgeBase?.objects || []).map(item => ({ value: item.code, label: `${item.name} (${item.code})` }))}
          />
          <Button icon={<ClearOutlined />} onClick={() => {
            setMessages([{
              id: 'welcome',
              role: 'assistant',
              content: welcomeMessage(t, selectedRole?.name || t('chat.advisorFallback'), selectedRole?.description || '', Boolean(objectCode)),
              roleId: selectedRoleId,
            }]);
          }}>
            {t('chat.clearButton')}
          </Button>
        </Space>
      </div>

      {knowledgeBases.length === 0 && (
        <Alert style={{ marginBottom: 12 }} type="warning" showIcon title={t('chat.noKnowledgeTitle')} description={t('chat.noKnowledgeHint')} />
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
                        {roles.find(r => r.id === item.roleId)?.name || t('chat.agentFallback')}
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
                            {t('chat.feedbackGiven')}{item.feedbackGiven === 'helpful' ? t('chat.feedbackHelpful') : item.feedbackGiven === 'unhelpful' ? t('chat.feedbackUnhelpfulRecorded') : t('chat.feedbackIncorrect')}
                          </Text>
                        ) : (
                          <Space size={4}>
                            <Button size="small" type="text" onClick={() => void handleFeedback(item, 'helpful')}>
                              {t('chat.feedbackHelpful')}
                            </Button>
                            <Button size="small" type="text" onClick={() => void handleFeedback(item, 'unhelpful')}>
                              {t('chat.feedbackUnhelpful')}
                            </Button>
                            <Button size="small" type="text" danger onClick={() => void handleFeedback(item, 'incorrect')}>
                              {t('chat.feedbackIncorrect')}
                            </Button>
                          </Space>
                        )}
                      </div>
                    )}
                    {item.result && (
                      <div style={{ marginTop: 8 }}>
                        <Space wrap size={[6, 6]}>
                          <Tag color="blue">{item.result.intent}</Tag>
                          {item.result.resolved.dataSourceId && <Tag>{t('chat.dataSourceTag', { id: item.result.resolved.dataSourceId })}</Tag>}
                          {item.result.resolved.objectCode && <Tag>{item.result.resolved.objectCode}</Tag>}
                          {item.result.model?.usedForUnderstanding && <Tag color="green">{t('chat.modelUnderstanding')}</Tag>}
                          {item.result.toolCalls && item.result.toolCalls.length > 0 && (
                            <Tag color="orange">{t('chat.toolCalls', { count: item.result.toolCalls.length })}</Tag>
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
              <Alert title={<Spin size="small" />} description={t('chat.analysing')} type="info" />
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
            placeholder={t('chat.askPlaceholder', { role: selectedRole?.name || t('chat.agentFallback') })}
            disabled={loading || !dataSourceId || !objectCode}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 10 }}>
            <Text type="secondary">{t('chat.enterHint')}</Text>
            <Button type="primary" icon={<SendOutlined />} onClick={() => ask()} loading={loading}>
              {t('chat.sendButton')}
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default OntologyChat;
