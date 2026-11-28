// SPDX-License-Identifier: Apache-2.0
// "You decide" (the guardian concept's page, founder pick 2026-11-28): the approval rule in one
// practice request. Optional, simulated, and it calls no API: nothing real moves (D-027: AI never
// actuates without a human approval). Hold to approve is used only because this practice action
// moves something; installs and settings get a normal button (founder pick 2026-11-21).
import { useEffect, useId, useRef } from 'react';
import { HoldToApprove } from '../../components/HoldToApprove';
import { StatusPill } from '../../components/StatusPill';
import { ShellIcon } from '../icons';
import type { PracticeAnswer } from '../firstRun';

export function DecideStep({ answer, onAnswer }: { answer: PracticeAnswer; onAnswer: (a: PracticeAnswer) => void }) {
  const result = useRef<HTMLParagraphElement>(null);
  const title = useId();
  const answered = useRef(answer !== 'none');
  useEffect(() => {
    // After an answer, focus goes to the "Practice done" row (HANDBACK: focus is kept when the card redraws).
    if (answer !== 'none' && !answered.current) result.current?.focus();
    answered.current = answer !== 'none';
  }, [answer]);

  return (
    <>
      <p className="oms-practice-tag"><StatusPill tone="neutral" label="Practice · simulated · nothing real moves" dot={false} /></p>
      <section className="oms-practice" aria-labelledby={title}>
        <div className="oms-practice-who">
          <span className="oms-practice-av" aria-hidden="true"><ShellIcon name="agent" size={18} /></span>
          <div>
            <h3 id={title} className="oms-practice-name">An AI agent asks</h3>
            <p className="om-hint">An example agent. Agents can read and ask; they cannot act.</p>
          </div>
        </div>
        <p className="oms-practice-ask">It is 31.8 °C in the practice greenhouse, over your 30 °C limit. Open the vent from 15 % to <strong>40 %</strong> for 45 minutes?</p>
        <dl className="oms-practice-plan">
          <div><dt>Goes back</dt><dd>to 15 % by itself after 45 minutes</dd></div>
          <div><dt>Stop</dt><dd>one tap at any time, no hold</dd></div>
          <div><dt>If nobody answers</dt><dd>nothing moves</dd></div>
        </dl>
        {answer === 'none' ? (
          <div className="oms-practice-actions">
            <HoldToApprove label="Hold to approve the practice request" onApprove={() => onAnswer('approved')} />
            <button type="button" className="om-btn om-btn-secondary" onClick={() => onAnswer('denied')}>Say no</button>
          </div>
        ) : (
          <p ref={result} tabIndex={-1} className="oms-practice-done" role="status">
            <ShellIcon name="check" size={16} /> Practice done: {answer === 'approved' ? 'you approved it. In real life the vent would open now, and go back by itself.' : 'you said no. Nothing moved.'}
            {' '}<button type="button" className="oms-linkbtn" onClick={() => onAnswer('none')}>Try again</button>
          </p>
        )}
      </section>
      <ul className="oms-facts-list">
        <li><ShellIcon name="approvals" size={16} /> You hold only when something moves or cannot be undone. Installs and settings get a normal button.</li>
        <li><ShellIcon name="info" size={16} /> Cannot hold? Choose “Use confirmation instead”: tap, wait two seconds, then confirm.</li>
        <li><ShellIcon name="lock" size={16} /> This practice is optional. Continue moves on without answering.</li>
      </ul>
    </>
  );
}
