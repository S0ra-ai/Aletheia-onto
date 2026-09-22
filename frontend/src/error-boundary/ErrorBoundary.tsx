import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Alert, Button, Result } from 'antd';
import { ReloadOutlined, SafetyOutlined } from '@ant-design/icons';

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

      if (this.props.fullPage) {
        return (
          <Result
            status="error"
            title="页面加载失败"
            subTitle={this.state.error?.message || '发生未知错误，请刷新页面重试'}
            extra={[
              <Button
                type="primary"
                key="reload"
                icon={<ReloadOutlined />}
                onClick={() => window.location.reload()}
              >
                刷新页面
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
          message="页面加载失败"
          description={
            <div>
              <p style={{ marginBottom: 8 }}>{this.state.error?.message || '发生未知错误'}</p>
              <Button
                type="link"
                icon={<ReloadOutlined />}
                onClick={() => window.location.reload()}
                style={{ padding: 0 }}
              >
                刷新重试
              </Button>
            </div>
          }
          style={{ margin: 16 }}
        />
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
