import React, { useEffect, useRef, useState } from 'react';
import { collectOrder } from '../api';
import './CollectPage.css';

const PIN_LENGTH = 6;
// how long a result stays on screen before the page is ready for the next customer
const RESULT_MS = 8000;

// what each backend answer means for the customer at the machine
function describeFailure(err) {
    if (err.status === 429) {
        return { tone: 'warn', title: 'Too many tries', text: 'Please wait a minute, then try again.' };
    }
    if (err.data?.reason === 'not_paid') {
        return { tone: 'warn', title: 'Not paid yet', text: 'This order is still waiting for payment. Finish paying in the app, then try again.' };
    }
    if (err.data?.reason === 'already_collected') {
        return { tone: 'warn', title: 'Already collected', text: 'This order was collected earlier. Please ask staff if that wasn\'t you.' };
    }
    if (err.data?.reason === 'not_found') {
        return { tone: 'error', title: 'Code not recognised', text: 'Check the PIN in your app. Orders can only be collected at the machine they were ordered for.' };
    }
    return { tone: 'error', title: 'Something went wrong', text: 'Please try again, or ask staff for help.' };
}

function CollectPage() {
    const [pin, setPin] = useState('');
    const [busy, setBusy] = useState(false);
    const [result, setResult] = useState(null);
    const scanInput = useRef(null);

    const submit = async (code) => {
        if (!code || busy) return;
        setBusy(true);
        try {
            const order = await collectOrder(code);
            setResult({
                tone: 'ok',
                title: 'Order collected',
                text: `Order #${order.id}, ${order.items.length} ${order.items.length === 1 ? 'drink' : 'drinks'}. Enjoy!`,
            });
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
                    <h1>{result.title}</h1>
                    <p>{result.text}</p>
                    <button className="collect-done" onClick={() => setResult(null)}>Done</button>
                </div>
            </div>
        );
    }

    return (
        <div className="collect-page">
            <h1>Collect your order</h1>
            <p className="collect-hint">Scan the pickup QR code from your app, or type your 6-digit PIN.</p>

            <form className="collect-scan" onSubmit={(e) => {
                e.preventDefault();
                submit(e.target.elements.code.value.trim());
                e.target.reset();
            }}>
                {/* receives the scanner's typing; invisible but focused */}
                <input ref={scanInput} name="code" aria-label="Scanned pickup code" autoComplete="off"
                    onBlur={() => setTimeout(() => scanInput.current?.focus(), 100)} />
            </form>

            <div className="collect-pin" aria-label="PIN entered">
                {Array.from({ length: PIN_LENGTH }, (_, i) => (
                    <span key={i} className={i < pin.length ? 'filled' : ''}>{pin[i] ?? ''}</span>
                ))}
            </div>

            <div className="collect-keypad">
                {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((d) => (
                    <button key={d} onClick={() => press(d)} disabled={busy}>{d}</button>
                ))}
                <button onClick={() => setPin(pin.slice(0, -1))} disabled={busy || !pin}>⌫</button>
                <button onClick={() => press('0')} disabled={busy}>0</button>
                <button onClick={() => setPin('')} disabled={busy || !pin}>Clear</button>
            </div>

            {busy && <p className="collect-hint">Checking…</p>}
        </div>
    );
}

export default CollectPage;
