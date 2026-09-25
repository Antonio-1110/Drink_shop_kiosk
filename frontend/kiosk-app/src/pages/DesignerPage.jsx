import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchDesignerOptions } from '../api';
import {
    blockedReason, cupLayers, findOption, designName, designNutrition, designPrice, designToCartItem,
    missingChoice, newDesign, toggleOption,
} from '../designer';
import { LEVELS } from '../menu';
import { GRADE_COLORS } from '../nutrigrade';
import './DesignerPage.css';

function Cup({ options, design }) {
    const layers = cupLayers(options, design);
    const total = layers.reduce((sum, layer) => sum + layer.ml, 0) || 1;
    const toppingColors = (design.selections.topping ?? []).map((id) => findOption(options, id).color);
    return (
        <div className="cup" aria-hidden="true">
            <div className="cup-liquid">
                {layers.map((layer) => (
                    <div key={layer.id} className="cup-layer" style={{ flexGrow: layer.ml / total, background: layer.color }} />
                ))}
            </div>
            {design.ice > 0 && <div className="cup-ice">{'❄'.repeat(design.ice)}</div>}
            <div className="cup-toppings">
                {toppingColors.flatMap((color, i) => Array.from({ length: 6 }, (_, j) => (
                    <span key={`${i}-${j}`} className="topping-dot" style={{ background: color }} />
                )))}
            </div>
        </div>
    );
}

function LevelRow({ label, value, onChange }) {
    return (
        <div className="designer-group">
            <h2>{label}</h2>
            <div className="option-row">
                {LEVELS.map((level) => (
                    <button key={level.value} className={`option-tile small ${value === level.value ? 'selected' : ''}`}
                        onClick={() => onChange(level.value)}>
                        {level.label}
                    </button>
                ))}
            </div>
        </div>
    );
}

function DesignerPage({ addCustomToCart }) {
    const navigate = useNavigate();
    const [options, setOptions] = useState(null);
    const [design, setDesign] = useState(null);
    const [loadError, setLoadError] = useState(null);

    useEffect(() => {
        fetchDesignerOptions()
            .then((data) => { setOptions(data); setDesign(newDesign(data)); })
            .catch((err) => setLoadError(err.message));
    }, []);

    if (loadError) return <p className="error-banner">Could not load the drink designer: {loadError}</p>;
    if (!options) return <p>Loading…</p>;

    const nutrition = designNutrition(options, design);
    const missing = missingChoice(options, design);
    const add = () => {
        addCustomToCart(designToCartItem(options, design));
        navigate('/cart');
    };

    return (
        <div className="designer-page">
            <div className="designer-options">
                <h1>Design your own drink</h1>
                {options.stub && <p className="stub-note">Demo options: prices and ingredients aren't final yet.</p>}

                <div className="designer-group">
                    <h2>Cup size</h2>
                    <div className="option-row">
                        {options.sizes.map((size) => (
                            <button key={size.value} className={`option-tile ${design.size === size.value ? 'selected' : ''}`}
                                onClick={() => setDesign({ ...design, size: size.value })}>
                                <strong>{size.label}</strong>
                                <span className="option-price">${Number(size.base_price).toFixed(2)}</span>
                            </button>
                        ))}
                    </div>
                </div>

                {options.groups.map((group) => (
                    <div key={group.key} className="designer-group">
                        <h2>{group.label} <span className="group-hint">{group.hint}</span></h2>
                        <div className="option-row">
                            {group.options.map((option) => {
                                const selected = design.selections[group.key].includes(option.id);
                                const reason = blockedReason(options, design, group, option.id);
                                return (
                                    <button key={option.id} disabled={Boolean(reason)}
                                        className={`option-tile ${selected ? 'selected' : ''}`}
                                        onClick={() => setDesign(toggleOption(options, design, group, option.id))}>
                                        <span className="swatch" style={{ background: option.color }} />
                                        <strong>{option.name}</strong>
                                        <span className="option-price">
                                            {Number(option.price) ? `+$${Number(option.price).toFixed(2)}` : 'Included'}
                                        </span>
                                        {reason && <span className="option-reason">{reason}</span>}
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                ))}

                <LevelRow label="Sugar" value={design.sugar} onChange={(sugar) => setDesign({ ...design, sugar })} />
                <LevelRow label="Ice" value={design.ice} onChange={(ice) => setDesign({ ...design, ice })} />
            </div>

            <aside className="designer-summary">
                <Cup options={options} design={design} />
                <h3>{designName(options, design)}</h3>
                <div className="grade-row">
                    <span className="grade-badge" style={{ background: GRADE_COLORS[nutrition.grade] }}>
                        {nutrition.grade}
                    </span>
                    <span className="grade-detail">
                        Nutri-Grade<br />
                        {nutrition.sugar.toFixed(1)} g sugar, {nutrition.satFat.toFixed(1)} g sat. fat per 100 mL
                    </span>
                </div>
                <div className="designer-total">${designPrice(options, design).toFixed(2)}</div>
                <button className="action-btn pay-btn" disabled={Boolean(missing)} onClick={add}>
                    {missing ?? 'Add to cart'}
                </button>
                <button className="link-btn" onClick={() => setDesign(newDesign(options))}>Start over</button>
            </aside>
        </div>
    );
}

export default DesignerPage;
