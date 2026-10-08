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

@st.cache_resource
def get_yf_session():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    return session

yf_session = get_yf_session()

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
# 1. DYNAAMISET TICKER-HAUT
# -------------------------------------------------------------

@st.cache_data(ttl=86400)
def fetch_sp500_tickers():
    """Hakee S&P 500 -osakkeet dynaamisesti Wikipediasta."""
    try:
        r = requests.get('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        tables = pd.read_html(io.StringIO(r.text))
        return tables[0]['Symbol'].str.replace('.', '-', regex=False).tolist()
    except Exception:
        return ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "ADBE", "NKE", "SBUX", "LULU", "V", "MA", "COST", "CRM", "INTU", "QCOM", "UNH", "ZTS", "DVA", "AMP", "DECK", "CF", "CLX", "BMY", "ALL"]

@st.cache_data(ttl=86400)
def fetch_nordic_tickers():
    """Hakee Pohjoismaiden pörssilistat dynaamisesti avoimesta pörssidatasta."""
    url = 'https://raw.githubusercontent.com/alvarobartt/investpy/master/investpy/resources/stocks.csv'
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
        # Fallback jos raw GitHub ei vastaa
        return {
            "Suomi": ["NESTE.HE", "KNEBV.HE", "UPM.HE", "SAMPO.HE", "WRT1V.HE", "METSO.HE", "KESKOB.HE", "ELISA.HE", "VALMT.HE", "ORNBV.HE", "NOKIA.HE", "TIETO.HE", "HUH1V.HE", "MANTA.HE", "KCR.HE", "NDA-FI.HE", "HARVIA.HE", "QTCOM.HE", "REG1V.HE", "KEMPOWR.HE", "MEKKO.HE", "PUUILO.HE", "TOKMAN.HE", "OLVAS.HE"],
            "Ruotsi": ["ATCO-A.ST", "INVE-B.ST", "NIBE-B.ST", "ASSA-B.ST", "HEXA-B.ST", "EVO.ST", "SAND.ST", "VOLV-B.ST", "EPI-A.ST", "ALFA.ST", "HM-B.ST", "AZN.ST", "SWED-A.ST", "THULE.ST", "INDT.ST", "LATO-B.ST"],
            "Tanska": ["NOVO-B.CO", "DSV.CO", "COLO-B.CO", "ORSTED.CO", "DEMANT.CO", "VWS.CO", "PNDORA.CO", "ISS.CO"],
            "Norja": ["EQNR.OL", "KOG.OL", "TOM.OL", "MOWI.OL", "DNB.OL", "YAR.OL", "TEL.OL", "BOUV.OL"]
        }

# -------------------------------------------------------------
# 2. FUNDAMENTTIEN JA DIPPILUKUJEN ANALYYSI
# -------------------------------------------------------------

def analyze_ticker(sym, region):
    """Analysoi yksittäisen osakkeen fundamentit virhesuojatusti."""
    try:
        # KORJATTU RIVI: Lisätty istunnonhallinta, joka huijaa Yahoota luulemaan sovellusta selaimeksi
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

        # LISÄTTY RIVI: Pieni 0.2 sekunnin huilaustauko pyyntöjen väliin rinnakkaisajossa
        time.sleep(0.2)

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

# -------------------------------------------------------------
# 3. KOKO SKANNAUKSEN SUORITUS (VÄLIMUISTISSA)
# -------------------------------------------------------------

@st.cache_data(ttl=21600, show_spinner=False)
def run_cached_scan(selected_regions, min_mcap_millions=100):
    """Suorittaa täyden rinnakkaishaun ja tallentaa tulokset 6h välimuistiin."""
    sp500 = fetch_sp500_tickers()
    nordics = fetch_nordic_tickers()

    targets = []
    if "USA (S&P 500)" in selected_regions:
        for s in sp500:
            targets.append((s, "USA (S&P 500)"))
    for reg in ["Suomi", "Ruotsi", "Tanska", "Norja"]:
        if reg in selected_regions and reg in nordics:
            for s in nordics[reg]:
                targets.append((s, reg))

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        future_map = {executor.submit(analyze_ticker, s, r): s for s, r in targets}
        for future in concurrent.futures.as_completed(future_map):
            res = future.result()
            if res:
                # Suodatetaan mikroyhtiöt pois jos määritelty
                if res["Market Cap (M€/$)"] >= min_mcap_millions:
                    results.append(res)

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)

    # Synteesipisteet: 33.3% Fwd P/E 27 + 33.3% ROE + 33.3% Omistajapalautus
    def pe_to_score(v):
        try:
            val = float(v)
            return 1.0 / val if 0 < val < 80 else 0.0
        except: return 0.0

    df['_pe_s'] = df['_pe27'].apply(pe_to_score).rank(pct=True) * 100
    df['_roe_s'] = df['_roe'].apply(lambda v: max(float(v), 0) if pd.notna(v) and v != '-' else 0).rank(pct=True) * 100
    df['_yd_s'] = df['_yield'].apply(lambda v: max(float(v), 0) if pd.notna(v) and v != '-' else 0).rank(pct=True) * 100

    df['Synteesi (0-100)'] = (0.3333 * df['_pe_s'] + 0.3333 * df['_roe_s'] + 0.3334 * df['_yd_s']).round(1)

    df = df.drop(columns=['_pe27', '_roe', '_yield', '_mcap', '_pe_s', '_roe_s', '_yd_s']).sort_values(by="Synteesi (0-100)", ascending=False).reset_index(drop=True)
    return df

# -------------------------------------------------------------
# 4. STREAMLIT KÄYTTÖLIITTYMÄ
# -------------------------------------------------------------

st.title("🎯 Laatuyhtiöt Alennuksessa")
st.caption("Etsi tilapäisesti pudonneet laatuyhtiöt S&P 500:sta ja Pohjoismaista. Synteesipainotus: 33.3% P/E + 33.3% ROE + 33.3% Omistajapalautus.")

# Sivupalkin suodattimet
with st.sidebar:
    st.header("⚙️ Suodattimet")

    selected_markets = st.multiselect(
        "Valitse markkinat:",
        options=["USA (S&P 500)", "Suomi", "Ruotsi", "Tanska", "Norja"],
        default=["USA (S&P 500)", "Suomi", "Ruotsi", "Tanska", "Norja"]
    )

    min_mcap = st.slider("Minimi Markkina-arvo (M€/$):", min_value=50, max_value=2000, value=150, step=50,
                         help="Suodattaa kaikkein pienimmät mikroyhtiöt pois (Mid & Large Cap fokus).")

    min_drop_ath = st.slider("Minimi ATH-dippi (%):", min_value=-80, max_value=0, value=-15, step=5)
    max_pe27 = st.slider("Maksimi Fwd P/E 2027:", min_value=5.0, max_value=45.0, value=30.0, step=1.0)
    min_roe = st.slider("Minimi ROE (%):", min_value=0.0, max_value=35.0, value=10.0, step=1.0)

    st.divider()
    if st.button("🔄 Pakota päivitys (Tyhjennä välimuisti)", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# Ladataan data
with st.spinner("⚡ Haetaan ja analysoidaan pörssidatoja..."):
    df_raw = run_cached_scan(selected_markets, min_mcap_millions=min_mcap)

if df_raw.empty:
    st.warning("Ei dataa saatavilla tai valituilta markkinoilta ei löytynyt kohteita.")
    st.stop()

# Suodatetaan käyttäjän säätimien mukaan
df_filtered = df_raw.copy()

# 1. ATH Dippi
df_filtered = df_filtered[df_filtered['ATH Dippi (%)'] <= min_drop_ath]

# 2. P/E 27
def filter_pe(val):
    if val == "-": return True
    try: return float(val) <= max_pe27
    except: return True
df_filtered = df_filtered[df_filtered['Fwd P/E 27'].apply(filter_pe)]

# 3. ROE
def filter_roe(val):
    if val == "-": return False
    try: return float(val) >= min_roe
    except: return False
df_filtered = df_filtered[df_filtered['ROE (%)'].apply(filter_roe)]

# Mittaristokortit
col1, col2, col3, col4 = st.columns(4)
col1.metric("Skannatut yhtiöt", f"{len(df_raw)} kpl")
col2.metric("Kriteerit täyttävät", f"{len(df_filtered)} kpl")
if not df_filtered.empty:
    top_stock = df_filtered.iloc[0]['Symboli']
    avg_ath = round(df_filtered['ATH Dippi (%)'].mean(), 1)
    col3.metric("Kärkiyhtiö", top_stock)
    col4.metric("Keskidippi ATH:sta", f"{avg_ath} %")

st.divider()

# Hakukenttä
search_query = st.text_input("🔍 Etsi osaketta nimellä, symbolilla tai maalla:", placeholder="Esim. Novo, Adobe, Suomi...")
if search_query:
    q = search_query.lower()
    df_filtered = df_filtered[
        df_filtered['Symboli'].str.lower().str.contains(q) |
        df_filtered['Nimi'].str.lower().str.contains(q) |
        df_filtered['Alue'].str.lower().str.contains(q)
    ]

# Interaktiivinen taulukko
st.dataframe(
    df_filtered,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Symboli": st.column_config.TextColumn("Symboli", width="small"),
        "Synteesi (0-100)": st.column_config.ProgressColumn("Synteesi 🏆", min_value=0, max_value=100, format="%.1f"),
        "ATH Dippi (%)": st.column_config.NumberColumn("ATH Dippi 🔻", format="%.1f %%"),
        "52v Dippi (%)": st.column_config.NumberColumn("52v Dippi", format="%.1f %%"),
        "Omistajille TTM (%)": st.column_config.NumberColumn("Omistajille 🎁", format="%.2f %%"),
        "Fwd P/E 27": st.column_config.TextColumn("P/E 27 ⚡"),
        "Fwd P/E 28": st.column_config.TextColumn("P/E 28 🔮"),
        "ROE (%)": st.column_config.TextColumn("ROE ⭐"),
    }
)

# Lataus CSV:ksi
csv = df_filtered.to_csv(index=False).encode('utf-8-sig')
st.download_button(
    label="📥 Lataa tulokset Excel/CSV-tiedostona",
    data=csv,
    file_name=f"laatuyhtiot_{datetime.now().strftime('%Y%m%d')}.csv",
    mime="text/csv",
    use_container_width=True
)
