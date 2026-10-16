import React from 'react';
import { Button, Result } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useT } from '../i18n/locale';

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
  const t = useT();

  return (
    <Result
      status="404"
      title={t('shell.notFound.title')}
      subTitle={t('shell.notFound.subtitle')}
      extra={
        <Button type="primary" onClick={() => navigate('/workbench')}>
          {t('shell.notFound.back')}
        </Button>
      }
    />
  );
};

export default NotFound;
