import MetaTrader5 as mt5
import math
import time
import random
import sys

# def TWAPStrategy1(symbol, action, execPeriod, execUnits, targetTWAP, slippage, qtyRatio, orderInterval, randMin = 0.5, randMax = 1.5, magic = 0, comment = ""):
#     if randMin < 0.0 or randMax < 0.0:
#         print("randMin or randMax must be not be negative.")
#         return
#     elif randMin + randMax != 2.0:
#         print("randMin and randMax must average out to 1.")
#         return
#     elif action != "Buy" and action != "Sell":
#         print("Invalid action: select either Buy or Sell")
#         return
#
#     optPath = {"Action": False, "TimeInterval": [], "OrderSize": []}
#     mt5.market_book_add(symbol)
#     depthMT5 = mt5.market_book_get(symbol)
#     depth = {"Offer": [], "Bid": []}
#     for item in depthMT5:
#         bookInfo = item._asdict()
#         if bookInfo["type"] == 1:
#             depth["Offer"].append([bookInfo["price"], bookInfo["volume_dbl"]])
#         else:
#             depth["Bid"].append([bookInfo["price"], bookInfo["volume_dbl"]])
#     if action == "Buy" and len(depth["Offer"]) > 0:
#         p = 1.0
#         expectedFillPrice = 0.0
#         i = -1
#         while p > 0.0 or i > -:
#             expectedFillPrice = depth["Offer"]
#
#     return optPath

def TWAPStrategy2(symbol, action, execPeriod, execMode, execUnits, targetTWAP, slippage, qtyRatio, orderInterval = 5, randMin = 0.5, randMax = 1.5, magic = 0, comment = ""):
    if randMin < 0.0 or randMax < 0.0:
        print("randMin or randMax must be not be negative.")
        return
    elif randMin + randMax != 2.0:
        print("randMin and randMax must average out to 1.")
        return
    elif action != "Buy" and action != "Sell":
        print("Invalid action: select either Buy or Sell")
        return
    elif execMode != "Value" and execMode != "Qty":
        print("Invalid execution mode (execMode): select either Value or Qty")
    elif action == "Sell" and execMode == "Value":
        print("Sell action not valid with execution mode (execMode) Value.")
        return

    unitsPerLot = 100.0
    transactedValue = 0.0 # Value transacted
    transactedQty = 0.0
    bal = execUnits
    startTime = time.time()
    mt5.market_book_add(symbol)
    while bal > 0.0 and time.time() <= startTime + execPeriod:
        depthMT5 = mt5.market_book_get(symbol)
        depth = {"Offer": [], "Bid": []}
        for item in depthMT5:
            bookInfo = item._asdict()
            if bookInfo["type"] == 1:
                depth["Offer"].append([bookInfo["price"], bookInfo["volume_dbl"]])
            else:
                depth["Bid"].append([bookInfo["price"], bookInfo["volume_dbl"]])
        if action == "Buy" and len(depth["Offer"]) > 0:
            refVol = math.floor(qtyRatio * depth["Offer"][-1][1] / unitsPerLot) * unitsPerLot
            if refVol <= 0.0:
                continue
            calcAvg = (transactedValue + depth["Offer"][-1][0] * refVol) / (transactedQty + refVol)
            if calcAvg <= targetTWAP + slippage:
                tradeVol = min(refVol, math.floor(bal / depth["Offer"][-1][0] / unitsPerLot) * unitsPerLot) if execMode == "Value" else min(refVol, math.floor(bal / unitsPerLot) * unitsPerLot)
                if tradeVol <= 0.0:
                    print("Last transaction volume less than minimum required units. End execution.")
                    break
                ret = OrderSend(symbol, tradeVol, mt5.ORDER_TYPE_BUY_LIMIT, depth["Offer"][-1][0], magic, comment)
                if ret:
                    transactedQty += tradeVol
                    transactedValue += depth["Offer"][-1][0] * tradeVol
                    bal = execUnits - transactedValue if execMode == "Value" else execUnits - transactedQty
                    print("Timestamp: {}, Matched Qty: {}, Matched Price: {}, Transacted Qty: {}, Transacted Value: {}, Balance: {}".format(time.time(), tradeVol, depth["Offer"][-1][0], transactedQty, transactedValue, bal))
                    time.sleep(int(round(random.uniform(randMin, randMax) * orderInterval)))
        elif action == "Sell" and len(depth["Bid"]) > 0:
            refVol = math.floor(qtyRatio * depth["Bid"][0][1] / unitsPerLot) * unitsPerLot
            if refVol <= 0.0:
                continue
            calcAvg = (transactedValue + depth["Bid"][0][0] * refVol) / (transactedQty + refVol)
            if calcAvg + slippage >= targetTWAP:
                # tradeVol = min(refVol, math.floor(bal / depth["Bid"][0][0] / unitsPerLot) * unitsPerLot)
                tradeVol = min(refVol, math.floor(bal / unitsPerLot) * unitsPerLot)
                if tradeVol <= 0.0:
                    print("Last transaction volume less than minimum required units. End execution.")
                    break
                ret = OrderSend(symbol, tradeVol, mt5.ORDER_TYPE_SELL_LIMIT, depth["Bid"][0][0], magic, comment)
                if ret:
                    transactedQty += tradeVol
                    transactedValue += depth["Bid"][0][0] * tradeVol
                    bal = execUnits - transactedQty
                    print("Timestamp: {}, Matched Qty: {}, Matched Price: {}, Transacted Qty: {}, Transacted Value: {}, Balance: {}".format(time.time(), tradeVol, depth["Bid"][0][0], transactedQty, transactedValue, bal))
                    time.sleep(int(round(random.uniform(randMin, randMax) * orderInterval)))
        else:
            print("The corresponding side of the order book does not exist to continue operation. Stop execution.")
            break

    if time.time() > startTime + execPeriod:
        print("Exceeded execution period specified. Stop execution.")

def OrderSend(symbol, volume, type, price, magic = 0, comment = ""):
    request = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": symbol,
        "volume": volume,
        "type": type,
        "price": price,
        "sl": 0.0,
        "tp": 0.0,
        "deviation": 0,
        "magic": magic,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(request)
        print(result.retcode)
        return False
    return True

# if not mt5.initialize():
#     sys.exit("MT5 failed to initialise.")
# print("MT5 successfully initialised.")
# TWAPStrategy2("PERTAMA", "Sell", 3600, "Qty", 1600.0, 2.85, 0.02, 0.02, 10, 0.5, 1.5, 20231129, "TWAP")
