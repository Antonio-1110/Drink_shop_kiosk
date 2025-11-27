class Drink:
    def __init__(self, name: str, size: str, price: float, ingredients: list):
        self.name = name
        self.size = size
        self.price = price
        self.ingredients = ingredients
    def __repr__(self):
        return f"Drink(name={self.name}, size={self.size}, price={self.price}, ingredients={self.ingredients})"