/**
 * The syntaxes the console can highlight, and why the list is short.
 *
 * Importing `react-syntax-highlighter`'s default `Prism` entry point pulls in **every**
 * grammar the package ships -- 300 of them, `refractor` alone is 2.8 MB on disk -- and the
 * bundler has no way to know which ones an answer will ever contain, so it keeps them all.
 * That single import made the markdown renderer the largest asset in the application:
 * 781 kB minified, 270 kB gzipped, larger than antd's core and roughly nine times the
 * application shell. It is loaded on the chat screen, the workbench and every panel that
 * renders a model answer.
 *
 * What an answer from this platform actually contains is bounded by what the platform
 * produces and cites: the SQL it read, the JSON it received, the rule expression it
 * evaluated, the command or code it suggests. That is this list.
 *
 * An unregistered language is not an error. `react-syntax-highlighter` catches the failure
 * and falls back to plain text, so a `fortran` block in a model's answer renders as
 * unhighlighted code rather than as a crash or an empty box. Registering nothing would be
 * wrong in the other direction -- a `sql` block with no colours is the case this feature
 * exists for -- which is why the list is chosen rather than omitted.
 *
 * Adding one is a deliberate act with a cost: `languages/prism/<name>` is imported eagerly,
 * so it is in the bundle whether or not any answer contains it.
 */
import { PrismLight as SyntaxHighlighter } from 'react-syntax-highlighter';

import bash from 'react-syntax-highlighter/dist/esm/languages/prism/bash';
import json from 'react-syntax-highlighter/dist/esm/languages/prism/json';
import javascript from 'react-syntax-highlighter/dist/esm/languages/prism/javascript';
import markup from 'react-syntax-highlighter/dist/esm/languages/prism/markup';
import python from 'react-syntax-highlighter/dist/esm/languages/prism/python';
import sql from 'react-syntax-highlighter/dist/esm/languages/prism/sql';
import typescript from 'react-syntax-highlighter/dist/esm/languages/prism/typescript';
import yaml from 'react-syntax-highlighter/dist/esm/languages/prism/yaml';

// Each grammar registers with its own aliases (`py`, `sh`, `yml`, `html`), so a fenced block
// written with any of them resolves to the same highlighter.
for (const [name, grammar] of Object.entries({
  bash,
  json,
  javascript,
  markup,
  python,
  sql,
  typescript,
  yaml,
})) {
  SyntaxHighlighter.registerLanguage(name, grammar);
}

/**
 * Languages whose fenced blocks get a label above them, and what to call them.
 *
 * `text` is absent on purpose: it is what an unlabelled or unrecognised block falls back
 * to, and labelling a block “text” says nothing. The label is a courtesy to the reader who
 * wants to know whether they are looking at SQL or at a shell command.
 */
export const LABELLED_LANGUAGES: ReadonlySet<string> = new Set([
  'bash',
  'json',
  'javascript',
  'markup',
  'python',
  'sql',
  'typescript',
  'yaml',
]);

export default SyntaxHighlighter;
