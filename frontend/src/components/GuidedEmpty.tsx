import React from 'react';
import { Empty, Space, Typography } from 'antd';

const { Text } = Typography;

export interface GuidedEmptyProps {
  /** One line naming what is missing, in the reader's terms. */
  title: string;
  /** Why it matters, or what it is for. Optional: some lists need only the next step. */
  body?: string;
  /**
   * Where the rows come from. This is the part a bare 暂无数据 never says, and the reason
   * this component exists: an empty list is read by somebody who has just arrived and does
   * not yet know which screen produces the thing they are looking at.
   */
  hint?: string;
  /** The buttons that get the reader to the state this list is empty of. */
  children?: React.ReactNode;
}

/**
 * An empty table, explained.
 *
 * antd's default empty state is the words 暂无数据 and nothing else. On a list that is the
 * *destination* of a flow -- mappings, backups, roles -- that is the least instructive
 * screen on the path, and it reads the same whether the feature is unused or broken. Every
 * list page here answers the same three questions in the same shape, so a reader who has
 * met one of them has met all of them.
 *
 * Used where the list can genuinely be empty on a working install. A table that is empty
 * only if something has gone wrong should say *that* instead, not this.
 */
const GuidedEmpty: React.FC<GuidedEmptyProps> = ({ title, body, hint, children }) => (
  <Empty
    image={Empty.PRESENTED_IMAGE_SIMPLE}
    description={
      <Space orientation="vertical" size={4} style={{ maxWidth: 620 }}>
        <Text strong>{title}</Text>
        {body && <Text type="secondary">{body}</Text>}
        {hint && (
          <Text type="secondary" style={{ fontSize: 12.5 }}>
            {hint}
          </Text>
        )}
      </Space>
    }
  >
    {children ? <Space wrap>{children}</Space> : null}
  </Empty>
);

export default GuidedEmpty;
