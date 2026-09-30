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
    fetchPaynowQr: vi.fn(),
}));

const wait = (ms) => act(() => { vi.advanceTimersByTime(ms); });

describe('payment screen idle timeout', () => {
    beforeEach(() => { vi.useFakeTimers(); });
    afterEach(() => { cleanup(); vi.useRealTimers(); vi.clearAllMocks(); });

    const renderPayment = () => render(
            <MemoryRouter initialEntries={[{ pathname: '/payment/42', state: { orderToken: 'tok' } }]}>
                <IdleProvider hasSession={false} onReset={() => {}}>
                    <Routes>
                        <Route path="/" element={<p>the menu</p>} />
                        <Route path="/payment/:orderId" element={<PaymentPage clearCart={() => {}} />} />
                    </Routes>
                </IdleProvider>
            </MemoryRouter>,
        );

    it('does not time out while the QR code is up waiting for payment', async () => {
        api.fetchPaynowQr.mockResolvedValue({ qr_code: 'data:,', amount: '4.50', reference: 'R1',
            expires_at: new Date(Date.now() + 600_000).toISOString() });
        renderPayment();
        await act(async () => {});
        wait(IDLE_MS * 3);
        expect(screen.queryByText('Still there?')).toBeNull();
        expect(api.cancelOrder).not.toHaveBeenCalled();
    });

    it('cancels the unpaid order with its order_token if it times out without a QR code', async () => {
        api.fetchPaynowQr.mockRejectedValue(new Error('PayNow is down'));
        renderPayment();
        await act(async () => {});
        wait(IDLE_MS);
        wait(PROMPT_MS);
        expect(api.cancelOrder).toHaveBeenCalledWith('42', 'tok');
        expect(screen.getByText('the menu')).toBeTruthy();
    });
});
