import React, { useCallback, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { cancelOrder, fetchOrderStatus, fetchPaynowQr } from '../api';
import Steps from '../components/Steps';
import { useIdleCleanup, useIdlePause } from '../idleContext';
import { useT } from '../i18n';
import './CartPage.css';

const POLL_MS = 3000;
// the countdown turns amber when this little time is left
const HURRY_MS = 60 * 1000;

function formatRemaining(ms) {
    const seconds = Math.max(0, Math.round(ms / 1000));
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

function PaymentPage({ clearCart }) {
    const t = useT();
    const { orderId } = useParams();
    const orderToken = useLocation().state?.orderToken;
    const navigate = useNavigate();
    const [qr, setQr] = useState(null);
    const [qrTry, setQrTry] = useState(0);
    const [orderStatus, setOrderStatus] = useState('PENDING');
    const [error, setError] = useState(null);
    const [now, setNow] = useState(() => Date.now());

    // the order is placed, so the cart is done with
    useEffect(() => { clearCart(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // the backend reuses the open payment, so trying again never makes a second one
    useEffect(() => {
        let cancelled = false;
        fetchPaynowQr(orderId, orderToken)
            .then((data) => { if (!cancelled) { setQr(data); setError(null); } })
            .catch((err) => { if (!cancelled) setError(err); });
        return () => { cancelled = true; };
    }, [orderId, orderToken, qrTry]);

    // the backend decides when the order is paid or has run out of time; ask it every few seconds
    useEffect(() => {
        if (orderStatus !== 'PENDING') return undefined;
        const timer = setInterval(() => {
            fetchOrderStatus(orderId, orderToken).then((data) => setOrderStatus(data.status)).catch(() => {});
        }, POLL_MS);
        return () => clearInterval(timer);
    }, [orderId, orderToken, orderStatus]);

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
            <div className="payment-page" role="status">
                <div className="result-mark muted" aria-hidden="true">×</div>
                <h1>{t('pay.cancelledTitle')}</h1>
                <p>{t('pay.cancelledText')}</p>
                <Link to="/" className="btn btn-primary">{t('pay.newOrder')}</Link>
            </div>
        );
    }

    if (orderStatus !== 'PENDING') {
        return (
            <div className="payment-page" role="status">
                <Steps current={2} />
                <div className="result-mark" aria-hidden="true">✓</div>
                <h1>{t('pay.thanks')}</h1>
                <p>{t('pay.paidText')}</p>
                <div className="order-number">
                    <span className="eyebrow">{t('pay.orderNumber')}</span>
                    <strong>{orderId}</strong>
                </div>
                <Link to="/" className="btn btn-ghost">{t('pay.newOrder')}</Link>
            </div>
        );
    }

    const remaining = qr ? new Date(qr.expires_at).getTime() - now : null;
    const hurry = remaining !== null && remaining < HURRY_MS;

    return (
        <div className="payment-page">
            <Steps current={1} />
            <h1>{t('pay.title')}</h1>
            <p>{t('pay.hint')}</p>
            {/* sandbox or a gateway's test keys: say so, so nobody thinks this is a real charge */}
            {qr?.test_mode && <p className="test-mode">{t('pay.testMode')}</p>}
            <div className="payment-card">
                {qr
                    ? <img className="paynow-qr" src={qr.qr_code} alt={t('pay.qrAlt')} />
                    : (
                        <div className="paynow-qr qr-placeholder" role={error ? 'alert' : 'status'}>
                            {error ? (
                                <>
                                    <span>{error.offline ? t('cart.offline') : t('pay.qrUnavailable')}</span>
                                    <button className="btn btn-ghost" onClick={() => setQrTry((n) => n + 1)}>{t('pay.retry')}</button>
                                </>
                            ) : t('pay.qrPreparing')}
                        </div>
                    )}
                {qr && (
                    <>
                        <div className="payment-amount price">${qr.amount}</div>
                        <div className="payment-meta">
                            <span>{t('pay.ref', { ref: qr.reference })}</span>
                            <span className={`countdown ${hurry ? 'hurry' : ''}`}>
                                {t('pay.left', { time: formatRemaining(remaining) })}
                            </span>
                        </div>
                        {/* said once, not every second, for screen readers */}
                        {hurry && <p className="hurry-note" role="alert">{t('pay.hurry')}</p>}
                    </>
                )}
            </div>
            {orderToken
                ? <button className="btn-text" onClick={cancel}>{t('pay.cancel')}</button>
                : <Link to="/" className="btn-text">{t('pay.newOrder')}</Link>}
        </div>
    );
}

export default PaymentPage;
