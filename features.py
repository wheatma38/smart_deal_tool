#-*- coding: utf-8 -*-
import numpy as np
import pandas as pd
import const as ct
from qfq import qfq
from common import get_market_name, number_of_days
#from cstock import CStock

def MACD(data, fastperiod=12, slowperiod=26, signalperiod=9):
    ewma12 = data.ewm(fastperiod).mean()
    ewma26 = data.ewm(slowperiod).mean()
    dif = ewma12 - ewma26
    dea = dif.ewm(signalperiod).mean()
    bar = (dif - dea)   #有些地方的bar = (dif-dea)*2，但是talib中MACD的计算是bar = (dif-dea) * 1
    return dif, dea, bar

def MA(data, peried):
    return data.rolling(peried).mean()

def SMA(d, N):
    last = np.nan
    v = pd.Series(index=d.index)
    for key in d.index:
        x = d[key]
        x1 = (x + (N - 1) * last) / N if last == last else x
        last = x1
        v[key] = x1
        if x1 != x1: last = x
    return v

def KDJ(data, N1=9, N2=3, N3=3):
    low  = data.low.rolling(N1).min()
    high = data.high.rolling(N1).max()
    rsv  = (data.close - low) / (high - low) * 100
    k = SMA(rsv, N2)
    d = SMA(k, N3)
    j = k * 3 - d * 2
    data['K'] = k
    data['D'] = d
    data['J'] = j
    return data

def BaseFloatingProfit(df, mdate = None):
    for _index, aprice in df.aprice.iteritems():
        pass

def GameKline(df, dist_data, mdate = None):
    if mdate is None:
        p_close_vol_list = list()
        groups = dist_data.groupby(dist_data.date)
        for _index, cdate in df.cdate.iteritems():
            drow = df.loc[_index]
            p_close = drow['close']
            outstanding = drow['outstanding']
            group = groups.get_group(cdate)
            p_close_vol_list.append(100 * group[group.price < p_close].volume.sum() / outstanding)
        df['gline'] = p_close_vol_list
    else:
        groups = dist_data.groupby(dist_data.date)
        group = groups.get_group(mdate)
        drow = df.loc[df.date == mdate]
        p_close = drow['close']
        outstanding = drow['outstanding']
        df.at[df.date == mdate, 'gline'] = 100 * dist_data[dist_data.price < p_close].volume.sum() / outstanding
    return df
        
#function           : u-limitted t-day moving avering price
#input data columns : ['pos', 'sdate', 'date', 'price', 'volume', 'outstanding']
def Mac(df, peried = 0):
    ulist = list()
    df = df.sort_values(by = 'date', ascending= True)
    for name, group in df.groupby(df.date):
        if peried != 0 and len(group) > peried:
            group = group.nlargest(peried, 'pos')
        total_volume = group.volume.sum()
        total_amount = group.price.dot(group.volume)
        ulist.append(total_amount / total_volume)
    return ulist
