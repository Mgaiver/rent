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
@st.cache_resource
def init_firestore():
    """Inicializa a conexão com o Firestore usando as credenciais dos segredos do Streamlit."""
    if not FIRESTORE_AVAILABLE:
        return None
    try:
        creds_dict = st.secrets["firebase_credentials"]
        creds = service_account.Credentials.from_service_account_info(creds_dict)
        db = firestore.Client(credentials=creds)
        return db
    except (KeyError, Exception) as e:
        return None

db = init_firestore()
DOC_ID = "dados_todos_clientes_v1"
COLLECTION_NAME = "analisador_ls_data"

def save_data_to_firestore(db_client, data):
    """Salva o dicionário de clientes no Firestore."""
    if db_client is None: return
    try:
        doc_ref = db_client.collection(COLLECTION_NAME).document(DOC_ID)
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
def get_stock_data(ticker):
    """
    Busca o preço mais recente e o nome da empresa, com mais robustez e retornando um timestamp.
    """
    try:
        if not ticker.endswith(".SA"):
            ticker += ".SA"
        stock = yf.Ticker(ticker)
        
        # 1. Tenta baixar o dado do último minuto para máxima precisão
        data = stock.history(period="2d", interval="1m", auto_adjust=True, prepost=True)
        if not data.empty:
            last_row = data.iloc[-1]
            price = last_row['Close']
            last_update_time = data.index[-1].strftime("%H:%M:%S")
            company_name = stock.info.get("longName", "N/A")
            return price, company_name, last_update_time

        # 2. Fallback: Usar o 'currentPrice' do .info se o método acima falhar
        info = stock.info
        current_price = info.get('currentPrice')
        company_name = info.get("longName", "N/A")
        if current_price:
            last_update_time = datetime.now().strftime("%H:%M:%S")
            return current_price, company_name, last_update_time

        # 3. Fallback final: Usar o histórico diário
        history = stock.history(period="1d")
        if not history.empty:
            price = history["Close"].iloc[-1]
            last_update_time = history.index[-1].strftime("%d/%m/%Y")
            return price, company_name, last_update_time

        return None, f"Não foi possível obter preço para {ticker}", None
    except Exception as e:
        return None, str(e), None

# --- FEEDBACK DE CONEXÃO COM O BANCO DE DADOS ---
if db:
    st.success("💾 Conectado ao banco de dados. Os dados serão salvos automaticamente.")
else:
    st.warning("🔌 Persistência de dados desativada. Os dados não serão salvos. Verifique as credenciais e bibliotecas.")

# --- CSS Customizado ---
st.markdown("""
    <style>
    .linha-verde { background-color: rgba(40, 167, 69, 0.15); border-left: 5px solid #28a745; border-radius: 8px; padding: 10px; margin-bottom: 8px; }
    .linha-vermelha { background-color: rgba(220, 53, 69, 0.1); border-left: 5px solid #dc3545; border-radius: 8px; padding: 10px; margin-bottom: 8px; }
    .linha-gain { background-color: rgba(0, 123, 255, 0.15); border-left: 5px solid #007bff; border-radius: 8px; padding: 10px; margin-bottom: 8px; }
    .linha-loss { background-color: rgba(111, 66, 193, 0.15); border-left: 5px solid #6f42c1; border-radius: 8px; padding: 10px; margin-bottom: 8px; }
    </style>
""", unsafe_allow_html=True)

# --- Inicialização e Carregamento dos Dados ---
if "clientes" not in st.session_state:
    if db:
        with st.spinner("Carregando dados salvos..."):
            st.session_state.clientes = load_data_from_firestore(db)
    else:
        st.session_state.clientes = {}
if "editing_operation" not in st.session_state:
    st.session_state.editing_operation = None

# --- Formulário de Edição (em um st.dialog) ---
if st.session_state.editing_operation is not None:
    cliente_edit, op_index_edit = st.session_state.editing_operation
    op_data = st.session_state.clientes[cliente_edit][op_index_edit]
    
    with st.dialog(f"Editando Operação: {op_data['ativo']}"):
        with st.form("edit_form"):
            st.write(f"**Ativo:** {op_data['ativo']} | **Tipo:** {'Compra' if op_data['tipo'] == 'c' else 'Venda'}")
            
            new_quantidade = st.number_input("Quantidade", step=100, min_value=1, value=op_data['quantidade'])
            new_preco_exec = st.number_input("Preço de Execução (R$)", step=0.01, format="%.2f", min_value=0.01, value=op_data['preco_exec'])
            new_stop_gain = st.number_input("Stop Gain", step=0.01, format="%.2f", min_value=0.0, value=op_data.get('stop_gain', 0.0))
            new_stop_loss = st.number_input("Stop Loss", step=0.01, format="%.2f", min_value=0.0, value=op_data.get('stop_loss', 0.0))
            
            submitted_edit = st.form_submit_button("Salvar Alterações")
            if submitted_edit:
                st.session_state.clientes[cliente_edit][op_index_edit]['quantidade'] = new_quantidade
                st.session_state.clientes[cliente_edit][op_index_edit]['preco_exec'] = new_preco_exec
                st.session_state.clientes[cliente_edit][op_index_edit]['stop_gain'] = new_stop_gain
                st.session_state.clientes[cliente_edit][op_index_edit]['stop_loss'] = new_stop_loss
                
                save_data_to_firestore(db, st.session_state.clientes)
                st.session_state.editing_operation = None
                st.rerun()

            if st.form_submit_button("Cancelar"):
                st.session_state.editing_operation = None
                st.rerun()

# --- Formulário de Entrada de Operação ---
with st.form("form_operacao"):
    st.subheader("Adicionar Nova Operação")
    c1, c2 = st.columns(2)
    with c1:
        cliente = st.text_input("Nome do Cliente", "").strip()
        quantidade = st.number_input("Quantidade", step=100, min_value=1)
        stop_gain = st.number_input("Stop Gain (Opcional)", step=0.01, format="%.2f", min_value=0.0, help="Deixe 0 para não definir.")
    with c2:
        ativo = st.text_input("Ativo (ex: PETR4)", "").strip().upper()
        preco_exec = st.number_input("Preço Exec. (R$)", step=0.01, format="%.2f", min_value=0.01)
        stop_loss = st.number_input("Stop Loss (Opcional)", step=0.01, format="%.2f", min_value=0.0, help="Deixe 0 para não definir.")
    
    tipo_operacao = st.radio("Tipo de Operação", ["Compra", "Venda"], horizontal=True)
    data_operacao = st.date_input("Data da Operação", datetime.now(), format="DD/MM/YYYY")
    submitted = st.form_submit_button("➕ Adicionar Operação", use_container_width=True)

# --- Lógica de Adição de Operação ---
if submitted and cliente and ativo and preco_exec > 0:
    if cliente not in st.session_state.clientes:
        st.session_state.clientes[cliente] = []
    st.session_state.clientes[cliente].append({
        "ativo": ativo, "tipo": "c" if tipo_operacao == "Compra" else "v", "quantidade": quantidade,
        "preco_exec": preco_exec, "data": data_operacao.strftime("%d/%m/%Y"),
        "stop_gain": stop_gain, "stop_loss": stop_loss
    })
    save_data_to_firestore(db, st.session_state.clientes)
    st.rerun()

# --- Exibição das Operações por Cliente ---
if not st.session_state.clientes:
    st.info("Adicione uma operação no formulário acima para começar a análise.")
else:
    for cliente, operacoes in list(st.session_state.clientes.items()):
        with st.expander(f"Cliente: {cliente}", expanded=True):
            st.subheader(f"Análise de {cliente}")
            
            if operacoes:
                st.markdown("##### 💵 Resumo Financeiro da Carteira")
                total_comprado = sum(op['quantidade'] * op['preco_exec'] for op in operacoes if op['tipo'] == 'c')
                total_vendido = sum(op['quantidade'] * op['preco_exec'] for op in operacoes if op['tipo'] == 'v')
                metric_cols = st.columns(3)
                metric_cols[0].metric("Total na Ponta Comprada", f"R$ {total_comprado:,.2f}")
                metric_cols[1].metric("Total na Ponta Vendida", f"R$ {total_vendido:,.2f}")
                metric_cols[2].metric("Financeiro Total", f"R$ {total_comprado + total_vendido:,.2f}")
                st.divider()

            st.markdown("##### Detalhes das Operações")
            headers = ["Ativo", "Tipo", "Qtd.", "Preço Exec.", "Preço Atual", "Custo (R$)", "Lucro Líq.", "% Líq.", "Data", "Ações"]
            cols_header = st.columns([1.5, 1, 1, 1.3, 1.5, 1.2, 1.3, 1.2, 1.2, 1])
            for col, header in zip(cols_header, headers):
                col.markdown(f"**{header}**")
            
            dados_para_df = []
            for i, op in enumerate(operacoes[:]):
                preco_atual, nome_empresa_ou_erro, timestamp = get_stock_data(op["ativo"])
                if preco_atual is None:
                    st.error(f"Ativo {op['ativo']}: {nome_empresa_ou_erro}")
                    continue
                
                qtd, preco_exec, tipo = op["quantidade"], op["preco_exec"], op["tipo"]
                
                valor_entrada = qtd * preco_exec
                valor_saida_atual = qtd * preco_atual
                custo_entrada, custo_saida = valor_entrada * 0.005, valor_saida_atual * 0.005
                custo_total = custo_entrada + custo_saida
                
                lucro_bruto = (preco_atual - preco_exec) * qtd if tipo == 'c' else (preco_exec - preco_atual) * qtd
                lucro_liquido = lucro_bruto - custo_total
                perc_liquido = (lucro_liquido / valor_entrada) * 100 if valor_entrada > 0 else 0
                
                classe_linha = "linha-verde" if lucro_liquido >= 0 else "linha-vermelha"
                mensagem_alvo, tipo_alvo = "", ""

                sg, sl = op.get('stop_gain', 0), op.get('stop_loss', 0)
                
                target_price_hit = False
                if tipo == 'c': # Compra
                    if sg > 0 and preco_atual >= sg: target_price_hit = True; mensagem_alvo = f"Alvo de Gain (R$ {sg:,.2f}) alcançado!"
                    elif sl > 0 and preco_atual <= sl: target_price_hit = True; mensagem_alvo = f"Alvo de Loss (R$ {sl:,.2f}) alcançado!"
                else: # Venda
                    if sg > 0 and preco_atual <= sg: target_price_hit = True; mensagem_alvo = f"Alvo de Gain (R$ {sg:,.2f}) alcançado!"
                    elif sl > 0 and preco_atual >= sl: target_price_hit = True; mensagem_alvo = f"Alvo de Loss (R$ {sl:,.2f}) alcançado!"
                
                if target_price_hit:
                    if lucro_liquido > 0:
                        classe_linha, tipo_alvo = "linha-gain", "gain"
                    elif lucro_liquido < 0:
                        classe_linha, tipo_alvo = "linha-loss", "loss"

                with st.container():
                    st.markdown(f"<div class='{classe_linha}'>", unsafe_allow_html=True)
                    
                    if tipo_alvo == "gain": st.success(f"🎯 GAIN ATINGIDO: {mensagem_alvo}")
                    elif tipo_alvo == "loss": st.error(f"🛑 LOSS ATINGIDO: {mensagem_alvo}")
                        
                    cols_data = st.columns([1.5, 1, 1, 1.3, 1.5, 1.2, 1.3, 1.2, 1.2, 1])
                    
                    cols_data[0].markdown(f"<span title='{nome_empresa_ou_erro}'>{op['ativo']}</span>", unsafe_allow_html=True)
                    cols_data[1].write("🟢 Compra" if tipo == "c" else "🔴 Venda")
                    cols_data[2].write(f"{qtd:,}")
                    cols_data[3].write(f"R$ {preco_exec:,.2f}")
                    # NOVO: Adiciona o timestamp ao preço atual
                    cols_data[4].markdown(f"R$ {preco_atual:,.2f}<br><small>({timestamp})</small>", unsafe_allow_html=True)
                    cols_data[5].write(f"R$ {custo_total:,.2f}")
                    cols_data[6].markdown(f"<b>R$ {lucro_liquido:,.2f}</b>", unsafe_allow_html=True)
                    cols_data[7].markdown(f"<b>{perc_liquido:.2f}%</b>", unsafe_allow_html=True)
                    cols_data[8].write(op["data"])
                    
                    action_cols = cols_data[9].columns([1,1])
                    if action_cols[0].button("✏️", key=f"edit_op_{cliente}_{i}", help="Editar operação"):
                        st.session_state.editing_operation = (cliente, i); st.rerun()
                    if action_cols[1].button("🗑️", key=f"del_op_{cliente}_{i}", help="Excluir operação"):
                        st.session_state.clientes[cliente].pop(i); save_data_to_firestore(db, st.session_state.clientes); st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)
                
                status_alvo = "N/A"
                if tipo_alvo == "gain": status_alvo = "Gain Atingido"
                elif tipo_alvo == "loss": status_alvo = "Loss Atingido"
                
                dados_para_df.append({
                    "Ativo": op["ativo"], "Tipo": "Compra" if tipo == "c" else "Venda", "Data": op["data"], "Qtd": qtd,
                    "Preço Exec.": preco_exec, "Preço Atual": preco_atual, "Custo (R$)": custo_total,
                    "Lucro Líquido (R$)": lucro_liquido, "Variação Líquida (%)": perc_liquido,
                    "Stop Gain": sg, "Stop Loss": sl, "Status Alvo": status_alvo, "Últ. Atuali.": timestamp
                })

            if dados_para_df:
                st.markdown("##### 📈 Resultado Consolidado do Cliente")
                df_resultado = pd.DataFrame(dados_para_df)
                lucro_total_liquido = df_resultado["Lucro Líquido (R$)"].sum()
                custo_total_df = df_resultado["Custo (R$)"].sum()
                valor_total_investido = (df_resultado["Qtd"] * df_resultado["Preço Exec."]).sum()
                rentabilidade_total = (lucro_total_liquido / valor_total_investido) * 100 if valor_total_investido > 0 else 0
                
                st.dataframe(df_resultado, use_container_width=True)
                
                cols_metricas = st.columns(2)
                cols_metricas[0].metric("Lucro/Prejuízo Total Líquido", f"R$ {lucro_total_liquido:,.2f}", f"{rentabilidade_total:,.2f}% sobre o total investido", delta_color="normal")
                cols_metricas[1].metric("Custo Total das Operações", value=f"R$ {custo_total_df:,.2f}")
                
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_resultado.to_excel(writer, index=False, sheet_name=f"Operacoes_{cliente}")
                st.download_button(label=f"📥 Baixar Planilha de {cliente}", data=output.getvalue(), file_name=f"analise_operacoes_{cliente.replace(' ', '_')}.xlsx")

    if st.button("🧹 Limpar TUDO (Todos os clientes e operações)", use_container_width=True):
        st.session_state.clientes.clear()
        save_data_to_firestore(db, st.session_state.clientes)
        st.rerun()
