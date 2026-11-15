import { useCallback, useEffect, useMemo, useState } from "react";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import OrderBar from "./components/OrderBar";
import MenuPage from "./pages/MenuPage";
import CartPage from "./pages/CartPage";
import PaymentPage from "./pages/PaymentPage";
import DesignerPage from "./pages/DesignerPage";
import CollectPage from "./pages/CollectPage";
import { fetchAvailableDrinks } from "./api";
import { CATEGORIES, sameDrink } from "./menu";
import IdleProvider from "./IdleProvider";
import { LanguageContext, useT } from "./i18n";
import './App.css';

// the order bar shows while browsing, not on the order review, payment or pickup screens
const BROWSING = ['/', '/designer', ...CATEGORIES.map(({ path }) => `/${path}`)];
// after a failed menu load, try again this soon; while it works, refresh it this often so drinks
// that sold out through the phone app disappear from the screen too
const RETRY_MS = 5000;
const REFRESH_MS = 60000;
// how long "Added …" shows on the order bar
const ADDED_MS = 2500;

function Layout({ cartItems, added, children }) {
  const { pathname } = useLocation();
  const showBar = BROWSING.includes(pathname) && cartItems.length > 0;
  return (
    <div className="app-layout">
      <Sidebar />
      <main className={`content-area ${showBar ? 'with-order-bar' : ''}`}>
        {children}
        {showBar && <OrderBar cartItems={cartItems} added={added} />}
      </main>
    </div>
  );
}

// a calm notice instead of a raw error while the kiosk can't reach the backend; it keeps retrying
function OfflineNotice({ onRetry }) {
  const t = useT();
  return (
    <div className="offline-notice" role="status">
      <span className="offline-dot" aria-hidden="true" />
      <div>
        <strong>{t('offline.title')}</strong>
        <span>{t('offline.text')}</span>
      </div>
      <button className="btn btn-ghost" onClick={onRetry}>{t('offline.retry')}</button>
    </div>
  );
}

function App() {
  // keeps track of current cart; each line has a qty (see menu.js)
  const [cartItems, setCartItems] = useState([])
  const [drinks, setDrinks] = useState(null) // null until the menu first loads
  const [loadError, setLoadError] = useState(null)
  const [reload, setReload] = useState(0)
  const [added, setAdded] = useState(null) // { name, at } for the order bar's "Added …"
  const [lang, setLang] = useState('en')
  const language = useMemo(() => ({ lang, setLang }), [lang]);

  // reload the menu whenever the cart changes, so drinks that ran out disappear
  useEffect(() => {
    let cancelled = false;
    fetchAvailableDrinks(cartItems)
      .then((data) => { if (!cancelled) { setDrinks(data); setLoadError(null); } })
      .catch((err) => { if (!cancelled) setLoadError(err); });
    return () => { cancelled = true; };
  }, [cartItems, reload]);

  // try again soon after a failure, now and then otherwise, and as soon as the network is back
  useEffect(() => {
    const timer = setTimeout(() => setReload((n) => n + 1), loadError ? RETRY_MS : REFRESH_MS);
    return () => clearTimeout(timer);
  }, [loadError, reload, cartItems]);
  useEffect(() => {
    const online = () => setReload((n) => n + 1);
    window.addEventListener('online', online);
    return () => window.removeEventListener('online', online);
  }, []);

  useEffect(() => {
    if (!added) return undefined;
    const timer = setTimeout(() => setAdded(null), ADDED_MS);
    return () => clearTimeout(timer);
  }, [added]);

  // the same cup again just raises the quantity
  const addLine = (line) => {
    setCartItems((items) => {
      const index = items.findIndex((item) => sameDrink(item, line));
      if (index === -1) return [...items, { ...line, qty: 1 }];
      return items.map((item, i) => (i === index ? { ...item, qty: (item.qty ?? 1) + 1 } : item));
    });
    setAdded({ name: line.drink.name, at: Date.now() });
  };
  const addToCart = (drink, { size, sugar, ice }) => addLine({ drink, size, sugar, ice });
  // a drink built in the designer, already shaped as a cart line (see designToCartItem)
  const addCustomToCart = (item) => addLine(item);
  const updateCartItem = (index, changes) => {
    setCartItems(cartItems.map((item, i) => (i === index ? { ...item, ...changes } : item)));
  }
  const removeFromCart = (index) => {
    setCartItems(cartItems.filter((_, i) => i !== index));
  }
  const clearCart = useCallback(() => setCartItems([]), []);
  // the next customer starts in English with an empty order
  const resetKiosk = useCallback(() => { setCartItems([]); setLang('en'); }, []);

  const shown = drinks ?? [];
  const menuProps = { addToCart, loading: drinks === null && !loadError };

  return (
    <LanguageContext.Provider value={language}>
      <BrowserRouter>
        <IdleProvider hasSession={cartItems.length > 0 || lang !== 'en'} onReset={resetKiosk}>
          <Layout cartItems={cartItems} added={added}>
            {loadError && <OfflineNotice onRetry={() => setReload((n) => n + 1)} />}
            <Routes>
              <Route path="/" element={
                <MenuPage titleKey="nav.all" subtitleKey="menu.allSub" drinks={shown} {...menuProps} />
              } />
              {CATEGORIES.map(({ path, label }) => (
                <Route key={path} path={`/${path}`} element={
                  <MenuPage titleKey={`cat.${path}`} subtitleKey={`cat.${path}.sub`}
                    drinks={shown.filter((d) => d.category === label)} {...menuProps} />
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
    </LanguageContext.Provider>
  );
}

export default App;
