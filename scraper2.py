from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
import time
import re
import random
import datetime
import matplotlib.pyplot as plt
import signal
import sys
import os

class TradingSimulator:
    def __init__(self, initial_balance=1000):
        self.balance = initial_balance
        self.positions = {}  # {contract_id_type: {"qty": qty, "price": price, "type": "yes/no"}}
        self.trade_history = []  # [(timestamp, balance, action, profit)]
        self.balance_history = [(datetime.datetime.now(), initial_balance)]
        self.next_sell_time = self.generate_next_sell_time()
        self.max_open_positions = 10
        self.sell_on_next_iteration = False
        self.forced_trade_indices = []
        
    def generate_next_sell_time(self):
        seconds = random.uniform(30, 90)
        return datetime.datetime.now() + datetime.timedelta(seconds=seconds)
    
    def get_total_open_contracts(self):
        return sum(position["qty"] for position in self.positions.values())
    
    def buy_contract(self, contract_id, contract_type, price):
        if self.get_total_open_contracts() >= self.max_open_positions:
            print(f"Position limit reached ({self.max_open_positions})")
            return False
        
        position_key = f"{contract_id}_{contract_type}"
        qty = 1
        cost = qty * price / 100.0
        
        if cost > self.balance:
            print(f"Not enough cash to buy {price}¢")
            return False
        
        self.balance -= cost
        
        if position_key in self.positions:
            current_qty = self.positions[position_key]["qty"]
            current_price = self.positions[position_key]["price"]
            total_qty = current_qty + qty
            avg_price = (current_qty * current_price + qty * price) / total_qty
            self.positions[position_key]["qty"] = total_qty
            self.positions[position_key]["price"] = avg_price
        else:
            self.positions[position_key] = {"qty": qty, "price": price, "type": contract_type}
        
        now = datetime.datetime.now()
        self.trade_history.append((now, self.balance, "BUY", 0))
        self.balance_history.append((now, self.balance))
        
        print(f"Bought {qty} {contract_type} contract at {price}¢")
        print(f"Balance: ${self.balance:.2f} | Positions: {self.get_total_open_contracts()}/{self.max_open_positions}")
        return True
    
    def sell_contract(self, position_key, price):
        if position_key not in self.positions:
            print(f"Position {position_key} not found")
            return False
        
        position = self.positions[position_key]
        qty = position["qty"]
        buy_price = position["price"]
        contract_type = position["type"]
        
        sell_amount = qty * price / 100.0
        cost_basis = qty * buy_price / 100.0
        profit = sell_amount - cost_basis
        
        self.balance += sell_amount
        del self.positions[position_key]
        
        now = datetime.datetime.now()
        self.trade_history.append((now, self.balance, "SELL", profit))
        self.balance_history.append((now, self.balance))
        
        contract_id = position_key.split('_')[0]
        print(f"Sold {qty} {contract_type} contract at {price}¢ (bought at {buy_price}¢)")
        print(f"Profit: ${profit:.2f} | Balance: ${self.balance:.2f}")
        
        return True
    
    def check_for_sells(self, markets_data):
        now = datetime.datetime.now()
        
        if now >= self.next_sell_time:
            print("\n----- Time to sell -----")
            if self.positions:
                self.sell_on_next_iteration = True
                print("Will sell next profitable position encountered")
            else:
                print("No open positions")
            
            self.next_sell_time = self.generate_next_sell_time()
            minutes = (self.next_sell_time - now).total_seconds() / 60.0
            print(f"Next sell: {self.next_sell_time.strftime('%H:%M:%S')} (in {minutes:.1f} min)")
            print("-----------------------\n")
    
    def sell_all_positions(self, markets_data):
        if not self.positions:
            return
            
        print("\n----- Selling positions in this bet -----")
        for position_key in list(self.positions.keys()):
            parts = position_key.split('_')
            if len(parts) < 2:
                continue
                
            contract_id, contract_type = parts[0], parts[1]
            price = None
            
            for market_info in markets_data:
                if market_info["id"] == contract_id:
                    if contract_type == "yes" and "yes_bid_price" in market_info:
                        price = market_info["yes_bid_price"]
                    elif contract_type == "no" and "no_bid_price" in market_info:
                        price = market_info["no_bid_price"]
                    break
            
            if not price:
                price = self.positions[position_key]["price"]
                print(f"No market data for {position_key}; using original price")
            
            self.forced_trade_indices.append(len(self.balance_history))
            self.sell_contract(position_key, price)
            
        print("-----------------------------\n")
    
    def plot_balance_history(self):
        if not self.balance_history:
            return
            
        os.makedirs("plots", exist_ok=True)
        times, balances = zip(*self.balance_history)
        
        plt.figure(figsize=(10, 6))
        
        for i in range(1, len(times)):
            is_forced = i in self.forced_trade_indices
            if is_forced:
                plt.plot([times[i-1], times[i]], [balances[i-1], balances[i]], 
                         marker='o', linestyle=':', color='red', alpha=0.7)
            else:
                plt.plot([times[i-1], times[i]], [balances[i-1], balances[i]], 
                         marker='o', linestyle='-', color='blue')
        
        plt.title('Account Balance')
        plt.xlabel('Time')
        plt.ylabel('Balance ($)')
        plt.grid(True)
        
        from matplotlib.lines import Line2D
        legend_elements = [
            Line2D([0], [0], color='blue', lw=2, marker='o', label='Normal Trading'),
            Line2D([0], [0], color='red', lw=2, linestyle=':', marker='o', label='Liquidation')
        ]
        plt.legend(handles=legend_elements, loc='upper left')
        
        initial_balance = self.balance_history[0][1]
        final_balance = balances[-1]
        profit = final_balance - initial_balance
        percent_return = (profit / initial_balance) * 100
        
        plt.annotate(f'P/L: ${profit:.2f} ({percent_return:.2f}%)',
                     xy=(0.02, 0.95), xycoords='axes fraction',
                     fontsize=10, bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.8))
        
        plt.gcf().autofmt_xdate()
        plt.tight_layout()
        plt.savefig('plots/trading_balance_history.png')
        plt.close()
        print("Balance history saved to 'plots/trading_balance_history.png'")

    def plot_profit_history(self):
        if not self.trade_history:
            return
            
        os.makedirs("plots", exist_ok=True)
        
        sell_times = [self.balance_history[0][0]]
        profits = [0]
        cumulative_profit = 0
        
        for timestamp, _, action, profit in self.trade_history:
            if action == "SELL":
                cumulative_profit += profit
                sell_times.append(timestamp)
                profits.append(cumulative_profit)
        
        if len(sell_times) <= 1:
            return
        
        plt.figure(figsize=(10, 6))
        
        plt.plot(sell_times, profits, marker='o', linestyle='-', color='blue')
        
        plt.title('Profit/Loss')
        plt.xlabel('Time')
        plt.ylabel('Profit/Loss ($)')
        plt.grid(True)
        
        plt.axhline(y=0, color='k', linestyle='-', alpha=0.3)
        
        final_profit = profits[-1]
        initial_balance = self.balance_history[0][1]
        percent_return = (final_profit / initial_balance) * 100
        
        plt.annotate(f'P/L: ${final_profit:.2f} ({percent_return:.2f}%)',
                     xy=(0.02, 0.95), xycoords='axes fraction',
                     fontsize=10, bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.8))
        
        plt.gcf().autofmt_xdate()
        plt.tight_layout()
        plt.savefig('plots/trading_profit_history.png')
        plt.close()
        print("Profit history saved to 'plots/trading_profit_history.png'")

    def generate_trade_summary(self):
        print("\n----- TRADING SUMMARY -----")
        print(f"Starting balance: ${self.balance_history[0][1]:.2f}")
        print(f"Final balance: ${self.balance:.2f}")
        
        profit = self.balance - self.balance_history[0][1]
        percent_return = (profit / self.balance_history[0][1]) * 100
        print(f"Total P/L: ${profit:.2f} ({percent_return:.2f}%)")
        
        buy_count = sum(1 for _, _, action, _ in self.trade_history if action == "BUY")
        
        regular_sells = [i for i, (_, _, action, _) in enumerate(self.trade_history) 
                        if action == "SELL" and i not in self.forced_trade_indices]
        forced_sells = [i for i, (_, _, action, _) in enumerate(self.trade_history) 
                       if action == "SELL" and i in self.forced_trade_indices]
        
        regular_count = len(regular_sells)
        forced_count = len(forced_sells)
        
        print(f"Buy trades: {buy_count}")
        print(f"Regular sells: {regular_count}")
        print(f"Forced sells: {forced_count}")
        
        if regular_count > 0:
            profitable = sum(1 for i, (_, _, action, profit) in enumerate(self.trade_history) 
                           if action == "SELL" and profit > 0 and i not in self.forced_trade_indices)
            
            print(f"Win rate: {(profitable/regular_count)*100:.2f}%")
            
            profits = [p for i, (_, _, action, p) in enumerate(self.trade_history) 
                     if action == "SELL" and p > 0 and i not in self.forced_trade_indices]
            losses = [p for i, (_, _, action, p) in enumerate(self.trade_history) 
                    if action == "SELL" and p <= 0 and i not in self.forced_trade_indices]
            
            if profits:
                print(f"Avg win: ${sum(profits)/len(profits):.2f}")
            
            if losses:
                print(f"Avg loss: ${sum(losses)/len(losses):.2f}")
        
        print("---------------------------\n")

def market_maker():
    simulator = TradingSimulator(initial_balance=1000)
    markets_data = []
    
    def signal_handler(sig, frame):
        print("\nExiting...")
        if markets_data:
            simulator.sell_all_positions(markets_data)
        
        simulator.generate_trade_summary()
        simulator.plot_balance_history()
        simulator.plot_profit_history()
        
        try:
            driver.quit()
        except:
            pass
        
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    driver = webdriver.Firefox()
    driver.get("https://kalshi.com/markets/kxhighaus/highest-temperature-in-austin")
    time.sleep(5)
    
    print("\n----- TRADING SIMULATION -----")
    print(f"Strategy: Buy up to {simulator.max_open_positions} contracts where spread ≥ 3¢")
    print(f"Selling one contract every 30-90 seconds to simulate Kalshi's liquidity and volume")
    print("-----------------------------\n")
    
    start_time = datetime.datetime.now()
    
    try:
        tile_group = driver.find_element(By.CLASS_NAME, 'tileGroup-0-1-124')
        while True:
            markets = tile_group.find_elements(By.XPATH, "*")
            markets = markets[0:3]
            markets_data = []
            
            for market in markets:
                try:
                    contract_id = f"temp_{len(markets_data)}"
                    market_data = {"id": contract_id}
                    
                    label = market.find_element(By.CLASS_NAME, 'flex').get_attribute("innerHTML")
                    market.click()
    
                    # yes prices
                    try:
                        headingContainer = market.find_elements(By.CLASS_NAME, 'headingContainer-0-1-230')[0]
                    except:
                        headingContainer = market.find_elements(By.CLASS_NAME, 'headingContainer-0-1-232')[0]
                    yes_button = headingContainer.find_elements(By.TAG_NAME, 'button')[0]
                    driver.execute_script("arguments[0].click();", yes_button)
    
                    yes_orderbook = market.find_element(By.CLASS_NAME, 'orderbookContent-0-1-280')
                    yes_prices_raw = yes_orderbook.find_elements(By.CLASS_NAME, 'orderBookItem-0-1-286')
                    yes_prices = []
                    for price in yes_prices_raw:
                        spans = price.find_elements(By.TAG_NAME, 'span')
                        if len(spans) == 5:
                            yes_prices.append(int(re.sub(r'[^\d.]', '', spans[2].text)))
                    
                    if len(yes_prices) >= 2:
                        yes_ask_price = yes_prices[0]
                        yes_bid_price = yes_prices[1]
                        
                        market_data["yes_ask_price"] = yes_ask_price
                        market_data["yes_bid_price"] = yes_bid_price
    
                        print(f"\n{label}")
                        print("Contract: Yes")
                        print(f"Ask Price: {yes_ask_price}")
                        print(f"Bid Price: {yes_bid_price}")
                        
                        position_key = f"{contract_id}_yes"
                        if simulator.sell_on_next_iteration and position_key in simulator.positions:
                            buy_price = simulator.positions[position_key]["price"]
                            qty = simulator.positions[position_key]["qty"]
                            sell_price = yes_ask_price - 1
                            print(f"Selling {qty} at {sell_price}¢ (bought at {buy_price}¢)")
                            simulator.sell_contract(position_key, sell_price)
                            simulator.sell_on_next_iteration = False
                        elif yes_ask_price - yes_bid_price >= 3:
                            print(f"Bid at {yes_bid_price + 1}\u00A2, Ask at {yes_ask_price - 1}\u00A2")
                            print(f"Profit: {yes_ask_price - yes_bid_price - 2}\u00A2")
                            if simulator.get_total_open_contracts() < simulator.max_open_positions:
                                simulator.buy_contract(contract_id, "yes", yes_bid_price + 1)
                        else:
                            print("No market making opportunity")
                    else:
                        print(f"\n{label}")
                        print("Contract: Yes - Insufficient data")
    
                    # no prices
                    try:
                        headingContainer = market.find_elements(By.CLASS_NAME, 'headingContainer-0-1-230')[0]
                    except:
                        headingContainer = market.find_elements(By.CLASS_NAME, 'headingContainer-0-1-232')[0]
                    no_button = headingContainer.find_elements(By.TAG_NAME, 'button')[1]
                    driver.execute_script("arguments[0].click();", no_button)
    
                    no_orderbook = market.find_element(By.CLASS_NAME, 'orderbookContent-0-1-280')
                    no_prices_raw = no_orderbook.find_elements(By.CLASS_NAME, 'orderBookItem-0-1-286')
                    no_prices = []
                    for price in no_prices_raw:
                        spans = price.find_elements(By.TAG_NAME, 'span')
                        if len(spans) == 5:
                            no_prices.append(int(re.sub(r'[^\d.]', '', spans[2].text)))
                    
                    if len(no_prices) >= 2:
                        no_ask_price = no_prices[0]
                        no_bid_price = no_prices[1]
                        
                        market_data["no_ask_price"] = no_ask_price
                        market_data["no_bid_price"] = no_bid_price
    
                        print(f"\n{label}")
                        print("Contract: No")
                        print(f"Ask Price: {no_ask_price}")
                        print(f"Bid Price: {no_bid_price}")
                        
                        position_key = f"{contract_id}_no"
                        if simulator.sell_on_next_iteration and position_key in simulator.positions:
                            buy_price = simulator.positions[position_key]["price"]
                            qty = simulator.positions[position_key]["qty"]
                            sell_price = no_ask_price - 1
                            print(f"Selling {qty} at {sell_price}¢ (bought at {buy_price}¢)")
                            simulator.sell_contract(position_key, sell_price)
                            simulator.sell_on_next_iteration = False
                        elif no_ask_price - no_bid_price >= 3:
                            print(f"Bid at {no_bid_price + 1}\u00A2, Ask at {no_ask_price - 1}\u00A2")
                            print(f"Profit: {no_ask_price - no_bid_price - 2}\u00A2")
                            if simulator.get_total_open_contracts() < simulator.max_open_positions:
                                simulator.buy_contract(contract_id, "no", no_bid_price + 1)
                        else:
                            print("No market making opportunity")
                    else:
                        print(f"\n{label}")
                        print("Contract: No - Insufficient data")
                    
                    markets_data.append(market_data)
                    
                except Exception as e:
                    print(f"Error: {e}")
                    continue
                    
                assert "No results found." not in driver.page_source
            
            simulator.check_for_sells(markets_data)
            time.sleep(3)
            
            if (datetime.datetime.now() - start_time).total_seconds() > 1800:
                print("\nReached 30 minute limit")
                simulator.sell_all_positions(markets_data)
                break
    
    except Exception as e:
        print(f"Error: {e}")
        if markets_data:
            simulator.sell_all_positions(markets_data)
    
    finally:
        end_time = datetime.datetime.now()
        print(f"\nEnded at {end_time}")
        print(f"Duration: {end_time - start_time}")
        
        simulator.generate_trade_summary()
        simulator.plot_balance_history()
        simulator.plot_profit_history()
        
        try:
            driver.quit()
        except:
            pass

if __name__ == "__main__":
    market_maker()
