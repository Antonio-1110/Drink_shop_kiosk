import { useCallback, useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import OrderBar from "./components/OrderBar";
import MenuPage from "./pages/MenuPage";
import CartPage from "./pages/CartPage";
import PaymentPage from "./pages/PaymentPage";
import DesignerPage from "./pages/DesignerPage";
import CollectPage from "./pages/CollectPage";
import { fetchAvailableDrinks } from "./api";
import { CATEGORIES } from "./menu";
import IdleProvider from "./IdleProvider";
import './App.css';

// the order bar shows while browsing, not on the order review, payment or pickup screens
const BROWSING = ['/', '/designer', ...CATEGORIES.map(({ path }) => `/${path}`)];

function Layout({ cartItems, children }) {
  const { pathname } = useLocation();
  const showBar = BROWSING.includes(pathname) && cartItems.length > 0;
  return (
    <div className="app-layout">
      <Sidebar />
      <main className={`content-area ${showBar ? 'with-order-bar' : ''}`}>
        {children}
        {showBar && <OrderBar cartItems={cartItems} />}
      </main>
    </div>
  );
}

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

  const addToCart = (drink, { size, sugar, ice }) => {
    setCartItems([...cartItems, { drink, size, sugar, ice }]);
  }
  // a drink built in the designer, already shaped as a cart line (see designToCartItem)
  const addCustomToCart = (item) => setCartItems([...cartItems, item]);
  const updateCartItem = (index, changes) => {
    setCartItems(cartItems.map((item, i) => (i === index ? { ...item, ...changes } : item)));
  }
  const removeFromCart = (index) => {
    setCartItems(cartItems.filter((_, i) => i !== index));
  }
  const clearCart = useCallback(() => setCartItems([]), []);

  return (
    <BrowserRouter>
      <IdleProvider hasSession={cartItems.length > 0} onReset={clearCart}>
        <Layout cartItems={cartItems}>
          {loadError && <p className="error-banner">Could not load the menu: {loadError}</p>}
          <Routes>
            <Route path="/" element={
              <MenuPage title="All drinks" subtitle="Made to order, one cup at a time." drinks={drinks} addToCart={addToCart} />
            } />
            {CATEGORIES.map(({ path, label, subtitle }) => (
              <Route key={path} path={`/${path}`} element={
                <MenuPage title={label} subtitle={subtitle}
                  drinks={drinks.filter((d) => d.category === label)} addToCart={addToCart} />
              } />
            ))}
            <Route path="/designer" element={<DesignerPage addCustomToCart={addCustomToCart} />} />
            <Route path="/cart" element={
              <CartPage cartItems={cartItems} updateCartItem={updateCartItem} removeFromCart={removeFromCart} />
            } />
            <Route path="/collect" element={<CollectPage />} />
            <Route path="/payment/:orderId" element={<PaymentPage clearCart={clearCart} />} />
          </Routes>
        </Layout>
      </IdleProvider>
    </BrowserRouter>
  );
}

export default App;
