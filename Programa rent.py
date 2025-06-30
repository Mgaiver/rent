import streamlit as st
import yfinance as yf
import pandas as pd
from io import BytesIO
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import json

# Tenta importar as bibliotecas do Google Cloud e FPDF.
try:
    from google.cloud import firestore
    from google.oauth2 import service_account
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False

try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True
except ImportError:
    FPDF_AVAILABLE = False

# --- Configurações da Página ---
st.set_page_config(page_title="Analisador de Long & Short", layout="wide")
st.title("🔁 Analisador de Long & Short")

# --- Atualização Automática ---
st_autorefresh(interval=15000, key="datarefresh")


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

DOC_ID_NEW = "dados_gerais_v3"
DOC_ID_OLD = "dados_todos_clientes_v1" # ID do documento da estrutura antiga
COLLECTION_NAME = "analisador_ls_data"

def save_data_to_firestore(data):
    if db_client is None: return
    try:
        doc_ref = db_client.collection(COLLECTION_NAME).document(DOC_ID_NEW)
        serializable_data = json.loads(json.dumps(data, default=str))
        doc_ref.set({"assessores": serializable_data})
    except Exception as e:
        st.error(f"Erro ao salvar no Firestore: {e}")

# --- FUNÇÃO DE CARREGAMENTO COM MIGRAÇÃO ROBUSTA ---
def load_data_from_firestore():
    if db_client is None: return {}
    try:
        new_doc_ref = db_client.collection(COLLECTION_NAME).document(DOC_ID_NEW)
        new_doc = new_doc_ref.get()
        if new_doc.exists and "assessores" in new_doc.to_dict():
            return new_doc.to_dict().get("assessores", {})

        old_doc_ref = db_client.collection(COLLECTION_NAME).document(DOC_ID_OLD)
        old_doc = old_doc_ref.get()
        if old_doc.exists and "clientes" in old_doc.to_dict():
            st.info("Detectamos dados antigos. Realizando migração automática para o assessor 'Gaja'.")
            old_clients = old_doc.to_dict().get("clientes", {})
            if old_clients:
                migrated_data = {"Gaja": old_clients}
                save_data_to_firestore(migrated_data)
                st.success("Migração concluída! Seus dados foram movidos para a nova estrutura.")
                return migrated_data
        
        return {}
    except Exception as e:
        st.error(f"Erro ao carregar ou migrar dados do Firestore: {e}")
        return {}


# --- FUNÇÃO get_stock_data ---
def get_stock_data(ticker):
    try:
        if not ticker.endswith(".SA"):
            ticker += ".SA"
        stock = yf.Ticker(ticker)
        data = stock.history(period="2d", interval="1m", auto_adjust=True, prepost=True)
        if not data.empty:
            last_row = data.iloc[-1]
            return last_row['Close'], stock.info.get("longName", "N/A"), data.index[-1].strftime("%H:%M:%S")
        info = stock.info
        price = info.get('currentPrice')
        if price:
            return price, info.get("longName", "N/A"), datetime.now().strftime("%H:%M:%S")
        return None, "Não foi possível obter preço", "N/A"
    except Exception as e:
        return None, str(e), "N/A"

# --- FUNÇÃO PARA GERAR PDF ---
def create_pdf_report(dataframe):
    if not FPDF_AVAILABLE:
        st.error("A biblioteca FPDF2 não está instalada. Adicione 'fpdf2' ao seu requirements.txt.")
        return None

    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    
    pdf.cell(277, 10, 'Relatório de Operações', 0, 1, 'C')
    pdf.ln(10)

    pdf.set_font("Arial", 'B', 7)
    
    col_widths = {
        'assessor': 22, 'cliente': 22, 'ativo': 12, 'tipo': 12, 'quantidade': 12, 
        'preco_exec': 18, 'preco_atual': 18, 'custo_total': 18, 'lucro_liquido': 22, 
        'perc_liquido': 20, 'data': 18, 'status': 18, 
        'preco_encerramento': 22, 'data_encerramento': 22, 'lucro_final': 22
    }
    
    report_columns = dataframe.columns
    for col in report_columns:
        if col not in col_widths:
            col_widths[col] = 18

    for header in report_columns:
        pdf.cell(col_widths[header], 7, str(header), 1, 0, 'C')
    pdf.ln()

    pdf.set_font("Arial", '', 7)
    for _, row in dataframe.iterrows():
        for col in report_columns:
            text = str(row.get(col, ''))
            if isinstance(row.get(col), (int, float)):
                text = f"{row[col]:,.2f}"
            pdf.cell(col_widths[col], 6, text, 1)
        pdf.ln()
        
    return pdf.output(dest='S').encode('latin-1')


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
    .linha-encerrada { background-color: rgba(108, 117, 125, 0.15); border-left: 5px solid #6c757d; border-radius: 8px; padding: 10px; margin-bottom: 8px; }
    </style>
""", unsafe_allow_html=True)

# --- INICIALIZAÇÃO DOS DADOS E ESTADOS ---
if "assessores" not in st.session_state:
    with st.spinner("Carregando dados salvos..."):
        st.session_state.assessores = load_data_from_firestore()

if "editing_operation" not in st.session_state: st.session_state.editing_operation = None
if "editing_client" not in st.session_state: st.session_state.editing_client = None
if "closing_operation" not in st.session_state: st.session_state.closing_operation = None
if "expand_all" not in st.session_state: st.session_state.expand_all = {}
if "report_df" not in st.session_state: st.session_state.report_df = None


# --- RENDERIZAÇÃO CONDICIONAL ---

# MODO DE EDIÇÃO DE CLIENTE
if st.session_state.editing_client:
    assessor_edit, old_client_name = st.session_state.editing_client
    st.subheader(f"Editando Cliente: {old_client_name} (Assessor: {assessor_edit})")
    with st.form("edit_client_form"):
        new_client_name = st.text_input("Novo nome do Cliente", value=old_client_name)
        if st.form_submit_button("Salvar Alterações"):
            if new_client_name and new_client_name != old_client_name:
                st.session_state.assessores[assessor_edit][new_client_name] = st.session_state.assessores[assessor_edit].pop(old_client_name)
                save_data_to_firestore(st.session_state.assessores)
            st.session_state.editing_client = None
            st.rerun()
        if st.form_submit_button("Cancelar"):
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
        if st.form_submit_button("Salvar"):
            op_data.update({'quantidade': new_quantidade, 'preco_exec': new_preco_exec, 'stop_gain': new_stop_gain, 'stop_loss': new_stop_loss})
            save_data_to_firestore(st.session_state.assessores)
            st.session_state.editing_operation = None
            st.rerun()
        if st.form_submit_button("Cancelar"):
            st.session_state.editing_operation = None
            st.rerun()

# MODO DE ENCERRAMENTO DE OPERAÇÃO
elif st.session_state.closing_operation:
    assessor_close, cliente_close, op_index_close = st.session_state.closing_operation
    op_data = st.session_state.assessores[assessor_close][cliente_close][op_index_close]
    st.subheader(f"Encerrando Operação: {op_data['ativo']} para {cliente_close}")
    with st.form("close_op_form"):
        preco_encerramento = st.number_input("Preço de Encerramento (R$)", format="%.2f", min_value=0.01, value=get_stock_data(op_data['ativo'])[0])
        data_encerramento = st.date_input("Data de Encerramento", datetime.now())
        if st.form_submit_button("Confirmar Encerramento"):
            op_data['status'] = 'encerrada'
            op_data['preco_encerramento'] = preco_encerramento
            op_data['data_encerramento'] = data_encerramento.strftime("%d/%m/%Y")
            qtd, preco_exec, tipo = op_data["quantidade"], op_data["preco_exec"], op_data["tipo"]
            valor_entrada, valor_saida = qtd * preco_exec, qtd * preco_encerramento
            custo_total = (valor_entrada * 0.005) + (valor_saida * 0.005)
            lucro_bruto = (preco_encerramento - preco_exec) * qtd if tipo == 'c' else (preco_exec - preco_encerramento) * qtd
            op_data['lucro_final'] = lucro_bruto - custo_total
            save_data_to_firestore(st.session_state.assessores)
            st.session_state.closing_operation = None
            st.rerun()
        if st.form_submit_button("Cancelar"):
            st.session_state.closing_operation = None
            st.rerun()

# MODO NORMAL (TELA PRINCIPAL)
else:
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
                
                new_op = {
                    "ativo": ativo, "tipo": "c" if tipo_operacao == "Compra" else "v", "quantidade": quantidade,
                    "preco_exec": preco_exec, "data": data_operacao.strftime("%d/%m/%Y"),
                    "stop_gain": stop_gain, "stop_loss": stop_loss, "status": 'ativa'
                }
                st.session_state.assessores[assessor][cliente].append(new_op)
                save_data_to_firestore(st.session_state.assessores)
                st.rerun()

    st.divider()
    st.subheader("Visão Geral das Carteiras")
    view_filter = st.radio("Filtrar Operações:", ["Ativas", "Encerradas", "Todas"], horizontal=True, key="view_filter")

    if not st.session_state.assessores:
        st.info("Adicione uma operação no formulário acima para começar a análise.")
    else:
        for assessor, clientes in list(st.session_state.assessores.items()):
            with st.container(border=True):
                st.title(f"Assessor: {assessor}")
                
                assessor_total_comprado = sum(op['quantidade'] * op['preco_exec'] for ops in clientes.values() for op in ops if op['tipo'] == 'c' and op.get('status', 'ativa') == 'ativa')
                assessor_total_vendido = sum(op['quantidade'] * op['preco_exec'] for ops in clientes.values() for op in ops if op['tipo'] == 'v' and op.get('status', 'ativa') == 'ativa')
                st.markdown("#### 💰 Financeiro Total do Assessor (Operações Ativas)")
                total_em_operacao = assessor_total_comprado + assessor_total_vendido
                st.metric("Total em Operação (Long + Short)", f"R$ {total_em_operacao:,.2f}")
                st.divider()

                col_exp, col_rec = st.columns(2)
                if col_exp.button(f"Expandir Todos ({assessor})", key=f"expand_{assessor}"):
                    st.session_state.expand_all[assessor] = True
                if col_rec.button(f"Recolher Todos ({assessor})", key=f"collapse_{assessor}"):
                    st.session_state.expand_all[assessor] = False

                for cliente, operacoes in list(clientes.items()):
                    
                    expanded_state = st.session_state.expand_all.get(assessor, True)
                    with st.expander(f"Cliente: {cliente}", expanded=expanded_state):
                        
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
                        
                        if view_filter == "Ativas":
                            operacoes_a_mostrar = [op for op in operacoes if op.get('status', 'ativa') == 'ativa']
                        elif view_filter == "Encerradas":
                            operacoes_a_mostrar = [op for op in operacoes if op.get('status') == 'encerrada']
                        else:
                            operacoes_a_mostrar = operacoes
                        
                        if not operacoes_a_mostrar:
                            st.info(f"Nenhuma operação '{view_filter}' para este cliente.")
                            continue

                        st.markdown("##### 💵 Resumo Financeiro da Carteira")
                        total_comprado = sum(op['quantidade'] * op['preco_exec'] for op in operacoes if op['tipo'] == 'c')
                        total_vendido = sum(op['quantidade'] * op['preco_exec'] for op in operacoes if op['tipo'] == 'v')
                        metric_cols = st.columns(3)
                        metric_cols[0].metric("Total na Ponta Comprada", f"R$ {total_comprado:,.2f}")
                        metric_cols[1].metric("Total na Ponta Vendida", f"R$ {total_vendido:,.2f}")
                        metric_cols[2].metric("Financeiro Total", f"R$ {total_comprado + total_vendido:,.2f}")
                        st.divider()

                        st.markdown("##### Detalhes das Operações")
                        headers = ["Ativo", "Tipo", "Qtd.", "Preço Exec.", "Preço Atual/Final", "Custo (R$)", "Lucro Líq.", "% Líq.", "Data", "Ações"]
                        cols_header = st.columns([1.5, 1, 1, 1.3, 1.5, 1.2, 1.3, 1.2, 1.2, 1.2])
                        for col, header in zip(cols_header, headers): col.markdown(f"**{header}**")
                        
                        for i, op in enumerate(operacoes):
                            if op not in operacoes_a_mostrar:
                                continue
                            
                            is_active = op.get('status', 'ativa') == 'ativa'
                            if is_active:
                                preco_atual, nome_empresa, timestamp = get_stock_data(op["ativo"])
                                if preco_atual is None:
                                    st.error(f"Ativo {op['ativo']}: {nome_empresa}")
                                    continue
                                valor_saida_atual = op['quantidade'] * preco_atual
                                custo_saida = valor_saida_atual * 0.005
                                lucro_bruto = (preco_atual - op['preco_exec']) * op['quantidade'] if op['tipo'] == 'c' else (op['preco_exec'] - preco_atual) * op['quantidade']
                                preco_display = f"R$ {preco_atual:,.2f}<br><small>({timestamp})</small>"
                            else: # Operação Encerrada
                                preco_atual = op.get('preco_encerramento', op['preco_exec'])
                                lucro_liquido = op.get('lucro_final', 0)
                                perc_liquido = (lucro_liquido / (op['quantidade'] * op['preco_exec'])) * 100 if (op['quantidade'] * op['preco_exec']) > 0 else 0
                                preco_display = f"R$ {preco_atual:,.2f}<br><small>(Encerrada)</small>"

                            qtd, preco_exec, tipo = op["quantidade"], op["preco_exec"], op["tipo"]
                            valor_entrada = qtd * preco_exec
                            custo_entrada = valor_entrada * 0.005
                            custo_total = custo_entrada + (custo_saida if is_active else valor_entrada * 0.005)
                            
                            if is_active:
                                lucro_liquido = lucro_bruto - custo_total
                                perc_liquido = (lucro_liquido / valor_entrada) * 100 if valor_entrada > 0 else 0

                            classe_linha = "linha-encerrada" if not is_active else ("linha-verde" if lucro_liquido >= 0 else "linha-vermelha")
                            
                            with st.container():
                                st.markdown(f"<div class='{classe_linha}'>", unsafe_allow_html=True)
                                cols_data = st.columns([1.5, 1, 1, 1.3, 1.5, 1.2, 1.3, 1.2, 1.2, 1.2])
                                cols_data[0].markdown(f"<span title='{nome_empresa if is_active else 'Operação Encerrada'}'>{op['ativo']}</span>", unsafe_allow_html=True)
                                cols_data[1].write("🟢 Compra" if tipo == "c" else "🔴 Venda")
                                cols_data[2].write(f"{qtd:,}")
                                cols_data[3].write(f"R$ {preco_exec:,.2f}")
                                cols_data[4].markdown(preco_display, unsafe_allow_html=True)
                                cols_data[5].write(f"R$ {custo_total:,.2f}")
                                cols_data[6].markdown(f"<b>R$ {lucro_liquido:,.2f}</b>", unsafe_allow_html=True)
                                cols_data[7].markdown(f"<b>{perc_liquido:.2f}%</b>", unsafe_allow_html=True)
                                cols_data[8].write(op["data"])
                                
                                action_cols = cols_data[9].columns([1,1,1] if is_active else [1])
                                if is_active:
                                    if action_cols[0].button("✏️", key=f"edit_op_{assessor}_{cliente}_{i}"): st.session_state.editing_operation = (assessor, cliente, i); st.rerun()
                                    if action_cols[1].button("🗑️", key=f"del_op_{assessor}_{cliente}_{i}"): operacoes.pop(i); save_data_to_firestore(st.session_state.assessores); st.rerun()
                                    if action_cols[2].button("🔒", key=f"close_op_{assessor}_{cliente}_{i}"): st.session_state.closing_operation = (assessor, cliente, i); st.rerun()
                                else:
                                    action_cols[0].write("🔒")
                                st.markdown("</div>", unsafe_allow_html=True)

    st.divider()
    # --- SEÇÃO DE RELATÓRIOS ---
    with st.container(border=True):
        st.header("Gerar Relatório Personalizado")
        
        assessores_disponiveis = list(st.session_state.assessores.keys())
        if assessores_disponiveis:
            assessores_selecionados = st.multiselect("Selecione os Assessores", options=assessores_disponiveis, default=assessores_disponiveis)
            status_relatorio = st.radio("Status das Operações para o Relatório", ["Ativas", "Encerradas", "Todas"], horizontal=True, key="report_status")
            
            if st.button("Gerar Relatório"):
                report_data = []
                for assessor in assessores_selecionados:
                    for cliente, operacoes in st.session_state.assessores.get(assessor, {}).items():
                        for op in operacoes:
                            status_op = op.get('status', 'ativa')
                            if (status_relatorio == "Todas") or \
                               (status_relatorio == "Ativas" and status_op == 'ativa') or \
                               (status_relatorio == "Encerradas" and status_op == 'encerrada'):
                                
                                op_details = op.copy()
                                op_details['assessor'] = assessor
                                op_details['cliente'] = cliente
                                report_data.append(op_details)
                
                if report_data:
                    st.session_state.report_df = pd.DataFrame(report_data)
                else:
                    st.session_state.report_df = None
                    st.warning("Nenhuma operação encontrada para os filtros selecionados.")
            
            if st.session_state.report_df is not None:
                st.dataframe(st.session_state.report_df)
                
                col1, col2, col3 = st.columns([2,2,1])
                output_excel = BytesIO()
                with pd.ExcelWriter(output_excel, engine='xlsxwriter') as writer:
                    st.session_state.report_df.to_excel(writer, index=False, sheet_name="Relatorio")
                
                col1.download_button(
                    label="📥 Baixar Relatório em Excel", data=output_excel.getvalue(),
                    file_name=f"relatorio_operacoes_{datetime.now().strftime('%Y%m%d')}.xlsx", use_container_width=True
                )
                pdf_data = create_pdf_report(st.session_state.report_df)
                if pdf_data:
                    col2.download_button(
                        label="📄 Baixar Relatório em PDF", data=pdf_data,
                        file_name=f"relatorio_operacoes_{datetime.now().strftime('%Y%m%d')}.pdf",
                        mime="application/pdf", use_container_width=True
                    )
                
                if col3.button("Limpar Relatório", use_container_width=True):
                    st.session_state.report_df = None
                    st.rerun()
        else:
            st.info("Nenhum assessor com operações cadastradas para gerar relatório.")
