import streamlit as st
from pypdf import PdfReader
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
import google.generativeai as genai
import io
from datetime import datetime
import re
import os

# ==========================================
# --- CONFIGURAÇÃO INICIAL E ESTADO ---
# ==========================================
st.set_page_config(page_title="Análise Caso a Caso RJAIA", page_icon="⚖️", layout="wide")

# Inicializa a chave de estado para forçar a limpeza dos uploaders
if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

def reset_app():
    """
    Função de Callback:
    Incrementa a chave de sessão. Isto fará com que os widgets de file_uploader
    sejam recriados com uma nova ID no próximo rerun, limpando os ficheiros antigos.
    """
    st.session_state.uploader_key += 1

# ==========================================
# --- SIDEBAR & SETUP IA ---
# ==========================================
with st.sidebar:
    st.header("🔐 Configuração")
    
    # Gestão da API Key (Secrets ou Input Manual)
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
        st.success("Chave API detetada!")
    else:
        api_key = st.text_input("Google API Key", type="password")
    
    selected_model = "gemini-1.5-flash" # Default
    
    if api_key:
        try:
            genai.configure(api_key=api_key)
            models = genai.list_models()
            valid_models = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
            
            if valid_models:
                # Prioriza modelos Flash
                idx = next((i for i, m in enumerate(valid_models) if 'flash' in m), 0)
                selected_model = st.selectbox("Modelo IA:", valid_models, index=idx)
                st.info("✅ Sistema Pronto")
            else:
                st.error("Chave válida sem modelos.")
        except Exception as e:
            st.error(f"Erro na Chave: {e}")

    st.divider()
    st.markdown("---")
    st.caption("v2.1 - Triangulação & Auto-Limpeza")

# ==========================================
# --- INTERFACE DE UPLOAD (DINÂMICA) ---
# ==========================================
st.title("⚖️ Análise Caso a Caso (RJAIA)")
st.markdown("### Triangulação de Dados e Decisão Automática")

col1, col2, col3 = st.columns(3)

# O segredo da limpeza está aqui: key=f"..._{st.session_state.uploader_key}"
# Quando a key muda, o Streamlit "esquece" o widget antigo e cria um novo vazio.

with col1:
    st.info("📂 1. Simulação SILiAmb")
    files_sim = st.file_uploader(
        "PDF da Simulação", 
        type=['pdf'], 
        accept_multiple_files=True, 
        key=f"up_sim_{st.session_state.uploader_key}"
    )

with col2:
    st.warning("📂 2. Formulário Submetido")
    files_form = st.file_uploader(
        "PDF do Formulário", 
        type=['pdf'], 
        accept_multiple_files=True, 
        key=f"up_form_{st.session_state.uploader_key}"
    )

with col3:
    st.success("📂 3. Projeto / Memória")
    files_doc = st.file_uploader(
        "Peças Escritas/Desenhadas", 
        type=['pdf'], 
        accept_multiple_files=True, 
        key=f"up_doc_{st.session_state.uploader_key}"
    )

# ==========================================
# --- FUNÇÕES DE PROCESSAMENTO ---
# ==========================================

def extract_text(files, label):
    """Extrai texto de múltiplos PDFs."""
    text_buffer = ""
    if not files: return ""
    for f in files:
        try:
            reader = PdfReader(f)
            text_buffer += f"\n\n--- INÍCIO {label}: {f.name} ---\n"
            for page in reader.pages:
                text_buffer += page.extract_text() + "\n"
        except Exception as e:
            st.error(f"Erro ao ler {f.name}: {e}")
    return text_buffer

def get_ai_response(prompt, model_name):
    """Chama a API do Gemini."""
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(prompt)
    return response.text

# --- PROMPT 1: VALIDAÇÃO ---
def analyze_consistency(t_sim, t_form, t_proj):
    prompt = f"""
    Atua como Auditor Técnico.
    Realiza uma TRIANGULAÇÃO DE DADOS entre 3 fontes:
    1. SIMULAÇÃO (Enquadramento teórico)
    2. FORMULÁRIO (Pedido oficial)
    3. PROJETO (Memória Descritiva)

    INPUTS:
    [SIMULAÇÃO]: {t_sim[:30000]}
    [FORMULÁRIO]: {t_form[:30000]}
    [PROJETO]: {t_proj[:100000]}

    TAREFA:
    Verifica consistência de: Identificação, Localização, CAEs, Áreas (Implantação/Total), Capacidades.
    
    SAÍDA:
    - Se houver divergências (>1%): Inicia com "STATUS: INCONSISTENTE". Lista as falhas.
    - Se consistente: Inicia com "STATUS: VALIDADO". Resume os dados.
    """
    return get_ai_response(prompt, selected_model)

# --- PROMPT 2: DECISÃO ---
def generate_decision(t_sim, t_form, t_proj):
    prompt = f"""
    Atua como Entidade Licenciadora. O projeto foi validado administrativamente.
    Produz a MINUTA DE ANÁLISE CASO A CASO (Screening RJAIA DL 151-B/2013).
    
    Usa a informação do PROJETO e FORMULÁRIO.

    CONTEXTO:
    {t_proj[:120000]}
    {t_form[:30000]}

    Preenche as tags abaixo para geração automática do documento:

    ### CAMPO_DESIGNACAO
    (Nome do projeto)
    ### CAMPO_TIPOLOGIA
    (Enquadramento legal exato: Anexo, Ponto, Alínea)
    ### CAMPO_LOCALIZACAO
    (Freguesia, Concelho)
    ### CAMPO_AREAS_SENSIVEIS
    (Sim/Não e quais)
    ### CAMPO_PROPONENTE
    (Nome da entidade)
    ### CAMPO_DESCRICAO
    (Resumo técnico claro)
    ### CAMPO_FUNDAMENTACAO_CARATERISTICAS
    (Análise Anexo III: Dimensão, recursos, resíduos)
    ### CAMPO_FUNDAMENTACAO_LOCALIZACAO
    (Análise Anexo III: Sensibilidade, capacidade de carga)
    ### CAMPO_FUNDAMENTACAO_IMPACTES
    (Análise Anexo III: Magnitude, probabilidade, duração)
    ### CAMPO_DECISAO
    ("SUJEITO A AIA" ou "NÃO SUJEITO A AIA")
    ### CAMPO_CONDICIONANTES
    (Lista de medidas cautelares em bullet points)
    """
    return get_ai_response(prompt, selected_model)

# ==========================================
# --- GERAÇÃO DE DOCUMENTOS WORD ---
# ==========================================

def create_inconsistency_doc(text):
    doc = Document()
    doc.add_heading("Relatório de Incongruências", 0)
    doc.add_paragraph(f"Data: {datetime.now().strftime('%d/%m/%Y')}")
    p = doc.add_paragraph("PARECER DESFAVORÁVEL: ")
    p.runs[0].bold = True
    p.runs[0].font.color.rgb = RGBColor(200, 0, 0)
    doc.add_paragraph(text)
    bio = io.BytesIO()
    doc.save(bio)
    return bio

def create_decision_doc(ai_text):
    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Arial'
    style.font.size = Pt(10)

    # 1. Cabeçalho
    h = doc.add_heading("ANÁLISE PRÉVIA E DECISÃO DE SUJEIÇÃO A AIA", 0)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("Regime Jurídico da Avaliação de Impacte Ambiental").alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("")

    # 2. Parser
    def get_tag(tag):
        m = re.search(f"### {tag}(.*?)###", ai_text, re.DOTALL)
        if not m: m = re.search(f"### {tag}(.*)", ai_text, re.DOTALL)
        return m.group(1).strip() if m else "N/A"

    # 3. Tabela
    table = doc.add_table(rows=0, cols=2)
    table.style = 'Table Grid'

    def add_merged_row(text, bold=False):
        row = table.add_row()
        c = row.cells[0]
        c.merge(row.cells[1])
        r = c.paragraphs[0].add_run(text)
        if bold: r.bold = True

    def add_kv(key, val):
        row = table.add_row()
        row.cells[0].paragraphs[0].add_run(key).bold = True
        row.cells[1].text = val

    add_merged_row("IDENTIFICAÇÃO", bold=True)
    add_kv("Designação", get_tag("CAMPO_DESIGNACAO"))
    add_kv("Tipologia", get_tag("CAMPO_TIPOLOGIA"))
    add_kv("Localização", get_tag("CAMPO_LOCALIZACAO"))
    add_kv("Áreas Sensíveis", get_tag("CAMPO_AREAS_SENSIVEIS"))
    add_kv("Proponente", get_tag("CAMPO_PROPONENTE"))

    add_merged_row("DESCRIÇÃO", bold=True)
    add_merged_row(get_tag("CAMPO_DESCRICAO"))

    add_merged_row("FUNDAMENTAÇÃO (ANEXO III do RJAIA)", bold=True)
    add_kv("Caraterísticas", get_tag("CAMPO_FUNDAMENTACAO_CARATERISTICAS"))
    add_kv("Localização", get_tag("CAMPO_FUNDAMENTACAO_LOCALIZACAO"))
    add_kv("Impactes Potenciais", get_tag("CAMPO_FUNDAMENTACAO_IMPACTES"))

    row = table.add_row()
    c = row.cells[0]
    c.merge(row.cells[1])
    c.text = "DECISÃO"
    c.paragraphs[0].runs[0].bold = True
    
    row = table.add_row()
    c = row.cells[0]
    c.merge(row.cells[1])
    run = c.paragraphs[0].add_run(get_tag("CAMPO_DECISAO"))
    run.bold = True
    run.font.size = Pt(12)
    run.font.color.rgb = RGBColor(0, 50, 100)

    add_merged_row("CONDICIONANTES", bold=True)
    add_merged_row(get_tag("CAMPO_CONDICIONANTES"))

    doc.add_paragraph("\n\nO Técnico,\n_______________________").alignment = WD_ALIGN_PARAGRAPH.CENTER

    bio = io.BytesIO()
    doc.save(bio)
    return bio

# ==========================================
# --- MOTOR PRINCIPAL ---
# ==========================================

st.markdown("---")
btn_run = st.button("🚀 Iniciar Análise e Decisão", type="primary", use_container_width=True)

if btn_run:
    if not (files_sim and files_form and files_doc):
        st.error("⚠️ Faltam documentos! Carregue ficheiros nas 3 caixas.")
    elif not api_key:
        st.error("⚠️ Falta API Key.")
    else:
        # 1. Leitura
        with st.spinner("📖 A ler e processar documentos..."):
            txt_sim = extract_text(files_sim, "SIMULAÇÃO")
            txt_form = extract_text(files_form, "FORMULÁRIO")
            txt_doc = extract_text(files_doc, "PROJETO")

        # 2. Triangulação
        with st.status("🕵️ A analisar consistência...") as status:
            consistency = analyze_consistency(txt_sim, txt_form, txt_doc)
            
            if "STATUS: INCONSISTENTE" in consistency.upper():
                status.update(label="❌ Incongruências Detetadas", state="error")
                st.error("Documentação inconsistente. A interromper processo.")
                
                # Gera Word Erros
                f_err = create_inconsistency_doc(consistency)
                
                # Botão com callback de limpeza
                st.download_button(
                    label="⬇️ Baixar Relatório de Erros (.docx)",
                    data=f_err.getvalue(),
                    file_name="Relatorio_Incongruencias.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    on_click=reset_app # LIMPA FICHEIROS AO CLICAR
                )
            
            else:
                status.update(label="✅ Dados Validados! A gerar Decisão...", state="complete")
                
                # 3. Decisão
                with st.spinner("⚖️ A escrever Decisão Final..."):
                    decision_txt = generate_decision(txt_sim, txt_form, txt_doc)
                
                st.success("Análise Concluída!")
                
                # Tabs para ver e baixar
                tab1, tab2 = st.tabs(["📄 Visualizar", "💾 Download Oficial"])
                with tab1:
                    st.markdown(decision_txt)
                with tab2:
                    f_dec = create_decision_doc(decision_txt)
                    
                    # Botão com callback de limpeza
                    st.download_button(
                        label="⬇️ Baixar DECISÃO FINAL (.docx)",
                        data=f_dec.getvalue(),
                        file_name="Decisao_AIA.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        type="primary",
                        on_click=reset_app # LIMPA FICHEIROS AO CLICAR
                    )
