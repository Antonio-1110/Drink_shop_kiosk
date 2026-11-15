import React, { useEffect, useRef, useState } from 'react';
import { collectOrder } from '../api';
import { useIdlePause } from '../idleContext';
import { useT } from '../i18n';
import './CollectPage.css';

const PIN_LENGTH = 6;
// how long a result stays on screen before the page is ready for the next customer
const RESULT_MS = 8000;

// what each backend answer means for the customer at the machine
const FAILURES = {
    not_paid: ['warn', 'notPaid'],
    cancelled: ['warn', 'cancelled'],
    // the machine's own steps (from the backend's drink-making statuses)
    preparing: ['warn', 'preparing'],
    failed: ['error', 'failed'],
    refunding: ['error', 'failed', 'refunding'],
    already_collected: ['warn', 'already'],
    not_found: ['error', 'notFound'],
};

function describeFailure(err) {
    if (err.status === 429) return { tone: 'warn', title: 'collect.tooManyTitle', text: 'collect.tooManyText' };
    const [tone, name, textName = name] = FAILURES[err.data?.reason] ?? ['error', 'error'];
    return { tone, title: `collect.${name}Title`, text: `collect.${textName}Text` };
}

function CollectPage() {
    const t = useT();
    const [pin, setPin] = useState('');
    const [busy, setBusy] = useState(false);
    const [result, setResult] = useState(null);
    const scanInput = useRef(null);

    // don't reset the kiosk under a customer who is waiting for, or reading, their result
    useIdlePause(busy || result !== null);

    const submit = async (code) => {
        if (!code || busy) return;
        setBusy(true);
        try {
            const order = await collectOrder(code);
            const drinks = t('cart.drinks', { count: order.items.length });
            setResult({ tone: 'ok', title: 'collect.okTitle', text: 'collect.okText', vars: { id: order.id, drinks } });
        } catch (err) {
            setResult(describeFailure(err));
        } finally {
            setBusy(false);
            setPin('');
        }
    };

    // clear the result after a while, ready for the next customer
    useEffect(() => {
        if (!result) return undefined;
        const timer = setTimeout(() => setResult(null), RESULT_MS);
        return () => clearTimeout(timer);
    }, [result]);

    // a QR scanner on the machine types the code and presses Enter, so keep an input focused for it
    useEffect(() => {
        if (!result) scanInput.current?.focus();
    }, [result, busy]);

    const press = (digit) => {
        const next = (pin + digit).slice(0, PIN_LENGTH);
        setPin(next);
        if (next.length === PIN_LENGTH) submit(next);
    };

    if (result) {
        return (
            <div className="collect-page">
                <div className={`collect-result collect-${result.tone}`} role="status">
                    <div className="collect-icon" aria-hidden="true">
                        {result.tone === 'ok' ? '✓' : result.tone === 'warn' ? '!' : '✕'}
                    </div>
                    <h1>{t(result.title)}</h1>
                    <p>{t(result.text, result.vars)}</p>
                    <button className="btn btn-primary collect-done" onClick={() => setResult(null)}>{t('collect.done')}</button>
                </div>
            </div>
        );
    }

    return (
        <div className="collect-page">
            <h1>{t('collect.title')}</h1>
            <p className="collect-hint">{t('collect.hint')}</p>

            <form className="collect-scan" onSubmit={(e) => {
                e.preventDefault();
                submit(e.target.elements.code.value.trim());
                e.target.reset();
            }}>
                {/* receives the scanner's typing; invisible but focused */}
                <input ref={scanInput} name="code" aria-label={t('collect.scanned')} autoComplete="off"
                    onBlur={() => setTimeout(() => scanInput.current?.focus(), 100)} />
            </form>

            <div className="collect-pin" aria-label={t('collect.pin')}>
                {Array.from({ length: PIN_LENGTH }, (_, i) => (
                    <span key={i} className={i < pin.length ? 'filled' : ''}>{pin[i] ?? ''}</span>
                ))}
            </div>

            <div className="collect-keypad">
                {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((d) => (
                    <button key={d} onClick={() => press(d)} disabled={busy}>{d}</button>
                ))}
                <button onClick={() => setPin(pin.slice(0, -1))} disabled={busy || !pin} aria-label={t('collect.delete')}>⌫</button>
                <button onClick={() => press('0')} disabled={busy}>0</button>
                <button onClick={() => setPin('')} disabled={busy || !pin}>{t('collect.clear')}</button>
            </div>

            {busy && <p className="collect-hint" role="status">{t('collect.checking')}</p>}
        </div>
    );
}

export default CollectPage;
