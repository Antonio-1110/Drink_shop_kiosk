import React, { useCallback, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { cancelOrder, fetchOrderStatus, fetchPaynowQr } from '../api';
import Steps from '../components/Steps';
import { useIdleCleanup, useIdlePause } from '../idleContext';
import './CartPage.css';

const POLL_MS = 3000;

function formatRemaining(ms) {
    const seconds = Math.max(0, Math.round(ms / 1000));
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

function PaymentPage({ clearCart }) {
    const { orderId } = useParams();
    const orderToken = useLocation().state?.orderToken;
    const navigate = useNavigate();
    const [qr, setQr] = useState(null);
    const [orderStatus, setOrderStatus] = useState('PENDING');
    const [error, setError] = useState(null);
    const [now, setNow] = useState(() => Date.now());

    // the order is placed, so the cart is done with
    useEffect(() => { clearCart(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

    useEffect(() => {
        fetchPaynowQr(orderId).then(setQr).catch((err) => setError(err.message));
    }, [orderId]);

    // the backend decides when the order is paid or has run out of time; ask it every few seconds
    useEffect(() => {
        if (orderStatus !== 'PENDING') return undefined;
        const timer = setInterval(() => {
            fetchOrderStatus(orderId).then((data) => setOrderStatus(data.status)).catch(() => {});
        }, POLL_MS);
        return () => clearInterval(timer);
    }, [orderId, orderStatus]);

    // a one-second tick for the countdown
    useEffect(() => {
        const tick = setInterval(() => setNow(Date.now()), 1000);
        return () => clearInterval(tick);
    }, []);

    const pending = orderStatus === 'PENDING';
    // someone paying looks at their phone, not the kiosk, so don't time out while the QR code is up
    // waiting for the payment; the payment window releases the ingredients if they walked away
    useIdlePause(pending && qr !== null);
    // if the timeout does fire with the order unpaid (e.g. the QR code never loaded), cancel it so
    // the ingredients go back on sale straight away
    const cancelIfUnpaid = useCallback(() => {
        if (pending && orderToken) cancelOrder(orderId, orderToken, 'idle_timeout').catch(() => {});
    }, [pending, orderId, orderToken]);
    useIdleCleanup(cancelIfUnpaid);

    const cancel = async () => {
        try {
            await cancelOrder(orderId, orderToken);
        } catch {
            // already paid or already cancelled; the status poll shows which
        }
        navigate('/');
    };

    if (orderStatus === 'CANCELLED') {
        return (
            <div className="payment-page">
                <div className="result-mark muted" aria-hidden="true">×</div>
                <h1>Order cancelled</h1>
                <p>The payment time ran out, so nothing was charged.</p>
                <Link to="/" className="btn btn-primary">Start a new order</Link>
            </div>
        );
    }

    if (orderStatus !== 'PENDING') {
        return (
            <div className="payment-page">
                <Steps current={2} />
                <div className="result-mark" aria-hidden="true">✓</div>
                <h1>Thank you</h1>
                <p>Payment received. Your drink is being made now.</p>
                <div className="order-number">
                    <span className="eyebrow">Order number</span>
                    <strong>{orderId}</strong>
                </div>
                <Link to="/" className="btn btn-ghost">Start a new order</Link>
            </div>
        );
    }

    const remaining = qr ? new Date(qr.expires_at).getTime() - now : null;

    return (
        <div className="payment-page">
            <Steps current={1} />
            <h1>Scan to pay</h1>
            <p>Open your banking app and scan with PayNow.</p>
            {error && <p className="error-banner">{error}</p>}
            <div className="payment-card">
                {qr
                    ? <img className="paynow-qr" src={qr.qr_code} alt="PayNow QR code" />
                    : <div className="paynow-qr qr-placeholder">{error ? 'QR code unavailable' : 'Preparing QR code…'}</div>}
                {qr && (
                    <>
                        <div className="payment-amount price">${qr.amount}</div>
                        <div className="payment-meta">
                            <span>Ref {qr.reference}</span>
                            <span className="countdown">{formatRemaining(remaining)} left</span>
                        </div>
                    </>
                )}
            </div>
            {orderToken
                ? <button className="btn-text" onClick={cancel}>Cancel order</button>
                : <Link to="/" className="btn-text">Start a new order</Link>}
        </div>
    );
}

export default PaymentPage;
