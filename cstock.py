#coding=utf-8
import os
import time
import _pickle
import datetime
from datetime import datetime
import const as ct
import pandas as pd
import tushare as ts
from cmysql import CMySQL
from ticks import read_tick
from cinfluxdb import CInflux  
from log import getLogger
from pytdx.hq import TdxHq_API
from futuquant.quote.quote_response_handler import TickerHandlerBase
from common import trace_func,is_trading_time,df_delta,create_redis_obj,delta_days,get_available_tdx_server
logger = getLogger(__name__)
pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)
class CStock(TickerHandlerBase):
    def __init__(self, dbinfo, code):
        self.code = code
        self.dbname = self.get_dbname(code)
        self.redis = create_redis_obj()
        self.name = self.get('name')
        self.data_type_dict = {9:"day"}
        self.influx_client = CInflux(ct.IN_DB_INFO, self.dbname)
        self.mysql_client = CMySQL(dbinfo, self.dbname)
        if not self.create(): raise Exception("create stock %s table failed" % self.code)

    @staticmethod
    def get_dbname(code):
        return "s%s" % code

    @staticmethod
    def get_redis_name(code):
        return "realtime_%s" % code

    def on_recv_rsp(self, rsp_pb):
        '''获取逐笔 get_rt_ticker 和 TickerHandlerBase'''
        ret, data = super(CStock, self).on_recv_rsp(rsp_pb)
        return ret, data

    def has_on_market(self, cdate):
        time2Market = self.get('timeToMarket')
        if str(time2Market) == '0': return False
        t = time.strptime(str(time2Market), "%Y%m%d")
        y,m,d = t[0:3]
        time2Market = datetime(y,m,d)

        t = time.strptime(cdate, "%Y-%m-%d")
        y,m,d = t[0:3]
        time4Date = datetime(y,m,d)
        return True if (time4Date - time2Market).days > 0 else False

    def is_subnew(self, time2Market = None, timeLimit = 365):
        if time2Market == '0': return False #for stock has not been in market
        if time2Market == None: time2Market = self.get('timeToMarket')
        t = time.strptime(time2Market, "%Y%m%d")
        y,m,d = t[0:3]
        time2Market = datetime(y,m,d)
        return True if (datetime.today()-time2Market).days < timeLimit else False

    def create(self):
        self.create_influx_db()
        return self.create_mysql_table()

    def create_influx_db(self):
        self.influx_client.create()

    def create_mysql_table(self):
        for _, table_name in self.data_type_dict.items():
            if table_name not in self.mysql_client.get_all_tables():
                sql = 'create table if not exists %s(cdate varchar(10) not null, open float, high float, close float, low float, volume float, amount float, PRIMARY KEY(cdate))' % table_name 
                if not self.mysql_client.create(sql, table_name): return False
        return True

    def create_ticket_table(self, table):
        sql = 'create table if not exists %s(date varchar(10) not null, ctime varchar(8) not null, price float(5,2), cchange varchar(10) not null, volume int not null, amount int not null, ctype varchar(9) not null, PRIMARY KEY (date, ctime, cchange, volume, amount, ctype))' % table
        return True if table in self.mysql_client.get_all_tables() else self.mysql_client.create(sql, table)

    #def create_realtime(self):
    #    return True
    #    sql = 'create table if not exists %s(date varchar(25),\
    #                                          name varchar(20),\
    #                                          code varchar(10),\
    #                                          open float,\
    #                                          pre_close float,\
    #                                          price float,\
    #                                          high float,\
    #                                          low float,\
    #                                          bid float,\
    #                                          ask float,\
    #                                          volume float,\
    #                                          amount float,\
    #                                          b1_v int,\
    #                                          b1_p float,\
    #                                          b2_v int,\
    #                                          b2_p float,\
    #                                          b3_v int,\
    #                                          b3_p float,\
    #                                          b4_v int,\
    #                                          b4_p float,\
    #                                          b5_v int,\
    #                                          b5_p float,\
    #                                          a1_v int,\
    #                                          a1_p float,\
    #                                          a2_v int,\
    #                                          a2_p float,\
    #                                          a3_v int,\
    #                                          a3_p float,\
    #                                          a4_v int,\
    #                                          a4_p float,\
    #                                          a5_v int,\
    #                                          a5_p float,\
    #                                          time varchar(20),\
    #                                          turnover float,\
    #                                          p_change float,\
    #                                          outstanding float,\
    #                                          limit_down_time varchar(20),\
    #                                          limit_up_time varchar(20))' % self.realtime_table
    #    return True if self.realtime_table in self.mysql_client.get_all_tables() else self.mysql_client.create(sql, self.realtime_table)

    def get(self, attribute):
        df_byte = self.redis.get(ct.STOCK_INFO)
        if df_byte is None: return None
        df = _pickle.loads(df_byte)
        if len(df.loc[df.code == self.code][attribute].values) == 0: return None
        return df.loc[df.code == self.code][attribute].values[0]

    def run(self, data):
        self.redis.set(self.get_redis_name(self.code), _pickle.dumps(data.tail(1), 2))
        self.influx_client.set(data)

    def merge_ticket(self, df):
        ex = df[df.duplicated(subset = ['ctime', 'cchange', 'volume', 'amount', 'ctype'], keep=False)]
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
            ex = df[df.duplicated(subset = ['ctime', 'cchange', 'volume', 'amount', 'ctype'], keep=False)]
            dlist = list(ex.index)
        return df

    def get_market(self):
        if (self.code.startswith("6") or self.code.startswith("500") or self.code.startswith("550") or self.code.startswith("510")) or self.code.startswith("7"):
            return ct.MARKET_SH
        elif (self.code.startswith("00") or self.code.startswith("30") or self.code.startswith("150") or self.code.startswith("159")):
            return ct.MARKET_SZ
        else:
            return ct.MARKET_OTHER

    def get_redis_tick_table(self, cdate):
        cdates = cdate.split('-')
        return "tick_%s_%s_%s" % (self.code, cdates[0], cdates[1])

    def is_tick_table_exists(self, tick_table):
        if self.redis.exists(self.dbname):
            return tick_table in set(str(table, encoding = "utf8") for table in self.redis.smembers(self.dbname))
        return False

    def is_date_exists(self, tick_table, cdate):
        if self.redis.exists(tick_table):
            return cdate in set(str(tdate, encoding = "utf8") for tdate in self.redis.smembers(tick_table))
        return False

    def set_k_data(self):
        prestr = "1" if self.get_market() == ct.MARKET_SH else "0"
        filename = "%s%s.csv" % (prestr, self.code)
        df = pd.read_csv("/data/tdx/history/days/%s" % filename, sep = ',')
        df = df[['date', 'open', 'high', 'close', 'low', 'amount', 'volume']]
        df['date'] = df['date'].astype(str)
        df['date'] = pd.to_datetime(df.date).dt.strftime("%Y-%m-%d")
        df = df.rename(columns={'date':'cdate'})
        df = df.reset_index(drop = True)
        return self.mysql_client.set(df, 'day', method = ct.REPLACE)

    def set_ticket(self, cdate = None):
        cdate = datetime.now().strftime('%Y-%m-%d') if cdate is None else cdate
        if not self.has_on_market(cdate):
            logger.debug("not on market code:%s, date:%s" % (self.code, cdate))
            return
        tick_table = self.get_redis_tick_table(cdate)
        if not self.is_tick_table_exists(tick_table):
            if not self.create_ticket_table(tick_table):
                logger.error("create tick table failed")
                return
        if self.is_date_exists(tick_table, cdate): 
            logger.debug("existed code:%s, date:%s" % (self.code, cdate))
            return
        df = ts.get_tick_data(self.code, date=cdate)
        df_tdx = read_tick(os.path.join(ct.TIC_DIR, '%s.tic' % datetime.strptime(cdate, "%Y-%m-%d").strftime("%Y%m%d")), self.code)
        if not df_tdx.empty: 
            if df is not None and not df.empty and df.loc[0]['time'].find("当天没有数据") == -1:
                net_volume = df.volume.sum()
                tdx_volume = df_tdx.volume.sum()
                if net_volume != tdx_volume:
                    raise Exception("code:%s, date:%s, net volume:%s, tdx volume:%s not equal" % (self.code, cdate, net_volume, tdx_volume))
            df = df_tdx
        else:
            if df is None:
                logger.debug("nonedata code:%s, date:%s" % (self.code, cdate))
                return
            if df.empty:
                logger.debug("emptydata code:%s, date:%s" % (self.code, cdate))
                return
            if df.loc[0]['time'].find("当天没有数据") != -1:
                logger.debug("nodata code:%s, date:%s" % (self.code, cdate))
                return
        df.columns = ['ctime', 'price', 'cchange', 'volume', 'amount', 'ctype']
        logger.debug("code:%s date:%s" % (self.code, cdate))
        df = self.merge_ticket(df)
        df['date'] = cdate
        logger.debug("write data code:%s, date:%s, table:%s" % (self.code, cdate, tick_table))
        if self.mysql_client.set(df, tick_table):
            logger.info("start record:%s. table:%s" % (self.code, tick_table))
            self.redis.sadd(tick_table, cdate)

    def get_ma():
        pass

    def get_vmacd():
        pass

    def get_k_data(self, date = None, dtype = 9):
        table_name = self.data_type_dict[dtype] 
        if date is not None:
            sql = "select * from %s where date=\"%s\"" %(table_name, date)
        else:
            sql = "select * from %s" % table_name
        return self.mysql_client.get(sql)

    def is_after_release(self, code_id, _date):
        time2Market = self.get('timeToMarket')
        t = time.strptime(str(time2Market), "%Y%m%d")
        y,m,d = t[0:3]
        time2Market = datetime(y,m,d)
        return (datetime.strptime(_date, "%Y-%m-%d") - time2Market).days > 0

if __name__ == "__main__":
    #code:300228 date:2016-01-07
    cs = CStock(ct.DB_INFO, '300228')
    print(cs.set_k_data())