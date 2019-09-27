# -*- coding: utf-8 -*-
import sys
from os.path import abspath, dirname
sys.path.insert(0, dirname(dirname(dirname(abspath(__file__)))))
import const as ct
import pandas as pd
from cstock import CStock
from rstock import RIndexStock
from ccalendar import CCalendar
from base.cobj import CMysqlObj
from base.clog import getLogger 
from cstock_info import CStockInfo
from cpython.cval import CValuation
from algotrade.technical.kdj import kdj
from algotrade.feed import dataFramefeed
from datetime import datetime, timedelta
from common import is_df_has_unexpected_data
from base.cdate import transfer_date_string_to_int, get_dates_array
ORDER_TABLE = 'orders'
ACCOUNT_TABLE = 'accounts'
POSITION_TABLE  = 'positions'
class QModel(CMysqlObj):
    def __init__(self, code, valuation_path = ct.VALUATION_PATH,
                bonus_path = ct.BONUS_PATH, stocks_dir = ct.STOCKS_DIR, 
                base_stock_path = ct.BASE_STOCK_PATH, report_dir = ct.REPORT_DIR,
                report_publish_dir = ct.REPORT_PUBLISH_DIR, pledge_file_dir = ct.PLEDGE_FILE_DIR,
                rvaluation_dir = ct.RVALUATION_DIR, cal_file_path = ct.CALENDAR_PATH, 
                dbinfo = ct.DB_INFO, redis_host = None, should_create_mysqldb = False):
        super(QModel, self).__init__(code, code, dbinfo, redis_host)
        self.logger = getLogger(__name__)
        self.rindex_client = RIndexStock(dbinfo, redis_host)
        self.cal_client = CCalendar(dbinfo = dbinfo, redis_host = redis_host, filepath = cal_file_path)
        self.val_client = CValuation(valuation_path, bonus_path, report_dir, report_publish_dir, pledge_file_dir, rvaluation_dir)
        self.stock_info_client = CStockInfo(dbinfo, redis_host, stocks_dir, base_stock_path)
        if should_create_mysqldb:
            if not self.create(should_create_mysqldb):
                raise Exception("create model {} table failed".format(self.code))

    def create(self, should_create_mysqldb):
        if should_create_mysqldb:
            return self.create_db(self.dbname) and self.create_order_table() and self.create_account_table() and self.create_position_table()
        return True

    def create_table(self, table_name):
        if not self.mysql_client.is_exists(table_name):
            sql = 'create table if not exists %s(date varchar(10) not null,\
                                                 code varchar(6) not null,\
                                                 name varchar(150) not null,\
                                                 industry varchar(150) not null,\
                                                 PRIMARY KEY(date, code))' % table_name 
            if not self.mysql_client.create(sql, table_name): return False
        return True

    def create_order_table(self, table_name = ORDER_TABLE):
        if not self.mysql_client.is_exists(table_name):
            sql = 'create table if not exists %s(date varchar(10) not null,\
                                                 order_id varchar(50) not null,\
                                                 trd_side varchar(10),\
                                                 order_type varchar(20),\
                                                 order_status varchar(20),\
                                                 code varchar(20),\
                                                 stock_name varchar(50),\
                                                 qty float,\
                                                 price float,\
                                                 create_time varchar(50),\
                                                 updated_time varchar(50),\
                                                 dealt_qty float,\
                                                 dealt_avg_price float,\
                                                 last_err_msg varchar(100),\
                                                 remark varchar(64) not null,\
                                                 PRIMARY KEY(date, order_id))' % table_name 
            if not self.mysql_client.create(sql, table_name): return False
        return True

    def create_account_table(self, table_name = ACCOUNT_TABLE):
        if not self.mysql_client.is_exists(table_name):
            sql = 'create table if not exists %s(date varchar(10) not null,\
                                                 power float not null,\
                                                 total_assets float not null,\
                                                 cash float not null,\
                                                 market_val float not null,\
                                                 frozen_cash float not null,\
                                                 avl_withdrawal_cash float not null,\
                                                 PRIMARY KEY(date))' % table_name 
            if not self.mysql_client.create(sql, table_name): return False
        return True

    def create_position_table(self, table_name = POSITION_TABLE):
        if not self.mysql_client.is_exists(table_name):
            sql = 'create table if not exists %s(date varchar(10) not null,\
                                                 code varchar(20) not null,\
                                                 position_side varchar(10) not null,\
                                                 stock_name varchar(50) not null,\
                                                 qty float,\
                                                 can_sell_qty float,\
                                                 nominal_price float,\
                                                 cost_price float,\
                                                 cost_price_valid boolean,\
                                                 market_val float,\
                                                 pl_ratio float,\
                                                 pl_ratio_valid	boolean,\
                                                 pl_val	float,\
                                                 pl_val_valid boolean,\
                                                 today_pl_val float,\
                                                 today_buy_qty float,\
                                                 today_buy_val float,\
                                                 today_sell_qty float,\
                                                 today_sell_val float,\
                                                 PRIMARY KEY(date, code))' % table_name 
            if not self.mysql_client.create(sql, table_name): return False
        return True

    def set_account_info(self, mdate, broker):
        account_info = broker.get_accinfo()
        account_info['date'] = mdate
        return self.mysql_client.set(account_info, ACCOUNT_TABLE)

    def get_info(self, table, start, end):
        sql = "select * from %s where date between \"%s\" and \"%s\"" % (table, start, end)
        return self.mysql_client.get(sql)

    def get_account_info(self, start, end):
        return self.get_info(ACCOUNT_TABLE, start, end)

    def get_position_info(self, start, end):
        return self.get_info(POSITION_TABLE, start, end)

    def get_history_order_info(self, start, end):
        return self.get_info(ORDER_TABLE, start, end)

    def set_position_info(self, mdate, broker):
        position_info = broker.get_postitions()
        position_info['date'] = mdate
        return self.mysql_client.set(position_info, POSITION_TABLE)

    def set_history_order_info(self, mdate, broker):
        order_info = broker.get_history_orders(start = mdate, end = mdate)
        order_info['date'] = mdate
        return self.mysql_client.set(order_info, ORDER_TABLE)

    def get_table_name(self, mdate):
        mdates = mdate.split('-')
        return "{}_{}".format(self.code, mdates[0])

    def get_hist_val(self, black_set, white_set, code):
        if code in white_set:
            return 1
        elif code in black_set:
            return -1
        else:
            return 0

    def get_min_val_in_range(self, dtype, code):
        vdf = self.val_client.get_horizontal_data(code)
        vdf = vdf[(vdf['date'] - 1231) % 10000 == 0]
        vdf = vdf[-5:]
        return vdf[dtype].median()

    def get_max_profit(self, code, mdate):
        data = CStock(code).get_k_data()
        mdata = data.loc[data.date == mdate]
        if mdata.empty:
            self.logger.error("{} has not data in {}".format(code, mdate))
            return None
        mdata = mdata.reset_index(drop = True)
        mdict = mdata.to_dict('records')[0]
        pos = mdict['ibase']
        return data.loc[pos:]['profit'].max()

    def get_deleted_reason(self, code, mdate):
        data = self.get_stock_pool(mdate)
        if data.empty: return "{} stock pool is empty".format(mdate)
        if code in set(data.code.tolist()):
            return "{} still in stock pool in {}".format(code, mdate)
        df = CStock(code).get_k_data(mdate)
        if df.empty:
            return "{} has not data in {}".format(code, mdate)
        df['code'] = code
        df['mv'] = df['totals'] * df['close'] / 100000000
        df['hlzh'] = df['ppercent'] - df['npercent']

        base_df = self.stock_info_client.get()
        base_df = base_df[['code', 'name', 'timeToMarket', 'industry']]
        df = pd.merge(df, base_df, how='inner', on=['code'])

        mdict = df.to_dict('records')[0]
        if mdict['pday'] < 60: 
            return "牛股时间小于60天, 当前天数:{}".format(mdict['pday'])
        if mdict['mv'] < 100:
            return "市值小于100亿"
        if mdict['mv'] > 2500:
            return "市值大于2500亿"
        if mdict['hlzh'] < 20:
            return "获利纵横小于20"
        if mdict['profit'] < 2:
            return "基础浮动盈利小于2"
        if mdict['profit'] > 7:
            return "基础浮动盈利大于7"
        if code in set(ct.BLACK_DICT.keys()):
            return "股票在黑名单中"
        if mdict['timeToMarket'] > int((datetime.now() - timedelta(days = 1825)).strftime('%Y%m%d')):
            return "上市时间少于5年"
        if mdict['name'].find('ST') != -1:
            return "股票成ST股"
        pledge_info = self.val_client.get_stock_pledge_info(code = code)
        if not pledge_info.empty and pledge_info.to_dict('records')[0]['pledge_rate'] > 50:
            return "最新的质押率大于50%"
        if df.apply(lambda row: self.get_min_val_in_range('roa', row['code']), axis = 1)[0] <= 8:
            return "最低净资产收益率小于8%"
        if df.apply(lambda row: self.get_max_profit(row['code'], mdate), axis = 1)[0] >= 7:
            return "最大获利盘大于100%"
        self.val_client.update_vertical_data(df, ['goodwill', 'ta'], transfer_date_string_to_int(mdate))
        df['gwr'] = 100 * df['goodwill'] / df['ta']
        if df.to_dict('records')[0]['gwr'] >= 30:
            return "商誉占总资产的比例大于30%"
        return "未知原因"

    def compute_stock_pool(self, mdate):
        df = self.rindex_client.get_data(mdate)
        df['mv'] = df['totals'] * df['close'] / 100000000
        df['hlzh'] = df['ppercent'] - df['npercent']
        df = df[df.pday > 60]
        df = df[(df.mv > 100) & (df.mv < 2500)]
        df = df[df.hlzh > 20]
        df = df[(df.profit > 2) & (df.profit < 7)]
        if df.empty: return df
        #黑名单
        black_set = set(ct.BLACK_DICT.keys())
        white_set = set(ct.WHITE_DICT.keys())
        if len(black_set.intersection(white_set)) > 0: raise Exception("black and white has intersection.")
        df['history'] = df.apply(lambda row: self.get_hist_val(black_set, white_set, row['code']), axis = 1)
        df = df[df['history'] > -1]
        #添加上市时间和行业信息
        base_df = self.stock_info_client.get()
        base_df = base_df[['code', 'name', 'timeToMarket', 'industry']]
        df = pd.merge(df, base_df, how='inner', on=['code'])
        start_time = int((datetime.now() - timedelta(days = 1825)).strftime('%Y%m%d'))
        df = df[(df['timeToMarket'] < start_time) | df.code.isin(list(ct.WHITE_DICT.keys()))]
        #不买包含ST的股票
        df = df[~df.name.str.contains("ST")]
        #质押率
        pledge_info = self.val_client.get_stock_pledge_info()
        pledge_info = pledge_info[['code', 'pledge_rate']]
        df = pd.merge(df, pledge_info, how='left', on=['code'])
        df = df.fillna(value = {'pledge_rate': 0})
        df = df[df['pledge_rate'] < 30]
        #ROE中位数
        df['min_roa'] = df.apply(lambda row: self.get_min_val_in_range('roa', row['code']), axis = 1)
        df = df[df['min_roa'] > 8] 
        #基本面信息
        self.val_client.update_vertical_data(df, ['goodwill', 'ta'], transfer_date_string_to_int(mdate))
        df['gwr'] = 100 * df['goodwill'] / df['ta']
        df = df[df['gwr'] < 30]
        #最大基础浮动盈利 < 7
        df['max_profit'] = df.apply(lambda row: self.get_max_profit(row['code'], mdate), axis = 1)
        df = df[df['max_profit'] < 7]
        df = df.dropna()
        df = df.reset_index(drop = True)
        df = df[['date', 'code', 'name', 'industry']]
        return df

    def generate_feed(self, start_date, end_date):
        all_df = pd.DataFrame()
        feed = dataFramefeed.Feed()
        date_array = get_dates_array(start_date, end_date, asending = True)
        is_first = True
        code_list = list()
        for mdate in date_array:
            if self.cal_client.is_trading_day(mdate):
                df = self.get_stock_pool(mdate)
                if is_first:
                   code_list = df.code.tolist()
                   is_first = False
                if not df.empty: all_df = all_df.append(df)
        codes = list(set(all_df.code.tolist()))
        for code in codes:
            data = CStock(code).get_k_data()
            data = kdj(data)
            data = data[(data.date >= start_date) & (data.date <= end_date)]
            data = data.sort_values(by=['date'], ascending = True)
            data = data.reset_index(drop = True)
            data = data.set_index('date')
            if is_df_has_unexpected_data(data): return None, list()
            data.index = pd.to_datetime(data.index)
            data = data.dropna(how='any')
            feed.addBarsFromDataFrame(code, data)
        return feed, code_list

    def generate_stock_pool(self, start_date, end_date):
        succeed = True
        date_array = get_dates_array(start_date, end_date)
        for mdate in date_array:
             if self.cal_client.is_trading_day(mdate):
                 if not self.set_stock_pool(mdate):
                     self.logger.error("set {} data for model failed".format(mdate))
                     succeed = False
        return succeed

    def get_stock_pool(self, mdate):
        if mdate is None: return pd.DataFrame()
        table_name = self.get_table_name(mdate)
        if not self.is_date_exists(table_name, mdate): return pd.DataFrame()
        sql = "select * from %s where date=\"%s\"" % (table_name, mdate)
        df = self.mysql_client.get(sql)
        return pd.DataFrame() if df is None else df

    def set_stock_pool(self, mdate):
        if mdate is None: return False
        table_name = self.get_table_name(mdate)
        if not self.is_table_exists(table_name):
            if not self.create_table(table_name):
                self.logger.error("create chip table:{} failed".format(table_name))
                return False

        if self.is_date_exists(table_name, mdate):
            self.logger.debug("existed data for code:{}, date:{}".format(self.code, mdate))
            return True

        df = self.compute_stock_pool(mdate)

        if self.mysql_client.set(df, table_name):
            return self.redis.sadd(table_name, mdate)
        return False

if __name__ == '__main__':
    start_date = '2017-09-23'
    end_date   = '2019-09-24'
    redis_host = "127.0.0.1"
    dbinfo = ct.OUT_DB_INFO
    report_dir = "/Volumes/data/quant/stock/data/tdx/report"
    cal_file_path = "/Volumes/data/quant/stock/conf/calAll.csv"
    stocks_dir = "/Volumes/data/quant/stock/data/tdx/history/days"
    bonus_path = "/Volumes/data/quant/stock/data/tdx/base/bonus.csv"
    rvaluation_dir = "/Volumes/data/quant/stock/data/valuation/rstock"
    base_stock_path = "/Volumes/data/quant/stock/data/tdx/history/days"
    valuation_path = "/Volumes/data/quant/stock/data/valuation/reports.csv"
    pledge_file_dir = "/Volumes/data/quant/stock/data/tdx/history/weeks/pledge"
    report_publish_dir = "/Volumes/data/quant/stock/data/crawler/stock/financial/report_announcement_date"
    ftm = QModel('follow_trend', valuation_path, bonus_path, stocks_dir, base_stock_path, report_dir, report_publish_dir, pledge_file_dir, rvaluation_dir, cal_file_path, dbinfo = dbinfo, redis_host = redis_host, should_create_mysqldb = True)
    ftm.generate_stock_pool(start_date, end_date)
    #feed, code_list = ftm.generate_feed(start_date, end_date)
    #print(ftm.get_deleted_reason('600570', '2019-09-17'))
    #ftm.get_deleted_reason('600570', '2019-09-23')
    #df = ftm.compute_stock_pool(mdate = '2019-09-23')
