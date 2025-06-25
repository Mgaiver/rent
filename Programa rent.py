import streamlit as st
import yfinance as yf
import pandas as pd
from io import BytesIO

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

# Exibir operações com botão de excluir
st.subheader("📋 Operações adicionadas")
dados_resultado = []
lucro_total = 0
valor_total = 0

for i, op in enumerate(st.session_state.operacoes):
    col1, col2, col3, col4, col5, col6, col7, col8 = st.columns([1.2, 1.2, 1, 1.5, 1.5, 1.5, 1.5, 0.5])
    preco = preco_atual(op["ativo"])
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

    col1.write(op["ativo"])
    col2.write("Compra" if tipo == "c" else "Venda")
    col3.write(qtd)
    col4.write(f"R$ {preco_exec:.2f}")
    col5.write(f"R$ {preco:.2f}")
    col6.write(f"R$ {lucro:.2f}")
    col7.write(f"{perc:.2f}%")

    if col8.button("🗑️", key=f"del_{i}"):
        st.session_state.operacoes.pop(i)
        st.experimental_rerun()

    dados_resultado.append({
        "Ativo": op["ativo"],
        "Tipo": "Compra" if tipo == "c" else "Venda",
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
        writer.save()
        st.download_button(
            label="📥 Baixar Excel das operações",
            data=output.getvalue(),
            file_name="analise_operacoes.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
else:
    st.info("Adicione uma operação para visualizar os resultados.")