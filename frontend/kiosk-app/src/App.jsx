import { useState } from "react";
import { BrowserRouter, Routes, Route  } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import MenuPage from "./pages/MenuPage";
import './App.css';

function App() {
  // keeps track of current cart
  const [cartItems, setCartItems] = useState([])

  const addToCart = (itemName) => {
    setCartItems([...cartItems, itemName]);
    alert(`${itemName} added to cart!`);
  }
  // Sample data for different drink categories
  const seasonalDrinks = [
    'Pumpkin Spice Latte',
    'Peppermint Mocha',
    'Gingerbread Frappe',
  ];

  const milkTeaDrinks = [
    'Classic Milk Tea',
    'Taro Milk Tea',
    'Matcha Milk Tea',
  ];

  const teaDrinks = [
    'Earl Grey',
    'Jasmine Green Tea',
    'Chamomile',
    'English Breakfast',
  ];

  return (
    <BrowserRouter>
      <div className="app-container">
        <Sidebar cartCount={cartItems.length} />

        <div className="content-area">
          <Routes>
            <Route path="/" element={<MenuPage title="Make Your Own Drink" drinks={["Custom Base", "Add Toppings"]} addToCart={addToCart} />} />
            <Route path="/seasonal" element={<MenuPage title="Seasonal Drinks" drinks={seasonalDrinks} addToCart={addToCart} />} />
            <Route path="/milktea" element={<MenuPage title="Milk Tea" drinks={milkTeaDrinks} addToCart={addToCart} />} />
            <Route path="/tea" element={<MenuPage title="Tea" drinks={teaDrinks} addToCart={addToCart} />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  );
}

export default App;