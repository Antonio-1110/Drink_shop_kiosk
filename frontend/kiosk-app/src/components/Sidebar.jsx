import React from 'react';
import { Link } from 'react-router-dom';
import { CATEGORIES } from '../menu';

function Sidebar({ cartCount}) {
    return (
        <div className="sidebar">
            <div className="logo-area">LOGO</div>

            <div className="nav-links">
                {/* We use Link to navigate without reloading the page */}
                <Link to="/" className="nav-btn">All Drinks</Link>
                {CATEGORIES.map(({ path, label }) => (
                    <Link key={path} to={`/${path}`} className="nav-btn">{label}</Link>
                ))}
            </div>

            {/* for customers who ordered ahead in the app */}
            <Link to="/collect" className="nav-btn">Collect my order</Link>

            {/* create new segment for cart link */}
            <Link to="/cart" className="cart-link">
                <div>View Cart</div>    
                <div>{cartCount} items</div>
            </Link>
        </div>
    );
}

export default Sidebar;
