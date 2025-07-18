import streamlit as st
import yfinance as yf
import pandas as pd
from io import BytesIO
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh
import json
import locale

# Configura o locale para português para exibir o nome do mês corretamente
try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
except locale.Error:
    pass # Se o locale não for encontrado, o nome do mês será exibido em inglês por padrão.


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
COLLECTION_NAME = "analisador_ls_data"

def save_data_to_firestore(data):
    if db_client is None: return
    try:
        doc_ref = db_client.collection(COLLECTION_NAME).document(DOC_ID_NEW)
        serializable_data = json.loads(json.dumps(data, default=str))
        doc_ref.set(serializable_data) # Salva o dicionário completo
    except Exception as e:
        st.error(f"Erro ao salvar no Firestore: {e}")

# --- FUNÇÃO DE CARREGAMENTO COM MIGRAÇÃO ROBUSTA ---
def load_data_from_firestore():
    if db_client is None: return {"assessores": {}, "potenciais": {}}
    try:
        doc_ref = db_client.collection(COLLECTION_NAME).document(DOC_ID_NEW)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        return {"assessores": {}, "potenciais": {}}
    except Exception as e:
        st.error(f"Erro ao carregar dados do Firestore: {e}")
        return {"assessores": {}, "potenciais": {}}


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
    
    pdf.cell(0, 10, 'Relatório de Operações', 0, 1, 'C')
    pdf.ln(10)

    pdf.set_font("Arial", 'B', 7)
    
    display_columns = ['assessor', 'cliente', 'ativo', 'tipo', 'quantidade', 'preco_exec', 'data', 'status', 'preco_encerramento', 'data_encerramento', 'lucro_final']
    df_display = dataframe[[col for col in display_columns if col in dataframe.columns]].copy()
    df_display['volume_financeiro'] = df_display['quantidade'] * df_display['preco_exec']

    col_widths = {
        'assessor': 25, 'cliente': 30, 'ativo': 15, 'tipo': 15, 'quantidade': 20, 
        'preco_exec': 20, 'data': 20, 'status': 20, 'preco_encerramento': 25, 
        'data_encerramento': 25, 'lucro_final': 25, 'volume_financeiro': 30
    }
    
    report_columns = df_display.columns
    for header in report_columns:
        pdf.cell(col_widths.get(header, 20), 7, str(header).replace('_', ' ').title(), 1, 0, 'C')
    pdf.ln()

    pdf.set_font("Arial", '', 8)
    for _, row in df_display.iterrows():
        for col in report_columns:
            text = str(row.get(col, '')).encode('latin-1', 'replace').decode('latin-1')
            if isinstance(row.get(col), (int, float)):
                text = f"{row[col]:,.2f}"
            pdf.cell(col_widths[col], 6, text, 1)
        pdf.ln()
        
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, 'Totais Consolidados', 0, 1, 'L')
    
    total_volume = df_display['volume_financeiro'].sum()
    total_lucro = df_display['lucro_final'].sum() if 'lucro_final' in df_display.columns else 0
    
    pdf.set_font("Arial", '', 10)
    pdf.cell(60, 8, f"Volume Financeiro Total:", 0, 0)
    pdf.cell(60, 8, f"R$ {total_volume:,.2f}", 0, 1)
    pdf.cell(60, 8, f"Lucro/Prejuízo Líquido Total:", 0, 0)
    pdf.cell(60, 8, f"R$ {total_lucro:,.2f}", 0, 1)

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
if "app_data" not in st.session_state:
    with st.spinner("Carregando dados salvos..."):
        st.session_state.app_data = load_data_from_firestore()
        if "assessores" not in st.session_state.app_data:
            st.session_state.app_data["assessores"] = {}
        if "potenciais" not in st.session_state.app_data:
            st.session_state.app_data["potenciais"] = {}

if "editing_operation" not in st.session_state: st.session_state.editing_operation = None
if "editing_client" not in st.session_state: st.session_state.editing_client = None
if "closing_operation" not in st.session_state: st.session_state.closing_operation = None
if "editing_potential" not in st.session_state: st.session_state.editing_potential = None
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
                st.session_state.app_data["assessores"][assessor_edit][new_client_name] = st.session_state.app_data["assessores"][assessor_edit].pop(old_client_name)
                save_data_to_firestore(st.session_state.app_data)
            st.session_state.editing_client = None
            st.rerun()
        if st.form_submit_button("Cancelar"):
            st.session_state.editing_client = None
            st.rerun()

# MODO DE EDIÇÃO DE OPERAÇÃO
elif st.session_state.editing_operation:
    assessor_edit, cliente_edit, op_index_edit = st.session_state.editing_operation
    op_data = st.session_state.app_data["assessores"][assessor_edit][cliente_edit][op_index_edit]
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

            save_data_to_firestore(st.session_state.app_data)
            st.session_state.editing_operation = None
            st.rerun()
        if st.form_submit_button("Cancelar"):
            st.session_state.editing_operation = None
            st.rerun()

# MODO DE ENCERRAMENTO DE OPERAÇÃO
elif st.session_state.closing_operation:
    assessor_close, cliente_close, op_index_close = st.session_state.closing_operation
    op_data = st.session_state.app_data["assessores"][assessor_close][cliente_close][op_index_close]
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
            save_data_to_firestore(st.session_state.app_data)
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
    # ... (código do painel dinâmico)

    st.divider()
    
    with st.form("form_operacao"):
        st.subheader("Adicionar Nova Operação")
        # ... (código do formulário de adicionar operação)
        if st.form_submit_button("➕ Adicionar Operação", use_container_width=True):
            # ... (lógica de adicionar operação)
            save_data_to_firestore(st.session_state.app_data)
            st.rerun()

    st.divider()
    st.subheader("Visão Geral das Carteiras")
    
    if not st.session_state.app_data["assessores"]:
        st.info("Adicione uma operação no formulário acima para começar a análise.")
    else:
        for assessor, clientes in list(st.session_state.app_data["assessores"].items()):
            with st.container(border=True):
                st.title(f"Assessor: {assessor}")
                # ... (código de exibição das carteiras)

    st.divider()
    # --- NOVO: MÓDULO DE CONTROLE DE POTENCIAL ---
    with st.container(border=True):
        st.header("Controle de Potencial de Aplicação")

        with st.form("potential_form"):
            st.write("**Cadastrar Novo Potencial**")
            col1, col2, col3 = st.columns([2, 2, 1])
            potential_client_name = col1.text_input("Nome do Cliente")
            potential_value = col2.number_input("Potencial de Aplicação (R$)", min_value=0.0, format="%.2f")
            
            if col3.form_submit_button("Cadastrar"):
                if potential_client_name and potential_value > 0:
                    st.session_state.app_data["potenciais"][potential_client_name] = potential_value
                    save_data_to_firestore(st.session_state.app_data)
                    st.success(f"Potencial de {potential_client_name} cadastrado com sucesso!")
        
        st.markdown("---")
        st.write("**Potencial dos Clientes**")

        all_clients = set()
        for clientes_assessor in st.session_state.app_data["assessores"].values():
            for cliente in clientes_assessor.keys():
                all_clients.add(cliente)
        
        for cliente in st.session_state.app_data["potenciais"].keys():
            all_clients.add(cliente)
            
        if not all_clients:
            st.info("Nenhum cliente cadastrado.")
        else:
            for client in sorted(list(all_clients)):
                col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 1])
                
                volume_operado = 0
                for assessor_clientes in st.session_state.app_data["assessores"].values():
                    if client in assessor_clientes:
                        volume_operado = sum(op['quantidade'] * op['preco_exec'] for op in assessor_clientes[client])

                potencial_cadastrado = st.session_state.app_data["potenciais"].get(client, 0.0)
                potencial_restante = potencial_cadastrado - volume_operado

                col1.write(client)
                col2.metric("Potencial Cadastrado", f"R$ {potencial_cadastrado:,.2f}")
                col3.metric("Volume Operado", f"R$ {volume_operado:,.2f}")
                col4.metric("Potencial Restante", f"R$ {potencial_restante:,.2f}")
                
                if col5.button("✏️", key=f"edit_potential_{client}", help="Editar Potencial"):
                    st.session_state.editing_potential = client
                    st.rerun()

    # MODO DE EDIÇÃO DE POTENCIAL
    if st.session_state.editing_potential:
        client_to_edit = st.session_state.editing_potential
        st.subheader(f"Editando Potencial de: {client_to_edit}")
        with st.form("edit_potential_form"):
            new_potential = st.number_input("Novo Potencial de Aplicação (R$)", min_value=0.0, format="%.2f", value=st.session_state.app_data["potenciais"].get(client_to_edit, 0.0))
            if st.form_submit_button("Salvar"):
                st.session_state.app_data["potenciais"][client_to_edit] = new_potential
                save_data_to_firestore(st.session_state.app_data)
                st.session_state.editing_potential = None
                st.rerun()
            if st.form_submit_button("Cancelar"):
                st.session_state.editing_potential = None
                st.rerun()

    st.divider()
    # --- SEÇÃO DE RELATÓRIOS ---
    with st.container(border=True):
        st.header("Gerar Relatório Personalizado")
        # ... (código da seção de relatórios)
