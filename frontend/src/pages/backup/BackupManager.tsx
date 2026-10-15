import React, { useEffect, useState } from 'react';
import { Button, Modal, Space, Table, Tag, Typography, message } from 'antd';
import { DatabaseOutlined, DownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { backupApi } from '../../api';

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
      message.error(error instanceof Error ? error.message : '加载备份列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadBackups();
  }, []);

  const handleCreate = async () => {
    setCreating(true);
    try {
      await backupApi.create();
      message.success('备份创建成功');
      await loadBackups();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '创建备份失败');
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
      message.error(error instanceof Error ? error.message : '下载备份失败');
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
          ? `恢复成功，请停止服务后重启平台。恢复前的平台库已存为备份 ${result.safetyCopy}`
          : '恢复成功，请停止服务后重启平台',
        8,
      );
      setRestoreModal(false);
      void loadBackups();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '恢复失败');
    } finally {
      setRestoring(false);
    }
  };

  const columns: ColumnsType<BackupItem> = [
    {
      title: '备份名称',
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
    },
    {
      // The archive was written at that instant and the platform records instants in UTC, so
      // the string has to say so before it is parsed: `new Date("2026-10-15 19:12:07")` is
      // read by the browser as *local* time, and every row was then displayed shifted by the
      // reader's offset. Labelled 本地 because that is what is being shown.
      title: '创建时间（本地）',
      dataIndex: 'created_at',
      key: 'createdAt',
      width: 210,
      render: (value: string) =>
        value ? new Date(`${value.replace(' ', 'T')}Z`).toLocaleString() : '',
    },
    {
      title: '大小',
      dataIndex: 'size',
      key: 'size',
      width: 110,
      render: (value: number) => formatSize(value),
    },
    {
      title: '操作',
      key: 'action',
      width: 190,
      render: (_, row) => (
        <Space>
          <Button size="small" icon={<DownloadOutlined />} onClick={() => void handleDownload(row.name)}>
            下载
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
            恢复
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <Title level={4}>数据备份管理</Title>
          <Text type="secondary">创建、下载和恢复 SQLite 平台库备份；服务端数据库请使用原生备份工具。</Text>
        </div>
        <Button type="primary" icon={<DatabaseOutlined />} loading={creating} onClick={() => void handleCreate()}>
          创建备份
        </Button>
      </Space>

      <Table columns={columns} dataSource={backups} rowKey="name" loading={loading} pagination={false} />

      <Modal
        title="确认恢复备份"
        open={restoreModal}
        onOk={() => void handleRestore()}
        confirmLoading={restoring}
        okText="确认恢复"
        cancelText="取消"
        onCancel={() => setRestoreModal(false)}
      >
        <p>
          即将恢复备份 <Tag>{selectedBackup}</Tag>
        </p>
        <p>恢复会替换当前 SQLite 平台库。请先停止服务，恢复完成后重启平台。</p>
        <p>
          恢复前平台会自动把当前库另存为一份 <Tag>before-restore-…</Tag> 备份，
          万一恢复的不是想要的那一份，可以用它换回来。
        </p>
      </Modal>
    </div>
  );
};

export default BackupManager;
