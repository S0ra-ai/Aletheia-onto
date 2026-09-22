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
      await backupApi.restore(selectedBackup);
      message.success('恢复成功，请停止服务后重启平台');
      setRestoreModal(false);
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
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'createdAt',
      width: 210,
      render: (value: string) => new Date(value).toLocaleString(),
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
      </Modal>
    </div>
  );
};

export default BackupManager;
