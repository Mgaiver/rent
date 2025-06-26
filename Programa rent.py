import streamlit as st
import yfinance as yf
import pandas as pd
from io import BytesIO
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import json

# Tente importar as bibliotecas do Google Cloud. Se não existirem, o app ainda funcionará, mas sem persistência.
try:
    from google.cloud import firestore
    from google.oauth2 import service_account
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False

# --- Configurações da Página ---
st.set_page_config(page_title="Analisador de Long & Short", layout="wide")
st.title("🔁 Analisador de Long & Short")

# --- Atualização Automática ---
st_autorefresh(interval=8000, key="datarefresh")

# --- Configuração do Firebase/Firestore ---
# Para a persistência de dados funcionar, siga estes passos:
# 1. Crie um projeto no Google Cloud/Firebase: https://firebase.google.com/
# 2. Ative o serviço Firestore.
# 3. Crie uma chave de conta de serviço (Service Account) com permissões de "Editor do Cloud Datastore".
# 4. Baixe o arquivo JSON da chave.
# 5. Se estiver rodando o app no Streamlit Cloud, adicione o conteúdo do arquivo JSON
#    aos segredos (Secrets) do seu app com a chave "firebase_credentials".
#
# Exemplo de como formatar o segredo em TOML (o erro "Invalid TOML" é comum aqui):
#
# [firebase_credentials]
# type = "service_account"
# project_id = "seu-project-id"
# private_key_id = "..."
#
# # IMPORTANTE: O valor da 'private_key' deve ser envolvido por TRÊS aspas duplas (""").
# # Copie a chave do seu JSON e cole entre as três aspas.
# private_key = """-----BEGIN PRIVATE KEY-----\nMII...etc...\n-----END PRIVATE KEY-----\n"""
#
# client_email = "..."
# # ... copie todo o resto do seu arquivo JSON, mantendo o formato chave = "valor"

@st.cache_resource
def init_firestore():
    """Inicializa a conexão com o Firestore usando as credenciais dos segredos do Streamlit."""
    if not FIRESTORE_AVAILABLE:
        return None
    try:
        # Tenta pegar as credenciais dos segredos do Streamlit
        creds_dict = st.secrets["firebase_credentials"]
        creds = service_account.Credentials.from_service_account_info(creds_dict)
        db = firestore.Client(credentials=creds)
        return db
    except (KeyError, Exception) as e:
        # Se falhar, retorna None para que a mensagem de aviso seja exibida
        return None

db = init_firestore()
# ID do documento para salvar os dados. Em um app real, isso poderia ser dinâmico por usuário.
DOC_ID = "dados_todos_clientes_v1"
COLLECTION_NAME = "analisador_ls_data"

def save_data_to_firestore(db_client, data):
    """Salva o dicionário de clientes no Firestore."""
    if db_client is None: return
    try:
        doc_ref = db_client.collection(COLLECTION_NAME).document(DOC_ID)
        # Garante que os dados são serializáveis em JSON antes de enviar
        serializable_data = json.loads(json.dumps(data, default=str))
        doc_ref.set({"clientes": serializable_data})
    except Exception as e:
        st.error(f"Erro ao salvar os dados no Firestore: {e}")

def load_data_from_firestore(db_client):
    """Carrega o dicionário de clientes do Firestore."""
    if db_client is None: return {}
    try:
        doc_ref = db_client.collection(COLLECTION_NAME).document(DOC_ID)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict().get("clientes", {})
        return {}
    except Exception as e:
        st.error(f"Erro ao carregar os dados do Firestore: {e}")
        return {}

# --- Funções do App ---
@st.cache_data
def get_stock_data(ticker):
    """Busca o preço de fechamento mais recente e o nome da empresa."""
    try:
        if not ticker.endswith(".SA"):
            ticker += ".SA"
        stock = yf.Ticker(ticker)
        history = stock.history(period="1d")
        company_name = stock.info.get("longName", "N/A")
        if history.empty:
            return None, company_name
        return history["Close"].iloc[-1], company_name
    except Exception as e:
        return None, str(e)

# --- FEEDBACK DE CONEXÃO COM O BANCO DE DADOS (VISÍVEL NO TOPO) ---
if db:
    st.success("💾 Conectado ao banco de dados. Os dados serão salvos automaticamente.")
else:
    st.warning("🔌 Persistência de dados desativada. Os dados não serão salvos. Verifique se as bibliotecas do Google Cloud estão no `requirements.txt` e se as credenciais do Firebase estão configuradas corretamente.")

# --- CSS Customizado ---
st.markdown("""
    <style>
    .linha-verde { background-color: rgba(40, 167, 69, 0.15); border-left: 5px solid #28a745; border-radius: 8px; padding: 10px; margin-bottom: 8px; }
    .linha-vermelha { background-color: rgba(220, 53, 69, 0.1); border-left: 5px solid #dc3545; border-radius: 8px; padding: 10px; margin-bottom: 8px; }
    </style>
""", unsafe_allow_html=True)

# --- Inicialização e Carregamento dos Dados ---
if "clientes" not in st.session_state:
    if db:
        with st.spinner("Carregando dados salvos..."):
            st.session_state.clientes = load_data_from_firestore(db)
    else:
        st.session_state.clientes = {}

# --- Formulário de Entrada de Operação ---
with st.form("form_operacao"):
    st.subheader("Adicionar Nova Operação")
    cols = st.columns([2, 2, 1, 1, 1.5])
    with cols[0]:
        cliente = st.text_input("Nome do Cliente", "").strip()
    with cols[1]:
        ativo = st.text_input("Ativo (ex: PETR4)", "").strip().upper()
    with cols[2]:
        tipo_operacao = st.radio("Tipo", ["Compra", "Venda"], horizontal=True, label_visibility="collapsed")
    with cols[3]:
        quantidade = st.number_input("Quantidade", step=100, min_value=1)
    with cols[4]:
        preco_exec = st.number_input("Preço Exec. (R$)", step=0.01, format="%.2f", min_value=0.01)
    data_operacao = st.date_input("Data da Operação", datetime.now(), format="DD/MM/YYYY")
    submitted = st.form_submit_button("➕ Adicionar Operação", use_container_width=True)

# --- Lógica de Adição de Operação ---
if submitted and cliente and ativo and preco_exec > 0 and tipo_operacao:
    if cliente not in st.session_state.clientes:
        st.session_state.clientes[cliente] = []
    st.session_state.clientes[cliente].append({
        "ativo": ativo, "tipo": "c" if tipo_operacao == "Compra" else "v", "quantidade": quantidade,
        "preco_exec": preco_exec, "data": data_operacao.strftime("%d/%m/%Y")
    })
    save_data_to_firestore(db, st.session_state.clientes)
    st.rerun()

# --- Exibição das Operações por Cliente ---
if not st.session_state.clientes:
    st.info("Adicione uma operação no formulário acima para começar a análise.")
else:
    for cliente, operacoes in list(st.session_state.clientes.items()):
        col1, col2 = st.columns([0.9, 0.1])
        with col1:
            st.header(f"Cliente: {cliente}")
        with col2:
            if st.button("🗑️", key=f"del_client_{cliente}", help=f"Excluir cliente {cliente} e todas as suas operações"):
                del st.session_state.clientes[cliente]
                save_data_to_firestore(db, st.session_state.clientes)
                st.rerun()
        
        # --- SEÇÃO DE MÉTRICAS FINANCEIRAS DO CLIENTE (COM DESTAQUE) ---
        if operacoes:
            st.markdown("##### 💵 Resumo Financeiro da Carteira")
            total_comprado = sum(op['quantidade'] * op['preco_exec'] for op in operacoes if op['tipo'] == 'c')
            total_vendido = sum(op['quantidade'] * op['preco_exec'] for op in operacoes if op['tipo'] == 'v')
            total_geral = total_comprado + total_vendido
            
            metric_cols = st.columns(3)
            metric_cols[0].metric("Total na Ponta Comprada", f"R$ {total_comprado:,.2f}")
            metric_cols[1].metric("Total na Ponta Vendida", f"R$ {total_vendido:,.2f}")
            metric_cols[2].metric("Financeiro Total", f"R$ {total_geral:,.2f}")
            st.divider()

        st.markdown("##### Detalhes das Operações")
        cols_header = st.columns([1.5, 1, 1, 1.3, 1.3, 1.2, 1.5, 1.2, 1.2, 0.5])
        headers = ["Ativo", "Tipo", "Qtd.", "Preço Exec.", "Preço Atual", "Custo (R$)", "Lucro Líq.", "% Líq.", "Data", ""]
        for col, header in zip(cols_header, headers):
            col.markdown(f"**{header}**")
        
        dados_para_df = []
        for i, op in enumerate(operacoes[:]):
            preco_atual, nome_empresa_ou_erro = get_stock_data(op["ativo"])
            if preco_atual is None:
                st.error(f"Ativo {op['ativo']} do cliente {cliente}: {nome_empresa_ou_erro}")
                continue
            qtd, preco_exec, tipo = op["quantidade"], op["preco_exec"], op["tipo"]
            # --- CUSTO ALTERADO PARA 1% ---
            valor_operacao, custo = qtd * preco_exec, (qtd * preco_exec) * 0.01
            lucro_bruto = (preco_atual - preco_exec) * qtd if tipo == 'c' else (preco_exec - preco_atual) * qtd
            lucro_liquido, perc_liquido = lucro_bruto - custo, ((lucro_bruto - custo) / valor_operacao) * 100 if valor_operacao > 0 else 0
            cor, classe_linha = ("green", "linha-verde") if lucro_liquido >= 0 else ("red", "linha-vermelha")

            with st.container():
                st.markdown(f"<div class='{classe_linha}'>", unsafe_allow_html=True)
                cols_data = st.columns([1.5, 1, 1, 1.3, 1.3, 1.2, 1.5, 1.2, 1.2, 0.5])
                cols_data[0].markdown(f"<span title='{nome_empresa_ou_erro}'>{op['ativo']}</span>", unsafe_allow_html=True)
                cols_data[1].write("🟢 Compra" if tipo == "c" else "🔴 Venda")
                cols_data[2].write(f"{qtd:,}")
                cols_data[3].write(f"R$ {preco_exec:,.2f}")
                cols_data[4].write(f"R$ {preco_atual:,.2f}")
                cols_data[5].write(f"R$ {custo:,.2f}")
                cols_data[6].markdown(f"<b style='color:{cor};'>R$ {lucro_liquido:,.2f}</b>", unsafe_allow_html=True)
                cols_data[7].markdown(f"<b style='color:{cor};'>{perc_liquido:.2f}%</b>", unsafe_allow_html=True)
                cols_data[8].write(op["data"])
                if cols_data[9].button("🗑️", key=f"del_op_{cliente}_{i}", help="Excluir operação"):
                    st.session_state.clientes[cliente].pop(i)
                    save_data_to_firestore(db, st.session_state.clientes)
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)
            
            dados_para_df.append({
                "Ativo": op["ativo"], "Tipo": "Compra" if tipo == "c" else "Venda", "Data": op["data"], "Qtd": qtd,
                "Preço Exec.": preco_exec, "Preço Atual": preco_atual, "Custo (R$)": custo,
                "Lucro Líquido (R$)": lucro_liquido, "Variação Líquida (%)": perc_liquido
            })

        if dados_para_df:
            st.markdown("##### 📈 Resultado Consolidado do Cliente")
            df_resultado = pd.DataFrame(dados_para_df)
            lucro_total_liquido, custo_total = df_resultado["Lucro Líquido (R$)"].sum(), df_resultado["Custo (R$)"].sum()
            valor_total_investido = (df_resultado["Qtd"] * df_resultado["Preço Exec."]).sum()
            rentabilidade_total = (lucro_total_liquido / valor_total_investido) * 100 if valor_total_investido > 0 else 0
            
            st.dataframe(df_resultado.style.applymap(
                lambda v: f"color: {'green' if v >= 0 else 'red'}", subset=["Lucro Líquido (R$)", "Variação Líquida (%)"]
            ).format({
                "Preço Exec.": "R$ {:,.2f}", "Preço Atual": "R$ {:,.2f}", "Custo (R$)": "R$ {:,.2f}",
                "Lucro Líquido (R$)": "R$ {:,.2f}", "Variação Líquida (%)": "{:,.2f}%"
            }), use_container_width=True)
            
            cols_metricas = st.columns(2)
            cols_metricas[0].metric(
                label="Lucro/Prejuízo Total Líquido", 
                value=f"R$ {lucro_total_liquido:,.2f}", 
                delta=f"{rentabilidade_total:,.2f}% sobre o total investido",
                delta_color="normal"
            )
            cols_metricas[1].metric(label="Custo Total das Operações", value=f"R$ {custo_total:,.2f}")
            
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_resultado.to_excel(writer, index=False, sheet_name=f"Operacoes_{cliente}")
            st.download_button(label=f"📥 Baixar Planilha de {cliente}", data=output.getvalue(), file_name=f"analise_operacoes_{cliente.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.xlsx")
        st.markdown("---")

    if len(st.session_state.clientes) > 1 and st.button("🧹 Limpar TUDO (Todos os clientes e operações)", use_container_width=True):
        st.session_state.clientes.clear()
        save_data_to_firestore(db, st.session_state.clientes)
        st.rerun()
