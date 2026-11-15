import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { fetchDesignerOptions } from '../api';
import {
    categories, decodeDesign, designName, designNutrition, designPrice, designToCartItem,
    ingredientPrice, missingChoice, newDesign, recipe, togglePick,
} from '../designer';
import { LEVELS } from '../menu';
import { GRADE_COLORS } from '../nutrigrade';
import { useT } from '../i18n';
import './DesignerPage.css';

function Cup({ lines, ice }) {
    const liquids = lines.filter((line) => line.unit === 'mL');
    const total = liquids.reduce((sum, line) => sum + line.amount, 0) || 1;
    const toppings = lines.filter((line) => line.unit === 'g');
    return (
        <div className="cup" aria-hidden="true">
            <div className="cup-liquid">
                {liquids.map((line) => (
                    <div key={line.code} className="cup-layer" style={{ flexGrow: line.amount / total, background: line.color }} />
                ))}
            </div>
            {ice > 0 && <div className="cup-ice">{'❄'.repeat(ice)}</div>}
            <div className="cup-toppings">
                {toppings.flatMap((line) => Array.from({ length: Math.max(2, Math.round(12 / toppings.length)) }, (_, j) => (
                    <span key={`${line.code}-${j}`} className="topping-dot" style={{ background: line.color }} />
                )))}
            </div>
        </div>
    );
}

function LevelRow({ label, value, onChange }) {
    return (
        <div className="designer-group" role="group" aria-label={label}>
            <h2>{label}</h2>
            <div className="option-row">
                {LEVELS.map((level) => (
                    <button key={level.value} aria-pressed={value === level.value} aria-label={`${label} ${level.label}`}
                        className={`option-tile small ${value === level.value ? 'selected' : ''}`}
                        onClick={() => onChange(level.value)}>
                        {level.label}
                    </button>
                ))}
            </div>
        </div>
    );
}

// Loads a drink code from the mobile app. A USB or built-in QR reader types the code and presses
// Enter like a keyboard, so the page listens for that anywhere; the box is for typing one in.
function useScannedCode(onCode) {
    const buffer = useRef('');
    const latest = useRef(onCode);
    useEffect(() => { latest.current = onCode; });
    useEffect(() => {
        const onKey = (e) => {
            if (e.target.tagName === 'INPUT') return;
            if (e.key === 'Enter') {
                if (buffer.current.toUpperCase().startsWith('DD1:')) latest.current(buffer.current);
                buffer.current = '';
            } else if (e.key.length === 1) {
                buffer.current = (buffer.current + e.key).slice(-200);
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, []);
}

function DesignerPage({ addCustomToCart }) {
    const t = useT();
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const [options, setOptions] = useState(null);
    const [design, setDesign] = useState(null);
    const [loadError, setLoadError] = useState(null);
    const [codeText, setCodeText] = useState('');
    const [codeMessage, setCodeMessage] = useState(null);
    const [reload, setReload] = useState(0);

    const loadCode = (opts, text) => {
        const result = decodeDesign(opts, text);
        if (result.design) {
            setDesign(result.design);
            setCodeMessage({ ok: true, text: t('designer.loaded') });
            setCodeText('');
        } else {
            setCodeMessage({ ok: false, text: result.error });
        }
    };

    useEffect(() => {
        fetchDesignerOptions()
            .then((data) => {
                setOptions(data);
                setDesign(newDesign(data));
                // a camera app that opens the QR's link lands here with ?code=
                const code = searchParams.get('code');
                if (code) loadCode(data, code);
            })
            .catch((err) => setLoadError(err.message));
    }, [searchParams, reload]); // eslint-disable-line react-hooks/exhaustive-deps

    useScannedCode((text) => options && loadCode(options, text));

    if (loadError) {
        return (
            <div className="designer-error" role="alert">
                <p className="error-banner">{t('designer.loadError')}</p>
                <button className="btn btn-ghost" onClick={() => { setLoadError(null); setReload((n) => n + 1); }}>{t('pay.retry')}</button>
            </div>
        );
    }
    if (!options) return <p className="empty-note" role="status">{t('designer.loading')}</p>;

    const lines = recipe(options, design);
    const nutrition = designNutrition(options, design);
    const missing = missingChoice(options, design);
    const add = () => {
        addCustomToCart(designToCartItem(options, design));
        navigate('/cart');
    };

    return (
        <div className="designer-page">
            <div className="designer-options">
                <header className="page-header">
                    <h1>{t('designer.title')}</h1>
                    <p>{t('designer.sub')}</p>
                </header>

                <form className="code-box" onSubmit={(e) => { e.preventDefault(); loadCode(options, codeText); }}>
                    <span>{t('designer.codeHint')}</span>
                    <input value={codeText} onChange={(e) => setCodeText(e.target.value)} placeholder="DD1:…" aria-label={t('designer.codeHint')} />
                    <button type="submit" className="btn btn-ghost" disabled={!codeText.trim()}>{t('designer.load')}</button>
                </form>
                {codeMessage && <p role="status" className={codeMessage.ok ? 'notice-ok' : 'error-banner'}>{codeMessage.text}</p>}

                <div className="designer-group">
                    <h2>{t('designer.cupSize')}</h2>
                    <div className="option-row">
                        {options.sizes.map((size) => (
                            <button key={size.value} aria-pressed={design.size === size.value} className={`option-tile ${design.size === size.value ? 'selected' : ''}`}
                                onClick={() => setDesign({ ...design, size: size.value })}>
                                <strong>{size.label}</strong>
                                <span className="option-price">${Number(options.pricing.cup[size.value]).toFixed(2)}</span>
                            </button>
                        ))}
                    </div>
                </div>

                {categories(options).map((category) => (
                    <div key={category} className="designer-group">
                        <h2>{category}</h2>
                        <div className="option-row">
                            {options.ingredients.filter((i) => i.category === category).map((ingredient) => {
                                const selected = design.picks.includes(ingredient.code);
                                const soldOut = ingredient.available === false && !selected;
                                const price = ingredientPrice(options, ingredient);
                                return (
                                    <button key={ingredient.code} disabled={soldOut} aria-pressed={selected}
                                        className={`option-tile ${selected ? 'selected' : ''}`}
                                        onClick={() => setDesign(togglePick(options, design, ingredient.code))}>
                                        <span className="swatch" style={{ background: ingredient.color }} />
                                        <strong>{ingredient.name}</strong>
                                        <span className="option-price">{price ? `+$${price.toFixed(2)}` : t('designer.included')}</span>
                                        {soldOut && <span className="option-reason">{t('designer.soldOut')}</span>}
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                ))}

                <LevelRow label={t('drink.sugar')} value={design.sugar} onChange={(sugar) => setDesign({ ...design, sugar })} />
                <LevelRow label={t('drink.ice')} value={design.ice} onChange={(ice) => setDesign({ ...design, ice })} />
            </div>

            <aside className="designer-summary">
                <Cup lines={lines} ice={design.ice} />
                <h3>{design.picks.length ? designName(options, design) : t('designer.ownDrink')}</h3>
                {/* amounts change as ingredients are added, so show what actually goes in */}
                <ul className="recipe-lines">
                    {lines.map((line) => (
                        <li key={line.code}><span>{line.name}</span><span>{Math.round(line.amount)} {line.unit}</span></li>
                    ))}
                </ul>
                <div className="grade-row">
                    <span className="grade-badge" style={{ background: GRADE_COLORS[nutrition.grade] }}>
                        {nutrition.grade}
                    </span>
                    <span className="grade-detail">
                        Nutri-Grade<br />
                        {t('designer.per100', { sugar: nutrition.sugar.toFixed(1), fat: nutrition.satFat.toFixed(1) })}
                    </span>
                </div>
                <div className="designer-total price">${designPrice(options, design).toFixed(2)}</div>
                <button className="btn btn-primary btn-block" disabled={Boolean(missing)} onClick={add}>
                    {missing ? t('designer.chooseLiquid') : t('drink.add')}
                </button>
                <button className="btn-text" onClick={() => { setDesign(newDesign(options)); setCodeMessage(null); }}>
                    {t('designer.startOver')}
                </button>
            </aside>
        </div>
    );
}

export default DesignerPage;
