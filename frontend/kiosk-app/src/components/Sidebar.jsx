import React from 'react';
import { Link } from 'react-router-dom';

function Sidebar({ cartCount}) {
    return (
        <div className="sidebar">
            <div className="logo-area">LOGO</div>

            <div className="nav-links">
                {/* We use Link to navigate without reloading the page */}
                <Link to="/" className="nav-btn">Make your own drink</Link>
                <Link to="/seasonal" className="nav-btn">Seasonal Drinks</Link>
                <Link to="/milktea" className="nav-btn">Milk Tea</Link>
                <Link to="/tea" className="nav-btn">Tea</Link>
            </div>

            {/* create new segment for cart link */}
            <Link to="/cart" className="cart-link">
                <div>View Cart</div>    
                <div>{cartCount} items</div>
            </Link>
        </div>
    );
}

export default Sidebar;