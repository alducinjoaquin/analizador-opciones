import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import io

# Configuración de la página
st.set_page_config(page_title="Analizador de Put Spreads", layout="wide")

st.title("📈 Analizador de Credit Put Spreads (Yahoo Finance)")
st.write("Estrategia de venta de Puts con protección (Bull Put Spread)")

# --- BARRA LATERAL / ENTRADAS DEL USUARIO ---
st.sidebar.header("Parámetros de Entrada")

tickers_input = st.sidebar.text_input(
    "5 Tickers de Acciones (separados por coma):",
    value="AAPL, MSFT, NVDA, AMZN, GOOGL"
)

plazo_dias = st.sidebar.number_input("Plazo objetivo (días a expiración):", min_value=1, value=30, step=1)
offset = st.sidebar.number_input("Offset sobre precio Spot ($):", min_value=0.0, value=5.0, step=0.5)
distancia_strikes = st.sidebar.selectbox("Distancia entre Strikes (número de saltos):", [1, 2, 3, 4], index=0)

botón_calcular = st.sidebar.button("Analizar Cadenas de Opciones", type="primary")

# --- LÓGICA PRINCIPAL ---
if botón_calcular:
    tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
    
    if len(tickers) == 0:
        st.error("Por favor ingresa al menos un ticker válido.")
    else:
        resultados = []
        
        with st.spinner("Consultando cadenas de opciones en Yahoo Finance..."):
            for ticker in tickers:
                try:
                    tk = yf.Ticker(ticker)
                    
                    # 1. Obtener precio spot
                    history = tk.history(period="1d")
                    if history.empty:
                        resultados.append({"Ticker": ticker, "Estado": "Sin datos de precio"})
                        continue
                    spot_price = history['Close'].iloc[-1]
                    
                    # 2. Buscar fecha de vencimiento más cercana al plazo
                    expirations = tk.options
                    if not expirations:
                        resultados.append({"Ticker": ticker, "Estado": "Sin opciones disponibles"})
                        continue
                    
                    hoy = datetime.now()
                    fechas_exp = [datetime.strptime(exp, "%Y-%m-%d") for exp in expirations]
                    dias_exp = [(exp - hoy).days for exp in fechas_exp]
                    
                    # Seleccionar el vencimiento con menor diferencia absoluta
                    idx_cercano = min(range(len(dias_exp)), key=lambda i: abs(dias_exp[i] - plazo_dias))
                    fecha_seleccionada = expirations[idx_cercano]
                    dias_reales = dias_exp[idx_cercano]
                    
                    # 3. Descargar la cadena de opciones de esa fecha
                    opt_chain = tk.option_chain(fecha_seleccionada)
                    puts = opt_chain.puts.copy()
                    
                    if puts.empty:
                        resultados.append({"Ticker": ticker, "Estado": "Cadena de Puts vacía"})
                        continue
                    
                    # Ordenar por Strike ascendente
                    puts = puts.sort_values(by="strike").reset_index(drop=True)
                    
                    # 4. Determinar Strike Superior (Cercano a Spot - Offset)
                    target_strike = spot_price - offset
                    
                    # Encontrar el índice del strike más cercano
                    puts['dif_strike'] = (puts['strike'] - target_strike).abs()
                    idx_sup = puts['dif_strike'].idxmin()
                    
                    # 5. Determinar Strike Inferior (distancia_strikes hacia abajo)
                    idx_inf = idx_sup - distancia_strikes
                    
                    if idx_inf < 0:
                        resultados.append({
                            "Ticker": ticker,
                            "Estado": f"No hay suficientes strikes por debajo para una distancia de {distancia_strikes}"
                        })
                        continue
                    
                    row_sup = puts.iloc[idx_sup]
                    row_inf = puts.iloc[idx_inf]
                    
                    strike_sup = row_sup['strike']
                    bid_sup = row_sup['bid']
                    
                    strike_inf = row_inf['strike']
                    ask_inf = row_inf['ask']
                    
                    # 6. Cálculos Financieros
                    prima_neta = bid_sup - ask_inf
                    importe_recibir = prima_neta * 100
                    utilidad_maxima = importe_recibir
                    
                    diferencia_strikes = strike_sup - strike_inf
                    perdida_maxima = (diferencia_strikes - prima_neta) * 100
                    
                    # Cálculo de la relación Utilidad / Pérdida (%)
                    if perdida_maxima > 0:
                        ratio_utilidad_perdida = (utilidad_maxima / perdida_maxima) * 100
                    else:
                        ratio_utilidad_perdida = 0.0
                    
                    resultados.append({
                        "Ticker": ticker,
                        "Precio Spot ($)": round(spot_price, 2),
                        "Expiración": fecha_seleccionada,
                        "Días DTE": dias_reales,
                        "Strike Vendido (Alto)": strike_sup,
                        "BID Vendido ($)": round(bid_sup, 2),
                        "Strike Comprado (Bajo)": strike_inf,
                        "ASK Comprado ($)": round(ask_inf, 2),
                        "Prima Neta ($)": round(prima_neta, 2),
                        "Importe a Recibir ($)": round(importe_recibir, 2),
                        "Utilidad Máx ($)": round(utilidad_maxima, 2),
                        "Pérdida Máx ($)": round(perdida_maxima, 2),
                        "Utilidad/Pérdida (%)": round(ratio_utilidad_perdida, 2),
                        "Estado": "OK"
                    })
                    
                except Exception as e:
                    resultados.append({"Ticker": ticker, "Estado": f"Error: {str(e)}"})
        
        # Convertir a DataFrame y mostrar resultados
        df_res = pd.DataFrame(resultados)
        
        # Filtrar exitosos de errores
        if "OK" in df_res.get("Estado", []).values:
            df_ok = df_res[df_res["Estado"] == "OK"].drop(columns=["Estado"])
            st.subheader("📊 Resultados de las Estrategias")
            st.dataframe(df_ok, use_container_width=True)
            
            # --- SECCIÓN DE DESCARGA DE ARCHIVOS ---
            st.markdown("### 📥 Descargar Resultados")
            col1, col2 = st.columns(2)
            
            # Descarga CSV
            csv_data = df_ok.to_csv(index=False).encode('utf-8')
            col1.download_button(
                label="📄 Descargar como CSV",
                data=csv_data,
                file_name=f"put_spreads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                type="secondary"
            )
            
            # Descarga Excel
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_ok.to_excel(writer, index=False, sheet_name='Put_Spreads')
            excel_data = buffer.getvalue()
            
            col2.download_button(
                label="📊 Descargar como Excel (.xlsx)",
                data=excel_data,
                file_name=f"put_spreads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="secondary"
            )
            
            # Mostrar errores o advertencias si los hubo
            df_err = df_res[df_res["Estado"] != "OK"][["Ticker", "Estado"]]
            if not df_err.empty:
                st.warning("Advertencias / Tickers no procesados:")
                st.table(df_err)
        else:
            st.error("No se pudieron procesar los tickers ingresados.")
            st.table(df_res)
