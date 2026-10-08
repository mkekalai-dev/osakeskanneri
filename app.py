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
# SUOJATTU ISTUNNONHALLINTA (Estää Yahoo 429 -bännit)
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
    """Hakee Pohjoismaiden pörssilistat fallback-valmiudella."""
    return {
        "Suomi": ["NESTE.HE", "KNEBV.HE", "UPM.HE", "SAMPO.HE", "WRT1V.HE", "METSO.HE", "KESKOB.HE", "ELISA.HE", "VALMT.HE", "ORNBV.HE", "NOKIA.HE", "TIETO.HE", "HUH1V.HE", "KCR.HE", "NDA-FI.HE", "HARVIA.HE", "QTCOM.HE", "KEMPOWR.HE", "MEKKO.HE", "PUUILO.HE", "TOKMAN.HE", "OLVAS.HE"],
        "Ruotsi": ["ATCO-A.ST", "INVE-B.ST", "NIBE-B.ST", "ASSA-B.ST", "HEXA-B.ST", "EVO.ST", "SAND.ST", "VOLV-B.ST", "EPI-A.ST", "ALFA.ST", "HM-B.ST", "AZN.ST", "SWED-A.ST", "THULE.ST", "INDT.ST", "LATO-B.ST"],
        "Tanska": ["NOVO-B.CO", "DSV.CO", "COLO-B.CO", "ORSTED.CO", "DEMANT.CO", "VWS.CO", "PNDORA.CO", "ISS.CO"],
        "Norja": ["EQNR.OL", "KOG.OL", "TOM.OL", "MOWI.OL", "DNB.OL", "YAR.OL", "TEL.OL", "BOUV.OL"]
    }

# -------------------------------------------------------------
# 2. FUNDAMENTTIEN JA DIPPILUKUJEN ANALYYSI (Optimoitu välimuistilla)
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

        # Forward P/E
        pe27 = None
        if i.get('forwardPE'):
            pe27 = round(i.get('forwardPE'), 1)

        # Omistajapalautus TTM (Osingot + Ostot)
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

        # Jos kassavirtadataa ei saatu, käytetään perusosinkotuottoa
        if tot_yield == 0.0 and i.get('dividendYield'):
            tot_yield = round(i.get('dividendYield') * 100, 2)
            div_y = tot_yield

        name = i.get('shortName') or i.get('longName') or sym
        currency = i.get('currency', '')

        time.sleep(0.1) # Pieni tauko suojaksi

        return {
            "Symboli": sym,
            "Nimi": name.strip()[:24],
            "Alue": region,
            "Hinta": f"{round(price, 2)} {currency}",
            "Market Cap (M€/$)": round(market_cap / 1_000_000, 0) if market_cap else 0,
            "ATH Dippi (%)": d_ath,
            "52v Dippi (%)": d52,
            "Fwd P/E 27": pe27 if pe27 else "-",
            "ROE (%)": roe_val if roe_val is not None else "-",
            "Liikevoitto-%": op_margin_val if op_margin_val is not None else "-",
            "Omistajille TTM (%)": tot_yield,
            "_pe27": pe27,
            "_roe": roe_val,
            "_yield": tot_yield
        }
    except Exception:
        return None

# -------------------------------------------------------------
# 3. KÄYTTÖLIITTYMÄ JA METODOLOGIA
# -------------------------------------------------------------

st.title("🎯 Laatuyhtiöt Alennuksessa")
st.subheader("Etsi markkinoiden parhaat yhtiöt, jotka treedaavat merkittävällä alennuksella")

# Sivupalkin valinnat
st.sidebar.header("Skannerin Asetukset")
market_selection = st.sidebar.multiselect(
    "Valitse Markkinat",
    ["S&P 500", "Suomi", "Ruotsi", "Tanska", "Norja"],
    default=["Suomi", "S&P 500"]
)

min_roe = st.sidebar.slider("Minimi ROE (%)", -10, 40, 10)
max_pe = st.sidebar.slider("Maksimi Forward P/E", 5, 50, 25)
min_dip = st.sidebar.slider("Minimi ATH Dippi (%)", -80, 0, -10)

# Kerätään valitut tickerit
tickers_to_scan = []

if "S&P 500" in market_selection:
    with st.spinner("Haetaan S&P 500 osakkeita..."):
        tickers_to_scan.extend([(sym, "S&P 500") for sym in fetch_sp500_tickers()[:60]]) # Rajoitetaan alkuun 60:een nopeuden vuoksi

nordic = fetch_nordic_tickers()
for m in ["Suomi", "Ruotsi", "Tanska", "Norja"]:
    if m in market_selection:
        tickers_to_scan.extend([(sym, m) for sym in nordic[m]])

if not tickers_to_scan:
    st.warning("Valitse vähintään yksi markkina-alue sivupalkista.")
else:
    st.info(f"Skannataan yhteensä {len(tickers_to_scan)} osaketta rinnakkain...")
    
    results = []
    # Suoritetaan haut tehokkaasti concurrent.futures -kirjastolla
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_ticker = {executor.submit(analyze_ticker, sym, reg): sym for sym, reg in tickers_to_scan}
        
        progress_bar = st.progress(0)
        completed = 0
        total = len(tickers_to_scan)
        
        for future in concurrent.futures.as_completed(future_to_ticker):
            res = future.result()
            if res:
                results.append(res)
            completed += 1
            progress_bar.progress(completed / total)
            
    if results:
        df = pd.DataFrame(results)
        
        # Suodatetaan tyhjät arvot pois numeerisista laskuista
        df_filtered = df.copy()
        
        # Käytetään suodatuksessa taustamuuttujia
        df_filtered = df_filtered[df_filtered['_roe'].apply(lambda x: x is not None and x >= min_roe)]
        df_filtered = df_filtered[df_filtered['_pe27'].apply(lambda x: x is not None and x <= max_pe)]
        df_filtered = df_filtered[df_filtered['ATH Dippi (%)'] <= min_dip]
        
        # -------------------------------------------------------------
        # 4. 33.3% SYNTEESIPISTEYTYS
        # -------------------------------------------------------------
        if not df_filtered.empty:
            # P/E Pisteet (pienempi parempi)
            df_filtered['pe_rank'] = df_filtered['_pe27'].rank(ascending=True)
            # ROE Pisteet (suurempi parempi)
            df_filtered['roe_rank'] = df_filtered['_roe'].rank(ascending=False)
            # Omistajapalautus Pisteet (suurempi parempi)
            df_filtered['yield_rank'] = df_filtered['_yield'].rank(ascending=False)
            
# Yhdistetty synteesipiste (pienempi kokonaissumma = parempi)
df_filtered['Synteesipisteet'] = round((df_filtered['pe_rank'] + df_filtered['roe_rank'] + df_filtered['yield_rank']) / 3, 1)
# Järjestetään parhaat ensin
df_filtered = df_filtered.sort_values(by='Synteesipisteet')
# Siistitään lopullinen näkymä käyttäjälle
output_cols = [
"Synteesipisteet", "Symboli", "Nimi", "Alue", "Hinta",
"Market Cap (M€/$)", "ATH Dippi (%)", "52v Dippi (%)",
"Fwd P/E 27", "ROE (%)", "Liikevoitto-%", "Omistajille TTM (%)"
]
st.success(f"Löydettiin {len(df_filtered)} kriteerit täyttävää laatuyhtiötä!")
st.dataframe(df_filtered[output_cols], use_container_width=True, hide_index=True)
else:
st.warning("Yksikään osake ei täyttänyt asetettuja suodatuskriteerejä. Löysennä sivupalkin arvoja.")
else:
st.error("Datan haku epäonnistui. Yahoo Finance saattaa yhä rajoittaa yhteyksiä Streamlit-palvelimelta.")
