# The Data Layer for a US Stock Swing-Trading Signal System: A Free & Low-Cost Sourcing Guide (2025–2026)

## TL;DR
- **You can cover roughly 90% of the eight research domains for $0/month** by combining four free pillars — yfinance (price/volume/options chains), SEC EDGAR via EdgarTools (fundamentals, insider Form 4, 13F), FRED via fredapi (all macro + VIX), and Finnhub's free tier (news, earnings calendar, basic fundamentals, sentiment) — with FINRA's free short-interest/short-volume files.
- **The factors that are genuinely hard or impossible to get free** are real-time options flow, dark-pool prints, intraday tick/Level-2 data, and timely short interest; these require paid tools ($30–$400+/month). For a signal-only swing system on daily bars, most of these are "nice to have," not essential — free proxies exist.
- **Recommended scale-up:** add Polygon.io/Massive Starter ($29/mo) or Tiingo ($10–30/mo) for reliable, ToS-clean price/fundamentals, then a single alt-data specialist (QuiverQuant API $30–75/mo or Unusual Whales $48/mo) only once the account justifies it.

## Key Findings
1. **yfinance is the most capable free tool but the least reliable and legally grayest.** It scrapes Yahoo Finance, whose Terms of Service explicitly prohibit accessing data "using any automated means... including but not limited to robots, spiders, scrapers... for any purpose without our express, prior permission." It breaks when Yahoo changes its site and offers no SLA. Fine for a personal, non-commercial signal system; not safe to build a business on.
2. **The free "official" backbone is excellent.** FRED (macro + VIX), SEC EDGAR (fundamentals, insider, institutional), FINRA (short interest), and CBOE (VIX history) are all free, official, stable, and legally clean. These cover Domains 03–08 surprisingly well.
3. **Alpha Vantage's free tier has collapsed to 25 requests/day** (down from 500, then 100). Per Alpha Vantage's own pricing page, "the majority of our API endpoints can be accessed for free. For use cases that exceed our standard API usage limit (25 API requests per day)..." This makes it nearly useless as a primary price feed but still useful for its free NEWS_SENTIMENT endpoint and 50+ technical indicators if used sparingly.
4. **Finnhub has the most generous free tier** — "60 API calls per minute, real-time US stock quotes, company news, basic fundamentals, SEC filings access, and WebSocket streaming for up to 50 symbols — all at no cost." It uniquely bundles news, social sentiment, earnings calendar, insider transactions/MSPR, and basic fundamentals for free — making it the single best free API for the news/sentiment/events domains.
5. **IEX Cloud is dead.** Per IEX's official closure notice, "The IEX Cloud API products were officially retired on August 31, 2024" (announced May 31, 2024, because IEX Cloud "was running at a loss and represented less than 2% of IEX Group overall revenue"). Separately, **Polygon.io rebranded to "Massive"** — per Massive's official blog, "We have just renamed Polygon.io to Massive.com, effective today (October 30, 2025) at 4 PM ET... your existing code, keys, and logins remain valid, with no updates required today." These are the two biggest recent platform changes.
6. **Smart-money "edge" data is where the money goes.** Real options flow and dark-pool analytics come from Unusual Whales ($48/mo retail; $150–375/mo API), QuiverQuant ($30–75/mo API), or ORATS ($99/mo). None are free, but FINRA + SEC + yfinance options chains provide workable free proxies.

## Details

### Strategy Overview & The Core Tradeoff
For a swing-trading signal system on a small account holding positions a few days to a month, working on **daily (end-of-day) bars**, you do **not** need expensive real-time or tick data. This is the single most important cost-saving insight: nearly every factor you listed can be computed from **daily OHLCV + fundamentals + free official datasets**, all of which are available for free.

The fundamental tradeoff is **reliability/legality vs. cost**:
- **Free scraped tools (yfinance, Stooq, StockTwits public endpoints)** — zero cost, broad coverage, but unofficial, brittle, and ToS-gray.
- **Free official APIs (FRED, SEC EDGAR, FINRA, CBOE)** — zero cost, rock-solid, legally clean, but narrow (macro/filings/short-interest only).
- **Free API tiers (Finnhub, Alpha Vantage, FMP, Tiingo, Twelve Data)** — clean and supported, but throttled by daily/per-minute request caps.
- **Low-cost paid ($10–50/mo: Tiingo, Polygon/Massive Starter, EODHD, Twelve Data Grow)** — reliable, ToS-clean, removes rate anxiety.
- **Specialist alt-data ($30–400/mo: QuiverQuant, Unusual Whales, ORATS)** — the only way to get true options flow / dark-pool / congressional data.

Technical indicators (RSI, MACD, moving averages, support/resistance, chart patterns) should be **computed locally** from OHLCV using the `pandas-ta` or `TA-Lib` Python libraries rather than paid for — this is free, more flexible, and avoids API quota burn.

### Master Table

| Factor / Data Type | Recommended Source | Cost | Free-Tier Limits | Rate Limits | Python Access |
|---|---|---|---|---|---|
| **01 Price/Volume/OHLCV (daily)** | yfinance (primary) → Tiingo/Stooq (backup) | Free | yfinance: unlimited-ish, unofficial; Tiingo free: 30+ yrs daily, 500 symbols/mo | yfinance: none official; Tiingo: 50 req/hr, 1,000/day | `yfinance`, `tiingo`, `pandas-datareader` (Stooq) |
| **01 Intraday OHLCV** | Polygon/Massive Starter; Finnhub free (limited) | $29/mo / Free | Finnhub: ~1 mo intraday history | Finnhub 60/min; Polygon unlimited (paid) | `polygon-api-client`, `finnhub-python` |
| **01 Technical indicators** | Compute locally from OHLCV | Free | n/a | n/a | `pandas-ta`, `TA-Lib` |
| **02 News headlines** | Finnhub (primary); Marketaux; Tiingo news | Free | Finnhub generous; Marketaux 100 req/day | Finnhub 60/min | `finnhub-python`, `requests` |
| **02 News sentiment** | Alpha Vantage NEWS_SENTIMENT; Finnhub | Free | AV: 25 req/day; Finnhub sentiment included | AV 5/min, 25/day | `requests`, `finnhub-python` |
| **02 Social sentiment** | StockTwits public endpoint; Finnhub social | Free | StockTwits: public read endpoints, no key | ~rate-limited politely | `requests`, `finnhub-python` |
| **03 Earnings dates** | Finnhub earnings calendar (primary); FMP | Free | Finnhub free; FMP 250 req/day | Finnhub 60/min | `finnhub-python`, `requests` |
| **03 Dividends/splits** | yfinance; FMP; Tiingo corporate actions | Free | full coverage | n/a | `yfinance`, `requests` |
| **03 Economic calendar** | FMP economic calendar; Finnhub | Free | FMP 250 req/day | n/a | `requests`, `finnhub-python` |
| **04 Macro (rates, CPI, GDP, jobs)** | FRED (primary) | Free | 844,000 series, full history | 120 req/min | `fredapi` |
| **04 Yield curve** | FRED (DGS10, DGS2, T10Y2Y) | Free | full history | 120 req/min | `fredapi` |
| **05 Sector rotation / themes** | Sector ETFs via yfinance; FMP sector performance | Free | full | n/a | `yfinance`, `requests` |
| **06 Insider transactions (Form 4)** | SEC EDGAR (primary); Finnhub | Free | full, official | SEC ~10 req/sec fair-use | `edgartools`, `sec-edgar-downloader` |
| **06 Institutional (13F)** | SEC EDGAR | Free | full, official, 45-day lag | SEC fair-use | `edgartools` |
| **06 Short interest** | FINRA (primary) | Free | bi-monthly, official | n/a | `requests` (FINRA API) |
| **06 Short volume (daily)** | FINRA daily short-sale files | Free | daily, official | n/a | `requests` |
| **06 Options flow / dark pool** | Unusual Whales / QuiverQuant (paid) | $30–375/mo | none free (FINRA proxy only) | varies | `requests` |
| **07 VIX / volatility regime** | FRED (VIXCLS); yfinance (^VIX); CBOE | Free | full history | n/a | `fredapi`, `yfinance` |
| **07 Market breadth / A-D** | Compute from index constituents; index data | Free | DIY | n/a | `yfinance` + compute |
| **08 Beta / correlation / vol** | Compute locally from OHLCV | Free | n/a | n/a | `pandas`, `numpy` |
| **08 Options chains (IV inputs)** | yfinance options; Tradier sandbox (free, delayed) | Free | delayed | n/a | `yfinance`, `requests` (Tradier) |

### Per-Source Detail

#### yfinance (Yahoo Finance, unofficial)
- **Provides:** Daily/intraday OHLCV, dividends, splits, basic fundamentals (`.info`, financials, balance sheet, cash flow), options chains (`.option_chain`), analyst data, `^VIX` and index data, sector ETF data. Covers Domains 01, 03, 05, 07, 08 and parts of 06.
- **Free-tier limits:** No formal limit — it scrapes Yahoo's public endpoints. Practically, aggressive use triggers rate-limiting/IP blocks. Data is delayed (typically 15+ minutes) and not guaranteed accurate.
- **Rate limits:** None official; Yahoo throttles heavy automated traffic. Use delays and caching.
- **Reliability:** **Unofficial and brittle.** Yahoo's Terms of Service prohibit accessing data "using any automated means... including but not limited to robots, spiders, scrapers... for any purpose without our express, prior permission." Yahoo discontinued its official API in 2017. yfinance breaks when Yahoo changes its site. **Legally gray; acceptable for personal/non-commercial use, risky for anything commercial.**
- **Python:** `pip install yfinance`. Example:
```python
import yfinance as yf
df = yf.Ticker("AAPL").history(period="1y")       # daily OHLCV
chain = yf.Ticker("AAPL").option_chain("2026-01-16")
vix = yf.Ticker("^VIX").history(period="5y")
```

#### Tiingo
- **Provides:** Clean, error-checked end-of-day prices (history back to 1962 on many tickers), corporate actions (dividends/splits), fundamentals (US), a 50M+ article news API, crypto/FX. Covers Domains 01, 02, 03.
- **Free-tier limits:** 30+ years daily price history; 5 years of fundamentals; **500 unique symbols/month, 50 requests/hour, 1,000 requests/day**. Free tier is personal/non-commercial.
- **Rate limits:** 50/hour, 1,000/day on free tier.
- **Reliability:** Official, paid-backed, with proprietary data-cleaning. Stable and ToS-clean. A genuine "real" provider, unlike yfinance.
- **Python:** `pip install tiingo` (official-style wrapper) or `requests`; also works via `pandas_datareader`.

#### Polygon.io / Massive
- **Provides:** Real-time and historical tick/minute/daily OHLCV for US stocks, options, FX, crypto, indices, futures; corporate actions, dividends, splits, technical indicators, ticker news, financials. Covers Domains 01, 02, 03, 06 (options), 07.
- **Free-tier limits:** Free "Basic" tier — **5 API calls/minute, end-of-day/15-min-delayed data, ~2 years history.** All US tickers.
- **Paid tiers:** Starter **$29/mo** — confirmed: "For $29 per month, you can upgrade to the Stocks Starter plan. This tier allows unlimited API calls and includes five years of historical data... With 15-minute delayed data updates"; Developer **$79–99/mo** (10 yrs history, trades); Advanced **$199/mo** (real-time, 20+ yrs, quotes, financials, non-professional only).
- **Rate limits:** Free 5/min; paid plans unlimited calls.
- **Reliability:** Official, institutional-grade, low latency. **Rebranded to "Massive" (massive.com) on October 30, 2025; existing Polygon API keys, code, and logins continue to work with no updates required.** Note: older comparisons sometimes cite legacy prices ($199 entry) — current Starter is $29/mo.
- **Python:** `pip install polygon-api-client`.

#### Finnhub
- **Provides:** Real-time US quotes, OHLCV candles, company news, **social sentiment (Reddit/Twitter), earnings calendar, insider transactions + MSPR insider-sentiment score, basic fundamentals, SEC filings, economic data, recommendation trends, congressional trading**. Covers Domains 01, 02, 03, 04, 06. The single most versatile free API for the "soft" factors.
- **Free-tier limits:** **60 API calls/minute** free, real-time US quotes, company news, basic fundamentals, SEC filing access, WebSocket streaming for up to 50 symbols. Free tier is personal/non-commercial; intraday candle history limited (~1 month); some fundamentals and international data require paid.
- **Rate limits:** 60/minute on free tier.
- **Reliability:** Official, well-documented, built by ex-Google/Bloomberg/Tradeweb engineers. Stable. Premium from ~$50/mo per market bundle.
- **Python:** `pip install finnhub-python`.

#### Alpha Vantage
- **Provides:** Daily/intraday OHLCV (split/dividend adjusted), 50+ pre-computed technical indicators, **NEWS_SENTIMENT (AI news + ticker-level sentiment scores)**, fundamentals, economic indicators, options. NASDAQ-licensed. Covers Domains 01, 02, 04.
- **Free-tier limits:** **25 requests/day, 5 requests/minute** (reduced over time from 500 → 100 → 25). NEWS_SENTIMENT is confirmed available on the free tier. Real-time US data requires premium.
- **Rate limits:** 5/min, 25/day free.
- **Paid:** $49.99/mo (75 RPM, 15-min delayed US data), $99.99/mo (150 RPM, real-time), $149.99/mo (300 RPM), up to $249.99/mo (1,200 RPM). All premium tiers remove the daily cap.
- **Reliability:** Official, NASDAQ-licensed, stable. The 25/day free cap makes it impractical as a primary price feed; best used selectively for its free indicators and news sentiment.
- **Python:** `pip install alpha_vantage` or `requests`.

#### Financial Modeling Prep (FMP)
- **Provides:** Real-time/historical prices, full financial statements (income, balance sheet, cash flow), calculated ratios, DCF, analyst estimates/ratings, earnings calendar, dividends calendar, economic calendar, social sentiment, sector performance, 30+ years history. Sourced from SEC EDGAR. Covers Domains 01, 02, 03, 05, 06.
- **Free-tier limits:** **250 requests/day**; 5 years of annual statements for US companies; 500MB trailing 30-day bandwidth. Some premium endpoints (earnings calendar, stock peers) require paid.
- **Rate limits:** 250/day free.
- **Reliability:** Official, developer-friendly, 30% student discount. Stable. Good fundamentals depth.
- **Python:** `requests` (no single canonical official package; community wrappers exist).

#### Twelve Data
- **Provides:** Time-series OHLCV (stocks, FX, crypto, ETFs, indices) 1-min to monthly, 30+ years EOD, technical indicators, WebSocket streaming (paid), fundamentals (paid tiers). Covers Domains 01, 08.
- **Free-tier limits:** **8 API credits/minute, 800/day**; US equities, FX, crypto.
- **Paid:** Grow $29/mo (55–377 calls/min, no daily cap), Pro $99/mo, Ultra $329/mo.
- **Reliability:** Official, 99.95% uptime SLA on top tier, well-documented. Personal plans are non-commercial.
- **Python:** `pip install twelvedata` or `requests`.

#### EOD Historical Data (EODHD)
- **Provides:** 30+ years EOD/intraday/live prices, fundamentals, options, macro indicators for 120,000+ global tickers; bulk downloads. Covers Domains 01, 03, 06.
- **Free-tier limits:** Limited demo; real value on paid.
- **Paid:** entry plan ~$19.99/mo. Strong value for global coverage and bulk historical downloads (good for backtesting large universes).
- **Reliability:** Official, France-based, well-rated. ToS-clean.
- **Python:** `requests` or community wrappers.

#### Stooq (via pandas-datareader)
- **Provides:** Free daily historical OHLCV for US and global stocks/indices, no API key. Covers Domain 01.
- **Free-tier limits:** No key required; reasonable for EOD history. Coverage and freshness less complete than paid sources.
- **Reliability:** Free public source, decent as a **backup/redundancy** to yfinance. Some symbols missing or stale.
- **Python:** `pandas_datareader.data.DataReader(ticker, "stooq")`.

#### FRED (Federal Reserve Economic Data) — Domain 04 backbone
- **Provides:** Per the FRED homepage, you can "Download, graph, and track 844,000 economic time series from 120 sources" — Fed funds rate, Treasury yields (DGS10, DGS2), yield-curve spread (T10Y2Y), CPI, PCE, unemployment (UNRATE), nonfarm payrolls, GDP, money supply, **and the VIX (VIXCLS, sourced from CBOE)**. Covers Domains 04 and 07.
- **Free-tier limits:** Entirely free; full history; requires a free API key.
- **Rate limits:** 120 requests/minute; up to 100,000 observations per request.
- **Reliability:** **Official, gold-standard, stable, legally clean.** The definitive free macro source.
- **Python:** `pip install fredapi`. Example:
```python
from fredapi import Fred
fred = Fred(api_key="YOUR_KEY")
ten_year = fred.get_series("DGS10")
curve    = fred.get_series("T10Y2Y")   # 10y-2y spread
vix      = fred.get_series("VIXCLS")
cpi      = fred.get_series("CPIAUCSL")
```
Alternative modern clients: `fedfred`, `full_fred`. World Bank, BLS, and BEA offer their own free APIs for deeper international/labor/GDP detail, but FRED mirrors most of what a swing trader needs in one place.

#### SEC EDGAR — Domain 06 backbone (insider + institutional + fundamentals)
- **Provides:** Every US public filing — 10-K/10-Q (income statement, balance sheet, cash flow via XBRL), 8-K, **Form 3/4/5 (insider transactions)**, **13F-HR (institutional holdings)**, 13D/G (activist stakes), DEF 14A, S-1. 20M+ filings back to 1994. Covers Domains 06 and fundamentals.
- **Free-tier limits:** Entirely free, official. 13F data carries the statutory ~45-day reporting lag (a fundamental limitation, not a vendor choice).
- **Rate limits:** SEC fair-access ~10 requests/second; must set a descriptive User-Agent header.
- **Reliability:** **Official, authoritative, free. The richest corporate-data source in the world.** Direct from the regulator.
- **Python:** `pip install edgartools` (best — parses to pandas DataFrames) or `sec-edgar-downloader`. Example:
```python
from edgar import Company, set_identity
set_identity("you@example.com")
form4 = Company("AAPL").get_filings(form="4")[0].obj()   # insider trades
balance = Company("AAPL").get_financials().balance_sheet()
```

#### FINRA — Short interest & short volume (Domain 06)
- **Provides:** Official **bi-monthly equity short interest** (per FINRA Rule 4560) and **daily short-sale volume files** (on-exchange + off-exchange/dark, by security). Covers the short-side of Domain 06.
- **Free-tier limits:** Free via FINRA Query API and downloadable pipe-delimited files; one rolling year online plus archives.
- **Reliability:** **Official regulator data.** Note the **inherent timeliness limitation**: short interest is published twice a month on a fixed schedule (settlement date + ~8 days), so it is never real-time. Daily short *volume* is more timely than short *interest*.
- **Python:** `requests` to `https://api.finra.org/data/group/otcMarket/name/EquityShortInterest` (POST with JSON filters), or download daily short-sale volume text files.

#### CBOE — VIX & volatility (Domain 07)
- **Provides:** Daily VIX history (1990–present), plus VVIX, VIX9D, VIX3M, sector/single-stock VIX, term structure. Free downloadable CSVs.
- **Reliability:** Official source of the VIX. For programmatic daily use, `FRED VIXCLS` or `yfinance ^VIX` are more convenient; CBOE is the authoritative archive and term-structure source.
- **Python:** `requests` to CBOE CSV URLs, or `fredapi`/`yfinance` for the headline index.

#### Nasdaq Data Link (formerly Quandl)
- **Provides:** Aggregator of financial/economic/alternative datasets. Some free (e.g., QDL publisher datasets, some macro); most premium datasets now paid. The old free WIKI EOD equity dataset is discontinued.
- **Free-tier limits:** Free datasets require a free key; equity EOD must be sourced elsewhere (XNAS premium).
- **Reliability:** Official (Nasdaq-owned). For a free swing system, less central than it once was — FRED + SEC + FINRA cover most of what Quandl's free tier used to.
- **Python:** `pip install nasdaq-data-link` (or legacy `quandl`).

#### News / Sentiment specialists
- **Marketaux:** Free tier **100 requests/day**; global financial news with entity recognition and ticker-level sentiment scores. `requests`. Good free secondary news/sentiment source.
- **NewsAPI:** General news, free tier for development (non-commercial, delayed), limited to older articles on free plan. Better for prototyping than production finance.
- **Tiingo News:** 50M+ articles, tagged to tickers; included with Tiingo account.
- **StockTwits:** Public unauthenticated stream endpoints (`api.stocktwits.com/api/2/streams/symbol/{SYM}.json`) provide recent messages, user bullish/bearish tags, and trending tickers — **free, no key for basic reads**, but undocumented/unofficial and subject to change/rate-limiting. The official developer program is limited.
- **Reddit:** via `praw` (free, requires free Reddit app credentials) for WallStreetBets mention/sentiment mining; `pytrends` (unofficial Google Trends) is a useful free retail-attention proxy.

#### Options data (Domain 06 / IV inputs for Domain 08)
- **yfinance options chains:** Free delayed chains with strikes, bid/ask, volume, OI, implied vol via `.option_chain()`. Best free option-chain source; brittle like all yfinance.
- **Tradier:** Brokerage API. **Sandbox provides FREE 15-minute-delayed market data and free options chains** (with Greeks/IV courtesy of ORATS); individual API tokens are free and never expire. Per Tradier's docs, "The sandbox is a paper trading account to test your integration with our API, including working with delayed market data" and data is delayed "the industry standard 15-minutes." Real-time data is tied to a funded production account (Tradier also offers a low-cost real-time Market Data add-on — commonly cited around $10/mo; verify current price on Tradier's pricing page). `requests`.
- **Polygon/Massive options:** Granular options trades/quotes/Greeks/IV back to 2014; Starter $29/mo gives 2 yrs options aggregates (delayed).
- **ORATS:** Options-specialist with computed Greeks, IV surface, IV rank, backtesting. **Individual plan $99/mo; Professional $299/mo; 14-day trial for $29; real-time/broker add-on +$50/mo.** Standalone historical data feeds priced separately ($199/mo intraday; ~$2,000 one-time for 2015–present history).

### "Hard or Impossible to Get Cheaply" — Difficult Factors & Workarounds

| Difficult factor | Why it's hard/expensive | Cheapest real option | Free proxy / workaround |
|---|---|---|---|
| **Real-time options flow** | Requires real-time OPRA feed + analytics; licensing is costly | Unusual Whales $48/mo (retail) or API $150–375/mo | Compute unusual volume vs. OI from yfinance/Polygon delayed chains; watch volume spikes |
| **Dark-pool prints (real-time)** | True ATS prints are licensed; real-time analytics are premium | Unusual Whales / Cheddar Flow (~$75/mo) | **FINRA off-exchange short-volume + ATS Transparency files (2-week delayed, free)**; flag days >1.5× 20-day avg |
| **Intraday tick / Level-2 data** | Exchange-licensed, bandwidth-heavy | Polygon/Massive Developer $79–99/mo | Not needed for daily-bar swing signals; use Finnhub limited intraday free |
| **Timely short interest** | FINRA publishes only bi-monthly by regulation | No vendor fixes the lag (it's regulatory) | Use FINRA **daily short-volume** files as a higher-frequency proxy |
| **Real-time Level 2 / order book** | Exchange depth-of-book licensing | Broker feed (e.g., IBKR) | Irrelevant to EOD swing system |
| **Professional-grade NLP sentiment** | RavenPack-class feeds cost thousands/month | Finnhub/Marketaux/AlphaVantage free sentiment | Roll your own VADER/FinBERT on free Finnhub/Marketaux headlines |
| **Congressional / insider alt-data, packaged** | Aggregation + cleaning is the product | QuiverQuant API $30 (Hobbyist) / $75 (Trader)/mo | Parse SEC Form 4 (insider) free via EdgarTools; Senate/House disclosures are public but messy |
| **13F real-time** | 45-day statutory filing lag | None | Accept the lag; it's structural |

**Bottom line on the hard factors:** For a daily-bar, signal-only swing system, the only genuinely valuable "premium" additions are (a) a clean ToS-safe price/fundamentals feed and (b) optionally one alt-data specialist for options flow or congressional/insider packaging. Everything else has a workable free proxy.

**Smart-money specialist pricing (2025/2026, for reference):**
- **Unusual Whales:** Retail web/app subscription **$48/mo** (~$528/yr; some sources cite $448/yr — confirm directly). Standalone developer **API is separate**: Basic $150/mo, Advanced $375/mo (effective May 27, 2025), $50/week trial; historical full-market option trades +$250/mo. Do not conflate the $48/mo consumer product with the $150–375/mo API.
- **QuiverQuant API:** Hobbyist (Tier 1 — congressional trading, government contracts, lobbying, off-exchange) **$30/mo** ($25/mo billed annually = $300/yr); Trader (Tier 1 & 2 — adds insider, hedge-fund 13F activity, ETF holdings, top shareholders, WSB sentiment) **$75/mo** ($62.50/mo annually = $750/yr); commercial use contact-priced. Website Premium plan ~$25/mo (annual).
- **ORATS:** Individual **$99/mo**, Professional **$299/mo**, 14-day trial $29, real-time/broker add-on +$50/mo.

### Recommended Stacks

#### MINIMAL FREE STACK ($0/month) — covers ~90% of factors
1. **yfinance** — daily OHLCV, dividends/splits, options chains, ^VIX, sector ETFs (Domains 01, 03, 05, 07, 08). *Backstop with Stooq via pandas-datareader for redundancy.*
2. **pandas-ta / TA-Lib** (local compute) — all technical indicators, beta, correlation, drawdown, position-sizing inputs (Domains 01, 08).
3. **FRED via fredapi** — all macro, yield curve, and VIX (Domains 04, 07).
4. **SEC EDGAR via edgartools** — fundamentals, insider Form 4, 13F institutional (Domain 06, fundamentals).
5. **FINRA** — short interest + daily short volume (Domain 06).
6. **Finnhub free (60/min)** — news, social sentiment, earnings calendar, insider sentiment, economic calendar (Domains 02, 03).
7. **Alpha Vantage free (25/day)** — supplementary NEWS_SENTIMENT and any indicators you'd rather not compute.

This stack leaves only real-time options flow and real-time dark-pool prints uncovered — both non-essential for daily swing signals (use FINRA proxies).

#### LOW-COST SCALE-UP STACK (~$30–50/month) — add as the account grows
- **First upgrade ($29/mo): Polygon.io/Massive Starter** — replaces yfinance as a reliable, ToS-clean primary price/options feed with unlimited calls and 5 years of history. This removes the single biggest fragility (yfinance breakage) in the free stack. *Alternatively Tiingo at $10–30/mo if you only need clean EOD prices + news.*
- **Second upgrade (+$30–75/mo): QuiverQuant API** — Hobbyist $30/mo (congressional trading, government contracts, lobbying, off-exchange) or Trader $75/mo (adds insider, hedge-fund 13F activity, ETF holdings, WSB sentiment). The cheapest way to get packaged smart-money alt-data.
- **Alternative second upgrade (+$48/mo): Unusual Whales retail** — if your edge thesis centers on options flow + dark-pool activity rather than congressional/insider data.
- **Keep Finnhub + FRED + SEC + FINRA free** in the stack regardless — paid tiers don't replace them.

**Total recommended scale-up: ~$30/mo (Polygon Starter alone) to ~$100/mo (Polygon + one alt-data specialist).** Stay below this until the account size and a validated edge justify ORATS ($99/mo) or Polygon Advanced ($199/mo, real-time).

## Recommendations
1. **Start today on the $0 stack.** Build your pipeline on yfinance + FRED + SEC EDGAR + FINRA + Finnhub. Compute indicators locally. This validates your signal logic at zero cost.
2. **Engineer for fragility from day one.** Wrap yfinance in a caching layer (store daily pulls to local Parquet/SQLite), add retry/backoff, and keep Stooq as a fallback. Assume yfinance *will* break periodically.
3. **First dollar spent → reliability, not exotic data.** When yfinance breakage becomes painful, the highest-ROI upgrade is Polygon/Massive Starter ($29/mo) or Tiingo ($10–30/mo) — a clean, legal primary feed. **Threshold: upgrade when you're trading real capital or yfinance outages cost you signals.**
4. **Only buy alt-data after a validated edge.** Don't pay for Unusual Whales/QuiverQuant/ORATS until backtests show options-flow or congressional/insider factors actually improve your signals. **Threshold: add one specialist ($30–75/mo) once a specific alt-data factor demonstrably lifts out-of-sample performance.**
5. **Respect Terms of Service as you scale.** yfinance is fine for a personal account; the moment you consider anything commercial (managing others' money, selling signals), migrate off scraped sources to licensed feeds (Polygon/Massive, Tiingo, Finnhub paid).
6. **Don't chase real-time.** For a few-days-to-a-month holding period on daily bars, 15-minute-delayed or EOD data is entirely sufficient. Real-time/tick/Level-2 feeds are a waste of money for this strategy.

## Caveats
- **Pricing and free-tier limits change frequently.** Alpha Vantage's free cap fell from 500 → 100 → 25 requests/day; Polygon rebranded to Massive (Oct 30, 2025) and restructured tiers; IEX Cloud shut down entirely (Aug 31, 2024). Verify current numbers on each provider's pricing page before committing.
- **yfinance legality is genuinely gray.** Yahoo's ToS prohibits automated scraping without permission. This guide treats it as acceptable for personal, non-commercial use only; it is not legal advice.
- **Some figures rely on third-party reviews** where official pricing pages render dynamically (notably Unusual Whales' exact annual price — sources conflict between $448 and $528/year — and Tradier's exact real-time Market Data add-on price). Confirm directly before purchase.
- **13F (45-day lag) and short interest (bi-monthly) timeliness limits are regulatory**, not vendor limitations — no amount of money removes them.
- **"Sentiment" quality varies enormously.** Free Finnhub/Marketaux/Alpha Vantage sentiment is lexicon/basic-ML grade, not RavenPack-class. Treat social sentiment as a contrarian/attention proxy, not a precise signal.
- This report assumes a daily-bar, signal-only, manual-execution workflow; conclusions about not needing real-time data would change for an intraday or automated-execution system.