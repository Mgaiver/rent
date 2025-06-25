import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="Analisador de Long & Short", layout="wide")

st.title("🔁 Analisador de Long & Short")
st.caption("Compare preços de entrada e mercado para avaliar operações individuais e o consolidado.")

# Função para buscar preço atual
def preco_atual(ticker):
    try:
        if not ticker.endswith(".SA"):
            ticker += ".SA"
        dados = yf.Ticker(ticker)
        historico = dados.history(period="1d")
        if historico.empty:
            return None
        return historico["Close"].iloc[-1]
    except Exception as e:
        st.warning(f"Erro ao buscar {ticker}: {e}")
        return None

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
        "preco_exec": preco_exec
    })

# Processar operações
dados_resultado = []
lucro_total = 0
valor_total = 0

for op in st.session_state.operacoes:
    preco = preco_atual(op["ativo"])
    if preco is None:
        continue

    qtd = op["quantidade"]
    preco_exec = op["preco_exec"]
    tipo = op["tipo"]
    valor_operacao = qtd * preco_exec
    valor_total += valor_operacao

    if tipo == 'c':
        lucro = (preco - preco_exec) * qtd
    else:  # venda
        lucro = (preco_exec - preco) * qtd

    lucro_total += lucro
    perc = (lucro / valor_operacao) * 100 if valor_operacao > 0 else 0

    dados_resultado.append({
        "Ativo": op["ativo"],
        "Tipo": "Compra" if tipo == "c" else "Venda",
        "Qtd": qtd,
        "Preço Exec.": round(preco_exec, 2),
        "Preço Atual": round(preco, 2),
        "Lucro/Prejuízo (R$)": round(lucro, 2),
        "Variação (%)": round(perc, 2)
    })

# Exibir resultados
if dados_resultado:
    df_resultado = pd.DataFrame(dados_resultado)
    st.dataframe(df_resultado, use_container_width=True)

    st.markdown(f"""
    ### 📈 Resultado Consolidado:
    **Lucro/Prejuízo total:** R$ {lucro_total:.2f}  
    **Rentabilidade total:** {((lucro_total / valor_total) * 100):.2f}%
    """)
else:
    st.info("Adicione uma operação para visualizar os resultados.")