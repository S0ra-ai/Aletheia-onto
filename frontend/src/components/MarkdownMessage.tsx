import React from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * Renders an agent answer as Markdown.
 *
 * Answers arrive with real structure -- rule verdicts as lists, evidence as
 * tables, rule codes and field names as inline code. Rendering them as
 * preformatted text made a compliance verdict read as one wall of characters,
 * which undercuts the whole point of showing the reasoning.
 *
 * Security: raw HTML is *not* enabled. react-markdown drops embedded HTML by
 * default, and no rehype-raw plugin is added here on purpose. Answer text can
 * include content derived from the connected database, so treating it as
 * trusted markup would be an injection path. Only Markdown syntax is honoured.
 */

export interface MarkdownMessageProps {
  content: string;
  /** Inverted palette for messages on a coloured (user) bubble. */
  inverted?: boolean;
}

const MarkdownMessage: React.FC<MarkdownMessageProps> = ({ content, inverted = false }) => {
  const codeBg = inverted ? 'rgba(255,255,255,0.18)' : 'rgba(0,0,0,0.06)';
  const borderColor = inverted ? 'rgba(255,255,255,0.35)' : '#d0d7e2';
  const mutedColor = inverted ? 'rgba(255,255,255,0.85)' : '#5b6b7f';

  return (
    <div className={`markdown-message${inverted ? ' markdown-message-inverted' : ''}`}>
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Paragraphs carry the bubble's line height; the last one must not add
          // trailing space or the bubble looks unbalanced.
          p: ({ children }) => <div style={{ margin: '0 0 8px' }}>{children}</div>,

          // Headings inside a chat bubble should read as emphasis, not as page
          // structure, so they stay close to body size.
          h1: ({ children }) => <div style={{ fontWeight: 600, fontSize: 15, margin: '10px 0 6px' }}>{children}</div>,
          h2: ({ children }) => <div style={{ fontWeight: 600, fontSize: 15, margin: '10px 0 6px' }}>{children}</div>,
          h3: ({ children }) => <div style={{ fontWeight: 600, fontSize: 14, margin: '8px 0 4px' }}>{children}</div>,

          ul: ({ children }) => <ul style={{ margin: '4px 0 8px', paddingInlineStart: 20 }}>{children}</ul>,
          ol: ({ children }) => <ol style={{ margin: '4px 0 8px', paddingInlineStart: 20 }}>{children}</ol>,
          li: ({ children }) => <li style={{ marginBottom: 2 }}>{children}</li>,

          strong: ({ children }) => <strong style={{ fontWeight: 600 }}>{children}</strong>,

          a: ({ href, children }) => (
            // Untrusted destinations: never grant window.opener access.
            <a href={href} target="_blank" rel="noreferrer noopener">
              {children}
            </a>
          ),

          code: ({ className, children }) => {
            const isBlock = Boolean(className?.startsWith('language-'));
            if (isBlock) {
              return (
                <pre
                  style={{
                    background: codeBg,
                    padding: '10px 12px',
                    borderRadius: 6,
                    overflowX: 'auto',
                    margin: '6px 0 8px',
                    fontSize: 12.5,
                    lineHeight: 1.6,
                  }}
                >
                  <code>{children}</code>
                </pre>
              );
            }
            // Inline code carries rule codes and column names, so keep it
            // visually distinct but not boxed in like a block.
            return (
              <code
                style={{
                  background: codeBg,
                  padding: '1px 5px',
                  borderRadius: 4,
                  fontSize: '0.92em',
                }}
              >
                {children}
              </code>
            );
          },

          blockquote: ({ children }) => (
            <div
              style={{
                borderInlineStart: `3px solid ${borderColor}`,
                paddingInlineStart: 10,
                margin: '6px 0 8px',
                color: mutedColor,
              }}
            >
              {children}
            </div>
          ),

          hr: () => <div style={{ height: 1, background: borderColor, margin: '10px 0' }} />,

          // Evidence often arrives as a table. antd's Table would need column
          // definitions we do not have, so render a plain table that inherits
          // the bubble's colours and scrolls rather than overflowing.
          table: ({ children }) => (
            <div style={{ overflowX: 'auto', margin: '6px 0 8px' }}>
              <table style={{ borderCollapse: 'collapse', fontSize: 12.5, width: '100%' }}>{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th
              style={{
                border: `1px solid ${borderColor}`,
                padding: '5px 8px',
                textAlign: 'start',
                fontWeight: 600,
                background: codeBg,
              }}
            >
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td style={{ border: `1px solid ${borderColor}`, padding: '5px 8px' }}>{children}</td>
          ),
        }}
      >
        {content}
      </Markdown>
    </div>
  );
};

export default MarkdownMessage;
