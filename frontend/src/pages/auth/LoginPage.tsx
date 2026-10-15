import React, { useState } from 'react';
import { Alert, Button, Card, Form, Input, Typography } from 'antd';
import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/useAuth';

const { Title, Paragraph } = Typography;

interface LoginFormValues {
  username: string;
  password: string;
}

const LoginPage: React.FC = () => {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const redirectTo = (location.state as { from?: string } | null)?.from ?? '/workbench';

  const handleSubmit = async (values: LoginFormValues) => {
    setSubmitting(true);
    setError('');
    try {
      await signIn(values.username, values.password);
      navigate(redirectTo, { replace: true });
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : '登录失败，请重试。');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#f5f5f5',
        padding: 24,
      }}
    >
      <Card style={{ width: 400, maxWidth: '100%' }}>
        <Title level={3} style={{ marginBottom: 4 }}>
          本体改造研发平台
        </Title>
        <Paragraph type="secondary" style={{ marginBottom: 24 }}>
          请使用平台账号登录。
        </Paragraph>

        {/*
          The bootstrap password is printed once, by `init`, in a console the person reading
          this screen may never have seen -- a deployment's log, or somebody else's terminal.
          Without this the login form is the end of the road: nothing here says which account
          to use or that there is a way to reset it.
        */}
        <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 16 }}>
          首次使用：管理员账号是 <Typography.Text code>admin</Typography.Text>，
          口令在 <Typography.Text code>aletheia init</Typography.Text> 的输出里，只显示一次。
          忘记了就在服务器上运行 <Typography.Text code>aletheia passwd</Typography.Text> 重设（会提示输入新口令）。
        </Paragraph>

        {error ? (
          <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} role="alert" />
        ) : null}

        <Form<LoginFormValues> layout="vertical" onFinish={handleSubmit} requiredMark={false}>
          <Form.Item
            name="username"
            label="用户名"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder="用户名"
              autoComplete="username"
              autoFocus
            />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="密码"
              autoComplete="current-password"
            />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" loading={submitting} block>
              登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </main>
  );
};

export default LoginPage;
