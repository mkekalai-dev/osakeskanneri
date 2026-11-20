"""
🎯 Laatuyhtiöt Alennuksessa - Osakeskanneri (Streamlit Web & Mobile App)
Dynaamiset markkinat: S&P 500 + Pohjoismaat (Suomi, Ruotsi, Tanska, Norja)
33.3% Synteesipisteytys (Fwd P/E 27 + ROE + Omistajapalautus TTM)
UUTTA: Interaktiivinen AI-Yhteenveto valitusta osakkeesta:
- 3v toteutuneet talousluvut
- 2v konsensusennusteet
- Vahvuudet, heikkoudet ja sijoituspäätelmät
"""

import sys
import io
import os
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
    .ai-box {
        background-color: #0f172a;
        border: 1px solid #38bdf8;
        border-radius: 12px;
        padding: 20px;
        margin-top: 15px;
        margin-bottom: 25px;
        color: #f8fafc;
        line-height: 1.6;
    }
    .strength-card {
        background-color: rgba(16, 185, 129, 0.12);
        border-left: 4px solid #10b981;
        padding: 14px;
        border-radius: 8px;
        margin-bottom: 12px;
    }
    .weakness-card {
        background-color: rgba(239, 68, 68, 0.12);
        border-left: 4px solid #ef4444;
        padding: 14px;
        border-radius: 8px;
        margin-bottom: 12px;
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
        # Ruotsi (.ST)
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
# 2. FUNDAMENTTIEN JA DIPPILUKUJEN ANALYYSI
# -------------------------------------------------------------

def analyze_ticker(sym, region):
    """Analysoi yksittäisen osakkeen fundamentit virhesuojatusti."""
    try:
        t = yf.Ticker(sym)
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

        return {
            "Symboli": sym,
            "Nimi": name.strip()[:24],
            "Alue": region,
            "Hinta": f"{round(price, 2)} {currency}",
            "Market Cap (M€/$)": round(market_cap / 1_000_000, 0) if market_cap else 0,
            "ATH Dippi (%)": d_ath,
            "52v Dippi (%)": d52,
            "Fwd P/E 27": str(pe27) if pe27 else "-",
            "Fwd P/E 28": str(pe28) if pe28 else "-",
            "Osinko TTM (%)": div_y,
            "Buyback TTM (%)": bb_y,
            "Omistajille TTM (%)": tot_yield,
            "ROE (%)": str(roe_val) if roe_val is not None else "-",
            "Liikevoitto-%": str(op_margin_val) if op_margin_val is not None else "-",
            "Velka/OmaP (%)": str(round(debt_eq, 1)) if debt_eq is not None else "-",
            "_pe27": pe27,
            "_roe": roe_val,
            "_yield": tot_yield,
            "_mcap": market_cap or 0
        }
    except Exception:
        return None

# -------------------------------------------------------------
# 3. KOKO SKANNAUKSEN SUORITUS (VÄLIMUISTISSA + FALLBACK)
# -------------------------------------------------------------

@st.cache_data(ttl=21600, show_spinner=False)
def run_cached_scan(selected_regions, min_mcap_millions=100):
    """Suorittaa haun tai käyttää valmiiksi tallennettua dataa fallbackina."""
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
    # Rinnakkaishaku
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
            future_map = {executor.submit(analyze_ticker, s, r): s for s, r in targets}
            for future in concurrent.futures.as_completed(future_map):
                res = future.result()
                if res and res["Market Cap (M€/$)"] >= min_mcap_millions:
                    results.append(res)
    except Exception:
        pass

    # Jos livehaku palauttaa vähän tuloksia (esim. rate limit), ladataan aiemmin tallennettu CSV
    if len(results) < 10 and os.path.exists("synteesi_sp500_nordic.csv"):
        try:
            cached_df = pd.read_csv("synteesi_sp500_nordic.csv")
            # Muutetaan sarakkeet string-tyyppisiksi PyArrow-yhteensopivuuden takaamiseksi
            for col in ['Fwd P/E 27', 'Fwd P/E 28', 'ROE (%)', 'Liikevoitto-%', 'Velka/OmaP (%)']:
                if col in cached_df.columns:
                    cached_df[col] = cached_df[col].astype(str)
            return cached_df
        except Exception:
            pass

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
    
    # Varmistetaan että kaikki tekstisarakkeet ovat puhtaita stringejä PyArrow-virheiden estämiseksi
    for col in ['Fwd P/E 27', 'Fwd P/E 28', 'ROE (%)', 'Liikevoitto-%', 'Velka/OmaP (%)']:
        if col in df.columns:
            df[col] = df[col].astype(str)
            
    return df

# -------------------------------------------------------------
# 4. YKSITYISKOHTAINEN TALOUSDATA JA AI-ANALYYSI
# -------------------------------------------------------------

@st.cache_data(ttl=7200, show_spinner=False)
def get_company_deep_dive(symbol, fallback_row=None):
    """Hakee 3 vuoden historiatiedot, 2 vuoden ennusteet ja yhtiön profiilin."""
    try:
        t = yf.Ticker(symbol)
        info = t.info or {}
        
        # Historiatiedot (3 viimeistä tilikautta)
        hist_data = []
        try:
            inc = t.income_stmt
            if inc is not None and not inc.empty:
                cols = [c for c in inc.columns][:3]
                cols.reverse()  # Vanhimmasta uusimpaan
                for c in cols:
                    year_str = str(c)[:4]
                    rev = inc.loc['Total Revenue', c] if 'Total Revenue' in inc.index else None
                    op_inc = inc.loc['Operating Income', c] if 'Operating Income' in inc.index else None
                    net_inc = inc.loc['Net Income Common Stockholders', c] if 'Net Income Common Stockholders' in inc.index else (inc.loc['Net Income', c] if 'Net Income' in inc.index else None)
                    eps = inc.loc['Diluted EPS', c] if 'Diluted EPS' in inc.index else None
                    
                    op_m = f"{round((op_inc / rev) * 100, 1)} %" if (rev and op_inc and rev > 0) else "-"
                    net_m = f"{round((net_inc / rev) * 100, 1)} %" if (rev and net_inc and rev > 0) else "-"
                    
                    hist_data.append({
                        "Vuosi": year_str,
                        "Liikevaihto (M)": f"{round(rev / 1_000_000, 1):,}" if rev else "-",
                        "Liikevoitto (M)": f"{round(op_inc / 1_000_000, 1):,}" if op_inc else "-",
                        "Nettotulos (M)": f"{round(net_inc / 1_000_000, 1):,}" if net_inc else "-",
                        "EPS": str(round(eps, 2)) if eps else "-",
                        "Liikevoitto-%": op_m,
                        "Nettomarginaali-%": net_m
                    })
        except Exception:
            pass
            
        df_hist = pd.DataFrame(hist_data)
        
        # Ennusteet (seuraavat 2 vuotta)
        est_data = []
        try:
            ee = t.earnings_estimate
            re = t.revenue_estimate
            periods = ['0y', '+1y']
            period_labels = ["Kuluva vuosi (Ennuste)", "Seuraava vuosi (+2v Ennuste)"]
            
            for p, label in zip(periods, period_labels):
                row = {"Jakso": label}
                if re is not None and not re.empty and p in re.index:
                    r_avg = re.loc[p, 'avg'] if 'avg' in re.columns else None
                    r_growth = re.loc[p, 'growth'] if 'growth' in re.columns else None
                    row["Liikevaihtoennuste (M)"] = f"{round(r_avg / 1_000_000, 1):,}" if r_avg else "-"
                    row["Liikevaihdon kasvu"] = f"{round(r_growth * 100, 1)}%" if (pd.notna(r_growth) and r_growth is not None) else "-"
                else:
                    row["Liikevaihtoennuste (M)"] = "-"
                    row["Liikevaihdon kasvu"] = "-"
                    
                if ee is not None and not ee.empty and p in ee.index:
                    e_avg = ee.loc[p, 'avg'] if 'avg' in ee.columns else None
                    e_growth = ee.loc[p, 'growth'] if 'growth' in ee.columns else None
                    row["EPS-ennuste"] = str(round(e_avg, 2)) if e_avg else "-"
                    row["EPS:n kasvu"] = f"{round(e_growth * 100, 1)}%" if (pd.notna(e_growth) and e_growth is not None) else "-"
                else:
                    row["EPS-ennuste"] = "-"
                    row["EPS:n kasvu"] = "-"
                    
                est_data.append(row)
        except Exception:
            pass
            
        df_est = pd.DataFrame(est_data)
        
        # Luodaan fallback-arvot jos info-kutsu on vajaa
        name = info.get('longName') or info.get('shortName') or (fallback_row['Nimi'] if fallback_row is not None else symbol)
        price = info.get('currentPrice') or info.get('regularMarketPrice') or (fallback_row['Hinta'] if fallback_row is not None else "-")
        currency = info.get('currency', '')
        
        return {
            "symbol": symbol,
            "name": name,
            "sector": info.get('sector', 'Toimiala ei saatavilla'),
            "industry": info.get('industry', 'Sektori ei saatavilla'),
            "summary": info.get('longBusinessSummary') or 'Yhtiö on pörssinoteerattu laatuyhtiö.',
            "price": price,
            "currency": currency,
            "market_cap": info.get('marketCap') or (fallback_row['Market Cap (M€/$)'] if fallback_row is not None else "-"),
            "pe": info.get('trailingPE') or "-",
            "fwd_pe": info.get('forwardPE') or (fallback_row['Fwd P/E 27'] if fallback_row is not None else "-"),
            "fwd_pe28": fallback_row['Fwd P/E 28'] if fallback_row is not None else "-",
            "peg": info.get('pegRatio') or "-",
            "roe": info.get('returnOnEquity') or (float(fallback_row['ROE (%)'])/100 if fallback_row is not None and fallback_row['ROE (%)'] != '-' else None),
            "debt_to_equity": info.get('debtToEquity') or (fallback_row['Velka/OmaP (%)'] if fallback_row is not None else "-"),
            "dividend_yield": info.get('dividendYield') or (float(fallback_row['Osinko TTM (%)'])/100 if fallback_row is not None and 'Osinko TTM (%)' in fallback_row else None),
            "buyback_yield": fallback_row['Buyback TTM (%)'] if fallback_row is not None and 'Buyback TTM (%)' in fallback_row else 0.0,
            "total_yield": fallback_row['Omistajille TTM (%)'] if fallback_row is not None and 'Omistajille TTM (%)' in fallback_row else "-",
            "ath_drop": fallback_row['ATH Dippi (%)'] if fallback_row is not None else "-",
            "52w_drop": fallback_row['52v Dippi (%)'] if fallback_row is not None else "-",
            "df_hist": df_hist,
            "df_est": df_est
        }
    except Exception:
        # Täydellinen suojaus: käytetään taulukon valmiita lukuja
        return {
            "symbol": symbol,
            "name": fallback_row['Nimi'] if fallback_row is not None else symbol,
            "sector": "Pörssiyhtiö",
            "industry": fallback_row['Alue'] if fallback_row is not None else "Osakemarkkinat",
            "summary": f"{symbol} on seurantalistan kriteerit täyttävä laatuyhtiö.",
            "price": fallback_row['Hinta'] if fallback_row is not None else "-",
            "currency": "",
            "market_cap": fallback_row['Market Cap (M€/$)'] if fallback_row is not None else "-",
            "pe": "-",
            "fwd_pe": fallback_row['Fwd P/E 27'] if fallback_row is not None else "-",
            "fwd_pe28": fallback_row['Fwd P/E 28'] if fallback_row is not None else "-",
            "peg": "-",
            "roe": float(fallback_row['ROE (%)'])/100 if fallback_row is not None and fallback_row['ROE (%)'] != '-' else None,
            "debt_to_equity": fallback_row['Velka/OmaP (%)'] if fallback_row is not None else "-",
            "dividend_yield": float(fallback_row['Osinko TTM (%)'])/100 if fallback_row is not None and 'Osinko TTM (%)' in fallback_row else None,
            "buyback_yield": fallback_row['Buyback TTM (%)'] if fallback_row is not None and 'Buyback TTM (%)' in fallback_row else 0.0,
            "total_yield": fallback_row['Omistajille TTM (%)'] if fallback_row is not None else "-",
            "ath_drop": fallback_row['ATH Dippi (%)'] if fallback_row is not None else "-",
            "52w_drop": fallback_row['52v Dippi (%)'] if fallback_row is not None else "-",
            "df_hist": pd.DataFrame(),
            "df_est": pd.DataFrame()
        }

def generate_gemini_analysis(data, api_key=None):
    """Luo kattavan AI-yhteenvedon Gemini-mallilla tai älykkäällä sääntöpohjaisella moottorilla."""
    if not data:
        return "Tietoja ei voitu noutaa."

    # Jos API-avain on annettu, kutsutaan Google Geminiä
    if api_key and api_key.strip():
        try:
            prompt = f"""
Olet kokenut osakeanalyytikko ja salkunhoitaja. Laadi suomeksi asiantunteva, terävä ja selkeä sijoitusyhteenveto seuraavasta pörssiyhtiöstä:

YHTIÖN PERUSTIEDOT:
- Nimi: {data['name']} ({data['symbol']})
- Toimiala & Sektori: {data['industry']} | {data['sector']}
- Nykykurssi: {data['price']} (ATH-dippi: {data['ath_drop']}%, 52v-dippi: {data['52w_drop']}%)
- Arvostus: Fwd P/E 2027: {data['fwd_pe']}, Fwd P/E 2028: {data['fwd_pe28']}
- ROE: {round(data['roe']*100, 1) if data['roe'] else '-'}%
- Velkaantumisaste (Debt/Equity): {data['debt_to_equity']}%
- Pääomanpalautus (Osinko + Buyback): {data['total_yield']}%

LIIKETOIMINTAKUVAUS:
{data['summary'][:600]}...

TALOUSLUVUT VIIMEISELTÄ 3 VUODELTA:
{data['df_hist'].to_markdown(index=False) if not data['df_hist'].empty else 'Ei yksityiskohtaista historiataulukkoa saatavilla'}

ENNUSTEET SEURAAVALLE 2 VUODELLE:
{data['df_est'].to_markdown(index=False) if not data['df_est'].empty else 'Ei yksityiskohtaista ennustetaulukkoa saatavilla'}

Laadi vastaus seuraavalla selkeällä rakenteella:
### 1. 🏢 Liiketoimintamalli ja asema markkinassa
(Tiivis selostus: miten yritys tekee rahaa ja mikä on sen asema toimialallaan)

### 2. 📊 Taloudellinen kehitys ja ennusteet
(Analysoi 3v toteutunutta tulosta ja 2v ennusteita: miten liikevaihto, tulos ja marginaalit ovat kehittyneet ja miltä tulevaisuus näyttää)

### 3. 💪 Keskeiset vahvuudet (Moat & Kilpailuedut)
- Listaa 3-4 konkreettista vahvuutta (esim. hinnoitteluvoima, pääoman tuotto, kassa, vallihauta, omien ostot)

### 4. ⚠️ Keskeiset heikkoudet ja riskit
- Listaa 3-4 konkreettista riskiä/heikkoutta (esim. toimialan syklisyys, velkaantuneisuus, kilpailu, miksi kurssi on laskenut)

### 5. ⚖️ Sijoittajan yhteenveto & Punninta
(Objektiivinen arvio: millaiselle sijoittajalle osake sopii ja onko nykyinen dippi houkutteleva ostopaikka)
"""
            # 1. Yritetään uutta virallista google.genai -kirjastoa
            try:
                from google import genai
                client = genai.Client(api_key=api_key.strip())
                resp = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt
                )
                if resp and resp.text:
                    return resp.text
            except Exception:
                # 2. Fallback google.generativeai
                import google.generativeai as legacy_genai
                legacy_genai.configure(api_key=api_key.strip())
                model = legacy_genai.GenerativeModel("gemini-1.5-flash")
                resp = model.generate_content(prompt)
                if resp and resp.text:
                    return resp.text
        except Exception as err:
            st.warning(f"Gemini API -kutsu ei onnistunut ({err}). Näytetään sääntöpohjainen analyysi.")

    # AUTOMATISOITU SÄÄNTÖPOHJAINEN ANALYYSI (toimii aina ilman API-avaintakin!)
    roe_val = data['roe'] * 100 if data['roe'] else 0
    try:
        pe_val = float(data['fwd_pe'])
    except Exception:
        pe_val = 999.0
    try:
        debt_val = float(data['debt_to_equity'])
    except Exception:
        debt_val = 0.0
    
    strengths = []
    weaknesses = []
    
    # Vahvuudet
    if roe_val >= 20:
        strengths.append(f"**Huippuluokan pääoman tuotto (ROE {roe_val:.1f} %):** Yhtiö kuuluu tuottavuudeltaan pörssin parhaaseen kymmenykseen.")
    elif roe_val >= 12:
        strengths.append(f"**Vahva kannattavuus (ROE {roe_val:.1f} %):** Pääoman tuotto ylittää selvästi pääomakustannuksen.")
    else:
        weaknesses.append(f"**Maltillinen pääoman tuotto (ROE {roe_val:.1f} %):** Kannattavuus jää jälkeen parhaista laatuyhtiöistä.")
        
    if pe_val < 15:
        strengths.append(f"**Matalat tuloskertoimet (Fwd P/E 2027: {pe_val:.1f}):** Arvostus tarjoaa turvamarginaalia pitkän aikavälin sijoittajalle.")
    elif pe_val > 30:
        weaknesses.append(f"**Korkeahko arvostuskerroin (Fwd P/E {pe_val:.1f}):** Odotukset ovat korkealla, mikä voi lisätä kurssiheiluntaa tulospettymysten sattuessa.")
        
    if debt_val > 0 and debt_val < 75:
        strengths.append(f"**Vahva ja vakaa tase (Velkaantuneisuus {debt_val:.0f} %):** Alhainen velkaisuus antaa taloudellista liikkumavaraa ja suojaa korkojen nousulta.")
    elif debt_val > 150:
        weaknesses.append(f"**Kohonnut velkaantuneisuus (Velka/OmaP {debt_val:.0f} %):** Taseessa on runsaasti velkaa, mikä nostaa rahoitusriskiä suhdannelaskussa.")
        
    try:
        tot_y = float(data['total_yield'])
        if tot_y >= 5.0:
            strengths.append(f"**Erinomainen kokonaisomistajatuotto ({tot_y:.1f} % TTM):** Yhtiö palkitsee omistajia anteliaasti osingoilla ja omien osakkeiden ostoilla.")
    except Exception:
        pass

    try:
        ath_d = float(data['ath_drop'])
        if ath_d <= -30:
            strengths.append(f"**Merkittävä kurssialennus (ATH Dippi {ath_d:.1f} %):** Osake on pudonnut huipputasoiltaan huomattavasti, tarjoten houkuttelevan ostopaikan.")
            weaknesses.append(f"**Syvä kurssilasku (ATH Dippi {ath_d:.1f} %):** Markkinoilla on ollut huolta kasvun hidastumisesta tai lyhyen aikavälin vastatuulesta.")
    except Exception:
        pass

    if not weaknesses:
        weaknesses.append("**Yleinen markkinariski:** Makrotalouden heilahtelut, korkotaso ja toimialan suhdanteet voivat luoda kurssiheiluntaa lyhyellä aikavälillä.")

    strengths_html = "\n".join([f"- {s}" for s in strengths])
    weaknesses_html = "\n".join([f"- {w}" for w in weaknesses])

    auto_text = f"""
### 🏢 {data['name']} ({data['symbol']}) – {data['industry']}
{data['summary'][:350]}...

### 💪 Keskeiset vahvuudet:
{strengths_html}

### ⚠️ Keskeiset heikkoudet ja riskit:
{weaknesses_html}

---
*💡 Haluatko syvemmän Gemini AI -tekstianalyysin? Syötä ilmainen Gemini API -avain vasemman reunan sivupalkkiin.*
"""
    return auto_text

# -------------------------------------------------------------
# 5. STREAMLIT KÄYTTÖLIITTYMÄ
# -------------------------------------------------------------

st.title("🎯 Laatuyhtiöt Alennuksessa")
st.caption("Etsi tilapäisesti pudonneet laatuyhtiöt S&P 500:sta ja Pohjoismaista. Klikkaa osaketta nähdäksesi tekoäly-yhteenvedon ja talousluvut.")

# Sivupalkin asetukset & suodattimet
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
    st.subheader("🤖 Tekoälyasetukset")
    gemini_key_input = st.text_input(
        "Gemini API -avain (valinnainen):",
        value=st.session_state.get("gemini_api_key", os.environ.get("GEMINI_API_KEY", "")),
        type="password",
        help="Voit hakea ilmaisen API-avaimen osoitteesta aistudio.google.com"
    )
    if gemini_key_input:
        st.session_state["gemini_api_key"] = gemini_key_input

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

# Hakukenttä ja taulukko
st.subheader("📋 Pörssiseula – Valitse osake nähdäksesi AI-yhteenvedon ja talousluvut")

search_query = st.text_input("🔍 Etsi osaketta nimellä, symbolilla tai maalla:", placeholder="Esim. Novo, Adobe, Suomi...")
if search_query:
    q = search_query.lower()
    df_filtered = df_filtered[
        df_filtered['Symboli'].str.lower().str.contains(q) |
        df_filtered['Nimi'].str.lower().str.contains(q) |
        df_filtered['Alue'].str.lower().str.contains(q)
    ]

# Interaktiivinen taulukko rivivalinnalla
event = st.dataframe(
    df_filtered,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
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

# Tarkistetaan valittu osake (taulukosta klikkaamalla tai valintalaatikosta)
clicked_ticker = None
if event and event.selection and event.selection.rows:
    selected_idx = event.selection.rows[0]
    if selected_idx < len(df_filtered):
        clicked_ticker = df_filtered.iloc[selected_idx]['Symboli']

# Valintapalkki puhelimelle ja tietokoneelle
ticker_list = ["(Valitse taulukosta tai valitse tästä valikosta)"] + df_filtered['Symboli'].tolist()
current_idx = ticker_list.index(clicked_ticker) if clicked_ticker in ticker_list else 0

selected_ticker = st.selectbox(
    "🔎 Valitse osake tarkasteluun & AI-analyysiin:",
    options=ticker_list,
    index=current_idx
)

if selected_ticker == "(Valitse taulukosta tai valitse tästä valikosta)":
    selected_ticker = clicked_ticker

# -------------------------------------------------------------
# 6. YHTIÖKOHTAINEN AI-SYVÄANALYYSI JA ENNUSTEET
# -------------------------------------------------------------

if selected_ticker and selected_ticker != "(Valitse taulukosta tai valitse tästä valikosta)":
    st.divider()
    
    # Etsitään valitun osakkeen rivitiedot taulukosta
    selected_row = df_filtered[df_filtered['Symboli'] == selected_ticker].iloc[0] if not df_filtered[df_filtered['Symboli'] == selected_ticker].empty else None
    
    st.markdown(f"## 🤖 AI-Yhteenveto & Talousanalyysi: **{selected_ticker}** ({selected_row['Nimi'] if selected_row is not None else ''})")

    with st.spinner(f"Haetaan yhtiön {selected_ticker} 3v toteutuneet talousluvut ja 2v konsensusennusteet..."):
        deep_data = get_company_deep_dive(selected_ticker, fallback_row=selected_row)

    if not deep_data:
        st.error(f"Yhtiön {selected_ticker} tarkempia tietoja ei voitu noutaa.")
    else:
        # Päämittarit kortteina
        mcol1, mcol2, mcol3, mcol4, mcol5 = st.columns(5)
        mcol1.metric("Nykykurssi", f"{deep_data['price']} {deep_data['currency']}")
        mcol2.metric("Fwd P/E 27", str(deep_data['fwd_pe']))
        mcol3.metric("Fwd P/E 28", str(deep_data['fwd_pe28']))
        mcol4.metric("ROE", f"{round(deep_data['roe']*100, 1)} %" if deep_data['roe'] else "-")
        mcol5.metric("Omistajapalautus", f"{deep_data['total_yield']} %")

        # Välilehdet: 1. AI-Yhteenveto | 2. 3v Taloushistoria | 3. 2v Ennusteet
        tab1, tab2, tab3 = st.tabs(["💡 AI-Analyysi (Vahvuudet & Heikkoudet)", "📊 3v Talousluvut (Toteutuneet)", "🔮 2v Ennusteet (Konsensus)"])

        with tab1:
            active_api_key = st.session_state.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY", "")
            try:
                active_api_key = active_api_key or st.secrets.get("GEMINI_API_KEY", "")
            except Exception:
                pass

            analysis_text = generate_gemini_analysis(deep_data, api_key=active_api_key)
            st.markdown(f"<div class='ai-box'>{analysis_text}</div>", unsafe_allow_html=True)

        with tab2:
            st.markdown("#### 📈 Toteutuneet keskeiset talousluvut (viimeiset 3 vuotta)")
            if not deep_data['df_hist'].empty:
                st.dataframe(deep_data['df_hist'], use_container_width=True, hide_index=True)
            else:
                st.info(f"Tarkkaa 3v tilinpäätöstaulukkoa ei saatu noudettua juuri nyt, mutta yhtiön ROE on {round(deep_data['roe']*100, 1) if deep_data['roe'] else '-'} % ja velkaisuus {deep_data['debt_to_equity']} %.")

        with tab3:
            st.markdown("#### 🎯 Analyytikoiden konsensusennusteet (seuraavat 2 vuotta)")
            if not deep_data['df_est'].empty:
                st.dataframe(deep_data['df_est'], use_container_width=True, hide_index=True)
            else:
                st.info(f"Yhtiön Fwd P/E 2027 ennuste on {deep_data['fwd_pe']} ja Fwd P/E 2028 on {deep_data['fwd_pe28']}.")

st.divider()

# Lataus CSV:ksi
csv = df_filtered.to_csv(index=False).encode('utf-8-sig')
st.download_button(
    label="📥 Lataa seulan tulokset Excel/CSV-tiedostona",
    data=csv,
    file_name=f"laatuyhtiot_{datetime.now().strftime('%Y%m%d')}.csv",
    mime="text/csv",
    use_container_width=True
)
