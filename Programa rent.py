import streamlit as st
import yfinance as yf
import pandas as pd
from io import BytesIO
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import json

# Tenta importar as bibliotecas do Google Cloud.
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
st_autorefresh(interval=10000, key="datarefresh")


# --- Configuração do Firestore ---
@st.cache_resource
def init_firestore():
    if not FIRESTORE_AVAILABLE: return None
    try:
        creds_dict = st.secrets["firebase_credentials"]
        creds = service_account.Credentials.from_service_account_info(creds_dict)
        return firestore.Client(credentials=creds)
    except Exception:
        return None

db_client = init_firestore()

DOC_ID = "dados_gerais_v2" 
COLLECTION_NAME = "analisador_ls_data"

def save_data_to_firestore(data):
    if db_client is None: return
    try:
        doc_ref = db_client.collection(COLLECTION_NAME).document(DOC_ID)
        serializable_data = json.loads(json.dumps(data, default=str))
        doc_ref.set({"assessores": serializable_data})
    except Exception as e:
        st.error(f"Erro ao salvar no Firestore: {e}")

# --- FUNÇÃO DE CARREGAMENTO COM MIGRAÇÃO AUTOMÁTICA ---
def load_data_from_firestore():
    if db_client is None: return {}
    try:
        doc_ref = db_client.collection(COLLECTION_NAME).document(DOC_ID)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            if "assessores" in data:
                return data.get("assessores", {})
            elif "clientes" in data:
                st.info("Detectamos dados antigos. Realizando migração automática para o assessor 'Gaja'.")
                old_clients = data.get("clientes", {})
                migrated_data = {"Gaja": old_clients}
                save_data_to_firestore(migrated_data)
                st.success("Migração concluída com sucesso!")
                return migrated_data

        old_doc_ref = db_client.collection(COLLECTION_NAME).document("dados_todos_clientes_v1")
        old_doc = old_doc_ref.get()
        if old_doc.exists:
            st.info("Detectamos dados antigos. Realizando migração automática para o assessor 'Gaja'.")
            old_data = old_doc.to_dict()
            old_clients = old_data.get("clientes", {})
            migrated_data = {"Gaja": old_clients}
            save_data_to_firestore(migrated_data)
            st.success("Migração concluída com sucesso!")
            return migrated_data
            
        return {}
    except Exception as e:
        st.error(f"Erro ao carregar ou migrar dados do Firestore: {e}")
        return {}


# --- FUNÇÃO get_stock_data VOLTANDO A USAR APENAS YFINANCE ---
def get_stock_data(ticker):
    """
    Busca o preço mais recente e o nome da empresa usando yfinance.
    """
    try:
        if not ticker.endswith(".SA"):
            ticker += ".SA"
        stock = yf.Ticker(ticker)
        
        data = stock.history(period="2d", interval="1m", auto_adjust=True, prepost=True)
        if not data.empty:
            last_row = data.iloc[-1]
            price = last_row['Close']
            last_update_time = data.index[-1].strftime("%H:%M:%S")
            company_name = stock.info.get("longName", "N/A")
            return price, company_name, last_update_time

        info = stock.info
        price = info.get('currentPrice')
        company_name = info.get("longName", "N/A")
        if price:
            return price, company_name, datetime.now().strftime("%H:%M:%S")

        return None, "Não foi possível obter preço", "N/A"
    except Exception as e:
        return None, str(e), "N/A"


# --- FEEDBACK DE CONEXÃO ---
if db_client:
    st.success("💾 Conectado ao banco de dados (Firestore).")
else:
    st.warning("🔌 Persistência de dados desativada. Verifique as credenciais do Firebase.")


# --- CSS E LÓGICA DO APP ---
st.markdown("""
    <style>
    .linha-verde { background-color: rgba(40, 167, 69, 0.15); border-left: 5px solid #28a745; border-radius: 8px; padding: 10px; margin-bottom: 8px; }
    .linha-vermelha { background-color: rgba(220, 53, 69, 0.1); border-left: 5px solid #dc3545; border-radius: 8px; padding: 10px; margin-bottom: 8px; }
    .linha-gain { background-color: rgba(0, 123, 255, 0.15); border-left: 5px solid #007bff; border-radius: 8px; padding: 10px; margin-bottom: 8px; }
    .linha-loss { background-color: rgba(111, 66, 193, 0.15); border-left: 5px solid #6f42c1; border-radius: 8px; padding: 10px; margin-bottom: 8px; }
    .assessor-container { border: 1px solid #e0e0e0; border-radius: 10px; padding: 15px; margin-bottom: 20px; }
    </style>
""", unsafe_allow_html=True)

# --- INICIALIZAÇÃO DOS DADOS E ESTADOS DE EDIÇÃO ---
if "assessores" not in st.session_state:
    with st.spinner("Carregando dados salvos..."):
        st.session_state.assessores = load_data_from_firestore()

if "editing_operation" not in st.session_state:
    st.session_state.editing_operation = None
if "editing_client" not in st.session_state:
    st.session_state.editing_client = None

# --- RENDERIZAÇÃO CONDICIONAL: MOSTRAR FORM DE EDIÇÃO OU TELA PRINCIPAL ---

# MODO DE EDIÇÃO DE CLIENTE
if st.session_state.editing_client:
    assessor_edit, old_client_name = st.session_state.editing_client
    st.subheader(f"Editando Cliente: {old_client_name} (Assessor: {assessor_edit})")
    
    with st.form("edit_client_form"):
        new_client_name = st.text_input("Novo nome do Cliente", value=old_client_name)
        
        col1, col2 = st.columns(2)
        if col1.form_submit_button("Salvar Alterações", use_container_width=True):
            if new_client_name and new_client_name != old_client_name:
                if new_client_name not in st.session_state.assessores[assessor_edit]:
                    st.session_state.assessores[assessor_edit][new_client_name] = st.session_state.assessores[assessor_edit].pop(old_client_name)
                    save_data_to_firestore(st.session_state.assessores)
                    st.session_state.editing_client = None
                    st.rerun()
                else:
                    st.error(f"O nome '{new_client_name}' já existe para este assessor.")
            else:
                st.session_state.editing_client = None
                st.rerun()
        if col2.form_submit_button("Cancelar", use_container_width=True):
            st.session_state.editing_client = None
            st.rerun()

# MODO DE EDIÇÃO DE OPERAÇÃO
elif st.session_state.editing_operation:
    assessor_edit, cliente_edit, op_index_edit = st.session_state.editing_operation
    op_data = st.session_state.assessores[assessor_edit][cliente_edit][op_index_edit]
    
    st.subheader(f"Editando Operação: {op_data['ativo']}")
    with st.form("edit_op_form"):
        st.write(f"**Assessor:** {assessor_edit} | **Cliente:** {cliente_edit}")
        new_quantidade = st.number_input("Quantidade", min_value=1, value=op_data['quantidade'])
        new_preco_exec = st.number_input("Preço de Execução (R$)", format="%.2f", min_value=0.01, value=op_data['preco_exec'])
        new_stop_gain = st.number_input("Stop Gain", format="%.2f", min_value=0.0, value=op_data.get('stop_gain', 0.0))
        new_stop_loss = st.number_input("Stop Loss", format="%.2f", min_value=0.0, value=op_data.get('stop_loss', 0.0))
        
        col1, col2 = st.columns(2)
        if col1.form_submit_button("Salvar Alterações", use_container_width=True):
            op_data.update({
                'quantidade': new_quantidade, 'preco_exec': new_preco_exec,
                'stop_gain': new_stop_gain, 'stop_loss': new_stop_loss
            })
            save_data_to_firestore(st.session_state.assessores)
            st.session_state.editing_operation = None
            st.rerun()
        if col2.form_submit_button("Cancelar", use_container_width=True):
            st.session_state.editing_operation = None
            st.rerun()

# MODO NORMAL (TELA PRINCIPAL)
else:
    # --- FORMULÁRIO DE ENTRADA DE OPERAÇÃO ---
    with st.form("form_operacao"):
        st.subheader("Adicionar Nova Operação")
        c1, c2, c3 = st.columns(3)
        with c1:
            assessor = st.selectbox("Assessor", ["Gaja", "Felber"])
            quantidade = st.number_input("Quantidade", step=100, min_value=1)
        with c2:
            cliente = st.text_input("Nome do Cliente", "").strip()
            preco_exec = st.number_input("Preço Exec. (R$)", format="%.2f", min_value=0.01)
        with c3:
            ativo = st.text_input("Ativo (ex: PETR4)", "").strip().upper()
            tipo_operacao = st.radio("Tipo de Operação", ["Compra", "Venda"], horizontal=True)

        c4, c5 = st.columns(2)
        with c4:
            stop_gain = st.number_input("Stop Gain (Opcional)", format="%.2f", min_value=0.0)
        with c5:
            stop_loss = st.number_input("Stop Loss (Opcional)", format="%.2f", min_value=0.0)
        
        data_operacao = st.date_input("Data da Operação", datetime.now(), format="DD/MM/YYYY")
        if st.form_submit_button("➕ Adicionar Operação", use_container_width=True):
            if cliente and ativo and preco_exec > 0:
                if assessor not in st.session_state.assessores:
                    st.session_state.assessores[assessor] = {}
                if cliente not in st.session_state.assessores[assessor]:
                    st.session_state.assessores[assessor][cliente] = []
                
                st.session_state.assessores[assessor][cliente].append({
                    "ativo": ativo, "tipo": "c" if tipo_operacao == "Compra" else "v", "quantidade": quantidade,
                    "preco_exec": preco_exec, "data": data_operacao.strftime("%d/%m/%Y"),
                    "stop_gain": stop_gain, "stop_loss": stop_loss
                })
                save_data_to_firestore(st.session_state.assessores)
                st.rerun()

    # --- LOOP DE EXIBIÇÃO ---
    if not st.session_state.assessores:
        st.info("Adicione uma operação no formulário acima para começar a análise.")
    else:
        for assessor, clientes in list(st.session_state.assessores.items()):
            with st.container(border=True):
                st.title(f"Assessor: {assessor}")

                assessor_total_comprado = sum(op['quantidade'] * op['preco_exec'] for ops in clientes.values() for op in ops if op['tipo'] == 'c')
                assessor_total_vendido = sum(op['quantidade'] * op['preco_exec'] for ops in clientes.values() for op in ops if op['tipo'] == 'v')

                st.markdown("#### 💰 Financeiro Total do Assessor")
                total_em_operacao = assessor_total_comprado + assessor_total_vendido
                st.metric("Total em Operação (Long + Short)", f"R$ {total_em_operacao:,.2f}")
                st.divider()

                for cliente, operacoes in list(clientes.items()):
                    with st.expander(f"Cliente: {cliente}", expanded=True):
                        
                        col1, col2, col3 = st.columns([0.9, 0.05, 0.05])
                        with col1:
                            st.subheader(f"Análise de {cliente}")
                        with col2:
                            if st.button("✏️", key=f"edit_client_{assessor}_{cliente}", help="Editar nome do cliente"):
                                st.session_state.editing_client = (assessor, cliente)
                                st.rerun()
                        with col3:
                            if st.button("🗑️", key=f"del_client_{assessor}_{cliente}", help=f"Excluir cliente {cliente}"):
                                del st.session_state.assessores[assessor][cliente]
                                save_data_to_firestore(st.session_state.assessores)
                                st.rerun()
                        
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
                            for col, header in zip(cols_header, headers): col.markdown(f"**{header}**")
                            
                            dados_para_df = []
                            for i, op in enumerate(operacoes[:]):
                                preco_atual, nome_empresa_ou_erro, timestamp = get_stock_data(op["ativo"])
                                if preco_atual is None:
                                    st.error(f"Ativo {op['ativo']}: {nome_empresa_ou_erro}")
                                    continue
                                
                                qtd, preco_exec, tipo = op["quantidade"], op["preco_exec"], op["tipo"]
                                valor_entrada = qtd * preco_exec
                                valor_saida_atual = qtd * preco_atual
                                custo_total = (valor_entrada * 0.005) + (valor_saida_atual * 0.005)
                                lucro_bruto = (preco_atual - preco_exec) * qtd if tipo == 'c' else (preco_exec - preco_atual) * qtd
                                lucro_liquido = lucro_bruto - custo_total
                                perc_liquido = (lucro_liquido / valor_entrada) * 100 if valor_entrada > 0 else 0
                                
                                classe_linha = "linha-verde" if lucro_liquido >= 0 else "linha-vermelha"
                                mensagem_alvo, tipo_alvo = "", ""
                                sg, sl = op.get('stop_gain', 0), op.get('stop_loss', 0)
                                
                                target_price_hit = False
                                if tipo == 'c':
                                    if sg > 0 and preco_atual >= sg: target_price_hit = True; mensagem_alvo = f"Gain (R$ {sg:,.2f})"
                                    elif sl > 0 and preco_atual <= sl: target_price_hit = True; mensagem_alvo = f"Loss (R$ {sl:,.2f})"
                                else:
                                    if sg > 0 and preco_atual <= sg: target_price_hit = True; mensagem_alvo = f"Gain (R$ {sg:,.2f})"
                                    elif sl > 0 and preco_atual >= sl: target_price_hit = True; mensagem_alvo = f"Loss (R$ {sl:,.2f})"
                                
                                if target_price_hit:
                                    if lucro_liquido > 0: classe_linha, tipo_alvo = "linha-gain", "gain"
                                    elif lucro_liquido < 0: classe_linha, tipo_alvo = "linha-loss", "loss"

                                with st.container():
                                    st.markdown(f"<div class='{classe_linha}'>", unsafe_allow_html=True)
                                    if tipo_alvo == "gain": st.success(f"🎯 ALVO ATINGIDO: {mensagem_alvo}")
                                    elif tipo_alvo == "loss": st.error(f"🛑 ALVO ATINGIDO: {mensagem_alvo}")
                                        
                                    cols_data = st.columns([1.5, 1, 1, 1.3, 1.5, 1.2, 1.3, 1.2, 1.2, 1])
                                    cols_data[0].markdown(f"<span title='{nome_empresa_ou_erro}'>{op['ativo']}</span>", unsafe_allow_html=True)
                                    cols_data[1].write("🟢 Compra" if tipo == "c" else "🔴 Venda")
                                    cols_data[2].write(f"{qtd:,}")
                                    cols_data[3].write(f"R$ {preco_exec:,.2f}")
                                    cols_data[4].markdown(f"R$ {preco_atual:,.2f}<br><small>({timestamp})</small>", unsafe_allow_html=True)
                                    cols_data[5].write(f"R$ {custo_total:,.2f}")
                                    cols_data[6].markdown(f"<b>R$ {lucro_liquido:,.2f}</b>", unsafe_allow_html=True)
                                    cols_data[7].markdown(f"<b>{perc_liquido:.2f}%</b>", unsafe_allow_html=True)
                                    cols_data[8].write(op["data"])
                                    
                                    action_cols = cols_data[9].columns([1,1])
                                    if action_cols[0].button("✏️", key=f"edit_op_{assessor}_{cliente}_{i}", help="Editar"):
                                        st.session_state.editing_operation = (assessor, cliente, i); st.rerun()
                                    if action_cols[1].button("🗑️", key=f"del_op_{assessor}_{cliente}_{i}", help="Excluir"):
                                        st.session_state.assessores[assessor][cliente].pop(i); save_data_to_firestore(st.session_state.assessores); st.rerun()
                                    st.markdown("</div>", unsafe_allow_html=True)
                                
                                dados_para_df.append({
                                    "Ativo": op["ativo"], "Tipo": "Compra" if tipo == "c" else "Venda", "Data": op["data"], "Qtd": qtd,
                                    "Preço Exec.": preco_exec, "Preço Atual": preco_atual, "Custo (R$)": custo_total,
                                    "Lucro Líquido (R$)": lucro_liquido, "Variação Líquida (%)": perc_liquido,
                                    "Stop Gain": sg, "Stop Loss": sl, "Status Alvo": tipo_alvo or "N/A", "Últ. Atuali.": timestamp
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

    if st.button("🧹 Limpar TUDO (Todos os assessores, clientes e operações)", use_container_width=True):
        st.session_state.assessores.clear()
        save_data_to_firestore(st.session_state.assessores)
        st.rerun()
