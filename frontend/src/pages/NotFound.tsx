import React from 'react';
import { Button, Result } from 'antd';
import { useNavigate } from 'react-router-dom';

/**
 * The page for a path the application does not have.
 *
 * Without it, react-router matched nothing and the layout rendered an empty content area:
 * the navigation and header stayed, the screen below them was blank, and nothing told the
 * user whether the page was missing, still loading, or broken. A blank frame is the one
 * failure a reader cannot act on.
 */
const NotFound: React.FC = () => {
  const navigate = useNavigate();

  return (
    <Result
      status="404"
      title="页面不存在"
      subTitle="这个地址没有对应的页面。可能是链接已失效，或地址被手写时有出入。"
      extra={
        <Button type="primary" onClick={() => navigate('/workbench')}>
          返回工作台
        </Button>
      }
    />
  );
};

export default NotFound;
