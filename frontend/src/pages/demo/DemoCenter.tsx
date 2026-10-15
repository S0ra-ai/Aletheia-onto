import React, { useState } from 'react';
import { Alert, Button, Card, Divider, message, Result, Typography } from 'antd';
import { RocketOutlined, FileTextOutlined, SettingOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { DECISION_STATUS, label } from '../../i18n/labels';
import { demoApi, requestErrorMessage } from '../../api';
import type { DemoBootstrapResult } from '../../types';

const { Title, Paragraph } = Typography;

const DemoCenter: React.FC = () => {
  const navigate = useNavigate();
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
      message.error(requestErrorMessage(error, '加载演示数据失败'));
    } finally {
      setLoading(null);
    }
  };

  return (
    <div>
      <Title level={3}>演示中心</Title>
      <Paragraph type="secondary">
        一键加载演示数据，体验完整业务流程
      </Paragraph>

      <Alert
        message="演示说明"
        description="点击下方按钮将自动创建样例数据库、注册数据源、执行元数据扫描并生成领域本体草案。"
        type="info"
        showIcon
        style={{ marginBottom: 24 }}
      />

      <div style={{ display: 'flex', gap: 24 }}>
        <Card
          title="合同管理演示"
          style={{ flex: 1 }}
          extra={<FileTextOutlined style={{ fontSize: 24, color: '#1890ff' }} />}
        >
          <Paragraph>
            演示合同管理场景，包含：
          </Paragraph>
          <ul>
            <li>客户、合同、付款计划、发票等业务对象</li>
            <li>黑名单客户、逾期付款等风险场景</li>
            <li>合同金额校验、付款逾期预警等规则</li>
          </ul>
          <Button
            type="primary"
            icon={<RocketOutlined />}
            loading={loading === 'contract'}
            onClick={() => bootstrap('contract')}
            block
          >
            启动合同管理演示
          </Button>
        </Card>

        <Card
          title="设备运维演示"
          style={{ flex: 1 }}
          extra={<SettingOutlined style={{ fontSize: 24, color: '#52c41a' }} />}
        >
          <Paragraph>
            演示设备运维场景，包含：
          </Paragraph>
          <ul>
            <li>设备、工单、点检记录、备件等业务对象</li>
            <li>重要设备未关闭工单、备件库存不足等风险</li>
            <li>设备状态校验、备件库存预警等规则</li>
          </ul>
          <Button
            type="primary"
            icon={<RocketOutlined />}
            loading={loading === 'equipment'}
            onClick={() => bootstrap('equipment')}
            block
            style={{ background: '#52c41a', borderColor: '#52c41a' }}
          >
            启动设备运维演示
          </Button>
        </Card>
      </div>

      {result && (
        <>
          <Divider />
          <Result
            status="success"
            title="演示数据加载成功"
            subTitle={
              result.decision
                ? `数据源 ${result.dataSource.id} 已接入，本体已生成，并对样例实例完成了一次研判：${label(DECISION_STATUS, result.decision)}`
                : `数据源ID: ${result.dataSource.id}，本体已生成`
            }
            extra={[
              <Button
                type="primary"
                key="datasource"
                onClick={() => navigate(`/datasource/${result.dataSource.id}`)}
              >
                查看数据源
              </Button>,
              <Button
                key="ontology"
                onClick={() => navigate(`/ontology/${result.ontology.id}`)}
              >
                查看本体
              </Button>,
              <Button
                key="semantic"
                onClick={() => navigate('/semantic')}
              >
                体验语义服务
              </Button>,
            ]}
          />
        </>
      )}
    </div>
  );
};

export default DemoCenter;
