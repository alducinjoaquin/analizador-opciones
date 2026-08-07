import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Configuración de la página
st.set_page_config(page_title="Portfolio Backtester & SPY Benchmark", layout="wide")

st.title("📊 Quantitative Portfolio Backtester & S&P 500 Benchmark")

# ==========================================
# SIDEBAR: CONFIGURACIÓN Y PARÁMETROS
# ==========================================
st.sidebar.header("⚙️ Parámetros del Portafolio")

# 1. Valor Inicial de Inversión
initial_investment = st.sidebar.number_input(
    "Monto Inicial de Inversión (USD)", 
    min_value=100.0, 
    value=10000.0, 
    step=1000.0,
    format="%.2f"
)

# 2. Tickers (3 a 10)
tickers_input = st.sidebar.text_input(
    "Tickers (3 a 10 separados por coma)", 
    "AAPL, MSFT, NVDA, GOOGL"
)
tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]

if len(tickers) < 3 or len(tickers) > 10:
    st.sidebar.warning("⚠️ Ingresa entre 3 y 10 tickers válidos.")

# 3. Rangos de Fechas
col_d1, col_d2 = st.sidebar.columns(2)
start_date = col_d1.date_input("Fecha Inicio", datetime.today() - timedelta(days=365*3))
end_date = col_d2.date_input("Fecha Final", datetime.today())

# 4. Asignación de Pesos
weight_type = st.sidebar.radio("Asignación de Pesos", ["Equal Weighted", "Personalizado"])
weights = []

if weight_type == "Equal Weighted":
    if len(tickers) > 0:
        weights = [1.0 / len(tickers)] * len(tickers)
else:
    st.sidebar.subheader("Pesos por Activo (%)")
    raw_weights = []
    for t in tickers:
        w = st.sidebar.number_input(f"Peso % {t}", min_value=0.0, max_value=100.0, value=100.0/len(tickers) if len(tickers)>0 else 0.0)
        raw_weights.append(w)
    total_w = sum(raw_weights)
    if total_w > 0:
        weights = [w / total_w for w in raw_weights]  # Normalización exacta a 1.0

# 5. Tratamiento de Dividendos
div_option = st.sidebar.radio("Manejo de Dividendos", ["Reinvertir (Total Return)", "Retirar (Efectivo)"])

# 6. Tasa Libre de Riesgo (Rf)
rf_rate = st.sidebar.number_input("Tasa Libre de Riesgo Anual % (Rf)", value=4.0, step=0.25) / 100.0

# 7. Rebalanceo Anual (> 24 meses)
num_months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
rebalance = False
if num_months > 24:
    rebalance_opt = st.sidebar.radio("Rebalanceo Anual (>24 meses)", ["Mantener Constante (Buy & Hold)", "Rebalancear Anualmente"])
    rebalance = (rebalance_opt == "Rebalancear Anualmente")

# ==========================================
# CÁLCULOS Y MOTOR DEL BACKTEST
# ==========================================
if st.sidebar.button("🚀 Ejecutar Backtest") and 3 <= len(tickers) <= 10:
    
    # Descarga de datos incluyendo el Benchmark SPY
    all_tickers = list(set(tickers + ["SPY"]))
    price_col = 'Adj Close' if div_option == "Reinvertir (Total Return)" else 'Close'
    
    with st.spinner("Descargando precios históricos de Yahoo Finance..."):
        downloaded = yf.download(all_tickers, start=start_date, end=end_date)
        
        if price_col in downloaded:
            raw_data = downloaded[price_col]
        else:
            raw_data = downloaded['Close']

        data = raw_data.dropna()

    if data.empty or "SPY" not in data.columns:
        st.error("Error al obtener los datos de Yahoo Finance. Revisa los tickers e intenta de nuevo.")
    else:
        # Separar retornos diarios del Portafolio y del Benchmark
        daily_returns = data[tickers].pct_change().dropna()
        spy_daily_returns = data["SPY"].pct_change().dropna()
        
        # Sincronización de índices
        common_index = daily_returns.index.intersection(spy_daily_returns.index)
        daily_returns = daily_returns.loc[common_index]
        spy_daily_returns = spy_daily_returns.loc[common_index]

        # ----------------------------------
        # Construcción Serie Temporal Portafolio
        # ----------------------------------
        if not rebalance:
            # Buy & Hold
            port_cum_return = (1 + daily_returns.dot(weights)).cumprod()
            portfolio_series = port_cum_return * initial_investment
        else:
            # Rebalanceo Anual cada 252 días de negociación
            port_values = [initial_investment]
            cur_weights = np.array(weights)
            
            for i in range(len(daily_returns)):
                r = daily_returns.iloc[i].values
                day_ret = np.sum(cur_weights * r)
                new_val = port_values[-1] * (1 + day_ret)
                port_values.append(new_val)
                
                # Drift de pesos
                cur_weights = cur_weights * (1 + r) / (1 + day_ret)
                
                # Rebalanceo al día 252
                if (i + 1) % 252 == 0:
                    cur_weights = np.array(weights)
                    
            portfolio_series = pd.Series(port_values[1:], index=daily_returns.index)

        # Serie Temporal Benchmark (SPY)
        spy_series = (1 + spy_daily_returns).cumprod() * initial_investment

        # ----------------------------------
        # MÉTRICAS CLAVE
        # ----------------------------------
        # Rendimientos Totales
        ret_total_port = (portfolio_series.iloc[-1] / initial_investment) - 1
        ret_total_spy = (spy_series.iloc[-1] / initial_investment) - 1

        # Anualización
        n_days = len(daily_returns)
        ann_factor = 252
        ret_ann_port = (1 + ret_total_port) ** (ann_factor / n_days) - 1
        ret_ann_spy = (1 + ret_total_spy) ** (ann_factor / n_days) - 1

        # Volatilidad Anualizada
        port_daily_ret = portfolio_series.pct_change().dropna()
        vol_ann_port = port_daily_ret.std() * np.sqrt(ann_factor)

        # Sharpe Ratio
        sharpe_ratio = (ret_ann_port - rf_rate) / vol_ann_port if vol_ann_port != 0 else np.nan

        # Sortino Ratio
        target_daily_rf = rf_rate / ann_factor
        downside_returns = port_daily_ret[port_daily_ret < target_daily_rf] - target_daily_rf
        downside_std = np.sqrt(np.mean(downside_returns**2)) * np.sqrt(ann_factor) if len(downside_returns) > 0 else np.nan
        sortino_ratio = (ret_ann_port - rf_rate) / downside_std if (downside_std and downside_std != 0) else np.nan

        # Maximum Drawdown (%)
        peak = portfolio_series.cummax()
        drawdowns = (portfolio_series - peak) / peak
        max_drawdown = drawdowns.min()

        # ==========================================
        # RESULTADOS Y VISUALIZACIÓN
        # ==========================================
        st.subheader("📈 Valor del Portafolio vs. S&P 500 (SPY)")
        
        # Dataframe comparativo para la gráfica
        chart_df = pd.DataFrame({
            "Mi Portafolio (USD)": portfolio_series,
            "S&P 500 Benchmark (USD)": spy_series
        })
        st.line_chart(chart_df, use_container_width=True)

        st.subheader("📌 Métricas Principales de Desempeño")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Rendimiento Portafolio", f"{ret_total_port * 100:.2f}%")
        m2.metric("Rendimiento S&P 500", f"{ret_total_spy * 100:.2f}%")
        m3.metric("Riesgo (Vol. Anual)", f"{vol_ann_port * 100:.2f}%")
        m4.metric("Max Drawdown", f"{max_drawdown * 100:.2f}%")
        m5.metric("Sharpe Ratio", f"{sharpe_ratio:.2f}" if not np.isnan(sharpe_ratio) else "N/A")

        # ----------------------------------
        # CUADRO DE TEXTO COMPARATIVO
        # ----------------------------------
        st.subheader("📝 Resumen Ejecutivo de Retornos")
        alpha = (ret_total_port - ret_total_spy) * 100
        
        summary_text = f"""
        **Análisis de Desempeño ({start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}):**
        
        * **Monto Inicial:** ${initial_investment:,.2f} USD
        * **Valor Final Portafolio:** ${portfolio_series.iloc[-1]:,.2f} USD | **Retorno Total:** {ret_total_port * 100:.2f}% (Anualizado: {ret_ann_port * 100:.2f}%)
        * **Valor Final S&P 500 (SPY):** ${spy_series.iloc[-1]:,.2f} USD | **Retorno Total:** {ret_total_spy * 100:.2f}% (Anualizado: {ret_ann_spy * 100:.2f}%)
        * **Diferencial (Alpha Bruto):** {alpha:+.2f}% frente al mercado.
        * **Caída Máxima (Max Drawdown):** {max_drawdown * 100:.2f}% desde su punto más alto en el período.
        * **Métricas Ajustadas por Riesgo:** Sharpe Ratio de **{sharpe_ratio:.2f}** y Sortino Ratio de **{sortino_ratio:.2f}** (utilizando Tasa Libre de Riesgo del {rf_rate*100:.2f}%).
        """
        st.info(summary_text)
