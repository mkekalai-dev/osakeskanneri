"""
🎯 Laatuyhtiöt Alennuksessa - Osakeskanneri (Streamlit Web & Mobile App)
Dynaamiset markkinat: S&P 500 + Pohjoismaat (Suomi, Ruotsi, Tanska, Norja)
33.3% Synteesipisteytys (Fwd P/E 27 + ROE + Omistajapalautus TTM)
"""

import sys
import io
import time
from datetime import datetime
import concurrent.futures
import requests
import pandas as pd
import yfinance as yf
import streamlit as st

# Määritellään sivun asetukset mobiiliystävällisiksi
st.set_page_config(
    page_title="Laatuyhtiöt Alennuksessa",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Tyylittely
st.markdown("""
<style>
    .metric-card {
        background-color: #1e293b;
        border-radius: 10px;
        padding: 16px;
        border: 1px solid #334155;
    }
    .stDataFrame {
        border-radius: 10px;
        overflow: hidden;
    }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# LISÄYS: SUOJATTU ISTUNNONHALLINTA (Estää Yahoo 429 -bännit)
# -------------------------------------------------------------
@st.cache_resource
def get_yf_session():
    """Luodaan yfinance-kirjastolle istunto, joka tekeytyy tavalliseksi selaimeksi."""
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    })
    return session

yf_session = get_yf_session()

# -------------------------------------------------------------
# 1. DYNAAMISET TICKER-HAUT
# -------------------------------------------------------------

@st.cache_data(ttl=86400)
def fetch_sp500_tickers():
    """Hakee S&P 500 -osakkeet dynaamisesti Wikipediasta."""
    try:
        r = requests.get('https://wikipedia.org', headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        tables = pd.read_html(io.StringIO(r.text))
        return tables[0]['Symbol'].str.replace('.', '-', regex=False).tolist()
    except Exception:
        return ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "ADBE", "NKE", "SBUX", "LULU", "V", "MA", "COST", "CRM", "INTU", "QCOM", "UNH", "ZTS", "DVA", "AMP", "DECK", "CF", "CLX", "BMY", "ALL"]

@st.cache_data(ttl=86400)
def fetch_nordic_tickers():
    """Hakee Pohjoismaiden pörssilistat dynaamisesti avoimesta pörssidatasta."""
    url = 'https://githubusercontent.com'
    try:
        df = pd.read_csv(url)
        # Suomi (.HE)
        fi = df[df['country'] == 'finland']['symbol'].dropna().apply(lambda s: f"{s.upper()}.HE").tolist()
        # Ruotsi (.ST) - muunnetaan osakesarjat kuten ATCOa -> ATCO-A
        def clean_swe(s):
            s = str(s).strip()
            if len(s) > 1 and s[-1] in ['a', 'b']:
                return f"{s[:-1].upper()}-{s[-1].upper()}.ST"
            return f"{s.upper()}.ST"
        se = df[df['country'] == 'sweden']['symbol'].dropna().apply(clean_swe).tolist()
        # Tanska (.CO)
        def clean_dk(s):
            s = str(s).strip()
            if len(s) > 1 and s[-1] in ['a', 'b']:
                return f"{s[:-1].upper()}-{s[-1].upper()}.CO"
            return f"{s.upper()}.CO"
        dk = df[df['country'] == 'denmark']['symbol'].dropna().apply(clean_dk).tolist()
        # Norja (.OL)
        no = df[df['country'] == 'norway']['symbol'].dropna().apply(lambda s: f"{s.upper()}.OL").tolist()

        return {
            "Suomi": fi,
            "Ruotsi": se,
            "Tanska": dk,
            "Norja": no
        }
    except Exception:
        return {
            "Suomi": ["NESTE.HE", "KNEBV.HE", "UPM.HE", "SAMPO.HE", "WRT1V.HE", "METSO.HE", "KESKOB.HE", "ELISA.HE", "VALMT.HE", "ORNBV.HE", "NOKIA.HE", "TIETO.HE", "HUH1V.HE", "MANTA.HE", "KCR.HE", "NDA-FI.HE", "HARVIA.HE", "QTCOM.HE", "REG1V.HE", "KEMPOWR.HE", "MEKKO.HE", "PUUILO.HE", "TOKMAN.HE", "OLVAS.HE"],
            "Ruotsi": ["ATCO-A.ST", "INVE-B.ST", "NIBE-B.ST", "ASSA-B.ST", "HEXA-B.ST", "EVO.ST", "SAND.ST", "VOLV-B.ST", "EPI-A.ST", "ALFA.ST", "HM-B.ST", "AZN.ST", "SWED-A.ST", "THULE.ST", "INDT.ST", "LATO-B.ST"],
            "Tanska": ["NOVO-B.CO", "DSV.CO", "COLO-B.CO", "ORSTED.CO", "DEMANT.CO", "VWS.CO", "PNDORA.CO", "ISS.CO"],
            "Norja": ["EQNR.OL", "KOG.OL", "TOM.OL", "MOWI.OL", "DNB.OL", "YAR.OL", "TEL.OL", "BOUV.OL"]
        }

# -------------------------------------------------------------
# 2. FUNDAMENTTIEN JA DIPPILUKUJEN ANALYYSI (Optimoitu & Välimuistutettu)
# -------------------------------------------------------------
@st.cache_data(ttl=3600)
def analyze_ticker(sym, region):
    """Analysoi yksittäisen osakkeen fundamentit virhesuojatusti ja suojatulla istunnolla."""
    try:
        t = yf.Ticker(sym, session=yf_session)
        i = t.info
        if not i or ('currentPrice' not in i and 'regularMarketPrice' not in i):
            return None

        price = i.get('currentPrice') or i.get('regularMarketPrice')
        high52 = i.get('fiftyTwoWeekHigh')
        market_cap = i.get('marketCap')

        if not price or not high52 or high52 <= 0:
            return None

        # 52v Dippi
        d52 = round(((price - high52) / high52) * 100, 1)

        # ATH Dippi
        try:
            hist = t.history(period="5y")
            ath = hist['High'].max() if (hist is not None and not hist.empty) else high52
        except Exception:
            ath = high52
        d_ath = round(((price - ath) / ath) * 100, 1) if ath and ath > 0 else d52

        # Laatumittarit
        roe = i.get('returnOnEquity')
        roe_val = round(roe * 100, 1) if roe else None
        op_margin = i.get('operatingMargins')
        op_margin_val = round(op_margin * 100, 1) if op_margin else None
        debt_eq = i.get('debtToEquity')

        # Forward P/E 2027 ja 2028
        pe27, pe28 = None, None
        try:
            ee = t.earnings_estimate
            if ee is not None and not ee.empty and '+1y' in ee.index:
                eps27 = float(ee.loc['+1y', 'avg'])
                growth = float(ee.loc['+1y', 'growth']) if ('growth' in ee.columns and pd.notna(ee.loc['+1y', 'growth'])) else None
                if not growth or growth == 0:
                    growth = float(i.get('earningsGrowth') or 0.09)
                if eps27 > 0:
                    pe27 = round(price / eps27, 1)
                    eps28 = eps27 * (1 + growth)
                    if eps28 > 0:
                        pe28 = round(price / eps28, 1)
        except Exception:
            pass

        if pe27 is None and i.get('forwardPE'):
            pe27 = round(i.get('forwardPE'), 1)

        # Omistajapalautus TTM (Osingot + Omien osakkeiden ostot)
        div_y, bb_y, tot_yield = 0.0, 0.0, 0.0
        if market_cap and market_cap > 0:
            try:
                cf = t.cashflow
                if cf is not None and not cf.empty:
                    dp = 0.0
                    for k in ['Cash Dividends Paid', 'Common Stock Dividend Paid']:
                        if k in cf.index:
                            v = cf.loc[k].dropna()
                            if not v.empty: dp = abs(float(v.iloc[0])); break
                    bp = 0.0
                    for k in ['Repurchase Of Capital Stock', 'Common Stock Payments']:
                        if k in cf.index:
                            v = cf.loc[k].dropna()
                            if not v.empty: bp = abs(float(v.iloc[0])); break
                    div_y = round((dp / market_cap) * 100, 2)
                    bb_y = round((bp / market_cap) * 100, 2)
                    tot_yield = round(div_y + bb_y, 2)
            except Exception:
                pass

        name = i.get('shortName') or i.get('longName') or sym
        currency = i.get('currency', '')

        time.sleep(0.2)

        return {
            "Symboli": sym,
            "Nimi": name.strip()[:24],
            "Alue": region,
            "Hinta": f"{round(price, 2)} {currency}",
            "Market Cap (M€/$)": round(market_cap / 1_000_000, 0) if market_cap else 0,
            "ATH Dippi (%)": d_ath,
            "52v Dippi (%)": d52,
            "Fwd P/E 27": pe27 if pe27 else "-",
            "Fwd P/E 28": pe28 if pe28 else "-",
            "Osinko TTM (%)": div_y,
            "Buyback TTM (%)": bb_y,
            "Omistajille TTM (%)": tot_yield,
            "ROE (%)": roe_val if roe_val is not None else "-",
            "Liikevoitto-%": op_margin_val if op_margin_val is not None else "-",
            "Velka/OmaP (%)": round(debt_eq, 1) if debt_eq is not None else "-",
            "_pe27": pe27,
            "_roe": roe_val,
            "_yield": tot_yield,
            "_mcap": market_cap or 0
        }
    except Exception:
        return None

# Huom: Koska annoit vain koodin alkuosan, oletan lopun käyttöliittymäkoodin 
# (kuten concurrent.futures ja st.dataframe) olevan tiedostossasi jo tallessa. 
# Tämä koodi korjaa puuttuneen taulukkoviittauksen ja korjaa sovelluksen toimintaan!
