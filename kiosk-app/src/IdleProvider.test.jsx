// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import IdleProvider from './IdleProvider';
import { IDLE_MS, PROMPT_MS, useIdleCleanup, useIdlePause } from './idleContext';

function Page({ paused = false, onCleanup }) {
    useIdlePause(paused);
    useIdleCleanup(onCleanup);
    return <p>some page</p>;
}

function renderKiosk({ path = '/cart', hasSession = true, paused = false } = {}) {
    const onReset = vi.fn();
    const onCleanup = vi.fn();
    render(
        <MemoryRouter initialEntries={[path]}>
            <IdleProvider hasSession={hasSession} onReset={onReset}>
                <Routes>
                    <Route path="/" element={<p>the menu</p>} />
                    <Route path="*" element={<Page paused={paused} onCleanup={onCleanup} />} />
                </Routes>
            </IdleProvider>
        </MemoryRouter>,
    );
    return { onReset, onCleanup };
}

const wait = (ms) => act(() => { vi.advanceTimersByTime(ms); });

describe('kiosk idle timeout', () => {
    beforeEach(() => { vi.useFakeTimers(); });
    afterEach(() => { cleanup(); vi.useRealTimers(); });

    it('waits 60 seconds by default', () => {
        expect(IDLE_MS).toBe(60_000);
        expect(PROMPT_MS).toBe(10_000);
    });

    it('asks "Still there?" after the idle time, then resets and goes back to the menu', () => {
        const { onReset, onCleanup } = renderKiosk();
        wait(IDLE_MS - 1);
        expect(screen.queryByText('Still there?')).toBeNull();
        wait(1);
        expect(screen.getByText('Still there?')).toBeTruthy();
        expect(screen.getByText(/Starting over in 10/)).toBeTruthy();

        wait(PROMPT_MS - 1000);
        expect(onReset).not.toHaveBeenCalled();
        wait(1000);
        expect(onCleanup).toHaveBeenCalledTimes(1);
        expect(onReset).toHaveBeenCalledTimes(1);
        expect(screen.getByText('the menu')).toBeTruthy();
        expect(screen.queryByText('Still there?')).toBeNull();
    });

    it('a touch restarts the clock', () => {
        const { onReset } = renderKiosk();
        wait(IDLE_MS - 1000);
        fireEvent.pointerDown(window);
        wait(IDLE_MS - 1000);
        expect(screen.queryByText('Still there?')).toBeNull();
        wait(1000);
        expect(screen.getByText('Still there?')).toBeTruthy();
        expect(onReset).not.toHaveBeenCalled();
    });

    it('a touch on the prompt keeps the order going', () => {
        const { onReset, onCleanup } = renderKiosk();
        wait(IDLE_MS + 5000);
        fireEvent.pointerDown(screen.getByText("I'm still here"));
        expect(screen.queryByText('Still there?')).toBeNull();
        wait(PROMPT_MS);
        expect(onReset).not.toHaveBeenCalled();
        expect(onCleanup).not.toHaveBeenCalled();
        expect(screen.getByText('some page')).toBeTruthy();
    });

    it('scanner typing counts as activity', () => {
        renderKiosk();
        wait(IDLE_MS - 1000);
        fireEvent.keyDown(window, { key: '1' });
        wait(IDLE_MS - 1000);
        expect(screen.queryByText('Still there?')).toBeNull();
    });

    it('never fires while a page holds it off', () => {
        const { onReset } = renderKiosk({ path: '/collect', paused: true });
        wait(IDLE_MS * 5);
        expect(screen.queryByText('Still there?')).toBeNull();
        expect(onReset).not.toHaveBeenCalled();
    });

    it('stays quiet on the menu when there is nothing to reset', () => {
        renderKiosk({ path: '/', hasSession: false });
        wait(IDLE_MS * 2);
        expect(screen.queryByText('Still there?')).toBeNull();
    });

    it('still resets on the menu when the cart has drinks in it', () => {
        const { onReset } = renderKiosk({ path: '/', hasSession: true });
        wait(IDLE_MS);
        wait(PROMPT_MS);
        expect(onReset).toHaveBeenCalledTimes(1);
    });
});
