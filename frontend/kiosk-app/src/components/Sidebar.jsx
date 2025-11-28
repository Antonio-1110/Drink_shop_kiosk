import React from 'react';
import { Link } from 'react-router-dom';

function Sidebar({ cartCount}) {
    return (
        <div className="sidebar">
            <div className="logo-area">LOGO</div>

            <nav>
                {/* We use Link to navigate without reloading the page */}
                <Link to="/" className="nav-btn">Make your own drink</Link>
                <Link to="/seasonal" className="nav-btn">Seasonal Drinks</Link>
                <Link to="/milktea" className="nav-btn">Milk Tea</Link>
                <Link to="tea" className="nav-btn">Tea</Link>
            </nav>

            {/* Display the Cart Count at the bottom or top */}
            <div style={{ marginTop: 'auto', padding: '20px', background: '#bfdbfe' }}>
                <h3>Cart: {cartCount} items</h3>
            </div>
        </div>
    );
}

export default Sidebar;