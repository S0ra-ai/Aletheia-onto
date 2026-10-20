import React, { useState } from 'react';
import { Alert, Button, Card, Form, Input, Typography } from 'antd';
import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/useAuth';
import { requestErrorMessage } from '../../api';
import { useT } from '../../i18n/locale';

const { Title, Paragraph } = Typography;

interface LoginFormValues {
  username: string;
  password: string;
}

const LoginPage: React.FC = () => {
  const t = useT();
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
      // Not `submitError.message`: an axios rejection carries its own English internals, so a
      // server that is unreachable printed “Network Error” under a Chinese form. The helper
      // shows the server's curated reason when there is one and the translated fallback
      // otherwise, which is the only two things worth putting here.
      setError(requestErrorMessage(submitError, t('shell.login.failed')));
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
          {t('shell.login.title')}
        </Title>
        <Paragraph type="secondary" style={{ marginBottom: 24 }}>
          {t('shell.login.subtitle')}
        </Paragraph>

        {/*
          The bootstrap password is printed once, by `init`, in a console the person reading
          this screen may never have seen -- a deployment's log, or somebody else's terminal.
          Without this the login form is the end of the road: nothing here says which account
          to use or that there is a way to reset it.
        */}
        <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 16 }}>
          {t('shell.login.firstRun')}
        </Paragraph>

        {error ? (
          <Alert type="error" title={error} showIcon style={{ marginBottom: 16 }} role="alert" />
        ) : null}

        <Form<LoginFormValues> layout="vertical" onFinish={handleSubmit} requiredMark={false}>
          <Form.Item
            name="username"
            label={t('shell.login.username')}
            rules={[{ required: true, message: t('shell.login.usernameRequired') }]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder={t('shell.login.username')}
              autoComplete="username"
              autoFocus
            />
          </Form.Item>
          <Form.Item
            name="password"
            label={t('shell.login.password')}
            rules={[{ required: true, message: t('shell.login.passwordRequired') }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder={t('shell.login.password')}
              autoComplete="current-password"
            />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" loading={submitting} block>
              {t('shell.login.submit')}
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </main>
  );
};

export default LoginPage;
