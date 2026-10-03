import React, { useId } from 'react';
import { drinkLook } from '../drinkLook';
import './DrinkArt.css';

// A drawn cup for the drink (tinted by drinkLook), or its photo when it has one
function DrinkArt({ drink, size = 'md' }) {
    const gradientId = useId();
    if (drink?.image_url) {
        return (
            <div className={`drink-art drink-art-${size}`}>
                <img src={drink.image_url} alt="" />
            </div>
        );
    }
    const look = drinkLook(drink);
    // tapered cup: 120 wide at the rim, 92 at the base
    return (
        <div className={`drink-art drink-art-${size}`} style={{ background: look.backdrop }} aria-hidden="true">
            <svg viewBox="0 0 200 220" role="presentation">
                <defs>
                    <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0" stopColor={look.top} />
                        <stop offset="0.35" stopColor={look.liquid} />
                        <stop offset="1" stopColor={look.base ?? look.liquid} />
                    </linearGradient>
                </defs>
                <ellipse cx="100" cy="206" rx="54" ry="6" fill="rgba(43,35,32,0.08)" />
                {/* straw */}
                <rect x="112" y="10" width="11" height="80" rx="5.5" transform="rotate(12 117 50)" fill="#2b2320" opacity="0.85" />
                {/* liquid */}
                <path d="M46 62 H154 L141 196 Q140 202 134 202 H66 Q60 202 59 196 Z" fill={`url(#${gradientId})`} />
                {look.pearls && [...Array(14)].map((_, i) => (
                    <circle key={i} cx={70 + (i % 7) * 10 + (i > 6 ? 5 : 0)} cy={i > 6 ? 183 : 193} r="5" fill="#3a2418" />
                ))}
                {look.seeds && [...Array(9)].map((_, i) => (
                    <circle key={i} cx={68 + i * 8} cy={110 + ((i * 17) % 60)} r="2.4" fill="#4b2e14" opacity="0.6" />
                ))}
                {look.slice && <circle cx="84" cy="118" r="17" fill="#f6e48b" stroke="#fff6c9" strokeWidth="3" opacity="0.9" />}
                {/* glass and rim */}
                <path d="M40 48 H160 L144 198 Q143 206 135 206 H65 Q57 206 56 198 Z"
                    fill="rgba(255,255,255,0.22)" stroke="rgba(43,35,32,0.18)" strokeWidth="2" />
                <rect x="34" y="42" width="132" height="12" rx="6" fill="#ffffff" stroke="rgba(43,35,32,0.15)" strokeWidth="2" />
                <path d="M58 70 L66 186" stroke="rgba(255,255,255,0.55)" strokeWidth="6" strokeLinecap="round" />
            </svg>
        </div>
    );
}

export default DrinkArt;
