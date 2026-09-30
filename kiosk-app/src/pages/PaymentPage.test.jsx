// @vitest-environment jsdom
import { act, cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import IdleProvider from '../IdleProvider';
import { IDLE_MS, PROMPT_MS } from '../idleContext';
import PaymentPage from './PaymentPage';
import * as api from '../api';

vi.mock('../api', () => ({
    cancelOrder: vi.fn(() => Promise.resolve({ status: 'CANCELLED' })),
    fetchOrderStatus: vi.fn(() => Promise.resolve({ status: 'PENDING' })),
    fetchPaynowQr: vi.fn(() => new Promise(() => {})),
}));

const wait = (ms) => act(() => { vi.advanceTimersByTime(ms); });

describe('payment screen idle timeout', () => {
    beforeEach(() => { vi.useFakeTimers(); });
    afterEach(() => { cleanup(); vi.useRealTimers(); vi.clearAllMocks(); });

    it('cancels the unpaid order with its order_token and goes back to the menu', () => {
        render(
            <MemoryRouter initialEntries={[{ pathname: '/payment/42', state: { orderToken: 'tok' } }]}>
                <IdleProvider hasSession={false} onReset={() => {}}>
                    <Routes>
                        <Route path="/" element={<p>the menu</p>} />
                        <Route path="/payment/:orderId" element={<PaymentPage clearCart={() => {}} />} />
                    </Routes>
                </IdleProvider>
            </MemoryRouter>,
        );
        wait(IDLE_MS);
        wait(PROMPT_MS);
        expect(api.cancelOrder).toHaveBeenCalledWith('42', 'tok');
        expect(screen.getByText('the menu')).toBeTruthy();
    });
});
