import React from 'react';
import { NavLink } from 'react-router-dom';
import { BRAND_NAME, CATEGORIES } from '../menu';
import { LANGUAGES, useLanguage, useT } from '../i18n';

// the brand mark until the shop has a logo: a single tea leaf
function LeafMark() {
    return (
        <svg viewBox="0 0 32 32" className="brand-mark" aria-hidden="true">
            <path d="M6 26C6 13 14 6 27 5c0 13-7 21-20 21z" fill="currentColor" />
            <path d="M7 25C12 19 17 14 23 10" stroke="var(--milk)" strokeWidth="1.6" fill="none" strokeLinecap="round" />
        </svg>
    );
}

// English / 中文, each written in its own language so a customer finds theirs at a glance
function LanguageSwitch() {
    const t = useT();
    const { lang, setLang } = useLanguage();
    return (
        <div className="lang-switch" role="group" aria-label={t('nav.language')}>
            {LANGUAGES.map(({ code, label }) => (
                <button key={code} lang={code} aria-pressed={lang === code}
                    className={lang === code ? 'selected' : ''} onClick={() => setLang(code)}>
                    {label}
                </button>
            ))}
        </div>
    );
}

function Sidebar() {
    const t = useT();
    const link = ({ isActive }) => `nav-link ${isActive ? 'active' : ''}`;
    return (
        <nav className="sidebar">
            <NavLink to="/" className="brand">
                <LeafMark />
                <span>{BRAND_NAME}</span>
            </NavLink>

            <div className="eyebrow nav-heading">{t('nav.menu')}</div>
            <NavLink to="/" end className={link}>{t('nav.all')}</NavLink>
            {CATEGORIES.map(({ path }) => (
                <NavLink key={path} to={`/${path}`} className={link}>{t(`cat.${path}`)}</NavLink>
            ))}

            <div className="nav-extras">
                <NavLink to="/designer" className={({ isActive }) => `nav-feature ${isActive ? 'active' : ''}`}>
                    <strong>{t('nav.design')}</strong>
                    <span>{t('nav.designHint')}</span>
                </NavLink>
                {/* for customers who ordered ahead in the app */}
                <NavLink to="/collect" className={link}>{t('nav.collect')}</NavLink>
                <LanguageSwitch />
            </div>
        </nav>
    );
}

export default Sidebar;
