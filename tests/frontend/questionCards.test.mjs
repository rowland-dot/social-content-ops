import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { runInNewContext } from 'node:vm';
import { test } from 'node:test';

const require = createRequire(new URL('../../web/frontend/package.json', import.meta.url));
const ts = require('typescript');
const source = readFileSync(new URL('../../web/frontend/src/components/QuestionCards.tsx', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
    jsx: ts.JsxEmit.ReactJSX,
  },
});
const component = { exports: {} };
runInNewContext(outputText, {
  exports: component.exports,
  require: name => name === '../lib/api' ? {} : require(name),
});
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

test('approval cards preserve long multiline commands and both permission choices', () => {
  const command = `Codex 请求额外权限（仅本次）：python /data/project/Easel/${'long_segment_'.repeat(200)}/render.py\n第二行 <script>alert(1)</script>`;
  const rendered = renderToStaticMarkup(React.createElement(component.exports.default, {
    questions: [{
      id: 'codex-approval',
      questions: [{
        questionId: 'permission',
        header: '执行授权',
        question: command,
        options: [{ label: '允许本次' }, { label: '拒绝' }],
      }],
    }],
  }));
  assert.ok(rendered.includes('long_segment_'.repeat(200)));
  assert.ok(rendered.includes('\n第二行 &lt;script&gt;alert(1)&lt;/script&gt;'));
  assert.match(rendered, /<strong>允许本次<\/strong>/);
  assert.match(rendered, /<strong>拒绝<\/strong>/);
  assert.match(rendered, /disabled="">提交<\/button>/);
});

test('approval card grids can shrink and wrap commands without clipping their content', () => {
  const styles = readFileSync(new URL('../../web/frontend/src/styles/index.css', import.meta.url), 'utf8');
  const rule = selector => {
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const matched = styles.match(new RegExp(`${escaped}\\s*\\{([^}]+)\\}`));
    assert.ok(matched, selector);
    return matched[1];
  };
  for (const selector of ['.question-card', '.question-card__item', '.question-card__option']) {
    assert.match(rule(selector), /grid-template-columns:\s*minmax\(0,\s*1fr\)/);
    assert.match(rule(selector), /min-width:\s*0/);
  }
  assert.match(rule('.question-card'), /overflow-wrap:\s*anywhere/);
  assert.match(rule('.question-card__title'), /white-space:\s*pre-wrap/);
  assert.match(rule('.question-card__options'), /minmax\(min\(150px,\s*100%\),\s*1fr\)/);
  assert.match(rule('.question-card__custom input'), /min-width:\s*0/);
});

const asked = { id: 'q-1', expiresAtMs: 1_000_000 + 125_000, questions: [{
  questionId: 'q1', header: '上图文字', question: '上图文字用哪个方案？', options: [{ label: '方案 A' }, { label: '方案 B' }] }] };

test('a live box shows its time left, counting down to the second', () => {
  const html = nowMs => renderToStaticMarkup(React.createElement(component.exports.default, { questions: [asked], nowMs }));
  assert.match(html(1_000_000), /question-card__timer">剩余 2:05</);
  assert.match(html(1_000_000 + 124_001), /剩余 0:01</);
});

test('a box past its deadline is marked expired in Chinese and says what a pick will do', () => {
  const rendered = renderToStaticMarkup(React.createElement(component.exports.default, { questions: [asked], nowMs: 1_000_000 + 125_000 }));
  assert.doesNotMatch(rendered, /question-card__timer/);
  assert.match(rendered, /question-card__expired">这道题已过期/);
  assert.match(rendered, /普通聊天消息/);
});

test('a late answer names the question it answers', () => {
  assert.equal(
    component.exports.lateAnswerMessage(asked, { q1: ['方案 B'] }),
    '回答你之前已过期的提问：\n「上图文字用哪个方案？」→ 我选：方案 B');
});
