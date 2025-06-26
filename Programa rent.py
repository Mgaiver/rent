import streamlit as st
import yfinance as yf
import pandas as pd
from io import BytesIO
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- Configurações da Página ---
st.set_page_config(page_title="Analisador de Long & Short", layout="wide")
st.title("🔁 Analisador de Long & Short")

# --- Atualização Automática ---
# Atualiza a página a cada 8 segundos para obter os preços mais recentes
st_autorefresh(interval=8000, key="datarefresh")

# --- Funções ---
def get_stock_data(ticker):
    """
    Busca o preço de fechamento mais recente e o nome da empresa para um determinado ticker.
    Adiciona o sufixo ".SA" se não estiver presente.
    """
    try:
        # Garante que o ticker tem o sufixo .SA para a B3
        if not ticker.endswith(".SA"):
            ticker += ".SA"
        
        stock = yf.Ticker(ticker)
        # Pega o histórico do último dia
        history = stock.history(period="1d")
        # Pega o nome completo da empresa
        company_name = stock.info.get("longName", "N/A")
        
        if history.empty:
            return None, company_name
        
        # Retorna o último preço de fechamento e o nome da empresa
        return history["Close"].iloc[-1], company_name
    except Exception as e:
        st.error(f"Não foi possível buscar dados para o ativo {ticker}. Erro: {e}")
        return None, ""

# --- CSS Customizado ---
# Estilos para colorir as linhas da tabela de operações com base no lucro/prejuízo
st.markdown("""
    <style>
    .linha-verde {
        background-color: rgba(40, 167, 69, 0.15); /* Verde claro com transparência */
        border-left: 5px solid #28a745; /* Borda verde à esquerda */
        border-radius: 8px;
        padding: 10px;
        margin-bottom: 8px;
    }
    .linha-vermelha {
        background-color: rgba(220, 53, 69, 0.1); /* Vermelho claro com transparência */
        border-left: 5px solid #dc3545; /* Borda vermelha à esquerda */
        border-radius: 8px;
        padding: 10px;
        margin-bottom: 8px;
    }
    </style>
""", unsafe_allow_html=True)

# --- Inicialização do Estado da Sessão ---
if "operacoes" not in st.session_state:
    st.session_state.operacoes = []

# --- Formulário de Entrada de Operação ---
with st.form("form_operacao"):
    st.subheader("Adicionar Nova Operação")
    cols = st.columns([2, 1, 1, 1.5])
    
    with cols[0]:
        ativo = st.text_input("Ativo (ex: PETR4)", "").strip().upper()
    
    with cols[1]:
        tipo_operacao = st.radio("Tipo", ["Compra", "Venda"], horizontal=True, label_visibility="collapsed")

    with cols[2]:
        quantidade = st.number_input("Quantidade", step=100, min_value=1)
    
    with cols[3]:
        preco_exec = st.number_input(
            "Preço de Execução (R$)",
            step=0.01,
            format="%.2f",
            min_value=0.01,
            help="Digite o valor por ação, e não o valor total da ordem."
        )
    
    data_operacao = st.date_input(
        "Data da Operação",
        datetime.now(),
        format="DD/MM/YYYY"
    )

    submitted = st.form_submit_button("➕ Adicionar Operação", use_container_width=True)

# --- Lógica de Adição de Operação ---
if submitted and ativo and preco_exec > 0 and tipo_operacao:
    st.session_state.operacoes.append({
        "ativo": ativo,
        "tipo": "c" if tipo_operacao == "Compra" else "v",
        "quantidade": quantidade,
        "preco_exec": preco_exec,
        "data": data_operacao.strftime("%d/%m/%Y")
    })
    st.rerun()

# --- Exibição das Operações ---
if st.session_state.operacoes:
    st.subheader("📋 Operações Adicionadas")
    
    cols_header = st.columns([1.5, 1, 1, 1.3, 1.3, 1.2, 1.5, 1.2, 1.2, 0.5])
    headers = ["Ativo", "Tipo", "Qtd.", "Preço Exec.", "Preço Atual", "Custo (R$)", "Lucro Líq.", "% Líq.", "Data", ""]
    for col, header in zip(cols_header, headers):
        col.markdown(f"**{header}**")
    
    dados_para_df = []
    
    for i, op in enumerate(st.session_state.operacoes[:]):
        preco_atual, nome_empresa = get_stock_data(op["ativo"])
        
        if preco_atual is None:
            st.warning(f"Não foi possível obter o preço atual de {op['ativo']}. A operação não será exibida.")
            continue

        qtd = op["quantidade"]
        preco_exec = op["preco_exec"]
        tipo = op["tipo"]
        
        # --- CÁLCULOS COM CUSTO ---
        valor_operacao = qtd * preco_exec
        custo = valor_operacao * 0.005  # Custo de 0.5%
        lucro_bruto = (preco_atual - preco_exec) * qtd if tipo == 'c' else (preco_exec - preco_atual) * qtd
        lucro_liquido = lucro_bruto - custo
        perc_liquido = (lucro_liquido / valor_operacao) * 100 if valor_operacao > 0 else 0
        
        cor = "green" if lucro_liquido >= 0 else "red"
        classe_linha = "linha-verde" if lucro_liquido >= 0 else "linha-vermelha"

        with st.container():
            st.markdown(f"<div class='{classe_linha}'>", unsafe_allow_html=True)
            cols_data = st.columns([1.5, 1, 1, 1.3, 1.3, 1.2, 1.5, 1.2, 1.2, 0.5])
            
            cols_data[0].markdown(f"<span title='{nome_empresa}'>{op['ativo']}</span>", unsafe_allow_html=True)
            cols_data[1].write("🟢 Compra" if tipo == "c" else "🔴 Venda")
            cols_data[2].write(qtd)
            cols_data[3].write(f"R$ {preco_exec:.2f}")
            cols_data[4].write(f"R$ {preco_atual:.2f}")
            cols_data[5].write(f"R$ {custo:.2f}")
            cols_data[6].markdown(f"<b style='color:{cor};'>R$ {lucro_liquido:,.2f}</b>", unsafe_allow_html=True)
            cols_data[7].markdown(f"<b style='color:{cor};'>{perc_liquido:.2f}%</b>", unsafe_allow_html=True)
            cols_data[8].write(op["data"])

            if cols_data[9].button("🗑️", key=f"del_{i}", help="Excluir operação"):
                st.session_state.operacoes.pop(i)
                st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)
        
        dados_para_df.append({
            "Ativo": op["ativo"], "Tipo": "Compra" if tipo == "c" else "Venda", "Data": op["data"],
            "Qtd": qtd, "Preço Exec.": preco_exec, "Preço Atual": preco_atual,
            "Custo (R$)": custo,
            "Lucro Líquido (R$)": lucro_liquido, 
            "Variação Líquida (%)": perc_liquido
        })

    # --- Resultado Consolidado e Exportação ---
    if dados_para_df:
        st.markdown("---")
        st.subheader("📈 Resultado Consolidado")
        
        df_resultado = pd.DataFrame(dados_para_df)
        
        lucro_total_liquido = df_resultado["Lucro Líquido (R$)"] .sum()
        custo_total = df_resultado["Custo (R$)"].sum()
        valor_total_investido = (df_resultado["Qtd"] * df_resultado["Preço Exec."]).sum()
        rentabilidade_total = (lucro_total_liquido / valor_total_investido) * 100 if valor_total_investido > 0 else 0
        
        st.dataframe(df_resultado.style.applymap(
            lambda v: f"color: {'green' if v >= 0 else 'red'}", subset=["Lucro Líquido (R$)", "Variação Líquida (%)"]
        ).format({
            "Preço Exec.": "R$ {:,.2f}", "Preço Atual": "R$ {:,.2f}", 
            "Custo (R$)": "R$ {:,.2f}",
            "Lucro Líquido (R$)": "R$ {:,.2f}", 
            "Variação Líquida (%)": "{:,.2f}%"
        }), use_container_width=True)
        
        cols_metricas = st.columns(2)
        cor_lucro = "green" if lucro_total_liquido >= 0 else "red"
        cols_metricas[0].metric(
            label="Lucro/Prejuízo Total Líquido",
            value=f"R$ {lucro_total_liquido:,.2f}",
            delta=f"{rentabilidade_total:,.2f}% sobre o total investido",
            delta_color="normal" if cor_lucro == "green" else "inverse"
        )
        cols_metricas[1].metric(
            label="Custo Total das Operações",
            value=f"R$ {custo_total:,.2f}"
        )
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_resultado.to_excel(writer, index=False, sheet_name="Operacoes")
        
        st.download_button(
            label="📥 Baixar Planilha Excel",
            data=output.getvalue(),
            file_name=f"analise_operacoes_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    if st.button("🧹 Limpar Todas as Operações", use_container_width=True):
        st.session_state.operacoes.clear()
        st.rerun()
else:
    st.info("Adicione uma operação no formulário acima para começar a análise.")