// Resets the kiosk when a customer walks away: after IDLE_MS with no touches a "Still there?"
// prompt counts down for PROMPT_MS, then the cart is cleared, any unpaid order is cancelled and
// the kiosk goes back to the menu.
import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { IDLE_MS, IdleContext, PROMPT_MS } from './idleContext';
import './IdleProvider.css';

// what counts as someone using the kiosk (a keyboard-wedge QR scanner types, so keys count too)
const ACTIVITY_EVENTS = ['pointerdown', 'touchstart', 'keydown'];

// `hasSession` says whether there is anything to reset. With an empty cart on the menu there isn't,
// so the prompt isn't shown to an empty room over and over.
function IdleProvider({ hasSession, onReset, children }) {
    const navigate = useNavigate();
    const { pathname } = useLocation();
    const [pauses, setPauses] = useState(0);
    const [promptLeft, setPromptLeft] = useState(null); // seconds left on the prompt, null when hidden
    const [activity, setActivity] = useState(0); // bumped on every touch to restart the clock
    const cleanups = useRef(new Set());

    const pause = useCallback(() => {
        setPauses((n) => n + 1);
        setPromptLeft(null);
        return () => setPauses((n) => n - 1);
    }, []);

    const addCleanup = useCallback((cleanup) => {
        cleanups.current.add(cleanup);
        return () => cleanups.current.delete(cleanup);
    }, []);

    const active = pauses === 0 && (hasSession || pathname !== '/');
    const prompting = active && promptLeft !== null;

    useEffect(() => {
        const touched = () => { setActivity((n) => n + 1); setPromptLeft(null); };
        ACTIVITY_EVENTS.forEach((e) => window.addEventListener(e, touched, true));
        return () => ACTIVITY_EVENTS.forEach((e) => window.removeEventListener(e, touched, true));
    }, []);

    // the quiet period before the prompt; restarts on every touch, page change and end of a pause
    useEffect(() => {
        if (!active || prompting) return undefined;
        const timer = setTimeout(() => setPromptLeft(Math.round(PROMPT_MS / 1000)), IDLE_MS);
        return () => clearTimeout(timer);
    }, [active, prompting, activity, pathname]);

    // the prompt's countdown, then the reset
    useEffect(() => {
        if (!prompting) return undefined;
        const tick = setInterval(() => setPromptLeft((left) => (left === null ? null : Math.max(0, left - 1))), 1000);
        const reset = setTimeout(() => {
            cleanups.current.forEach((cleanup) => cleanup());
            onReset();
            setPromptLeft(null);
            navigate('/');
        }, PROMPT_MS);
        return () => { clearInterval(tick); clearTimeout(reset); };
    }, [prompting, onReset, navigate]);

    return (
        <IdleContext.Provider value={{ pause, addCleanup }}>
            {children}
            {prompting && (
                <div className="idle-overlay" role="alertdialog" aria-labelledby="idle-title">
                    <div className="idle-dialog">
                        <h2 id="idle-title">Still there?</h2>
                        <p>Touch the screen to keep going. Starting over in {promptLeft}…</p>
                        <button className="idle-continue">I'm still here</button>
                    </div>
                </div>
            )}
        </IdleContext.Provider>
    );
}

export default IdleProvider;
