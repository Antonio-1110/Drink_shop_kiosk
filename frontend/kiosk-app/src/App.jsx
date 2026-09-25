import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import MenuPage from "./pages/MenuPage";
import CartPage from "./pages/CartPage";
import PaymentPage from "./pages/PaymentPage";
import { fetchAvailableDrinks } from "./api";
import { CATEGORIES } from "./menu";
import './App.css';

function App() {
  // keeps track of current cart
  const [cartItems, setCartItems] = useState([])
  const [drinks, setDrinks] = useState([])
  const [loadError, setLoadError] = useState(null)

  // reload the menu whenever the cart changes, so drinks that ran out disappear
  useEffect(() => {
    let cancelled = false;
    fetchAvailableDrinks(cartItems)
      .then((data) => { if (!cancelled) { setDrinks(data); setLoadError(null); } })
      .catch((err) => { if (!cancelled) setLoadError(err.message); });
    return () => { cancelled = true; };
  }, [cartItems]);

  const addToCart = (drink, size) => {
    setCartItems([...cartItems, { drink, size, sugar: 4, ice: 4 }]);
  }
  const updateCartItem = (index, changes) => {
    setCartItems(cartItems.map((item, i) => (i === index ? { ...item, ...changes } : item)));
  }
  const removeFromCart = (index) => {
    setCartItems(cartItems.filter((_, i) => i !== index));
  }
  const clearCart = () => setCartItems([]);

  return (
    <BrowserRouter>
      <div className="app-layout">
        <Sidebar cartCount={cartItems.length} />

        <div className="content-area">
          {loadError && <p className="error-banner">Could not load the menu: {loadError}</p>}
          <Routes>
            <Route path="/" element={<MenuPage title="All Drinks" drinks={drinks} addToCart={addToCart} />} />
            {CATEGORIES.map(({ path, label }) => (
              <Route key={path} path={`/${path}`} element={
                <MenuPage title={label} drinks={drinks.filter((d) => d.category === label)} addToCart={addToCart} />
              } />
            ))}
            <Route path="/cart" element={
              <CartPage cartItems={cartItems} updateCartItem={updateCartItem} removeFromCart={removeFromCart} />
            } />
            <Route path="/payment/:orderId" element={<PaymentPage clearCart={clearCart} />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  );
}

export default App;
