import React, { Component, type ErrorInfo, type ReactNode } from 'react';
import { Alert, Button, Result } from 'antd';
import { ReloadOutlined, SafetyOutlined } from '@ant-design/icons';
import { useT } from '../i18n/locale';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  /** Show a full-page result instead of inline alert */
  fullPage?: boolean;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

interface ErrorFallbackProps {
  fullPage?: boolean;
  error: Error | null;
}

/**
 * The fallback text lives in a function component: a class component cannot call `useT()`,
 * and this text has to follow the language switch like every other screen's does.
 */
const ErrorFallback: React.FC<ErrorFallbackProps> = ({ fullPage, error }) => {
  const t = useT();

  if (fullPage) {
    return (
      <Result
        status="error"
        title={t('errors.title')}
        subTitle={error?.message || t('errors.unknown')}
        extra={[
          <Button
            type="primary"
            key="reload"
            icon={<ReloadOutlined />}
            onClick={() => window.location.reload()}
          >
            {t('errors.reload')}
          </Button>,
        ]}
      />
    );
  }

  return (
    <Alert
      type="error"
      showIcon
      icon={<SafetyOutlined />}
      message={t('errors.title')}
      description={
        <div>
          <p style={{ marginBottom: 8 }}>{error?.message || t('errors.unknownShort')}</p>
          <Button
            type="link"
            icon={<ReloadOutlined />}
            onClick={() => window.location.reload()}
            style={{ padding: 0 }}
          >
            {t('errors.retry')}
          </Button>
        </div>
      }
      style={{ margin: 16 }}
    />
  );
};

class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('未捕获的组件错误:', error, errorInfo);
    this.props.onError?.(error, errorInfo);
  }

  public render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return <ErrorFallback fullPage={this.props.fullPage} error={this.state.error} />;
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
