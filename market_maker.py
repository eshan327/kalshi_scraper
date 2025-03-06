import asyncio

async def market_making(client, climate_markets):
    while True:
        for market in climate_markets:
            market_id = market['id']
            yes_bid = market.get('yes_bid')
            yes_ask = market.get('yes_ask')

            if yes_bid is not None and yes_ask is not None:
                spread = yes_ask - yes_bid
                if spread > 2:  # Need room for profit
                    buy_price = yes_bid + 1
                    sell_price = yes_ask - 1

                    buy_order = client.place_order(market_id, "buy", buy_price, 1)
                    print(f"Placed buy order: {buy_order}")
                    sell_order = client.place_order(market_id, "sell", sell_price, 1)
                    print(f"Placed sell order: {sell_order}")

        await asyncio.sleep(10)