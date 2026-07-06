import React, { useEffect, useState } from 'react';
import { Card, Col, Row, Statistic, Button, Space, Typography, Alert } from 'antd';
import {
  DatabaseOutlined,
  ApartmentOutlined,
  SafetyCertificateOutlined,
  RocketOutlined,
  ApiOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { modelApi } from '../../api';
import type { ModelStatus } from '../../types';

const { Title, Paragraph } = Typography;

const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null);

  useEffect(() => {
    const fetchModelStatus = async () => {
      try {
        const status = await modelApi.getStatus();
        setModelStatus(status);
      } catch (error) {
        console.error('Failed to fetch model status:', error);
      }
    };
    fetchModelStatus();
  }, []);

  return (
    <div>
      <Title level={2}>工作台</Title>
      <Paragraph type="secondary">
        本体改造研发平台 - 为传统业务系统安装可演进的业务语义内核
      </Paragraph>

      <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable onClick={() => navigate('/datasource')}>
            <Statistic
              title="数据源管理"
              value="接入"
              prefix={<DatabaseOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
            <Paragraph type="secondary" style={{ marginTop: 8 }}>
              登记和管理传统业务系统
            </Paragraph>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable onClick={() => navigate('/ontology')}>
            <Statistic
              title="本体建模"
              value="建模"
              prefix={<ApartmentOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
            <Paragraph type="secondary" style={{ marginTop: 8 }}>
              构建业务对象和关系
            </Paragraph>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable onClick={() => navigate('/rules')}>
            <Statistic
              title="规则管理"
              value="配置"
              prefix={<SafetyCertificateOutlined />}
              valueStyle={{ color: '#faad14' }}
            />
            <Paragraph type="secondary" style={{ marginTop: 8 }}>
              定义业务规则和约束
            </Paragraph>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable onClick={() => navigate('/semantic')}>
            <Statistic
              title="语义服务"
              value="研判"
              prefix={<ApiOutlined />}
              valueStyle={{ color: '#ff4d4f' }}
            />
            <Paragraph type="secondary" style={{ marginTop: 8 }}>
              实例解释和风险研判
            </Paragraph>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
        <Col xs={24} lg={16}>
          <Card title="快速开始">
            <Space direction="vertical" style={{ width: '100%' }}>
              <Alert
                message="演示模式"
                description="点击下方按钮一键加载演示数据，体验完整业务流程"
                type="info"
                showIcon
              />
              <Space>
                <Button
                  type="primary"
                  icon={<RocketOutlined />}
                  onClick={() => navigate('/demo')}
                >
                  进入演示中心
                </Button>
                <Button onClick={() => navigate('/datasource')}>
                  手动接入数据源
                </Button>
              </Space>
            </Space>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="系统状态">
            <Statistic
              title="模型配置"
              value={modelStatus?.configured ? '已配置' : '未配置'}
              valueStyle={{ color: modelStatus?.configured ? '#52c41a' : '#ff4d4f' }}
            />
            {modelStatus?.configured && (
              <>
                <Statistic
                  title="当前模型"
                  value={modelStatus.model}
                  style={{ marginTop: 16 }}
                />
                <Statistic
                  title="提供商"
                  value={modelStatus.provider}
                  style={{ marginTop: 16 }}
                />
              </>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default Dashboard;
