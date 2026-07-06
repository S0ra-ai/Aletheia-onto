import React, { useState } from 'react';
import { Card, Button, Typography, Alert, Result, Divider } from 'antd';
import { RocketOutlined, FileTextOutlined, SettingOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { demoApi } from '../../api';
import type { DemoBootstrapResult } from '../../types';

const { Title, Paragraph } = Typography;

const DemoCenter: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState<'contract' | 'equipment' | null>(null);
  const [result, setResult] = useState<DemoBootstrapResult | null>(null);

  const handleBootstrapContract = async () => {
    setLoading('contract');
    try {
      const data = await demoApi.bootstrapContract();
      setResult(data);
    } catch (error) {
      console.error('Failed to bootstrap contract demo:', error);
    } finally {
      setLoading(null);
    }
  };

  const handleBootstrapEquipment = async () => {
    setLoading('equipment');
    try {
      const data = await demoApi.bootstrapEquipment();
      setResult(data);
    } catch (error) {
      console.error('Failed to bootstrap equipment demo:', error);
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
            onClick={handleBootstrapContract}
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
            onClick={handleBootstrapEquipment}
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
            subTitle={`数据源ID: ${result.dataSource.id}，本体已生成`}
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
