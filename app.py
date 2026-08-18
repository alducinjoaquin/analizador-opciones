import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import io
import time  # Importante para pausar consultas masivas

# Configuración de la página
st.set_page_config(page_title="Analizador de Put Spreads", layout="wide")

st.title("📈 Analizador de Credit Put Spreads (Yahoo Finance)")
st.write("Estrategia de venta de Puts con protección (Bull Put Spread)")

# --- FUNCIÓN CON CACHÉ PARA EVITAR EL BLOQUEO DE YAHOO FINANCE ---
@st.cache_data(ttl=900)  # Guarda los datos en memoria por 15 minutos (900 segundos)
def obtener_datos_opcion(ticker, plazo_dias):
    tk = yf.Ticker(ticker)
    
    # 1. Obtener precio spot
    history = tk.history(period="1d")
    if history.empty:
        return None, None, None, None, "Sin datos de precio"
    
    spot_price = history['Close'].iloc[-1]
    
    # 2. Vencimientos
    expirations = tk.options
    if not expirations:
        return None, None, None, None, "Sin opciones disponibles"
    
    hoy = datetime.now()
    fechas_exp = [datetime.strptime(exp, "%Y-%m-%d") for exp in expirations]
    dias_exp = [(exp - hoy).days for exp in fechas_exp]
    
    idx_cercano = min(range(len(dias_exp)), key=lambda i: abs(dias_exp[i] - plazo_dias))
    fecha_seleccionada = expirations[idx_cercano]
    dias_reales = dias_exp[idx_cercano]
    
    # 3. Descargar cadena
    opt_chain = tk.option_chain(fecha_seleccionada)
    puts = opt_chain.puts.copy()
    
    if puts.empty:
        return None, None, None, None, "Cadena de Puts vacía"
        
    return spot_price, fecha_seleccionada, dias_reales, puts, "OK"


# --- BARRA LATERAL / ENTRADAS DEL USUARIO ---
st.sidebar.header("Parámetros de Entrada")

tickers_input = st.sidebar.text_input(
    "5 Tickers de Acciones (separados por coma):",
    value="AAPL, MSFT, NVDA, AMZN, GOOGL"
)

plazo_dias = st.sidebar.number_input("Plazo objetivo (días a expiración):", min_value=1, value=30, step=1)

offset_pasos = st.sidebar.number_input(
    "Offset en número de strikes (0 a 5):", 
    min_value=0, 
    max_value=5, 
    value=0, 
    step=1,
    help="0 selecciona el strike disponible más cercano por debajo o igual al precio Spot."
)

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
                    # Pausa de 0.5 segundos entre llamadas para ser respetuosos con Yahoo
                    time.sleep(0.5)
                    
                    spot_price, fecha_seleccionada, dias_reales, puts, estado = obtener_datos_opcion(ticker, plazo_dias)
                    
                    if estado != "OK":
                        resultados.append({"Ticker": ticker, "Estado": estado})
                        continue
                    
                    # Ordenar por Strike ascendente
                    puts = puts.sort_values(by="strike").reset_index(drop=True)
                    
                    # Determinar Strike Base
                    puts_debajo_spot = puts[puts['strike'] <= spot_price]
                    
                    if puts_debajo_spot.empty:
                        resultados.append({
                            "Ticker": ticker,
                            "Estado": f"No existen strikes menores o iguales al precio spot (${spot_price:.2f})"
                        })
                        continue
                    
                    idx_base = puts_debajo_spot['strike'].idxmax()
                    idx_sup = idx_base - offset_pasos
                    
                    if idx_sup < 0:
                        resultados.append({
                            "Ticker": ticker,
                            "Estado": f"El offset de {offset_pasos} excede los strikes disponibles hacia abajo."
                        })
                        continue
                    
                    idx_inf = idx_sup - distancia_strikes
                    
                    if idx_inf < 0:
                        resultados.append({
                            "Ticker": ticker,
                            "Estado": f"No hay suficientes strikes por debajo para distancia {distancia_strikes}"
                        })
                        continue
                    
                    row_sup = puts.iloc[idx_sup]
                    row_inf = puts.iloc[idx_inf]
                    
                    strike_sup, bid_sup = row_sup['strike'], row_sup['bid']
                    strike_inf, ask_inf = row_inf['strike'], row_inf['ask']
                    
                    prima_neta = bid_sup - ask_inf
                    importe_recibir = prima_neta * 100
                    utilidad_maxima = importe_recibir
                    
                    diferencia_strikes = strike_sup - strike_inf
                    perdida_maxima = (diferencia_strikes - prima_neta) * 100
                    
                    ratio_utilidad_perdida = (utilidad_maxima / perdida_maxima * 100) if perdida_maxima > 0 else 0.0
                    
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
        
        # Mostrar resultados
        df_res = pd.DataFrame(resultados)
        
        if "OK" in df_res.get("Estado", []).values:
            df_ok = df_res[df_res["Estado"] == "OK"].drop(columns=["Estado"])
            st.subheader("📊 Resultados de las Estrategias")
            st.dataframe(df_ok, use_container_width=True)
            
            st.markdown("### 📥 Descargar Resultados")
            col1, col2 = st.columns(2)
            
            csv_data = df_ok.to_csv(index=False).encode('utf-8')
            col1.download_button("📄 Descargar como CSV", data=csv_data, file_name="put_spreads.csv", mime="text/csv")
            
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_ok.to_excel(writer, index=False, sheet_name='Put_Spreads')
            col2.download_button("📊 Descargar como Excel", data=buffer.getvalue(), file_name="put_spreads.xlsx")
            
            df_err = df_res[df_res["Estado"] != "OK"][["Ticker", "Estado"]]
            if not df_err.empty:
                st.warning("Advertencias / Tickers no procesados:")
                st.table(df_err)
        else:
            st.error("No se pudieron procesar los tickers ingresados.")
            st.table(df_res)
