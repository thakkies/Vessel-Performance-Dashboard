import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
import numpy as np
import datetime
import json
import pydeck as pdk
import folium
from streamlit_folium import st_folium
import re

# streamlit run C:\Users\thoma\Documents\S6_Cruise_ship\S6.py

title_text = "Vessel Performance"
st.set_page_config(page_title=title_text, layout="wide", initial_sidebar_state="collapsed")
st.title(title_text)


uploaded_files = st.file_uploader("Upload Vessel Data", type=["csv", "txt", "xlsx"], accept_multiple_files=True)
if uploaded_files:
    lijst_met_dfs = []
    
    for file in uploaded_files:
        if file.name.endswith('.csv') or file.name.endswith('.txt'):
            df_temp = pd.read_csv(file, sep=None, engine='python', encoding='utf-16')
        else:
            df_temp = pd.read_excel(file)
        
        lijst_met_dfs.append(df_temp)

    df = pd.concat(lijst_met_dfs, ignore_index=True)
    df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
    df = df.sort_values('Time')

    fuel_cols2 = [c for c in df.columns if 'Fuel Rate' in c]

    if fuel_cols2:
        for col in fuel_cols2:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        averages = df[fuel_cols2].mean()
        filtered_avg = {k: v for k, v in averages.items() if v > 0.05}
        
        labels = ["Total fuel rate"] + list(filtered_avg.keys())
        sources = [0] * len(filtered_avg)
        targets = list(range(1, len(filtered_avg) + 1))
        values = list(filtered_avg.values())
        total_val = sum(values)

        fig = go.Figure(data=[go.Sankey(
            textfont=dict(color="black", size =16),
            node=dict(
                pad=15, thickness=20,
                label=[f"{label} ({val:.1f} L/h - {(val/total_val)*100:.1f}%)" if i>0 else f"{label} ({total_val:.1f} L/h)" 
               for i, (label, val) in enumerate(zip(labels, [total_val] + values))],
                color="#ff0000",
            ),
            link=dict(source=sources, target=targets, value=values, color="rgba(255, 0, 0, 0.2)")
        )])

        st.subheader("Average Fuelrate (L/h)")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No columns found with the name 'Fuel Rate'.")

    
    min_tijd = df['Time'].min().to_pydatetime()
    max_tijd = df['Time'].max().to_pydatetime()

    if 'slider_key_v' not in st.session_state:
        st.session_state.slider_key_v = 0
    
    if st.button('Reset'):
        st.session_state.slider_key_v += 1
        st.rerun()

    gekozen_bereik = st.slider(
        "Select timeperiod:",
        min_value = min_tijd,
        max_value = max_tijd,
        value = (min_tijd, max_tijd),
        format = "DD/MM/YY HH:mm",
        step = datetime.timedelta(minutes=5),
        key = f"slider_{st.session_state.slider_key_v}"
    )

    start_tijd, eind_tijd = gekozen_bereik
    mask = (df['Time'] >= start_tijd) & (df['Time'] <= eind_tijd)
    df_filtered = df.loc[mask].copy()
    tijd_uren = (df_filtered['Time'] - df_filtered['Time'].iloc[0]).dt.total_seconds() / 3600

    consumption_enginesb   = np.trapezoid(df_filtered['ME SB Fuel Rate'].fillna(0), tijd_uren).round(0)
    consumption_engineps   = np.trapezoid(df_filtered['ME PS Fuel Rate'].fillna(0), tijd_uren).round(0)
    consumption_genfwd     = np.trapezoid(df_filtered['Generator FWD Fuel Rate'].fillna(0), tijd_uren).round(0)
    consumption_gensb      = np.trapezoid(df_filtered['Generator Starboard AFT Fuel Rate'].fillna(0), tijd_uren).round(0)
    consumption_genps      = np.trapezoid(df_filtered['Generator Port AFT Fuel Rate'].fillna(0), tijd_uren).round(0)
    consumption_heater1    = np.trapezoid(df_filtered['Heater 1 Fuel Rate'], tijd_uren).round(0)
    consumption_heater2    = np.trapezoid(df_filtered['Heater 2 Fuel Rate'], tijd_uren).round(0)
    consumption_total      = consumption_enginesb + consumption_engineps + consumption_genfwd + consumption_gensb + consumption_genps + consumption_heater1 + consumption_heater2

    fuel_consumption = [
        consumption_enginesb, consumption_engineps,
        consumption_genfwd, consumption_gensb, consumption_genps,
        consumption_heater1, consumption_heater2, consumption_total
    ]

    fuel_cols = [
        'ME SB Fuel Rate', 'ME PS Fuel Rate', 
        'Generator FWD Fuel Rate', 'Generator Starboard AFT Fuel Rate',
        'Generator Port AFT Fuel Rate', 'Heater 1 Fuel Rate', 'Heater 2 Fuel Rate'
    ]

    
    df_filtered['Total Fuel Rate'] = df_filtered[fuel_cols].sum(axis=1)

    all_cols = fuel_cols + ['Total Fuel Rate']

    avg_series = df_filtered[all_cols].mean().round(0)

    history_data = [df_filtered[col].fillna(0).tolist() for col in all_cols]

    result_df = pd.DataFrame({
        'Type'                      : avg_series.index,
        'Average Fuel Rate [L/h]'   : avg_series.values,
        'Fuel consumption [L]'      : fuel_consumption,
        'Rate over Time'            : history_data,
    })

    st.subheader("Fuel consumption")
    st.dataframe(
        result_df,
        column_config={
            "Rate over Time": st.column_config.LineChartColumn(
                "Fuel Rate Trend",
                width="medium",
                help="Consumption trend over the selected period"
            ),
        },
        hide_index=True,
    )

    bunker_cols = ['Bunker Aft Current Volume', 'Bunker FWD Current Volume']
    df_filtered[bunker_cols] = df_filtered[bunker_cols].interpolate(method='linear', limit_direction='both')

    window_size = 10 
    df_filtered['Bunker_AFT_Smooth'] = df_filtered['Bunker Aft Current Volume'].rolling(window=window_size, center=True).mean()
    df_filtered['Bunker_FWD_Smooth'] = df_filtered['Bunker FWD Current Volume'].rolling(window=window_size, center=True).mean()
    df_filtered['Total_Bunker_Smooth'] = df_filtered['Bunker_AFT_Smooth'] + df_filtered['Bunker_FWD_Smooth']

    
    trend_window = 125 
    df_filtered['Trend_Delta'] = df_filtered['Total_Bunker_Smooth'].diff(periods=trend_window)

    max_increase = df_filtered['Trend_Delta'].max()

    if max_increase > 2000:
        idx_bunker = df_filtered['Trend_Delta'].idxmax()
        vol_before = df_filtered.loc[:idx_bunker, 'Total_Bunker_Smooth'].tail(trend_window).min()
        vol_after = df_filtered.loc[idx_bunker:, 'Total_Bunker_Smooth'].head(trend_window).max()
        
        hoeveelheid_getankt = vol_after - vol_before
        tijdstip_getankt = idx_bunker
    vol_start = df_filtered['Total_Bunker_Smooth'].bfill().iloc[0]
    vol_eind = df_filtered['Total_Bunker_Smooth'].ffill().iloc[-1]

    verbruik_bunker = (vol_before - vol_after) + hoeveelheid_getankt
    afwijking_procent = ((consumption_total - verbruik_bunker) / verbruik_bunker) * 100 if verbruik_bunker != 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Consumption based on bunkervolumes", f"{verbruik_bunker:.0f} L")
    col2.metric("Consumption based on integrating the fuelrates", f"{consumption_total:.0f} L")
    col3.metric("Deviation", f"{afwijking_procent:.1f}%", delta=f"{afwijking_procent:.1f}%", delta_color="inverse")
    col4.metric("Refueled", f"{hoeveelheid_getankt:.0f} L")

    st.header("Trend analysis")


    fuel_rate_columns = [
        "ME PS Fuel Rate", 
        "ME SB Fuel Rate", 
        "Generator FWD Fuel Rate", 
        "Generator Port AFT Fuel Rate", 
        "Generator Starboard AFT Fuel Rate", 
        "Heater 1 Fuel Rate", 
        "Heater 2 Fuel Rate"
    ]

    bunker_volume_columns = [
        "Bunker Aft Current Volume", "Bunker FWD Current Volume"
    ]

    df["Total Fuel Rate"] = df[fuel_rate_columns].sum(axis=1, min_count=1)
    df["Total Bunkervolume"] = df[bunker_volume_columns].sum(axis=1, min_count=1)

    max_drop = -10000
    df.loc[df["Total Bunkervolume"].diff() < max_drop, "Total Bunkervolume"] = np.nan
    df["Total Bunkervolume"] = df["Total Bunkervolume"].interpolate(method="linear")


    GROUPS = {
        "**General**": ["Speed Over Ground", "Depth", "Course Over Ground", "Bunker Aft Current Volume", "Bunker FWD Current Volume"
        ],
        "**Extern**": ["Humidity Air", "Temperature Air", "App Wind Speed", "App Wind Angle"],
        "**Heaters**": [
            "Heater 1 Fuel Rate", "Heater 1 Fuel Temp", "Heater 2 Fuel Rate", "Heater 2 Fuel Temp"],

        "**Engines**": [
            "ME SB Alternator Voltage", "ME SB Boost Pressure", "ME SB Coolant Pressure", "ME SB Coolant Temp", "ME SB Load", "ME SB Exhaust Temp",
            "ME SB Fuel Rate", "ME SB Fuel Temp", "ME SB Oil Pressure", "ME SB Oil Temp", "ME SB RPM", "ME PS Alternator Voltage",
            "ME PS Boost Pressure", "ME PS Coolant Pressure", "ME PS Coolant Temp", "ME PS Load", "ME PS Exhaust Temp", "ME PS Fuel Rate",
            "ME PS FuelTemp", "ME PS Oil Pressure", "ME PS Oil Temp", "ME PS RPM"
        ],
        "**Generators**": [
            "Generator FWD Fuel Rate", "Generator FWD Real Power", "Generator FWD Apparent Power", "Generator FWD Phase A Current",
            "Generator FWD Phase B Current", "Generator FWD Phase C Current", "Generator Port AFT Fuel Rate", "Generator Port AFT Real Power",
            "Generator Port AFT Apparent Power", "Generator Port AFT Phase A Current", "Generator Port AFT Phase B Current",
            "Generator Port AFT Phase C Current", "Generator Starboard AFT Fuel Rate", "Generator Starboard AFT Real Power",
            "Generator Starboard AFT Apparent Power", "Generator Starboard AFT Phase A Current", "Generator Starboard AFT Phase B Current",
            "Generator Starboard AFT Phase C Current"
        ],
        "**Totals**": ["Total Fuel Rate", "Total Bunkervolume", 'Total_Bunker_Smooth']
    }

    COL_MAPPING = [
        ["**General**", "**Extern**", "**Heaters**"],
        ["**Engines**"],
        ["**Generators**"],
        ["**Totals**"]
    ]
        
    selected_metrics = []
        
    ui_cols = st.columns(5)
    
    for i, groups_in_col in enumerate(COL_MAPPING):
        with ui_cols[i]:
            for group_name in groups_in_col:
                st.markdown(f"###### {group_name}")
                for m in GROUPS[group_name]:
                    if m in df.columns:
                        if st.checkbox(m, key=f"cb_{group_name}_{m}"):
                            selected_metrics.append(m)
                st.write("")

    st.divider()

    if selected_metrics:
        fig = px.line(df, x='Time', y=selected_metrics)
        fig.update_layout(
            hovermode="x unified",
            xaxis_title="Time",
            yaxis_title="Value (Liters)"
        )
        st.plotly_chart(fig, use_container_width=True)

st.title("Vessel route")

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0 
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi/2)**2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda/2)**2
    return 2 * R * np.arctan2(np.sqrt(a), np.sqrt(1-a))


def bereken_statistieken(df, drempel_snelheid=0.5, drempel_gem_snelheid=3.0):
    if df.empty or len(df) < 2:
        return 0, "0h 0m", "0h 0m", 0
    
    df = df.copy()
    df['dt'] = df['Time'].diff().dt.total_seconds() / 3600 # in uren
    gemiddeld_interval = df['dt'].median()
    df['dt'] = df['dt'].fillna(gemiddeld_interval)
    df['dist'] = haversine(df['lat'].shift(), df['lon'].shift(), df['lat'], df['lon']
    df['dist'] = df['dist'].fillna(df['dist'].median() if not df['dist'].empty else 0)
    df['calc_speed_kmh'] = df['dist'] / df['dt']
    
    drempel_kmh = drempel_snelheid
    avg_drempel_kmh = drempel_gem_snelheid
    
    vaar_tijd = df[df['calc_speed_kmh'] > drempel_kmh]['dt'].sum()
    stop_tijd = df[df['calc_speed_kmh'] <= drempel_kmh]['dt'].sum()
    totaal_afstand = df['dist'].sum()
    
    df_sneller = df[df['calc_speed_kmh'] > avg_drempel_kmh]
    gem_snelheid = (df_sneller['dist'].sum() / df_sneller['dt'].sum()) if not df_sneller.empty else 0
    
    def format_tijd(uren):
        h = int(uren)
        m = round((uren - h) * 60)
        return f"{h}h {m}m"

    return round(totaal_afstand, 2), format_tijd(vaar_tijd), format_tijd(stop_tijd), round(gem_snelheid, 1)

with st.sidebar:
    st.header("Mapsettings")
    toon_route = st.checkbox("Show route (Line)", value=True)
    toon_richting = st.checkbox("Show route (Arrows)", value=False)

coord_files = st.file_uploader("Upload Vessel Data", type=["csv", "txt", "xlsx"], accept_multiple_files=True, key="coords_up")

if coord_files:
    lijst_met_dfs = []
    for file in coord_files:
        if file.name.endswith(('.csv', '.txt')):
            df_temp = pd.read_csv(file, sep=None, engine='python', encoding='utf-16')
        else:
            df_temp = pd.read_excel(file)
        lijst_met_dfs.append(df_temp)

    df_coords = pd.concat(lijst_met_dfs, ignore_index=True)
    df_coords['Time'] = pd.to_datetime(df_coords['Time'], errors='coerce')
    df_coords = df_coords.sort_values('Time')

    def extract_all(row):
        try:
            pos = json.loads(str(row['Position']).replace("'", '"'))
            course = float(re.sub(r'[^0-9.]', '', str(row['CourseOverGround'])))
            return pd.Series([float(pos['latitude']), float(pos['longitude']), course])
        except:
            return pd.Series([None, None, None])


    df_coords[['lat', 'lon', 'course']] = df_coords.apply(extract_all, axis=1)
    df_coords = df_coords.dropna(subset=['lat', 'lon', 'Time'])

    min_tijd = df_coords['Time'].min().to_pydatetime()
    max_tijd = df_coords['Time'].max().to_pydatetime()

    if 'slider_key_route' not in st.session_state:
        st.session_state.slider_key_route = 0

    if st.button('Reset', key='reset_button_coords'):
        st.session_state.slider_key_route += 1
        st.rerun()

    gekozen_range = st.slider(
        "Select timeperiod:",
        min_value=min_tijd,
        max_value=max_tijd,
        value=(min_tijd, max_tijd),
        format="DD/MM/YY HH:mm",
        step=datetime.timedelta(minutes=5),
        key=f"route_slider_{st.session_state.slider_key_route}"
    )

    start, eind = gekozen_range
    df_final = df_coords[(df_coords['Time'] >= start) & (df_coords['Time'] <= eind)].copy()

    afstand, vaartijd, stoptijd, gem_snelheid = bereken_statistieken(
        df_final, 
        drempel_snelheid=0.5, 
        drempel_gem_snelheid=3.0
    )

    col1, col2 = st.columns([4, 1])

    with col1:
        try:
            m = folium.Map(
                location=[df_final['lat'].median(), df_final['lon'].median()],
                zoom_start=12,
                tiles=None 
            )

            folium.TileLayer(
                tiles='https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
                attr='&copy; OpenStreetMap &copy; CARTO',
                name='CartoDB Voyager'
            ).add_to(m)


            if toon_route and not df_final.empty:
                folium.PolyLine(df_final[['lat', 'lon']].values.tolist(), color="blue", weight=3).add_to(m)

            if toon_richting and not df_final.empty:
                for _, row in df_final.iloc[::5].iterrows():
                    icon_html = f'<div style="transform: rotate({row["course"]}deg); width: 0; height: 0; border-left: 5px solid transparent; border-right: 5px solid transparent; border-bottom: 15px solid red;"></div>'
                    folium.Marker([row['lat'], row['lon']], icon=folium.DivIcon(html=icon_html)).add_to(m)

            st_folium(m, width=1100, height=700, returned_objects=[])

        except Exception as e:
            st.error(f"Fout bij kaart: {e}")

    with col2:
        st.subheader("Statistics")
        df_stats = pd.DataFrame({
            "Metric": ["Distance", "Time Sailed", "Time Stopped", "Avg Speed (Sailing)"],
            "Value": [f"{afstand} km", vaartijd, stoptijd, f"{gem_snelheid} km/h"]
        })
        st.table(df_stats)