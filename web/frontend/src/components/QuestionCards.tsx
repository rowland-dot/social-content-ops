import { useEffect, useMemo, useState } from 'react';
import type { ChatQuestion, ChatQuestionItem } from '../lib/api';
import { answerQuestion } from '../lib/api';

/**
 * ask_user 问答题卡片。
 *
 * OpenClaw 的 ask_user 一次可带 1-3 个问题（question.questions[]）。gateway 的
 * question.resolve 要求 answers 里**每个问题都有答案**（单个缺失即报
 * QUESTION_INVALID_ANSWER: "question 'xxx' requires an answer"）。
 * 因此多问题时渲染全部题目，用户每问答完一项，全部选齐后自动提交一次。
 *
 * 多选：问题对象带 multiSelect: true 时，answers[qid] 可携带多个 label
 * （gateway 对 multiSelect=false 的多值直接报 "does not allow multiple answers"，
 * 前端只按数据渲染，不绕过校验）。
 */
/** 题已关闭：被标为过期，或已过截止时间。 */
export function isExpired(q: ChatQuestion, nowMs: number): boolean {
  return q.expired === true || (q.expiresAtMs != null && nowMs >= q.expiresAtMs);
}

/** 活题的剩余时间，如「剩余 9:41」。没有截止时间则不显示。 */
export function timeLeftText(q: ChatQuestion, nowMs: number): string {
  if (q.expiresAtMs == null) return '';
  const s = Math.max(0, Math.ceil((q.expiresAtMs - nowMs) / 1000));
  return `剩余 ${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

/** 过期题的补答：作为普通聊天消息发给 AI，写明回答的是哪道题。 */
export function lateAnswerMessage(q: ChatQuestion, answers: Record<string, string[]>): string {
  const lines = q.questions.map((it) => `「${it.question}」→ 我选：${(answers[it.questionId] || []).join('、')}`);
  return `回答你之前已过期的提问：\n${lines.join('\n')}`;
}

function useNow(fixed: number | undefined, ticking: boolean): number {
  const [now, setNow] = useState(() => fixed ?? Date.now());
  useEffect(() => {
    if (fixed != null || !ticking) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [fixed, ticking]);
  return fixed ?? now;
}

type LateAnswer = (q: ChatQuestion, answers: Record<string, string[]>) => void;

function QuestionCard({ question, onAnswered, onLateAnswer, nowMs }: {
  question: ChatQuestion; onAnswered: () => void; onLateAnswer?: LateAnswer; nowMs?: number;
}) {
  const now = useNow(nowMs, question.expiresAtMs != null && !question.expired);
  const expired = isExpired(question, now);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<Record<string, string[]>>({});
  const [custom, setCustom] = useState<Record<string, string>>({});
  const [customVals, setCustomVals] = useState<Record<string, string[]>>({});
  const [showCustom, setShowCustom] = useState<Record<string, boolean>>({});

  const items: ChatQuestionItem[] = question.questions || [];
  const valsOf = (it: ChatQuestionItem): string[] => selected[it.questionId] || [];
  const allAnswered = items.length > 0 && items.every((it) => valsOf(it).length > 0);

  const pick = (it: ChatQuestionItem, label: string) => {
    setSelected((s) => {
      const cur = s[it.questionId] || [];
      const next = it.multiSelect
        ? (cur.includes(label) ? cur.filter((v) => v !== label) : [...cur, label])
        : [label];
      return { ...s, [it.questionId]: next };
    });
  };

  const fillCustom = (it: ChatQuestionItem) => {
    const v = (custom[it.questionId] || '').trim();
    if (!v) return;
    setSelected((s) => {
      const cur = s[it.questionId] || [];
      return { ...s, [it.questionId]: it.multiSelect && !cur.includes(v) ? [...cur, v] : [v] };
    });
    setCustomVals((c) => {
      const cur = c[it.questionId] || [];
      return { ...c, [it.questionId]: cur.includes(v) ? cur : [...cur, v] };
    });
  };

  const removeCustom = (it: ChatQuestionItem, v: string) => {
    setSelected((s) => ({ ...s, [it.questionId]: (s[it.questionId] || []).filter((x) => x !== v) }));
    setCustomVals((c) => ({ ...c, [it.questionId]: (c[it.questionId] || []).filter((x) => x !== v) }));
  };

  const submit = async () => {
    if (busy || !allAnswered || question.waiting) return;
    const answers: Record<string, string[]> = {};
    for (const it of items) answers[it.questionId] = valsOf(it);
    // 已过期的题不再问网关：答案直接作为聊天消息发给 AI
    if (expired && onLateAnswer) { onLateAnswer(question, answers); return; }
    setBusy(true); setError('');
    try {
      const res = await answerQuestion({ questionId: question.id, answers });
      if (res.expired && onLateAnswer) onLateAnswer(question, answers);
      else if (!res.ok) setError(res.error || '提交失败');
      else onAnswered();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="message-row assistant">
      <div className="msg-col assistant" style={{ maxWidth: '80%' }}>
        <div className="question-card">
          {!expired && question.expiresAtMs != null && (
            <div className="question-card__timer">{timeLeftText(question, now)}</div>
          )}
          {items.map((it, idx) => {
            const options: { label: string; description?: string }[] = it.options || [];
            const vals = valsOf(it);
            const ctl = showCustom[it.questionId];
            const cvals = customVals[it.questionId] || [];
            return (
              <div key={it.questionId} className="question-card__item">
                {idx > 0 && <div className="question-card__divider" />}
                {it.header && <div className="question-card__chip">{it.header}</div>}
                <div className="question-card__title">
                  {it.question || '请选择'}
                  {it.multiSelect && <span className="question-card__multi">可多选</span>}
                </div>
                <div className="question-card__options">
                  {options.map((opt) => (
                    <button key={opt.label}
                      className={`question-card__option${vals.includes(opt.label) ? ' question-card__option--selected' : ''}`}
                      disabled={busy}
                      onClick={() => pick(it, opt.label)}>
                      <strong>{opt.label}</strong>
                      {opt.description && <span>{opt.description}</span>}
                    </button>
                  ))}
                  {cvals.map((v) => (
                    <button key={`custom-${v}`}
                      className="question-card__option question-card__option--selected"
                      disabled={busy}
                      title="点击移除"
                      onClick={() => removeCustom(it, v)}>
                      <strong>{v}</strong>
                      <span>自定义 · 点击移除</span>
                    </button>
                  ))}
                  <button className="question-card__other" disabled={busy}
                    onClick={() => setShowCustom((s) => ({ ...s, [it.questionId]: !s[it.questionId] }))}>
                    {ctl ? '收起自定义输入' : '自行输入…'}
                  </button>
                </div>
                {ctl && (
                  <div className="question-card__custom">
                    <input
                      type="text"
                      value={custom[it.questionId] || ''}
                      placeholder="输入你的答案"
                      onChange={(e) => setCustom((c) => ({ ...c, [it.questionId]: e.target.value }))}
                    />
                    <button disabled={busy || !(custom[it.questionId] || '').trim()}
                      onClick={() => fillCustom(it)}>
                      填入
                    </button>
                  </div>
                )}
              </div>
            );
          })}

          {/* 单选题：选完点提交；多题：全部选齐后提交（单选/多选同一规则） */}
          {items.length === 1 ? (
            <div className="question-card__actions">
              <button className="question-card__submit" disabled={busy || !allAnswered}
                onClick={() => void submit()}>
                提交
              </button>
            </div>
          ) : (
            allAnswered && !busy && (
              <div className="question-card__actions">
                <button className="question-card__submit" disabled={busy} onClick={() => void submit()}>
                  全部已选，提交
                </button>
              </div>
            )
          )}
          {expired && !question.waiting && (
            <div className="question-card__expired">
              这道题已过期，AI 已不再等待。选好后点提交，你的选择会作为一条普通聊天消息发给 AI。
            </div>
          )}
          {question.waiting && (
            <div className="question-card__hint">AI 这一轮还没结束，等它结束后会自动把你的选择发出去…</div>
          )}
          {busy && <div className="question-card__hint">已提交，Agent 继续处理中…</div>}
          {error && <div className="question-card__hint question-card__error">{error}</div>}
        </div>
      </div>
    </div>
  );
}

/** 流式中的 ask_user 问答题列表（一次性卡片，答完即从当前流移除）。 */
export default function QuestionCards({ questions, onDone, onLateAnswer, nowMs }: {
  questions: ChatQuestion[]; onDone?: (questionId: string) => void; onLateAnswer?: LateAnswer; nowMs?: number;
}) {
  const [answered, setAnswered] = useState<Record<string, boolean>>({});
  const visible = useMemo(
    () => questions.filter((q) => !answered[q.id]),
    [questions, answered],
  );
  if (!visible.length) return null;
  return (
    <>
      {visible.map((q) => (
        <QuestionCard key={q.id} question={q} onLateAnswer={onLateAnswer} nowMs={nowMs} onAnswered={() => {
          setAnswered((a) => ({ ...a, [q.id]: true }));
          onDone?.(q.id);   // 通知 App：此题已答，重放/恢复不再出现
        }} />
      ))}
    </>
  );
}
