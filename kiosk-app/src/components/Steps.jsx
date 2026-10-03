import React from 'react';

const STEPS = ['Review order', 'Pay', 'Enjoy'];

// where the customer is in checkout; `current` is the index into STEPS
function Steps({ current }) {
    return (
        <ol className="steps">
            {STEPS.map((label, i) => (
                <li key={label} className={i === current ? 'current' : i < current ? 'done' : ''}>
                    <span className="step-dot">{i < current ? '✓' : i + 1}</span>
                    {label}
                </li>
            ))}
        </ol>
    );
}

export default Steps;
