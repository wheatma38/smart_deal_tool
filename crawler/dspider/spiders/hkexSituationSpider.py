#coding=utf-8
import json
import const as ct
from scrapy import signals
from scrapy import Request
from datetime import datetime
from base.clog import getLogger 
from dspider.myspider import BasicSpider
from dspider.items import HkexTradeOverviewItem, HkexTradeTopTenItem
class HkexSpider(BasicSpider):
    name = 'hkexSpider'
    logger = getLogger(__name__)
    scraped_dates = set()
    custom_settings = {
        'ROBOTSTXT_OBEY': False,
        'SPIDERMON_ENABLED': True,
        'DOWNLOAD_DELAY': 1.0,
        'CONCURRENT_REQUESTS_PER_IP': 10,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 1,
        'RANDOMIZE_DOWNLOAD_DELAY': False,
        'SPIDERMON_VALIDATION_ADD_ERRORS_TO_ITEMS': True,
        'SPIDERMON_VALIDATION_ERRORS_FIELD': ct.SPIDERMON_VALIDATION_ERRORS_FIELD,
        'EXTENSIONS': {
            'spidermon.contrib.scrapy.extensions.Spidermon': 500,
        },
        'ITEM_PIPELINES': {
            'spidermon.contrib.scrapy.pipelines.ItemValidationPipeline': 200,
            'dspider.pipelines.DspiderPipeline': 300,
        },
        'SPIDERMON_UNWANTED_HTTP_CODES': ct.DEFAULT_ERROR_CODES,
        'SPIDERMON_VALIDATION_MODELS': {
            HkexTradeTopTenItem: 'dspider.validators.HkexTradeTopTenModel',
            HkexTradeOverviewItem: 'dspider.validators.HkexTradeOverviewModel',
        },
        'SPIDERMON_SPIDER_CLOSE_MONITORS': (
            'dspider.monitors.SpiderCloseMonitorSuite',
        )
    }
    def start_requests(self):
        self.scraped_dates = set()
        matching_url = "https://sc.hkex.com.hk/TuniS/www.hkex.com.hk/chi/csm/DailyStat/data_tab_daily_{}c.js"
        end_date = datetime.now().strftime('%Y.%m.%d')
        start_date = self.get_nday_ago(end_date, 10, dformat = '%Y.%m.%d')
        while start_date < end_date:
            start_date = self.get_tomorrow_date(sdate = start_date)
            url = matching_url.format(start_date.replace('.', ''))
            yield Request(url=url, callback=self.parse, errback=self.errback_httpbin)

    def parse(self, response):
        try:
            jsonstr = response.text.split("=")[1].strip()
            if jsonstr.find("阅\\文") >= 0: jsonstr = jsonstr.replace("阅\\文", "阅文")
            data = json.loads(jsonstr)
            sse_northbond = data[0]
            sse_northbond_overview_item = self.parseTradeOverviewItem(sse_northbond, "sse", "north")
            yield sse_northbond_overview_item
            sse_northbond_top_ten_items = self.parseTradeTopTenItem(sse_northbond, "sse", "north")
            for i in range(len(sse_northbond_top_ten_items)):
                yield sse_northbond_top_ten_items[i]

            sse_southbond = data[1]
            sse_southbond_overview_item = self.parseTradeOverviewItem(sse_southbond, "sse", "south")
            yield sse_southbond_overview_item
            sse_southbond_top_ten_items = self.parseTradeTopTenItem(sse_southbond, "sse", "south")
            for i in range(len(sse_southbond_top_ten_items)):
                yield sse_southbond_top_ten_items[i]

            szse_northbond = data[2]
            szse_northbond_overview_item = self.parseTradeOverviewItem(szse_northbond, "szse", "north")
            yield szse_northbond_overview_item
            szse_northbond_top_ten_items = self.parseTradeTopTenItem(szse_northbond, "szse", "north")
            for i in range(len(szse_northbond_top_ten_items)):
                yield szse_northbond_top_ten_items[i]

            szse_southbond = data[3]
            szse_southbond_overview_item = self.parseTradeOverviewItem(szse_southbond, "szse", "south")
            yield szse_southbond_overview_item
            szse_southbond_top_ten_items = self.parseTradeTopTenItem(szse_southbond, "szse", "south")
            for i in range(len(szse_southbond_top_ten_items)):
                yield szse_southbond_top_ten_items[i]
        except Exception as e:
            self.logger.error("wrong url:{}, failure:{}".format(response.url, failure.value))

    def parseTradeOverviewItem(self, need_parse_data, market, direction):
        trade_overview_tr = need_parse_data["content"][0]["table"]["tr"]
        item = HkexTradeOverviewItem()
        item['market'] = market
        item['direction'] = direction
        item['date'] = need_parse_data["date"]
        item['total_turnover'] = item.convert(trade_overview_tr[0]["td"][0][0])
        item['buy_turnover'] = item.convert(trade_overview_tr[1]["td"][0][0])
        item['sell_turnover'] = item.convert(trade_overview_tr[2]["td"][0][0])
        item['total_trade_count'] = item.convert(trade_overview_tr[3]["td"][0][0], int)
        item['buy_trade_count'] = item.convert(trade_overview_tr[4]["td"][0][0], int)
        item['sell_trade_count'] = item.convert(trade_overview_tr[5]["td"][0][0], int)
        if need_parse_data["market"] == "SSE Northbound" or need_parse_data["market"] == "SZSE Northbound":
            #剩余额度总额和和使用额度总额比例, 如果卖出大于买入，会导致dqb_ratio > 100%
            item['dqb'] = item.convert(trade_overview_tr[6]["td"][0][0])
            item['dqb_ratio'] = item.convert(trade_overview_tr[7]["td"][0][0])
        else:
            item['dqb'] = 0.0
            item['dqb_ratio'] = 0.0
        return item

    def parseTradeTopTenItem(self, need_parse_data, market, direction):
        items = []
        trade_top_ten_tr = need_parse_data["content"][1]["table"]["tr"]
        for i in range(10):
            item = HkexTradeTopTenItem()
            item['market'] = market
            item['direction'] = direction
            item['date'] = need_parse_data["date"]
            item['rank'] = item.convert(trade_top_ten_tr[i]["td"][0][0], int)
            item['code'] = item.format_code(trade_top_ten_tr[i]["td"][0][1], direction)
            item['name'] = trade_top_ten_tr[i]["td"][0][2].strip()
            item['buy_turnover'] = item.convert(trade_top_ten_tr[i]["td"][0][3], float)
            item['sell_turnover'] = item.convert(trade_top_ten_tr[i]["td"][0][4], float)
            item['total_turnover'] = item.convert(trade_top_ten_tr[i]["td"][0][5], float)
            items.append(item)
        return items


    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(HkexSpider, cls).from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_error, signal=signals.spider_error)
        crawler.signals.connect(spider.item_scraped, signal=signals.item_scraped)
        crawler.signals.connect(spider.spider_closed, signal=signals.spider_closed)
        return spider

    def item_scraped(self, item, response, spider):
        if item:
            self.scraped_dates.add(item['date'])

    def spider_error(self, failure, response, spider):
        self.logger.error("wrong url:{}, failure:{}".format(response.url, failure.value))

    def spider_closed(self, spider, reason):
        mdate = datetime.now().strftime('%Y-%m-%d')
        if mdate in self.scraped_dates:
            self.status = True
            self.message = "get data at {} succeed".format(mdate)
        else:
            self.status = False
            self.message = "get data not include {}".format(mdate)
        self.collect_spider_info()
