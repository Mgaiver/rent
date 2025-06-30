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

DOC_ID = "dados_gerais_v3"
COLLECTION_NAME = "analisador_ls_data"

def save_data_to_firestore(data):
    if db_client is None: return
    try:
        doc_ref = db_client.collection(COLLECTION_NAME).document(DOC_ID)
        serializable_data = json.loads(json.dumps(data, default=str))
        doc_ref.set({"assessores": serializable_data})
    except Exception as e:
        st.error(f"Erro ao salvar no Firestore: {e}")

def load_data_from_firestore():
    if db_client is None: return {}
    try:
        doc_ref = db_client.collection(COLLECTION_NAME).document(DOC_ID)
        doc = doc_ref.get()
        return doc.to_dict().get("assessores", {}) if doc.exists else {}
    except Exception as e:
        st.error(f"Erro ao carregar do Firestore: {e}")
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

# --- NOVA FUNÇÃO PARA GERAR PDF ---
def create_pdf_report(dataframe):
    if not FPDF_AVAILABLE:
        st.error("A biblioteca FPDF2 não está instalada. Adicione 'fpdf2' ao seu requirements.txt.")
        return None

    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    
    # Título
    pdf.cell(277, 10, 'Relatório de Operações', 0, 1, 'C')
    pdf.ln(10)

    # Cabeçalho da Tabela
    pdf.set_font("Arial", 'B', 8)
    col_widths = {'assessor': 25, 'cliente': 25, 'Ativo': 15, 'Tipo': 15, 'Qtd': 15, 'Preço Exec.': 20, 'Preço Atual': 20, 'Custo (R$)': 20, 'Lucro Líquido (R$)': 30, 'Variação Líquida (%)': 22, 'Data': 20, 'Status Alvo': 20}
    
    for header in dataframe.columns:
        pdf.cell(col_widths.get(header, 20), 7, str(header), 1, 0, 'C')
    pdf.ln()

    # Dados da Tabela
    pdf.set_font("Arial", '', 8)
    for index, row in dataframe.iterrows():
        for col in dataframe.columns:
            text = str(row[col])
            # Formatação para valores numéricos
            if isinstance(row[col], (int, float)):
                text = f"{row[col]:,.2f}"
            pdf.cell(col_widths.get(col, 20), 6, text, 1)
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

# Estados de UI
if "editing_operation" not in st.session_state: st.session_state.editing_operation = None
if "editing_client" not in st.session_state: st.session_state.editing_client = None
if "closing_operation" not in st.session_state: st.session_state.closing_operation = None
if "expand_all" not in st.session_state: st.session_state.expand_all = {}


# --- MODO DE EDIÇÃO DE CLIENTE ---
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

# --- MODO DE EDIÇÃO DE OPERAÇÃO ---
elif st.session_state.editing_operation:
    assessor_edit, cliente_edit, op_index_edit = st.session_state.editing_operation
    op_data = st.session_state.assessores[assessor_edit][cliente_edit][op_index_edit]
    st.subheader(f"Editando Operação: {op_data['ativo']}")
    with st.form("edit_op_form"):
        # ... (código do formulário de edição de operação)
        st.session_state.editing_operation = None # Resetar estado
        st.rerun()

# --- MODO DE ENCERRAMENTO DE OPERAÇÃO ---
elif st.session_state.closing_operation:
    assessor_close, cliente_close, op_index_close = st.session_state.closing_operation
    op_data = st.session_state.assessores[assessor_close][cliente_close][op_index_close]
    st.subheader(f"Encerrando Operação: {op_data['ativo']} para {cliente_close}")
    with st.form("close_op_form"):
        preco_encerramento = st.number_input("Preço de Encerramento (R$)", format="%.2f", min_value=0.01, value=get_stock_data(op_data['ativo'])[0])
        data_encerramento = st.date_input("Data de Encerramento", datetime.now())
        
        if st.form_submit_button("Confirmar Encerramento", use_container_width=True):
            op_data['status'] = 'encerrada'
            op_data['preco_encerramento'] = preco_encerramento
            op_data['data_encerramento'] = data_encerramento.strftime("%d/%m/%Y")
            
            # Cálculo final do lucro/prejuízo
            qtd, preco_exec, tipo = op_data["quantidade"], op_data["preco_exec"], op_data["tipo"]
            valor_entrada = qtd * preco_exec
            valor_saida = qtd * preco_encerramento
            custo_total = (valor_entrada * 0.005) + (valor_saida * 0.005)
            lucro_bruto = (preco_encerramento - preco_exec) * qtd if tipo == 'c' else (preco_exec - preco_encerramento) * qtd
            op_data['lucro_final'] = lucro_bruto - custo_total
            
            save_data_to_firestore(st.session_state.assessores)
            st.session_state.closing_operation = None
            st.rerun()
        if st.form_submit_button("Cancelar", use_container_width=True):
            st.session_state.closing_operation = None
            st.rerun()


# --- MODO NORMAL (TELA PRINCIPAL) ---
else:
    with st.form("form_operacao"):
        st.subheader("Adicionar Nova Operação")
        # ... (código do formulário de adicionar operação)
        if st.form_submit_button("➕ Adicionar Operação", use_container_width=True):
            # ... (lógica de adicionar operação)
            op_data['status'] = 'ativa' # Adiciona o status inicial
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
                
                # ... (código de resumo do assessor)

                # --- BOTÕES DE EXPANDIR/RECOLHER ---
                col_exp, col_rec = st.columns(2)
                if col_exp.button(f"Expandir Todos ({assessor})", key=f"expand_{assessor}"):
                    st.session_state.expand_all[assessor] = True
                if col_rec.button(f"Recolher Todos ({assessor})", key=f"collapse_{assessor}"):
                    st.session_state.expand_all[assessor] = False
                
                # --- LOOP DE CLIENTES ---
                for cliente, operacoes in list(clientes.items()):
                    # Filtra as operações com base na seleção
                    operacoes_filtradas = [op for op in operacoes if 
                                           (view_filter == "Todas") or 
                                           (view_filter == "Ativas" and op.get('status', 'ativa') == 'ativa') or 
                                           (view_filter == "Encerradas" and op.get('status') == 'encerrada')]
                    
                    if not operacoes_filtradas:
                        continue

                    expanded_state = st.session_state.expand_all.get(assessor, True)
                    with st.expander(f"Cliente: {cliente}", expanded=expanded_state):
                        # ... (código de exibição das operações, agora usando operacoes_filtradas)
                        # Adicionar o botão de encerrar (🔒) para operações ativas
                        if op.get('status', 'ativa') == 'ativa':
                            if action_cols[2].button("🔒", key=f"close_op_{assessor}_{cliente}_{i}", help="Encerrar operação"):
                                st.session_state.closing_operation = (assessor, cliente, i)
                                st.rerun()

    st.divider()
    # --- SEÇÃO DE RELATÓRIOS ---
    with st.container(border=True):
        st.header("Gerar Relatório Personalizado")
        
        assessores_disponiveis = list(st.session_state.assessores.keys())
        assessores_selecionados = st.multiselect("Selecione os Assessores", options=assessores_disponiveis, default=assessores_disponiveis)
        
        status_relatorio = st.radio("Status das Operações para o Relatório", ["Ativas", "Encerradas", "Todas"], horizontal=True, key="report_status")
        
        if st.button("Gerar Relatório"):
            report_data = []
            for assessor in assessores_selecionados:
                for cliente, operacoes in st.session_state.assessores.get(assessor, {}).items():
                    for op in operacoes:
                        if (status_relatorio == "Todas") or \
                           (status_relatorio == "Ativas" and op.get('status', 'ativa') == 'ativa') or \
                           (status_relatorio == "Encerradas" and op.get('status') == 'encerrada'):
                            
                            op_details = op.copy()
                            op_details['assessor'] = assessor
                            op_details['cliente'] = cliente
                            report_data.append(op_details)
            
            if report_data:
                df_report = pd.DataFrame(report_data)
                st.dataframe(df_report)
                
                col1, col2 = st.columns(2)

                # Botão de Download em Excel
                output_excel = BytesIO()
                with pd.ExcelWriter(output_excel, engine='xlsxwriter') as writer:
                    df_report.to_excel(writer, index=False, sheet_name="Relatorio")
                
                col1.download_button(
                    label="📥 Baixar Relatório em Excel",
                    data=output_excel.getvalue(),
                    file_name=f"relatorio_operacoes_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    use_container_width=True
                )

                # Botão de Download em PDF
                pdf_data = create_pdf_report(df_report)
                if pdf_data:
                    col2.download_button(
                        label="📄 Baixar Relatório em PDF",
                        data=pdf_data,
                        file_name=f"relatorio_operacoes_{datetime.now().strftime('%Y%m%d')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
            else:
                st.warning("Nenhuma operação encontrada para os filtros selecionados.")