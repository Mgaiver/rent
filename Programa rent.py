import streamlit as st
import yfinance as yf
import pandas as pd
from io import BytesIO
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Analisador de Long & Short", layout="wide")
st.title("🔁 Analisador de Long & Short")
st.caption("Compare preços de entrada e mercado para avaliar operações individuais e o consolidado.")

# Atualização automática a cada 8 segundos
st_autorefresh(interval=8000, key="refresh")

# Função para buscar preço atual + nome da empresa
def preco_atual(ticker):
    try:
        if not ticker.endswith(".SA"):
            ticker += ".SA"
        dados = yf.Ticker(ticker)
        historico = dados.history(period="1d")
        nome_empresa = dados.info.get("longName", "")
        if historico.empty:
            return None, nome_empresa
        return historico["Close"].iloc[-1], nome_empresa
    except Exception as e:
        return None, ""

# Entrada de dados
with st.form("form_operacao"):
    col1, col2, col3 = st.columns(3)
    with col1:
        ativo = st.text_input("Ativo (ex: PETR4)", "").strip().upper()
        tipo = st.selectbox("Tipo de operação", ["Compra", "Venda"])
    with col2:
        quantidade = st.number_input("Quantidade executada", step=100, min_value=1)
        preco_exec = st.number_input(
            "Preço de execução (por ação)",
            step=0.01,
            format="%.2f",
            min_value=0.01,
            max_value=1000.0,
            help="Digite o valor por ação, e não o valor total da ordem."
        )
    with col3:
        data_operacao = st.date_input("Data da operação", datetime.now().date())
    submit = st.form_submit_button("Adicionar operação")

# Inicializa sessão
if "operacoes" not in st.session_state:
    st.session_state.operacoes = []

# Adiciona operação
if submit and ativo and preco_exec > 0:
    st.session_state.operacoes.append({
        "ativo": ativo,
        "tipo": "c" if tipo == "Compra" else "v",
        "quantidade": quantidade,
        "preco_exec": preco_exec,
        "data": str(data_operacao)
    })

# Botão para resetar todas as operações
if st.button("🧹 Resetar todas as operações"):
    st.session_state.operacoes.clear()
    st.experimental_rerun()

# Exibir operações com botão de excluir
dados_resultado = []
lucro_total = 0
valor_total = 0

if st.session_state.operacoes:
    st.subheader("📋 Operações adicionadas")
    for i, op in enumerate(st.session_state.operacoes):
        col1, col2, col3, col4, col5, col6, col7, col8, col9 = st.columns([1.2, 1.2, 1, 1.5, 1.5, 1.5, 1.5, 1.2, 0.5])
        preco, nome_empresa = preco_atual(op["ativo"])
        if preco is None:
            continue

        qtd = op["quantidade"]
        preco_exec = op["preco_exec"]
        tipo = op["tipo"]
        valor_operacao = qtd * preco_exec
        if tipo == 'c':
            lucro = (preco - preco_exec) * qtd
        else:
            lucro = (preco_exec - preco) * qtd
        perc = (lucro / valor_operacao) * 100 if valor_operacao > 0 else 0
        cor = "green" if lucro > 0 else "red"

        col1.markdown(f"<span title='{nome_empresa}'>{op['ativo']}</span>", unsafe_allow_html=True)
        col2.write("Compra" if tipo == "c" else "Venda")
        col3.write(qtd)
        col4.write(f"R$ {preco_exec:.2f}")
        col5.write(f"R$ {preco:.2f}")
        col6.markdown(f"<div style='background-color: #fff3cd; padding: 4px; border-radius: 5px;'><span style='color:{cor};'>R$ {lucro:.2f}</span></div>", unsafe_allow_html=True)
        col7.markdown(f"<div style='background-color: #fff3cd; padding: 4px; border-radius: 5px;'><span style='color:{cor};'>{perc:.2f}%</span></div>", unsafe_allow_html=True)
        col8.write(op["data"])

        if col9.button("🗑️", key=f"del_{i}"):
            st.session_state.operacoes.pop(i)
            st.experimental_rerun()

        dados_resultado.append({
            "Ativo": op["ativo"],
            "Tipo": "Compra" if tipo == "c" else "Venda",
            "Data": op["data"],
            "Qtd": qtd,
            "Preço Exec.": round(preco_exec, 2),
            "Preço Atual": round(preco, 2),
            "Lucro/Prejuízo (R$)": round(lucro, 2),
            "Variação (%)": round(perc, 2)
        })

# Exibir resultado consolidado
if dados_resultado:
    st.markdown("### 📈 Resultado Consolidado:")
    df_resultado = pd.DataFrame(dados_resultado)
    for op in st.session_state.operacoes:
        valor_total += op["quantidade"] * op["preco_exec"]
    lucro_total = df_resultado["Lucro/Prejuízo (R$)"].sum()
    rentabilidade_total = (lucro_total / valor_total) * 100 if valor_total > 0 else 0

    st.dataframe(df_resultado, use_container_width=True)

    st.success(f"**Lucro/Prejuízo total:** R$ {lucro_total:.2f}")
    st.success(f"**Rentabilidade total:** {rentabilidade_total:.2f}%")

    # Exportar para Excel
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_resultado.to_excel(writer, index=False, sheet_name="Operações")

    st.download_button(
        label="📥 Baixar Excel das operações",
        data=output.getvalue(),
        file_name="analise_operacoes.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
else:
    st.info("Adicione uma operação para visualizar os resultados.")