from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
import random
import datetime
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import signal
import sys
import os
import configparser

class TradingSimulator:
    def __init__(self, initial_balance=1000):
        self.balance = initial_balance
        self.positions = {}  # {contract_id_type: {"qty": qty, "price": price, "type": "yes/no"}}
        self.trade_history = []  # [(timestamp, balance, action, profit)]
        self.balance_history = [(datetime.datetime.now(), initial_balance)]
        self.next_sell_time = self.generate_next_sell_time()
        self.max_open_positions = 2
        self.sell_on_next_iteration = False
        self.forced_trade_indices = []
        self.order_tracker = OrderTracker()

         # New methods to handle order tracking
    def place_order_on_kalshi(self, logged_driver, label, yes_no, buy_sell, price, qty):
        """Place an order on Kalshi but don't update simulator yet"""
        order = place_order(logged_driver, label, yes_no, buy_sell, price, qty)
        if order:
            self.order_tracker.add_pending_order(order)
        return order
    
    def process_filled_orders(self, order_driver):
        """Check for filled orders and update simulator state"""
        filled_orders = self.order_tracker.check_fills(order_driver)
        for filled_order in filled_orders:
            contract_id = f"kalshi_{len(self.trade_history)}"  # Generate a unique ID
            
            if filled_order.buy_sell == 0:  # Buy order
                contract_type = "yes" if filled_order.yes_no == 0 else "no"
                self.buy_contract(contract_id, contract_type, filled_order.price)
            else:  # Sell order
                position_key = f"{contract_id}_{contract_type}"
                self.sell_contract(position_key, filled_order.price)

    def generate_next_sell_time(self):
        seconds = random.uniform(10, 15)
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
        
        # Add order tracking statistics
        print(f"Total orders placed: {self.order_tracker.total_orders_placed}")
        print(f"Total orders filled: {self.order_tracker.total_orders_filled}")
        print(f"Orders fill rate: {(self.order_tracker.total_orders_filled/self.order_tracker.total_orders_placed)*100:.2f}%" if self.order_tracker.total_orders_placed > 0 else "N/A")
        
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

def market_maker(logged_driver, order_driver, market_url):
    
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
    driver.get(market_url)
    time.sleep(5)
    
    print("\n----- TRADING SIMULATION -----")
    print(f"Strategy: Buy up to {simulator.max_open_positions} contracts where spread ≥ 3¢")
    # print(f"Selling one contract every 30-90 seconds to simulate Kalshi's liquidity and volume")
    print("-----------------------------\n")
    
    start_time = datetime.datetime.now()
    
    try:
        tile_group = driver.find_element(By.CLASS_NAME, 'tileGroup-0-1-124')
        while True:
            simulator.process_filled_orders(order_driver)
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
                    headingContainer = market.find_element(By.CSS_SELECTOR, "[class^='headingContainer']")
                    yes_button = headingContainer.find_elements(By.TAG_NAME, 'button')[0]
                    driver.execute_script("arguments[0].click();", yes_button)
    
                    yes_orderbook = market.find_element(By.CSS_SELECTOR, "[class^='orderbookContent']")
                    yes_prices_raw = yes_orderbook.find_elements(By.CSS_SELECTOR, "[class^='orderBookItem']")
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

                            simulator.place_order_on_kalshi(logged_driver, label, yes_no=0, buy_sell=1, price=sell_price, qty=qty)
                                
                            # simulator.sell_contract(position_key, sell_price)
                            # simulator.sell_on_next_iteration = False
                        elif yes_ask_price - yes_bid_price >= 3:
                            print(f"Bid at {yes_bid_price + 1}\u00A2, Ask at {yes_ask_price - 1}\u00A2")
                            print(f"Profit: {yes_ask_price - yes_bid_price - 2}\u00A2")
                            if simulator.get_total_open_contracts() < simulator.max_open_positions:

                                simulator.place_order_on_kalshi(logged_driver, label, yes_no=0, buy_sell=0, price=yes_bid_price + 1, qty=1)
                                
                                # simulator.buy_contract(contract_id, "yes", yes_bid_price + 1)
                        else:
                            print("No market making opportunity")
                    else:
                        print(f"\n{label}")
                        print("Contract: Yes - Insufficient data")
    
                    # no prices
                    headingContainer = market.find_element(By.CSS_SELECTOR, "[class^='headingContainer']")
                    no_button = headingContainer.find_elements(By.TAG_NAME, 'button')[1]
                    driver.execute_script("arguments[0].click();", no_button)
    
                    no_orderbook = market.find_element(By.CSS_SELECTOR, "[class^='orderbookContent']")
                    no_prices_raw = no_orderbook.find_elements(By.CSS_SELECTOR, "[class^='orderBookItem']")
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

                            simulator.place_order_on_kalshi(logged_driver, label, yes_no=1, buy_sell=1, price=sell_price, qty=qty)
                            
                            # simulator.sell_contract(position_key, sell_price)
                            # simulator.sell_on_next_iteration = False
                        elif no_ask_price - no_bid_price >= 3:
                            print(f"Bid at {no_bid_price + 1}\u00A2, Ask at {no_ask_price - 1}\u00A2")
                            print(f"Profit: {no_ask_price - no_bid_price - 2}\u00A2")
                            if simulator.get_total_open_contracts() < simulator.max_open_positions:
                                sell_price = no_ask_price + 1
                                simulator.place_order_on_kalshi(logged_driver, label, yes_no=1, buy_sell=0, price=no_bid_price + 1, qty=1)
                            
                                # simulator.buy_contract(contract_id, "no", no_bid_price + 1)
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

class Order:
    def __init__(self, label, yes_no, buy_sell, price, qty, order_id=None):
        self.label = label
        self.yes_no = yes_no  # 0 for Yes, 1 for No
        self.buy_sell = buy_sell  # 0 for Buy, 1 for Sell
        self.price = price
        self.qty = qty
        self.timestamp = datetime.datetime.now()
        self.order_id = order_id  # Unique ID from Kalshi if available
        self.filled = False
        self.fill_timestamp = None
    
    def __str__(self):
        contract_type = "Yes" if self.yes_no == 0 else "No"
        action = "Buy" if self.buy_sell == 0 else "Sell"
        status = "Filled" if self.filled else "Pending"
        return f"{self.label} - {contract_type} - {action} - {self.price}¢ - {self.qty} contracts - {status}"
    
    def mark_as_filled(self):
        self.filled = True
        self.fill_timestamp = datetime.datetime.now()
        
def place_order(logged_driver, label, yes_no, buy_sell, price, qty, wait_time=5):
    order = Order(label, yes_no, buy_sell, price, qty)
    
    try:
        temp_group = logged_driver.find_element(By.XPATH, f'//*[contains(text(), "{label}")]/ancestor::*[5]')
        yes_button = temp_group.find_elements(By.CSS_SELECTOR, "[class^='pill']")[0]
        logged_driver.execute_script("arguments[0].click();", yes_button)
        
        yes_no_container = logged_driver.find_element(By.CSS_SELECTOR, '[style="display: flex; justify-content: space-between; align-items: center; flex: 1 0 0%;"]')
        yes_no_button = yes_no_container.find_elements(By.TAG_NAME, 'button')[yes_no]  
        logged_driver.execute_script("arguments[0].click();", yes_no_button)         
        
        buy_sell_container = logged_driver.find_element(By.CSS_SELECTOR, '[style="display: flex; justify-content: space-between; align-items: center; box-sizing: border-box; border-bottom: 1px solid var(--kalshi-palette-fill-x50, rgba(0, 0, 0, 0.05));"]')
        buy_sell_button = buy_sell_container.find_elements(By.CSS_SELECTOR, '[style="display: flex; min-width: 32px; justify-content: center; align-items: center;"]')[buy_sell]
        logged_driver.execute_script("arguments[0].click();", buy_sell_button)
        
        input_container = logged_driver.find_element(By.CSS_SELECTOR, '[style="border-radius: 8px; border: 1px solid var(--kalshi-palette-fill-x50, rgba(0, 0, 0, 0.05));"]')  
        contract_input = input_container.find_elements(By.TAG_NAME, 'input')[0]
        contract_input.clear()
        contract_input.send_keys(qty)
        
        limit_input = input_container.find_elements(By.TAG_NAME, 'input')[1]
        limit_input.clear()
        limit_input.send_keys(price)
        
        review_container = logged_driver.find_element(By.CSS_SELECTOR, '[style="display: flex; flex-direction: column; margin-top: 8px;"]')                         
        review_button = review_container.find_elements(By.TAG_NAME, 'button')[0]
        logged_driver.execute_script("arguments[0].click();", review_button) 
    
        confirm_container = logged_driver.find_element(By.CLASS_NAME, 'flex.gap-2')
        confirm_button = confirm_container.find_elements(By.TAG_NAME, 'button')[1]
        logged_driver.execute_script("arguments[0].click();", confirm_button)
        
        print(f"Order placed on Kalshi: {order}")
        time.sleep(wait_time)
        return order
        
    except Exception as e:
        print(f"Failed to place order on Kalshi: {e}")
        return None
    
class OrderTracker:
    def __init__(self):
        self.pending_orders = []
        self.filled_orders = []
        self.total_orders_placed = 0
        self.total_orders_filled = 0
    
    def add_pending_order(self, order):
        if order is not None:
            self.pending_orders.append(order)
            self.total_orders_placed += 1
            print(f"Added pending order: {order}")
            print(f"Total orders placed: {self.total_orders_placed}, Filled: {self.total_orders_filled}, Pending: {len(self.pending_orders)}")
    
    def check_fills(self, order_driver):
        """Check which orders have been filled using orders tab"""
        print("Checking for order fills...")
        filled_orders = []
        
        try:
            order_driver.refresh()
            time.sleep(2)  
            
            orders_table = order_driver.find_element(By.CSS_SELECTOR, "[class^='tableBox'][class*='fullWidth']")
            order_rows = orders_table.find_elements(By.CSS_SELECTOR, "[class^='row'][class*='interactive']")
  
            print(f"Found {len(order_rows)} order entries")
            
            for pending_order in list(self.pending_orders):
                order_filled = False
                
                for row in order_rows:
                    try:
                        label_parts = pending_order.label.split("°")
                        temp_start = label_parts[0].strip()
                        # temp_end = label_parts[1].replace("to", "").strip()

                        market_text = row.find_elements(By.TAG_NAME, 'a')[0].text
                        status_text = row.find_elements(By.TAG_NAME, 'span')[0].text
                        
                        print(temp_start, market_text, status_text)

                        if temp_start in market_text:
                            if (("Order Filled" in status_text and pending_order.buy_sell == 0) or
                                ("Trade Completed" in status_text and pending_order.buy_sell == 1)):
                                order_filled = True
                                filled_orders.append(pending_order)
                                self.pending_orders.remove(pending_order)
                                pending_order.mark_as_filled()
                                self.filled_orders.append(pending_order)
                                self.total_orders_filled += 1
                                print(f"Order confirmed filled: {pending_order}")
                                break
                    except Exception as e:
                        print(f"Error processing order row: {e}")
            
            print(f"Total orders placed: {self.total_orders_placed}, Filled: {self.total_orders_filled}, Pending: {len(self.pending_orders)}")
            return filled_orders
            
        except Exception as e:
            print(f"Error checking order fills: {e}")
            return []

def login(driver):
    config = configparser.ConfigParser()
    try:
        config.read('config.ini')
        username = config['Credentials']['username']
        password = config['Credentials']['password']
        max_position = int(config['Trading']['max_position'])
        max_capital = int(config['Trading']['max_capital'])
        market_url = config['Trading']['url']
    except:
        print("Error loading config.ini.")
    
    driver.get("https://kalshi.com/sign-in")
    print("Signing in...")
    time.sleep(5)
    
    try:
        username_field = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='email']"))
        )
        password_field = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='password']"))
        )
        
        username_field.clear()
        username_field.send_keys(username)
        password_field.clear()
        password_field.send_keys(password)
        
        login_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.CSS_SELECTOR, "button[class^='button'][class*='fullWidth'][class*='medium'][class*='brand'][type='submit']"
            ))
        )

        driver.execute_script("arguments[0].click();", login_button)
        
        time.sleep(3)
        current_url = driver.current_url
        
        if "two-factor-code" in current_url:
            print("2FA required. Input the code.")
            
            max_wait = 120 
            start_time = time.time()
            
            while "two-factor-code" in driver.current_url:
                if time.time() - start_time > max_wait:
                    print("Timed out waiting for 2FA")
                    driver.quit()
                time.sleep(2)
                
            print("2FA complete.")
        
        WebDriverWait(driver, 30).until(
            EC.any_of(
                EC.url_contains("/markets"),
                EC.url_contains("kalshi.com/"),
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'userMenuContainer')]"))
            )
        )
        print("Login successful")
        
    except Exception as e:
        print(f"Login failed: {e}")
        driver.quit()

    driver.get(market_url)
    time.sleep(2)
    return market_url

def setup_orders_window(driver):
    """Create a new tab in the existing driver to monitor orders"""
    try:
        login(driver)
        driver.get("https://kalshi.com/account/activity")
        # container = driver.find_element(By.CLASS_NAME, 'pills-0-1-156')
        # orders_tab = container.find_elements(By.TAG_NAME, 'button')[4]
        # driver.execute_script("arguments[0].click();", orders_tab)
        print("Created order monitoring tab")
        time.sleep(3) 
        
    except Exception as e:
        print(f"Error creating orders tab: {e}")
        orders_window = None

if __name__ == "__main__":
    driver = webdriver.Firefox()
    market_url = login(driver)
    time.sleep(2)
    dollars_button = driver.find_elements(By.CSS_SELECTOR, "[class^='interactiveHeader']")[0]
    driver.execute_script("arguments[0].click();", dollars_button)
    container = driver.find_element(By.CSS_SELECTOR, '[style="display: flex; min-width: 200px; padding: 4px 16px;"]')
    limit_button = container.find_elements(By.CSS_SELECTOR, "[class^='row'][class*='interactive']")[2]
    driver.execute_script("arguments[0].click();", limit_button)
    order_driver = webdriver.Firefox()
    setup_orders_window(order_driver)
    time.sleep(5)

    market_maker(driver, order_driver, market_url)