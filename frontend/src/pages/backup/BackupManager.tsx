import React, { useEffect, useState } from 'react';
import { Button, Modal, Space, Table, Tag, Typography, message } from 'antd';
import { DatabaseOutlined, DownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { backupApi } from '../../api';
import { useT } from '../../i18n/locale';

const { Title, Text } = Typography;

interface BackupItem {
  name: string;
  path: string;
  size: number;
  created_at: string;
}

const formatSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
};

const BackupManager: React.FC = () => {
  const t = useT();
  const [backups, setBackups] = useState<BackupItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [restoreModal, setRestoreModal] = useState(false);
  const [selectedBackup, setSelectedBackup] = useState('');

  const loadBackups = async () => {
    setLoading(true);
    try {
      setBackups(await backupApi.list());
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('backup.listFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadBackups();
  }, [t]);

  const handleCreate = async () => {
    setCreating(true);
    try {
      await backupApi.create();
      message.success(t('backup.createSuccess'));
      await loadBackups();
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('backup.createFailed'));
    } finally {
      setCreating(false);
    }
  };

  const handleDownload = async (name: string) => {
    try {
      const blob = await backupApi.download(name);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${name}.tar.gz`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('backup.downloadFailed'));
    }
  };

  const handleRestore = async () => {
    if (!selectedBackup) return;
    setRestoring(true);
    try {
      const result = await backupApi.restore(selectedBackup);
      // Name the way back. The server snapshots the platform database before replacing it,
      // because picking the wrong archive out of a list of fifty is an ordinary mistake --
      // and the message that only said 「恢复成功」 left that snapshot invisible.
      message.success(
        result?.safetyCopy
          ? t('backup.restoreSuccess', { name: result.safetyCopy })
          : t('backup.restoreSuccessNoSnapshot'),
        8,
      );
      setRestoreModal(false);
      void loadBackups();
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('backup.restoreFailed'));
    } finally {
      setRestoring(false);
    }
  };

  const columns: ColumnsType<BackupItem> = [
    {
      title: t('backup.nameColumn'),
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
    },
    {
      // The archive was written at that instant and the platform records instants in UTC, so
      // the string has to say so before it is parsed: `new Date("2026-10-15 19:12:07")` is
      // read by the browser as *local* time, and every row was then displayed shifted by the
      // reader's offset. Labelled 本地 because that is what is being shown.
      title: t('backup.createdAtColumn'),
      dataIndex: 'created_at',
      key: 'createdAt',
      width: 210,
      render: (value: string) =>
        value ? new Date(`${value.replace(' ', 'T')}Z`).toLocaleString() : '',
    },
    {
      title: t('backup.sizeColumn'),
      dataIndex: 'size',
      key: 'size',
      width: 110,
      render: (value: number) => formatSize(value),
    },
    {
      title: t('shell.common.actions'),
      key: 'action',
      width: 190,
      render: (_, row) => (
        <Space>
          <Button size="small" icon={<DownloadOutlined />} onClick={() => void handleDownload(row.name)}>
            {t('backup.downloadButton')}
          </Button>
          <Button
            size="small"
            type="primary"
            danger
            icon={<ReloadOutlined />}
            onClick={() => {
              setSelectedBackup(row.name);
              setRestoreModal(true);
            }}
          >
            {t('backup.restoreButton')}
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <Title level={4}>{t('backup.title')}</Title>
          <Text type="secondary">{t('backup.subtitle')}</Text>
        </div>
        <Button type="primary" icon={<DatabaseOutlined />} loading={creating} onClick={() => void handleCreate()}>
          {t('backup.createButton')}
        </Button>
      </Space>

      <Table columns={columns} dataSource={backups} rowKey="name" loading={loading} pagination={false} />

      <Modal
        title={t('backup.restoreConfirmTitle')}
        open={restoreModal}
        onOk={() => void handleRestore()}
        confirmLoading={restoring}
        okText={t('backup.restoreConfirmButton')}
        cancelText={t('shell.common.cancel')}
        onCancel={() => setRestoreModal(false)}
      >
        <p>
          {t('backup.restorePrompt')} <Tag>{selectedBackup}</Tag>
        </p>
        <p>{t('backup.restoreWarning')}</p>
        <p>
          {t('backup.safetyCopyBefore')} <Tag>before-restore-…</Tag> {t('backup.safetyCopyAfter')}
        </p>
      </Modal>
    </div>
  );
};

export default BackupManager;
