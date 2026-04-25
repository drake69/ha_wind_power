import math
import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go


def wind_turbine_power(turbine_type, blade_length, diameter, height, air_density,
                       wind_speed, cp, kw, km, ke, ke_t, kt):
    if turbine_type == 'HAWT':
        A = math.pi * blade_length ** 2
    elif turbine_type == 'VAWT':
        A = diameter * height
    else:
        raise ValueError("Invalid turbine type. Use 'HAWT' or 'VAWT'.")

    P_wind = 0.5 * air_density * wind_speed ** 3 * A
    mu = (1 - kw) * (1 - km) * (1 - ke) * (1 - ke_t) * (1 - kt) * cp
    P_output = mu * P_wind
    return P_output


def fetch_ha_history(base_url, token, entity_id, start_date, end_date):
    """Fetch sensor history from Home Assistant REST API."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    # HA API expects ISO format
    start_iso = start_date.isoformat()
    end_iso = end_date.isoformat()

    url = f"{base_url}/api/history/period/{start_iso}"
    params = {
        "filter_entity_id": entity_id,
        "end_time": end_iso,
        "minimal_response": "",
        "no_attributes": "",
    }
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()

    data = resp.json()
    if not data or not data[0]:
        return pd.DataFrame()

    records = []
    for entry in data[0]:
        records.append({
            "last_changed": entry.get("last_changed") or entry.get("last_updated"),
            "state": entry.get("state"),
        })
    return pd.DataFrame(records)


def process_data(df, turbine_type, blade_length, diameter, height,
                 air_density, cp, kw, km, ke, ke_t, kt, unit_kmh):
    df = df.copy()
    df = df.dropna()
    df = df[pd.to_numeric(df['state'], errors='coerce').notnull()]
    df['state'] = df['state'].astype(float)

    df['last_changed'] = pd.to_datetime(df['last_changed'])
    df = df.sort_values('last_changed').reset_index(drop=True)
    df['time_diff'] = df['last_changed'].diff().dt.total_seconds().fillna(0)

    # Convert to m/s if needed
    if unit_kmh:
        df['speed_ms'] = df['state'] / 3.6
    else:
        df['speed_ms'] = df['state']

    df['power_W'] = df['speed_ms'].apply(
        lambda v: wind_turbine_power(turbine_type, blade_length, diameter,
                                     height, air_density, v, cp, kw, km, ke, ke_t, kt)
    )

    # Energy in kWh
    df['energy_kWh'] = df['power_W'] * df['time_diff'] / 3_600_000
    df['cumulative_kWh'] = df['energy_kWh'].cumsum()

    df['date'] = df['last_changed'].dt.date
    df['month'] = df['last_changed'].dt.to_period('M').astype(str)
    df['week'] = df['last_changed'].dt.isocalendar().week.astype(int)
    df['year_week'] = df['last_changed'].dt.strftime('%Y-W%W')

    return df


# ─── Streamlit App ───────────────────────────────────────────────────────────

st.set_page_config(page_title="Wind Power Dashboard", layout="wide")
st.title("Wind Power Dashboard")

# ─── Sidebar: Home Assistant connection ──────────────────────────────────────
st.sidebar.header("Home Assistant")
ha_url = st.sidebar.text_input("HA URL", value="http://homeassistant.local:8123",
                               help="Base URL di Home Assistant")
ha_token = st.sidebar.text_input("Long-Lived Access Token", type="password")
entity_id = st.sidebar.text_input("Entity ID sensore vento", value="sensor.wind_speed")
unit_kmh = st.sidebar.radio("Unità sensore", ["km/h", "m/s"], index=0) == "km/h"

# ─── Sidebar: Date range ────────────────────────────────────────────────────
st.sidebar.header("Periodo")
today = datetime.now().date()
col1, col2 = st.sidebar.columns(2)
start_date = col1.date_input("Da", value=today - timedelta(days=30))
end_date = col2.date_input("A", value=today)

# ─── Sidebar: Turbine parameters ────────────────────────────────────────────
st.sidebar.header("Parametri turbina")
turbine_type = st.sidebar.selectbox("Tipo turbina", ["VAWT", "HAWT"])
if turbine_type == "HAWT":
    blade_length = st.sidebar.number_input("Lunghezza pala (m)", value=1.0, min_value=0.1, step=0.1)
    diameter = 0.0
    height = 0.0
else:
    blade_length = 0.0
    diameter = st.sidebar.number_input("Diametro (m)", value=0.4, min_value=0.1, step=0.1)
    height = st.sidebar.number_input("Altezza (m)", value=1.0, min_value=0.1, step=0.1)

air_density = st.sidebar.number_input("Densità aria (kg/m³)", value=1.225, min_value=0.5, step=0.01)

# ─── Sidebar: Efficiency coefficients ───────────────────────────────────────
st.sidebar.header("Coefficienti di rendimento")
cp = st.sidebar.slider("Cp - Coefficiente di potenza", 0.0, 0.593, 0.40, 0.01,
                        help="Max teorico (Betz): 0.593")
kw = st.sidebar.slider("Kw - Perdite scia (%)", 0.0, 0.30, 0.05, 0.01)
km = st.sidebar.slider("Km - Perdite meccaniche (%)", 0.0, 0.10, 0.003, 0.001, format="%.3f")
ke = st.sidebar.slider("Ke - Perdite elettriche (%)", 0.0, 0.10, 0.015, 0.001, format="%.3f")
ke_t = st.sidebar.slider("Ke_t - Perdite trasmissione (%)", 0.0, 0.30, 0.10, 0.01)
kt = st.sidebar.slider("Kt - Perdite downtime (%)", 0.0, 0.20, 0.03, 0.01)

# ─── Sidebar: Economic ──────────────────────────────────────────────────────
st.sidebar.header("Parametri economici")
euro_per_kwh = st.sidebar.number_input("€/kWh", value=0.44, min_value=0.0, step=0.01)

# ─── Show total efficiency ──────────────────────────────────────────────────
total_efficiency = (1 - kw) * (1 - km) * (1 - ke) * (1 - ke_t) * (1 - kt) * cp
st.sidebar.markdown("---")
st.sidebar.metric("Rendimento totale", f"{total_efficiency:.1%}")

# ─── Fetch & Process ────────────────────────────────────────────────────────
fetch = st.sidebar.button("Scarica dati", type="primary", use_container_width=True)

if fetch:
    if not ha_token:
        st.error("Inserisci il Long-Lived Access Token di Home Assistant.")
        st.stop()

    with st.spinner("Scaricamento dati da Home Assistant..."):
        try:
            start_dt = datetime.combine(start_date, datetime.min.time())
            end_dt = datetime.combine(end_date, datetime.max.time())
            df_raw = fetch_ha_history(ha_url, ha_token, entity_id, start_dt, end_dt)
        except requests.exceptions.RequestException as e:
            st.error(f"Errore connessione HA: {e}")
            st.stop()

    if df_raw.empty:
        st.warning("Nessun dato trovato per il periodo selezionato.")
        st.stop()

    df = process_data(df_raw, turbine_type, blade_length, diameter, height,
                      air_density, cp, kw, km, ke, ke_t, kt, unit_kmh)

    st.session_state['df'] = df
    st.session_state['df_raw'] = df_raw

if 'df' not in st.session_state:
    st.info("Configura i parametri nella sidebar e premi **Scarica dati**.")
    st.stop()

df = st.session_state['df']

# ─── KPI Cards ───────────────────────────────────────────────────────────────
total_energy = df['energy_kWh'].sum()
total_euro = total_energy * euro_per_kwh
avg_wind = df['speed_ms'].mean()
max_wind = df['speed_ms'].max()
avg_power = df['power_W'].mean()
num_days = (df['last_changed'].max() - df['last_changed'].min()).days or 1

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Energia totale", f"{total_energy:.3f} kWh")
k2.metric("Valore economico", f"€ {total_euro:.2f}")
k3.metric("Velocità media vento", f"{avg_wind:.1f} m/s")
k4.metric("Velocità max vento", f"{max_wind:.1f} m/s")
k5.metric("Potenza media", f"{avg_power:.1f} W")

st.markdown("---")

# ─── Charts ──────────────────────────────────────────────────────────────────
tab_day, tab_week, tab_month, tab_cum, tab_wind, tab_data = st.tabs(
    ["Giornaliero", "Settimanale", "Mensile", "Cumulativo", "Vento", "Dati"])

with tab_day:
    daily = df.groupby('date').agg(
        energy_kWh=('energy_kWh', 'sum'),
        avg_wind=('speed_ms', 'mean'),
        max_wind=('speed_ms', 'max'),
    ).reset_index()
    daily['euro'] = daily['energy_kWh'] * euro_per_kwh

    fig = px.bar(daily, x='date', y='energy_kWh',
                 title="Energia giornaliera (kWh)",
                 labels={'date': 'Data', 'energy_kWh': 'Energia (kWh)'},
                 hover_data=['avg_wind', 'max_wind', 'euro'])
    fig.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(daily.rename(columns={
        'date': 'Data', 'energy_kWh': 'Energia (kWh)',
        'avg_wind': 'Vento medio (m/s)', 'max_wind': 'Vento max (m/s)',
        'euro': 'Valore (€)'
    }), use_container_width=True, hide_index=True)

with tab_week:
    weekly = df.groupby('year_week').agg(
        energy_kWh=('energy_kWh', 'sum'),
        avg_wind=('speed_ms', 'mean'),
    ).reset_index()
    weekly['euro'] = weekly['energy_kWh'] * euro_per_kwh

    fig = px.bar(weekly, x='year_week', y='energy_kWh',
                 title="Energia settimanale (kWh)",
                 labels={'year_week': 'Settimana', 'energy_kWh': 'Energia (kWh)'},
                 hover_data=['avg_wind', 'euro'])
    st.plotly_chart(fig, use_container_width=True)

with tab_month:
    monthly = df.groupby('month').agg(
        energy_kWh=('energy_kWh', 'sum'),
        avg_wind=('speed_ms', 'mean'),
    ).reset_index()
    monthly['euro'] = monthly['energy_kWh'] * euro_per_kwh

    fig = px.bar(monthly, x='month', y='energy_kWh',
                 title="Energia mensile (kWh)",
                 labels={'month': 'Mese', 'energy_kWh': 'Energia (kWh)'},
                 hover_data=['avg_wind', 'euro'])
    st.plotly_chart(fig, use_container_width=True)

with tab_cum:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df['last_changed'], y=df['cumulative_kWh'],
                             mode='lines', name='Energia cumulativa (kWh)'))
    fig.update_layout(title="Energia cumulativa",
                      xaxis_title="Data", yaxis_title="kWh")
    st.plotly_chart(fig, use_container_width=True)

    # Cumulative euro
    df['cumulative_euro'] = df['cumulative_kWh'] * euro_per_kwh
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=df['last_changed'], y=df['cumulative_euro'],
                              mode='lines', name='Valore cumulativo (€)',
                              line=dict(color='green')))
    fig2.update_layout(title="Valore economico cumulativo",
                       xaxis_title="Data", yaxis_title="€")
    st.plotly_chart(fig2, use_container_width=True)

with tab_wind:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df['last_changed'], y=df['speed_ms'],
                             mode='lines', name='Velocità vento (m/s)',
                             line=dict(width=0.5)))
    fig.update_layout(title="Velocità del vento nel tempo",
                      xaxis_title="Data", yaxis_title="m/s")
    st.plotly_chart(fig, use_container_width=True)

    # Wind distribution histogram
    fig2 = px.histogram(df, x='speed_ms', nbins=50,
                        title="Distribuzione velocità del vento",
                        labels={'speed_ms': 'Velocità (m/s)'})
    st.plotly_chart(fig2, use_container_width=True)

    # Power curve
    speeds = [v / 10 for v in range(1, 201)]
    powers = [wind_turbine_power(turbine_type, blade_length, diameter, height,
                                 air_density, v, cp, kw, km, ke, ke_t, kt) for v in speeds]
    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(x=speeds, y=powers, mode='lines', name='Curva di potenza'))
    fig3.update_layout(title="Curva di potenza della turbina",
                       xaxis_title="Velocità vento (m/s)", yaxis_title="Potenza (W)")
    st.plotly_chart(fig3, use_container_width=True)

with tab_data:
    st.subheader("Dati grezzi")
    st.dataframe(df[['last_changed', 'state', 'speed_ms', 'power_W',
                      'energy_kWh', 'cumulative_kWh']].rename(columns={
        'last_changed': 'Timestamp', 'state': 'Valore sensore',
        'speed_ms': 'Velocità (m/s)', 'power_W': 'Potenza (W)',
        'energy_kWh': 'Energia (kWh)', 'cumulative_kWh': 'Cumulativa (kWh)'
    }), use_container_width=True, hide_index=True)

    # Download CSV
    csv = df.to_csv(index=False)
    st.download_button("Scarica CSV", csv, "wind_power_output.csv", "text/csv")
