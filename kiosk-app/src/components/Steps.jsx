import React from 'react';
import { useT } from '../i18n';

const STEPS = ['steps.review', 'steps.pay', 'steps.enjoy'];

// where the customer is in checkout; `current` is the index into STEPS
function Steps({ current }) {
    const t = useT();
    return (
        <ol className="steps">
            {STEPS.map((key, i) => (
                <li key={key} aria-current={i === current ? 'step' : undefined}
                    className={i === current ? 'current' : i < current ? 'done' : ''}>
                    <span className="step-dot" aria-hidden="true">{i < current ? '✓' : i + 1}</span>
                    {t(key)}
                </li>
            ))}
        </ol>
    );
}

export default Steps;
