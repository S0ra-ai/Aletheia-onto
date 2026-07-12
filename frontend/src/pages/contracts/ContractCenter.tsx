import React, { useEffect, useState } from 'react';
import { Alert, Button, Card, Col, Descriptions, Divider, Input, List, message, Row, Space, Table, Tag, Typography, Upload } from 'antd';
import { DownloadOutlined, InboxOutlined, SearchOutlined } from '@ant-design/icons';
import { contractApi } from '../../api';
import type { ContractComparison, ManagedContract } from '../../types';

const { Title, Paragraph, Text } = Typography;
const { Dragger } = Upload;

const ContractCenter: React.FC = () => {
  const [contracts, setContracts] = useState<ManagedContract[]>([]);
  const [selected, setSelected] = useState<ManagedContract>();
  const [question, setQuestion] = useState('这份合同的金额和甲乙方是什么？');
  const [comparison, setComparison] = useState<ContractComparison>();
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    const items = await contractApi.list();
    setContracts(items);
    if (!selected && items.length) setSelected(items[0]);
  };
  useEffect(() => {
    contractApi.list().then(items => {
      setContracts(items);
      if (items.length) setSelected(items[0]);
    }).catch(() => message.error('合同列表加载失败'));
  }, []);

  const compare = async () => {
    if (!selected) return message.warning('请先选择合同');
    setLoading(true);
    try { setComparison(await contractApi.compare(selected.id, question)); }
    catch { message.error('对照分析失败'); }
    finally { setLoading(false); }
  };

  return <div>
    <Title level={3}>Word 合同中心</Title>
    <Alert type="info" showIcon message="Word 是合同主文档" description="系统只接受 .docx；MySQL 保存合同业务索引、文档版本、SHA-256 和语义快照，结构化记录不代替 Word 原件。" />
    <Dragger accept=".docx" showUploadList={false} style={{ margin: '20px 0' }} customRequest={async ({ file, onSuccess, onError }) => {
      try { const item = await contractApi.upload(file as File); message.success(`已导入 ${item.contractNo}`); await refresh(); onSuccess?.(item); }
      catch (error) { message.error('导入失败，请确认 Word 中存在合同编号'); onError?.(error as Error); }
    }}><p className="ant-upload-drag-icon"><InboxOutlined /></p><p>拖入或点击上传 .docx 合同</p></Dragger>
    <Row gutter={20}>
      <Col span={8}><Card title={`合同列表（${contracts.length}）`}><List dataSource={contracts} renderItem={item => <List.Item onClick={() => { setSelected(item); setComparison(undefined); }} style={{ cursor: 'pointer', background: selected?.id === item.id ? '#e6f4ff' : undefined, padding: 12 }}><List.Item.Meta title={item.title} description={`${item.contractNo} · v${item.currentVersion}`} /></List.Item>} /></Card></Col>
      <Col span={16}><Card title="合同事实与可验证对照" extra={selected && <Button icon={<DownloadOutlined />} href={contractApi.documentUrl(selected.id)}>下载 Word</Button>}>
        {selected ? <><Descriptions column={2} size="small"><Descriptions.Item label="合同编号">{selected.contractNo}</Descriptions.Item><Descriptions.Item label="状态"><Tag>{selected.status}</Tag></Descriptions.Item><Descriptions.Item label="甲方">{selected.partyA}</Descriptions.Item><Descriptions.Item label="乙方">{selected.partyB}</Descriptions.Item><Descriptions.Item label="金额">{selected.amount} {selected.currency}</Descriptions.Item><Descriptions.Item label="Word 版本">v{selected.currentVersion}</Descriptions.Item></Descriptions><Divider />
          <Space.Compact block><Input value={question} onChange={e => setQuestion(e.target.value)} onPressEnter={compare} /><Button type="primary" icon={<SearchOutlined />} loading={loading} onClick={compare}>同题对照</Button></Space.Compact>
          {comparison && <><Row gutter={16} style={{ marginTop: 18 }}><Col span={12}><Card size="small" title="传统 RAG：文本召回"><Paragraph>{comparison.rag.answer}</Paragraph><Text type="secondary">召回片段 {comparison.rag.citations.length} 条；不执行业务规则。</Text></Card></Col><Col span={12}><Card size="small" title="本体系统：语义事实与推理"><Paragraph>{comparison.ontology.answer}</Paragraph><Text type="secondary">{comparison.ontology.relations.join(' · ')}</Text></Card></Col></Row><Table style={{ marginTop: 16 }} size="small" pagination={false} dataSource={comparison.differences} rowKey="dimension" columns={[{ title: '维度', dataIndex: 'dimension' }, { title: '传统 RAG', dataIndex: 'rag' }, { title: '本体系统', dataIndex: 'ontology' }]} /></>}
        </> : <Paragraph type="secondary">上传或选择一份合同。</Paragraph>}
      </Card></Col>
    </Row>
  </div>;
};

export default ContractCenter;
