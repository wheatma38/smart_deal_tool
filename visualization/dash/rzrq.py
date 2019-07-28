# -*- coding: utf-8 -*-
import os
import sys
from os.path import abspath, dirname
sys.path.insert(0, dirname(dirname(dirname(abspath(__file__)))))
import const as ct
from datamanager.margin import Margin
class RZRQ(object):
    def __init__(self, dbinfo):
        self.sh_df = None
        self.sz_df = None
        self.margin_client = Margin(dbinfo)

    def update(self, start_date, end_date):
        sh_data = self.get_data(ct.SH_MARKET_SYMBOL, start_date, end_date)
        sz_data = self.get_data(ct.SZ_MARKET_SYMBOL, start_date, end_date)
        date_list = list(set(sh_data.date.tolist()).intersection(set(sz_data.date.tolist())))
        sh_data = sh_data[sh_data.date.isin(date_list)]
        sz_data = sz_data[sz_data.date.isin(date_list)]
        self.sh_df = sh_data.reset_index(drop = True)
        self.sz_df = sz_data.reset_index(drop = True)

    def get_data(self, market, start_date, end_date):
        df = self.margin_client.get_k_data_in_range(start_date, end_date)
        if market == ct.SH_MARKET_SYMBOL:
            df = df.loc[df.code == 'SSE']
            df['code'] = '上海市场'
        else:
            df = df.loc[df.code == 'SZSE']
            df['code'] = '深圳市场'
        df = df.round(2)
        df['rzye']   = df['rzye']/1e+8
        df['rzmre']  = df['rzmre']/1e+8
        df['rzche']  = df['rzche']/1e+8
        df['rqye']   = df['rqye']/1e+8
        df['rzrqye'] = df['rzrqye']/1e+8
        df = df.drop_duplicates()
        df = df.reset_index(drop = True)
        df = df.sort_values(by = 'date', ascending= True)
        return df