// Settings and hooks for the kiosk idle timeout (the provider itself is in IdleProvider.jsx).
import { createContext, useContext, useEffect } from 'react';

export const IDLE_MS = Number(import.meta.env.VITE_IDLE_TIMEOUT_SECONDS ?? 60) * 1000;
export const PROMPT_MS = 30 * 1000;

export const IdleContext = createContext(null);

// Pages call this to hold the timeout off while `paused` is true (e.g. a result being shown or a
// payment being confirmed). The idle clock starts again from zero when the pause ends.
export function useIdlePause(paused) {
    const { pause } = useContext(IdleContext);
    useEffect(() => (paused ? pause() : undefined), [paused, pause]);
}

// Pages call this with a function to run when the kiosk times out (e.g. cancel the unpaid order).
export function useIdleCleanup(cleanup) {
    const { addCleanup } = useContext(IdleContext);
    useEffect(() => addCleanup(cleanup), [cleanup, addCleanup]);
}
