# -*- coding: utf-8 -*-
import os
import sys
from os.path import abspath, dirname
sys.path.insert(0, dirname(dirname(abspath(__file__))))
import _pickle
import const as ct
import pandas as pd
#from cinfluxdb import CInflux
from datetime import datetime
from functools import partial
#from cpython.cstock import pro_nei_chip
#from cpython.mchip import compute_distribution, compute_oneday_distribution
from base.cobj import CMysqlObj
from base.clog import getLogger 
from cstock_info import CStockInfo
from cpython.cstock import pro_nei_chip
from cpython.cstock import base_floating_profit
#from cpython.features import base_floating_profit
from cpython.mchip import mac
#from cpython.cchip import mac
from common import is_df_has_unexpected_data, concurrent_run, get_pre_str
from cpython.cchip import compute_distribution, compute_oneday_distribution
from base.cdate import get_years_between, transfer_date_string_to_int, transfer_int_to_date_string
logger = getLogger(__name__)
class CStock(CMysqlObj):
    def __init__(self, code, dbinfo = ct.DB_INFO, should_create_influxdb = False, should_create_mysqldb = False, redis_host = None):
        super(CStock, self).__init__(code, self.get_dbname(code), dbinfo, redis_host)
        #self.influx_client = CInflux(ct.IN_DB_INFO, dbname = self.dbname, iredis = self.redis)
        if not self.create(should_create_influxdb, should_create_mysqldb):
            raise Exception("create stock %s table failed" % self.code)

    def __del__(self):
        #self.influx_client = None
        pass

    @staticmethod
    def get_dbname(code):
        return "s%s" % code

    @staticmethod
    def get_redis_name(code):
        return "realtime_s%s" % code

    def adjust_share(self, data, info):
        data['outstanding'] = 0
        data['totals'] = 0
        if 0 == len(info): return pd.DataFrame()
        cur_totals = 0
        cur_outstanding = 0
        next_totals = 0
        next_outstanding = 0
        start_index = 0
        for info_index, end_date in info.date.iteritems():
            cur_outstanding = int(info.at[info_index, 'money'])  #当前流通盘
            cur_totals = int(info.at[info_index, 'price'])       #当前总股本
            next_outstanding = int(info.at[info_index, 'count']) #后流通盘
            next_totals = int(info.at[info_index, 'rate'])       #后总股本

            dates = data.loc[data.date < end_date].index.tolist()
            if len(dates) == 0:
                if info_index == len(info) - 1:
                    data.at[start_index:, 'outstanding'] = next_outstanding
                    data.at[start_index:, 'totals'] = next_totals
                continue
            
            end_index = dates[-1] + 1
            #if cur_outstanding != last_pre_outstanding:
            #   logger.debug("%s 日期:%s 前流通盘:%s 不等于 预期前流通盘:%s" % (self.code, start_date, cur_outstanding, last_pre_outstanding))
            #elif cur_totals != last_pre_totals:
            #   logger.debug("%s 日期:%s 后流通盘:%s 不等于 预期后流通盘:%s" % (self.code, start_date, cur_totals, last_pre_totals))
            data.at[start_index:end_index, 'outstanding'] = cur_outstanding
            data.at[start_index:end_index, 'totals'] = cur_totals
            start_index = end_index

            #finish the last date
            if info_index == len(info) - 1:
                data.at[start_index:, 'outstanding'] = next_outstanding
                data.at[start_index:, 'totals'] = next_totals

        data['totals']      = data['totals'].astype(int)
        data['totals']      = data['totals'] * 10000
        data['outstanding'] = data['outstanding'].astype(int)
        data['outstanding'] = data['outstanding'] * 10000

        data = data[data.volume < data.outstanding]
        data = data.reset_index(drop = True)
        return data

    def qfq(self, data, info):
        data['adj'] = 1.0
        data['preclose'] = data['close'].shift(1)
        data.at[0, 'preclose'] = data.loc[0, 'open']
        for info_index, start_date in info.date.iteritems():
            dates = data.loc[data.date <= start_date].index.tolist()
            if len(dates) == 0 : continue
            rate  = info.loc[info_index, 'rate']    #配k股
            price = info.loc[info_index, 'price']   #配股价格
            money = info.loc[info_index, 'money']   #分红
            count = info.loc[info_index, 'count']   #转送股数量
            start_index = dates[len(dates) - 1]
            adj = (data.loc[start_index, 'preclose'] * 10 - money + rate * price) / ((10 + rate + count) * data.loc[start_index, 'preclose'])
            if start_date == data['date'][start_index]:
                data.at[:start_index - 1, 'adj'] = data.loc[:start_index - 1, 'adj'] * adj
            else:
                data.at[:start_index, 'adj'] = data.loc[:start_index, 'adj'] * adj
        return data

    def create(self, should_create_influxdb, should_create_mysqldb):
        influxdb_flag = self.create_influx_db() if should_create_influxdb else True
        mysql_flag = self.create_db(self.dbname) and self.create_mysql_table(self.get_day_table()) if should_create_mysqldb else True
        return influxdb_flag and mysql_flag

    def create_influx_db(self):
        #return self.influx_client.create()
        return True

    def create_mysql_table(self, table_name):
        if table_name not in self.mysql_client.get_all_tables():
            sql = 'create table if not exists %s(date varchar(10) not null,\
                                                 open float,\
                                                 high float,\
                                                 close float,\
                                                 preclose float,\
                                                 low float,\
                                                 volume bigint,\
                                                 amount float,\
                                                 outstanding bigint,\
                                                 totals bigint,\
                                                 adj float,\
                                                 aprice float,\
                                                 pchange float,\
                                                 turnover float,\
                                                 sai float,\
                                                 sri float,\
                                                 uprice float,\
                                                 sprice float,\
                                                 mprice float,\
                                                 lprice float,\
                                                 ppercent float,\
                                                 npercent float,\
                                                 base float,\
                                                 ibase bigint,\
                                                 breakup int,\
                                                 ibreakup bigint,\
                                                 pday int,\
                                                 profit float,\
                                                 gamekline float,\
                                                 PRIMARY KEY(date))' % table_name 
            if not self.mysql_client.create(sql, table_name): return False
        return True

    def run(self, data):
        self.redis.set(self.get_redis_name(self.code), _pickle.dumps(data.tail(1), 2))
        self.influx_client.set(data)

    def merge_ticket(self, df):
        ex = df[df.duplicated(subset = ['time', 'cchange', 'volume', 'amount', 'ctype'], keep=False)]
        dlist = list(ex.index)
        while len(dlist) > 0:
            snum = 1
            sindex = dlist[0]
            for _index in range(1, len(dlist)):
                if sindex + 1 == dlist[_index]: 
                    snum += 1
                    if _index == len(dlist) -1:
                        df.drop_duplicates(keep='first', inplace=True)
                        df.at[sindex, 'volume'] = snum * df.loc[sindex]['volume']
                        df.at[sindex, 'amount'] = snum * df.loc[sindex]['amount']
                else:
                    df.drop_duplicates(keep='first', inplace=True)
                    df.at[sindex, 'volume'] = snum * df.loc[sindex]['volume']
                    df.at[sindex, 'amount'] = snum * df.loc[sindex]['amount']
                    sindex = dlist[_index]
                    snum = 1
            df = df.reset_index(drop = True)
            ex = df[df.duplicated(subset = ['time', 'cchange', 'volume', 'amount', 'ctype'], keep=False)]
            dlist = list(ex.index)
        return df

    def get_chip_distribution_table(self, cdate):
        cdates = cdate.split('-')
        return "chip_%s_%s" % (self.dbname, cdates[0])

    def get_redis_tick_table(self, cdate):
        cdates = cdate.split('-')
        return "tick_%s_%s_%s" % (self.dbname, cdates[0], cdates[1])

    def get_day_table(self):
        return "%s_day" % self.dbname

    def get_profit_table(self):
        return "%s_profit" % self.dbname

    def create_chip_table(self, table):
        sql = 'create table if not exists %s(pos int not null,\
                                             sdate varchar(10) not null,\
                                             date varchar(10) not null,\
                                             price decimal(8,2) not null,\
                                             volume bigint not null,\
                                             outstanding bigint not null,\
                                             PRIMARY KEY (pos, sdate, date, price, volume, outstanding))' % table
        return True if table in self.mysql_client.get_all_tables() else self.mysql_client.create(sql, table)

    def read(self, cdate = None, fpath = "/data/tdx/history/days/%s%s.csv"):
        prestr = get_pre_str(self.code)
        filename = fpath % (prestr, self.code)
        if not os.path.exists(filename): return pd.DataFrame(), None
        dheaders = ['date', 'open', 'high', 'close', 'low', 'amount', 'volume']
        dtypes = {'date': 'int', 'open': 'float', 'high': 'float', 'close': 'float', 'low': 'float', 'amount': 'float', 'volume': 'int'}
        df = pd.read_csv(filename, sep = ',', usecols = dheaders, dtype = dtypes)
        df = df[(df['volume'] > 0) & (df['amount'] > 0)]
        df = df.drop_duplicates(subset=['date'], keep='first')
        df = df.sort_values(by = 'date', ascending= True)
        df = df.reset_index(drop = True)
        if cdate is not None:
            index_list = df.loc[df.date == transfer_date_string_to_int(cdate)].index.values
            if len(index_list) == 0: return pd.DataFrame(), None
            preday_index = index_list[0] - 1
            if preday_index < 0:
                return df.loc[df.date == transfer_date_string_to_int(cdate)], None
            else:
                pre_day = df.at[preday_index, 'date']
                return df.loc[df.date == transfer_date_string_to_int(cdate)], transfer_int_to_date_string(pre_day)
        return df, None

    def collect_right_info(self, info, cdate = None):
        sinfo = info[(info.code == self.code) & (info.date <= int(datetime.now().strftime('%Y%m%d')))]
        sinfo = sinfo.sort_values(by = 'date' , ascending = True)
        sinfo = sinfo.reset_index(drop = True)

        #collect stock amount change info
        #6:增发新股(如: 600887 2002-08-20), no change for stock or price 
        total_stock_change_type_list = ['2', '3', '4', '5', '7', '8', '9', '10', '11']
        quantity_change_info = sinfo[sinfo.type.isin(total_stock_change_type_list)]
        quantity_change_info = quantity_change_info[['date', 'type', 'money', 'price', 'count', 'rate']] 
        quantity_change_info = quantity_change_info.sort_index(ascending = True)
        quantity_change_info = quantity_change_info.reset_index(drop = True)
        quantity_change_info['money'] = quantity_change_info['money'].astype(int)
        quantity_change_info['price'] = quantity_change_info['price'].astype(int)

        #collect stock price change info
        price_change_info = sinfo[sinfo.type == 1]
        price_change_info = price_change_info[['money', 'price', 'count', 'rate', 'date']]
        price_change_info = price_change_info.sort_index(ascending = True)
        price_change_info = price_change_info.reset_index(drop = True)
        return quantity_change_info, price_change_info

    def transfer2adjusted(self, df):
        df = df[['date', 'open', 'high', 'close', 'preclose', 'low', 'volume', 'amount', 'outstanding', 'totals', 'adj']]
        df['date'] = df['date'].astype(str)
        df['date'] = pd.to_datetime(df.date).dt.strftime("%Y-%m-%d")
        df['low']  = df['adj'] * df['low']
        df['open'] = df['adj'] * df['open']
        df['high'] = df['adj'] * df['high']
        df['close'] = df['adj'] * df['close']
        df['preclose'] = df['adj'] * df['preclose']
        df['volume'] = df['volume'].astype(int)
        df['aprice'] = df['adj'] * df['amount'] / df['volume']
        df['pchange'] = 100 * (df['close'] - df['preclose']) / df['preclose']
        df['turnover'] = 100 * df['volume'] / df['outstanding']
        return df

    def is_need_reright(self, cdate, price_change_info, quantity_change_info):
        if len(price_change_info) == 0 and len(quantity_change_info): return False
        now_date = transfer_date_string_to_int(cdate)
        p_index = price_change_info.date.index[-1]
        p_date = price_change_info.date[p_index]
        if now_date == p_date:
            logger.debug("{} for {} is need reright for price info changed".format(self.code, cdate))
            return True
        p_index = quantity_change_info.date.index[-1]
        p_date = quantity_change_info.date[p_index]
        if now_date == p_date:
            logger.debug("{} for {} is need reright for quantity info changed".format(self.code, cdate))
            return True
        return False

    def relative_index_strength(self, df, index_df, cdate = None):
        index_df = index_df.loc[index_df.date.isin(df.date.tolist())]
        if len(df) != len(index_df): logger.debug("length of code %s is not equal to index." % self.code)
        index_df.index = df.loc[df.date.isin(index_df.date.tolist())].index
        if cdate is None:
            df['sai'] = 0
            df['sri'] = 0
            s_pchange = (df['close'] - df['preclose']) / df['preclose']
            i_pchange = (index_df['close'] - index_df['preclose']) / index_df['preclose']
            df['sri'] = 100 * (s_pchange - i_pchange)
            df['sri'] = df['sri'].fillna(0)
            df.at[(i_pchange < 0) & (s_pchange > 0), 'sai'] = df.loc[(i_pchange < 0) & (s_pchange > 0), 'sri']
        else:
            s_pchange = (df.loc[df.date == cdate, 'close'] - df.loc[df.date == cdate, 'preclose']) / df.loc[df.date == cdate, 'preclose']
            s_pchange = s_pchange.values[0]
            i_pchange = (index_df.loc[index_df.date == cdate, 'close'] - index_df.loc[index_df.date == cdate, 'preclose']) / index_df.loc[index_df.date == cdate, 'preclose']
            i_pchange = i_pchange.values[0]
            df['sai'] = 100 * (s_pchange - i_pchange) if s_pchange > 0 and i_pchange < 0 else 0
            df['sri'] = 100 * (s_pchange - i_pchange)
        return df 

    def set_oneday_data(self, df, index_df, time2Market, pre_date, cdate):
        day_table = self.get_day_table()
        if self.is_date_exists(day_table, cdate):
            logger.debug("existed data for code:%s, date:%s" % (self.code, cdate))
            return True
       
        index_df = index_df.loc[index_df.date == cdate]

        preday_df = self.get_k_data(date = pre_date)

        if preday_df is None:
            logger.error("%s get %s data failed." % (self.code, pre_date))
            return False

        if preday_df.empty:
            logger.error("%s get %s data empty." % (self.code, pre_date))
            return False

        df['adj']         = 1.0
        df['preclose']    = preday_df['close'][0]
        df['totals']      = preday_df['totals'][0] 
        df['outstanding'] = preday_df['outstanding'][0] 

        #transfer data to split-adjusted share prices
        df = self.transfer2adjusted(df)

        df = self.relative_index_strength(df, index_df, cdate)
        if df is None: return False

        #set chip distribution
        dist_df = df.append(preday_df, sort = False)
        dist_df = dist_df.sort_values(by = 'date', ascending = True)

        dist_data = self.compute_distribution(dist_df, cdate)

        if dist_data.empty:
            logger.error("%s chip distribution compute failed." % self.code)
            return False

        if self.set_chip_distribution(dist_data, time2Market, zdate = cdate):
            df['uprice'] = mac(dist_data, 0)
            df['sprice'] = mac(dist_data, 5)
            df['mprice'] = mac(dist_data, 13)
            df['lprice'] = mac(dist_data, 37)
            df = pro_nei_chip(df, dist_data, preday_df, cdate)
            if is_df_has_unexpected_data(df):
                logger.error("data for %s is not clean." % self.code)
                return False
            if self.mysql_client.set(df, day_table):
                return self.redis.sadd(day_table, cdate)
        return False

    def set_all_data(self, quantity_change_info, price_change_info, index_info, time2Market):
        df, _ = self.read()
        if df.empty:
            logger.error("read empty file for:%s" % self.code)
            return False

        #modify price and quanity for all split-adjusted share prices
        df = self.adjust_share(df, quantity_change_info)
        if df.empty: 
            logger.error("adjust share %s failed" % self.code)
            return False
        
        df = self.qfq(df, price_change_info)
        if df.empty: 
            logger.error("qfq %s failed" % self.code)
            return False

        #transfer data to split-adjusted share prices
        df = self.transfer2adjusted(df)

        #compute strength relative index
        df = self.relative_index_strength(df, index_info)
        if df is None:
            logger.error("length of code %s is not equal to index." % self.code)
            return False

        #set chip distribution
        dist_data = self.compute_distribution(df)
        if dist_data.empty:
            logger.error("%s is empty distribution." % self.code)
            return False

        if not self.set_chip_distribution(dist_data, time2Market):
            logger.error("store %s distribution failed" % self.code)
            return False

        df['uprice'] = mac(dist_data, 0)
        df['sprice'] = mac(dist_data, 5)
        df['mprice'] = mac(dist_data, 13)
        df['lprice'] = mac(dist_data, 37)
        df = pro_nei_chip(df, dist_data)

        if is_df_has_unexpected_data(df):
            logger.error("data for %s is not clean." % self.code)
            return False

        day_table = self.get_day_table()
        if not self.mysql_client.delsert(df, day_table): 
            logger.error("save %s data to mysql failed." % self.code)
            return False

        self.redis.sadd(day_table, *set(df.date.tolist()))
        return True

    def get_base_floating_profit(self, date = None):
        return self.get_k_data(date)

    def get_base_floating_profit_in_range(self, start_date, end_date):
        return self.get_k_data_in_range(start_date, end_date)

    def set_base_floating_profit(self):
        df = self.get_k_data()
        if df is None: return False
        if df.empty: return True
        df['base'] = 0.0
        df['ibase'] = 0
        df['breakup'] = 0
        df['ibreakup'] = 0
        df['pday'] = 0
        df['profit'] = 0.0
        df = base_floating_profit(df)
        return self.mysql_client.upsert(df, self.get_day_table(), pri_keys = ['date'])

    def get_time2market(self, df):
        return df.loc[df.code == self.code]['timeToMarket'].values[0]

    def set_k_data(self, bonus_info, index_info, stock_info, cdate = None):
        if self.code == '003031': return True
        #logger.debug("enter set k data for {} at {}".format(self.code, cdate))
        time2Market = self.get_time2market(stock_info)
        quantity_change_info, price_change_info = self.collect_right_info(bonus_info)
        if cdate is None or self.is_need_reright(cdate, price_change_info, quantity_change_info): 
            return self.set_all_data(quantity_change_info, price_change_info, index_info, time2Market)
        else:
            today_df, pre_date = self.read(cdate)
            if today_df.empty: return True
            if pre_date is None:
                return self.set_all_data(quantity_change_info, price_change_info, index_info, time2Market)
            else:
                return self.set_oneday_data(today_df, index_info, time2Market, pre_date, cdate)

    def get_chip_distribution(self, mdate = None):
        df = pd.DataFrame()
        if mdate is not None:
            table = self.get_chip_distribution_table(mdate)
            if self.is_table_exists(table):
                df = self.mysql_client.get("select * from %s where date=\"%s\"" % (table, mdate))
                df = df.reset_index(drop = True)
                return df
        else:
            start_year  = 1990
            end_year    = int(datetime.now().strftime('%Y'))
            year_list   = get_years_between(start_year, end_year, asending = False)
            for table in [self.get_chip_distribution_table(myear) for myear in year_list]:
                if not self.is_table_exists(table): break
                tmp_df = self.mysql_client.get("select * from %s" % table)
                df = df.append(tmp_df)
            df = df.reset_index(drop = True)
        return df

    def compute_distribution(self, data, zdate = None):
        data = data[['date', 'open', 'aprice', 'outstanding', 'volume', 'amount']]
        if zdate is None:
            df = compute_distribution(data)
        else:
            mdate_list = data.date.tolist()
            pre_date, now_date = mdate_list
            if now_date != zdate:
                logger.error("{} data new date {} is not equal to now date {}".format(self.code, now_date, zdate))
                return pd.DataFrame()

            pre_date_dist = self.get_chip_distribution(pre_date)
            if pre_date_dist.empty:
                logger.error("pre data for {} dist {} is empty".format(self.code, pre_date))
                return pd.DataFrame()
            pre_date_dist = pre_date_dist.sort_values(by = 'pos', ascending= True)
            pos = data.loc[data.date == zdate].index[0]
            volume = data.loc[data.date == zdate, 'volume'].tolist()[0]
            aprice = data.loc[data.date == zdate, 'aprice'].tolist()[0]
            outstanding = data.loc[data.date == zdate, 'outstanding'].tolist()[0]
            pre_outstanding = data.loc[data.date == pre_date, 'outstanding'].tolist()[0]
            zdate = zdate.encode("UTF-8")
            df = compute_oneday_distribution(pre_date_dist, zdate, pos, volume, aprice, pre_outstanding, outstanding)
        return df

    def set_chip_table(self, df, myear):
        #get new df
        tmp_df = df.loc[df.date.str.startswith(myear)]
        #some stock halted more than one year
        if tmp_df.empty: return (myear, True)
        tmp_df = tmp_df.reset_index(drop = True)
        #get chip table name
        chip_table = self.get_chip_distribution_table(myear)
        if not self.is_table_exists(chip_table):
            if not self.create_chip_table(chip_table):
                logger.error("create chip table:%s failed" % chip_table)
                return (myear, False)
            if not self.mysql_client.set(tmp_df, chip_table):
                return (myear, False)
        else:
            #update df to mysql
            if not self.mysql_client.delsert(tmp_df, chip_table):
                return (myear, False)
        self.redis.sadd(chip_table, *set(tmp_df.date.tolist()))
        return (myear, True)

    def set_chip_distribution(self, df, time2Market, zdate = None):
        if zdate is None:
            start_year = int(time2Market / 10000)
            end_year = int(datetime.now().strftime('%Y'))
            year_list = get_years_between(start_year, end_year)
            cfunc = partial(self.set_chip_table, df)
            return concurrent_run(cfunc, year_list, num = 20)
        else:
            chip_table = self.get_chip_distribution_table(zdate)
            if not self.is_table_exists(chip_table):
                if not self.create_chip_table(chip_table):
                    logger.error("create chip table:%s failed" % chip_table)
                    return False

            if self.is_date_exists(chip_table, zdate): 
                logger.debug("existed chip for code:%s, date:%s" % (self.code, zdate))
                return True

            if is_df_has_unexpected_data(df):
                logger.error("data for %s is not clear" % self.code)
                return False

            if self.mysql_client.set(df, chip_table): 
                if self.redis.sadd(chip_table, zdate):
                    logger.debug("finish record chip:%s. table:%s" % (self.code, chip_table))
                    return True
            return False

    def get_k_data_in_range(self, start_date, end_date, dtype = 9):
        table_name = self.get_day_table()
        sql = "select * from %s where date between \"%s\" and \"%s\"" %(table_name, start_date, end_date)
        return self.mysql_client.get(sql)

    def get_k_data(self, date = None, dtype = 9):
        table_name = self.get_day_table()
        if date is not None:
            sql = "select * from %s where date=\"%s\"" %(table_name, date)
        else:
            sql = "select * from %s" % table_name
        return self.mysql_client.get(sql)

    def get_val_filename(self):
        return "%s_val.csv" % self.dbname

    def get_val_data(self, mdate):
        stock_val_path = os.path.join("/data/valuation/stocks", self.get_val_filename())
        if not os.path.exists(stock_val_path): return None
        df = pd.read_csv(stock_val_path)
        if mdate is None:
            return df
        else:
            tdate = transfer_date_string_to_int(mdate)
            return df.loc[df.date == tdate].reset_index(drop = True)

    def set_val_data(self, df, mdate = '', fpath = "/data/valuation/stocks"):
        stock_val_path = os.path.join(fpath, self.get_val_filename())
        if mdate == '':
            df.to_csv(stock_val_path, index=False, header=True, mode='w', encoding='utf8')
        else:
            if not os.path.exists(stock_val_path):
                df.to_csv(stock_val_path, index=False, header=True, mode='w', encoding='utf8')
            else:
                vdf = self.get_val_data(mdate)
                if vdf.empty:
                    df.to_csv(stock_val_path, index=False, header=False, mode='a+', encoding='utf8')
        return True

if __name__ == '__main__':
    mdate = None
    #mdate = '2020-09-24'
    from cindex import CIndex
    index_info = CIndex('000001').get_k_data(mdate)
    stock_info = CStockInfo().get()
    bonus_info = pd.read_csv("/data/tdx/base/bonus.csv", sep = ',', dtype = {'code' : str, 'market': int, 'type': int, 'money': float, 'price': float, 'count': float, 'rate': float, 'date': int})
    cstock = CStock('003020', should_create_influxdb = True, should_create_mysqldb = True)
    logger.info("start compute")
    cstock.set_k_data(bonus_info, index_info, stock_info, cdate = mdate)
    logger.info("enter set base floating profit")
    cstock.set_base_floating_profit()
    logger.info("end compute")
