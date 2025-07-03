import streamlit as st
import yfinance as yf
import pandas as pd
from io import BytesIO
from datetime import datetime, timedelta
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
st.set_page_config(page_title="Acompanhamento de Long & Short", layout="wide")
st.title("🔁 Acompanhamento de Long & Short")

# --- Atualização Automática ---
st_autorefresh(interval=30000, key="datarefresh")


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
        'assessor': 20, 'cliente': 20, 'ativo': 12, 'tipo': 12, 'quantidade': 12, 
        'preco_exec': 18, 'preco_atual': 18, 'custo_total': 18, 'lucro_liquido': 20, 
        'perc_bruto': 18, 'perc_liquido': 18, 'data': 18, 'status': 18, 
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
            text = str(row.get(col, '')).encode('latin-1', 'replace').decode('latin-1')
            if isinstance(row.get(col), (int, float)):
                text = f"{row[col]:,.2f}"
            pdf.cell(col_widths[col], 6, text, 1)
        pdf.ln()
    
    return bytes(pdf.output())


# --- FEEDBACK DE CONEXÃO ---
if db_client:
    st.success("💾 Conectado ao banco de dados.")
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
    
    .metric-card {
        padding: 15px;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 10px;
    }
    .metric-card-green {
        background-color: #28a745;
    }
    .metric-card-red {
        background-color: #dc3545;
    }
    .metric-card .label {
        font-size: 1em;
        font-weight: bold;
    }
    .metric-card .value {
        font-size: 1.5em;
        font-weight: bolder;
    }
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
    is_active_edit = op_data.get('status', 'ativa') == 'ativa'
    
    st.subheader(f"Editando Operação: {op_data['ativo']}")
    with st.form("edit_op_form"):
        st.write(f"**Assessor:** {assessor_edit} | **Cliente:** {cliente_edit}")
        new_quantidade = st.number_input("Quantidade", min_value=1, value=op_data['quantidade'])
        new_preco_exec = st.number_input("Preço de Execução (R$)", format="%.2f", min_value=0.01, value=op_data['preco_exec'])
        
        if not is_active_edit:
            new_preco_encerramento = st.number_input("Preço de Encerramento (R$)", format="%.2f", min_value=0.01, value=op_data.get('preco_encerramento', 0.0))
            current_data_encerramento = datetime.strptime(op_data.get('data_encerramento'), "%d/%m/%Y") if op_data.get('data_encerramento') else datetime.now()
            new_data_encerramento = st.date_input("Data de Encerramento", value=current_data_encerramento, format="DD/MM/YYYY")
        else:
            new_stop_gain = st.number_input("Stop Gain", format="%.2f", min_value=0.0, value=op_data.get('stop_gain', 0.0))
            new_stop_loss = st.number_input("Stop Loss", format="%.2f", min_value=0.0, value=op_data.get('stop_loss', 0.0))

        if st.form_submit_button("Salvar"):
            op_data.update({'quantidade': new_quantidade, 'preco_exec': new_preco_exec})
            if is_active_edit:
                op_data.update({'stop_gain': new_stop_gain, 'stop_loss': new_stop_loss})
            else:
                op_data.update({'preco_encerramento': new_preco_encerramento, 'data_encerramento': new_data_encerramento.strftime("%d/%m/%Y")})
                qtd, preco_exec, tipo = op_data["quantidade"], op_data["preco_exec"], op_data["tipo"]
                valor_entrada, valor_saida = qtd * preco_exec, qtd * new_preco_encerramento
                custo_total = (valor_entrada * 0.005) + (valor_saida * 0.005)
                lucro_bruto = (new_preco_encerramento - preco_exec) * qtd if tipo == 'c' else (preco_exec - new_preco_encerramento) * qtd
                op_data['lucro_final'] = lucro_bruto - custo_total

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
        preco_encerramento = st.number_input("Preço de Encerramento (R$)", format="%.2f", min_value=0.01)
        data_encerramento = st.date_input("Data de Encerramento", datetime.now(), format="DD/MM/YYYY")
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
    # --- PAINEL DINÂMICO DE OPERAÇÕES ATIVAS ---
    st.subheader("Painel Dinâmico de Clientes (Operações Ativas)")
    client_summary = []
    for assessor, clientes in st.session_state.assessores.items():
        for cliente, operacoes in clientes.items():
            active_ops = [op for op in operacoes if op.get('status', 'ativa') == 'ativa']
            if not active_ops:
                continue

            total_lucro_liquido = 0
            total_investido = 0
            for op in active_ops:
                preco_atual, _, _ = get_stock_data(op["ativo"])
                if preco_atual is None: continue
                
                qtd, preco_exec, tipo = op["quantidade"], op["preco_exec"], op["tipo"]
                valor_entrada = qtd * preco_exec
                valor_saida_atual = qtd * preco_atual
                custo_total = (valor_entrada * 0.005) + (valor_saida_atual * 0.005)
                lucro_bruto = (preco_atual - preco_exec) * qtd if tipo == 'c' else (preco_exec - preco_atual) * qtd
                
                total_lucro_liquido += lucro_bruto - custo_total
                total_investido += valor_entrada
            
            perc_consolidado = (total_lucro_liquido / total_investido) * 100 if total_investido > 0 else 0
            client_summary.append({"cliente": f"{cliente} ({assessor})", "resultado": perc_consolidado})

    if client_summary:
        cols = st.columns(5) 
        for i, summary in enumerate(client_summary):
            with cols[i % 5]:
                color_class = "metric-card-green" if summary['resultado'] >= 0 else "metric-card-red"
                st.markdown(f'<div class="metric-card {color_class}"><div class="label">{summary["cliente"]}</div><div class="value">{summary["resultado"]:.2f}%</div></div>', unsafe_allow_html=True)
    else:
        st.info("Nenhum cliente com operações ativas para exibir no painel.")

    # --- PAINEL DE OPERAÇÕES ENCERRADAS ---
    st.subheader("Painel de Operações Encerradas")
    closed_client_summary = []
    for assessor, clientes in st.session_state.assessores.items():
        for cliente, operacoes in clientes.items():
            closed_ops = [op for op in operacoes if op.get('status') == 'encerrada']
            if not closed_ops:
                continue

            total_lucro_final = sum(op.get('lucro_final', 0) for op in closed_ops)
            total_investido = sum(op['quantidade'] * op['preco_exec'] for op in closed_ops)
            
            perc_consolidado = (total_lucro_final / total_investido) * 100 if total_investido > 0 else 0
            closed_client_summary.append({"cliente": f"{cliente} ({assessor})", "resultado": perc_consolidado})
    
    if closed_client_summary:
        cols = st.columns(5)
        for i, summary in enumerate(closed_client_summary):
            with cols[i % 5]:
                color_class = "metric-card-green" if summary['resultado'] >= 0 else "metric-card-red"
                st.markdown(f'<div class="metric-card {color_class}"><div class="label">{summary["cliente"]}</div><div class="value">{summary["resultado"]:.2f}%</div></div>', unsafe_allow_html=True)
    else:
        st.info("Nenhum cliente com operações encerradas para exibir no painel.")


    st.divider()
    
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
    
    if not st.session_state.assessores:
        st.info("Adicione uma operação no formulário acima para começar a análise.")
    else:
        for assessor, clientes in list(st.session_state.assessores.items()):
            with st.container(border=True):
                st.title(f"Assessor: {assessor}")
                
                assessor_total_comprado = sum(op['quantidade'] * op['preco_exec'] for ops in clientes.values() for op in ops if op['tipo'] == 'c' and op.get('status', 'ativa') == 'ativa')
                assessor_total_vendido = sum(op['quantidade'] * op['preco_exec'] for ops in clientes.values() for op in ops if op['tipo'] == 'v' and op.get('status', 'ativa') == 'ativa')
                
                today = datetime.now()
                last_day_of_last_month = today.replace(day=1) - timedelta(days=1)
                last_month = last_day_of_last_month.month
                last_month_year = last_day_of_last_month.year
                
                resultado_encerrado_mes = 0
                for ops in clientes.values():
                    for op in ops:
                        if op.get('status') == 'encerrada' and 'data_encerramento' in op:
                            try:
                                data_encerramento_dt = datetime.strptime(op['data_encerramento'], "%d/%m/%Y")
                                if data_encerramento_dt.month == last_month and data_encerramento_dt.year == last_month_year:
                                    resultado_encerrado_mes += op.get('lucro_final', 0)
                            except (ValueError, TypeError):
                                continue

                st.markdown("#### 💰 Financeiro Total do Assessor")
                metric_cols = st.columns(2)
                total_em_operacao = assessor_total_comprado + assessor_total_vendido
                metric_cols[0].metric("Total em Operação (Ativas)", f"R$ {total_em_operacao:,.2f}")
                month_name = last_day_of_last_month.strftime("%B").capitalize()
                metric_cols[1].metric(f"Resultado Encerrado ({month_name})", f"R$ {resultado_encerrado_mes:,.2f}")
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
                        
                        tab_ativas, tab_encerradas = st.tabs(["Operações Ativas", "Operações Encerradas"])

                        def display_operation_row(op, op_index, is_active_op, assessor_name, cliente_name):
                            qtd, preco_exec, tipo = op["quantidade"], op["preco_exec"], op["tipo"]
                            valor_entrada = qtd * preco_exec
                            custo_entrada = valor_entrada * 0.005

                            if is_active_op:
                                preco_atual, nome_empresa, timestamp = get_stock_data(op["ativo"])
                                if preco_atual is None:
                                    st.error(f"Ativo {op['ativo']}: {nome_empresa}")
                                    return
                                valor_saida_atual = op['quantidade'] * preco_atual
                                custo_saida = valor_saida_atual * 0.005
                                if op['tipo'] == 'c':
                                    lucro_bruto = (preco_atual - preco_exec) * qtd
                                else: # Venda
                                    lucro_bruto = (preco_exec - preco_atual) * qtd
                                preco_display = f"R$ {preco_atual:,.2f}<br><small>({timestamp})</small>"
                                custo_total = custo_entrada + custo_saida
                                lucro_liquido = lucro_bruto - custo_total
                            else: # Operação Encerrada
                                preco_final = op.get('preco_encerramento', preco_exec)
                                lucro_liquido = op.get('lucro_final', 0)
                                if op['tipo'] == 'c':
                                    lucro_bruto = (preco_final - preco_exec) * qtd
                                else: # Venda
                                    lucro_bruto = (preco_exec - preco_final) * qtd
                                preco_display = f"R$ {preco_final:,.2f}<br><small>(Encerrada)</small>"
                                custo_total = (valor_entrada * 0.005) + ((qtd * preco_final) * 0.005)

                            perc_bruto = (lucro_bruto / valor_entrada) * 100 if valor_entrada > 0 else 0
                            perc_liquido = (lucro_liquido / valor_entrada) * 100 if valor_entrada > 0 else 0

                            classe_linha = "linha-encerrada" if not is_active_op else ("linha-verde" if lucro_liquido >= 0 else "linha-vermelha")
                            
                            with st.container():
                                st.markdown(f"<div class='{classe_linha}'>", unsafe_allow_html=True)
                                cols_data = st.columns([1.5, 1, 1, 1.3, 1.5, 1.2, 1.3, 1.2, 1.2, 1.2, 1.2])
                                cols_data[0].markdown(f"<span title='{nome_empresa if is_active_op else 'Operação Encerrada'}'>{op['ativo']}</span>", unsafe_allow_html=True)
                                cols_data[1].write("🟢 Compra" if tipo == "c" else "🔴 Venda")
                                cols_data[2].write(f"{qtd:,}")
                                cols_data[3].write(f"R$ {preco_exec:,.2f}")
                                cols_data[4].markdown(preco_display, unsafe_allow_html=True)
                                cols_data[5].write(f"R$ {custo_total:,.2f}")
                                cols_data[6].markdown(f"<b>R$ {lucro_liquido:,.2f}</b>", unsafe_allow_html=True)
                                cols_data[7].markdown(f"<b>{perc_bruto:.2f}%</b>", unsafe_allow_html=True)
                                cols_data[8].markdown(f"<b>{perc_liquido:.2f}%</b>", unsafe_allow_html=True)
                                cols_data[9].write(op["data"])
                                
                                action_cols = cols_data[10].columns([1,1,1] if is_active_op else [1])
                                if is_active_op:
                                    if action_cols[0].button("✏️", key=f"edit_op_{assessor_name}_{cliente_name}_{op_index}"): st.session_state.editing_operation = (assessor_name, cliente_name, op_index); st.rerun()
                                    if action_cols[1].button("🏁", key=f"close_op_{assessor_name}_{cliente_name}_{op_index}", help="Encerrar"): st.session_state.closing_operation = (assessor_name, cliente_name, op_index); st.rerun()
                                    if action_cols[2].button("🗑️", key=f"del_op_{assessor_name}_{cliente_name}_{op_index}"): operacoes.pop(op_index); save_data_to_firestore(st.session_state.assessores); st.rerun()
                                else:
                                    if action_cols[0].button("✏️", key=f"edit_closed_op_{assessor_name}_{cliente_name}_{op_index}", help="Editar Encerrada"): st.session_state.editing_operation = (assessor_name, cliente_name, op_index); st.rerun()
                                st.markdown("</div>", unsafe_allow_html=True)

                        with tab_ativas:
                            operacoes_ativas = [op for op in operacoes if op.get('status', 'ativa') == 'ativa']
                            if not operacoes_ativas:
                                st.info("Nenhuma operação ativa para este cliente.")
                            else:
                                headers = ["Ativo", "Tipo", "Qtd.", "Preço Exec.", "Preço Atual", "Custo (R$)", "Lucro Líq.", "% Bruto", "% Líq.", "Data", "Ações"]
                                cols_header = st.columns([1.5, 1, 1, 1.3, 1.5, 1.2, 1.3, 1.2, 1.2, 1.2, 1.2])
                                for col, header in zip(cols_header, headers): col.markdown(f"**{header}**")
                                for i, op in enumerate(operacoes):
                                    if op.get('status', 'ativa') == 'ativa':
                                        display_operation_row(op, i, True, assessor, cliente)

                        with tab_encerradas:
                            operacoes_encerradas = [op for op in operacoes if op.get('status') == 'encerrada']
                            if not operacoes_encerradas:
                                st.info("Nenhuma operação encerrada para este cliente.")
                            else:
                                headers = ["Ativo", "Tipo", "Qtd.", "Preço Exec.", "Preço Final", "Custo (R$)", "Lucro Líq.", "% Bruto", "% Líq.", "Data", "Ações"]
                                cols_header = st.columns([1.5, 1, 1, 1.3, 1.5, 1.2, 1.3, 1.2, 1.2, 1.2, 1.2])
                                for col, header in zip(cols_header, headers): col.markdown(f"**{header}**")
                                for i, op in enumerate(operacoes):
                                    if op.get('status') == 'encerrada':
                                        display_operation_row(op, i, False, assessor, cliente)

    st.divider()
    # --- SEÇÃO DE RELATÓRIOS ---
    with st.container(border=True):
        st.header("Gerar Relatório Personalizado")
        
        assessores_disponiveis = list(st.session_state.assessores.keys())
        if assessores_disponiveis:
            assessores_selecionados = st.multiselect("Selecione os Assessores", options=assessores_disponiveis, default=assessores_disponiveis)
            status_relatorio = st.radio("Status das Operações para o Relatório", ["Ativas", "Encerradas", "Todas"], horizontal=True, key="report_status")
            
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
            
            if not report_data:
                st.warning("Nenhuma operação encontrada para os filtros selecionados.")
            else:
                df_report = pd.DataFrame(report_data)
                
                col1, col2 = st.columns(2)
                
                output_excel = BytesIO()
                with pd.ExcelWriter(output_excel, engine='xlsxwriter') as writer:
                    df_report.to_excel(writer, index=False, sheet_name="Relatorio")
                
                col1.download_button(
                    label="📥 Baixar Relatório em Excel", data=output_excel.getvalue(),
                    file_name=f"relatorio_operacoes_{datetime.now().strftime('%Y%m%d')}.xlsx", use_container_width=True
                )
                
                pdf_data = create_pdf_report(df_report)
                if pdf_data:
                    col2.download_button(
                        label="📄 Baixar Relatório em PDF", data=pdf_data,
                        file_name=f"relatorio_operacoes_{datetime.now().strftime('%Y%m%d')}.pdf",
                        mime="application/pdf", use_container_width=True
                    )
        else:
            st.info("Nenhum assessor com operações cadastradas para gerar relatório.")
