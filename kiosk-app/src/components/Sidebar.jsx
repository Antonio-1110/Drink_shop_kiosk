import React from 'react';
import { NavLink } from 'react-router-dom';
import { BRAND_NAME, CATEGORIES } from '../menu';

// the brand mark until the shop has a logo: a single tea leaf
function LeafMark() {
    return (
        <svg viewBox="0 0 32 32" className="brand-mark" aria-hidden="true">
            <path d="M6 26C6 13 14 6 27 5c0 13-7 21-20 21z" fill="currentColor" />
            <path d="M7 25C12 19 17 14 23 10" stroke="var(--milk)" strokeWidth="1.6" fill="none" strokeLinecap="round" />
        </svg>
    );
}

function Sidebar() {
    const link = ({ isActive }) => `nav-link ${isActive ? 'active' : ''}`;
    return (
        <nav className="sidebar">
            <NavLink to="/" className="brand">
                <LeafMark />
                <span>{BRAND_NAME}</span>
            </NavLink>

            <div className="eyebrow nav-heading">Menu</div>
            <NavLink to="/" end className={link}>All drinks</NavLink>
            {CATEGORIES.map(({ path, label }) => (
                <NavLink key={path} to={`/${path}`} className={link}>{label}</NavLink>
            ))}

            <div className="nav-extras">
                <NavLink to="/designer" className={({ isActive }) => `nav-feature ${isActive ? 'active' : ''}`}>
                    <strong>Design your own</strong>
                    <span>Choose your tea, milk and toppings</span>
                </NavLink>
                {/* for customers who ordered ahead in the app */}
                <NavLink to="/collect" className={link}>Collect an app order</NavLink>
            </div>
        </nav>
    );
}

export default Sidebar;
