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

if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

def reset_app():
    """Limpa os ficheiros ao incrementar a chave dos uploaders."""
    st.session_state.uploader_key += 1

# ==========================================
# --- SIDEBAR & SETUP ---
# ==========================================
with st.sidebar:
    st.header("🔐 Configuração")
    
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
        st.success("Chave API detetada!")
    else:
        api_key = st.text_input("Google API Key", type="password")
    
    selected_model = "gemini-1.5-flash"
    
    if api_key:
        try:
            genai.configure(api_key=api_key)
            models = genai.list_models()
            valid_models = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
            if valid_models:
                idx = next((i for i, m in enumerate(valid_models) if 'flash' in m), 0)
                selected_model = st.selectbox("Modelo IA:", valid_models, index=idx)
                st.info("✅ Sistema Pronto")
            else:
                st.error("Chave sem modelos.")
        except Exception as e:
            st.error(f"Erro: {e}")

    st.divider()
    st.markdown("""
    **Fluxo de Trabalho:**
    1. **Triangulação:** Verifica a consistência dos dados.
    2. **Decisão:** Gera a minuta (Anexo III) independentemente do resultado da validação.
    3. **Técnico:** Decide se as incongruências são impeditivas ou negligenciáveis.
    """)

# ==========================================
# --- INTERFACE ---
# ==========================================
st.title("⚖️ Análise Caso a Caso (RJAIA)")
st.markdown("### Validação Técnica e Decisão")

col1, col2, col3 = st.columns(3)

with col1:
    st.info("📂 1. Simulação SILiAmb")
    files_sim = st.file_uploader("PDF Simulação", type=['pdf'], accept_multiple_files=True, key=f"up_sim_{st.session_state.uploader_key}")

with col2:
    st.warning("📂 2. Formulário Submetido")
    files_form = st.file_uploader("PDF Formulário", type=['pdf'], accept_multiple_files=True, key=f"up_form_{st.session_state.uploader_key}")

with col3:
    st.success("📂 3. Projeto / Memória")
    files_doc = st.file_uploader("Peças Escritas", type=['pdf'], accept_multiple_files=True, key=f"up_doc_{st.session_state.uploader_key}")

# ==========================================
# --- FUNÇÕES ---
# ==========================================

def extract_text(files, label):
    text = ""
    if not files: return ""
    for f in files:
        try:
            r = PdfReader(f)
            text += f"\n\n--- {label}: {f.name} ---\n"
            for p in r.pages: text += p.extract_text() + "\n"
        except: pass
    return text

def get_ai(prompt):
    model = genai.GenerativeModel(selected_model)
    return model.generate_content(prompt).text

# --- PROMPT 1: VALIDAÇÃO ---
def analyze_validation(t_sim, t_form, t_proj):
    return get_ai(f"""
    Atua como Auditor Técnico. Realiza uma TRIANGULAÇÃO DE DADOS entre:
    1. SIMULAÇÃO | 2. FORMULÁRIO | 3. PROJETO
    
    DADOS:
    [SIMULAÇÃO]: {t_sim[:30000]}
    [FORMULÁRIO]: {t_form[:30000]}
    [PROJETO]: {t_proj[:100000]}

    TAREFA:
    Verifica consistência de: Identificação, Localização, CAEs, Áreas, Capacidades.
    
    SAÍDA:
    Produz um relatório técnico.
    - Se houver divergências (>1%): Inicia com "STATUS: ALERTA DE INCONSISTÊNCIA". Lista as falhas detalhadamente.
    - Se consistente: Inicia com "STATUS: VALIDADO". Resume os dados confirmados.
    """)

# --- PROMPT 2: DECISÃO ---
def generate_decision_text(t_sim, t_form, t_proj):
    return get_ai(f"""
    Atua como Entidade Licenciadora. Produz a MINUTA DE ANÁLISE CASO A CASO (DL 151-B/2013).
    Assume que os dados do PROJETO são os mais corretos em caso de dúvida.

    CONTEXTO:
    {t_proj[:120000]}
    {t_form[:30000]}

    Preenche as tags para a minuta:
    ### CAMPO_DESIGNACAO
    ### CAMPO_TIPOLOGIA (Anexo, Ponto, Alínea)
    ### CAMPO_LOCALIZACAO
    ### CAMPO_AREAS_SENSIVEIS
    ### CAMPO_PROPONENTE
    ### CAMPO_DESCRICAO (Resumo técnico)
    ### CAMPO_FUNDAMENTACAO_CARATERISTICAS (Anexo III)
    ### CAMPO_FUNDAMENTACAO_LOCALIZACAO (Anexo III)
    ### CAMPO_FUNDAMENTACAO_IMPACTES (Anexo III)
    ### CAMPO_DECISAO ("SUJEITO" ou "NÃO SUJEITO")
    ### CAMPO_CONDICIONANTES (Bullet points)
    """)

# ==========================================
# --- WORD GENERATORS ---
# ==========================================

def create_validation_doc(text):
    doc = Document()
    doc.add_heading("Relatório de Validação da Instrução", 0)
    doc.add_paragraph(f"Data: {datetime.now().strftime('%d/%m/%Y')}")
    
    if "ALERTA" in text.upper() or "INCONSIST" in text.upper():
        p = doc.add_paragraph("ALERTA: FORAM DETETADAS INCONGRUÊNCIAS")
        p.runs[0].bold = True
        p.runs[0].font.color.rgb = RGBColor(200, 0, 0)
    else:
        p = doc.add_paragraph("PROCESSO VALIDADO")
        p.runs[0].bold = True
        p.runs[0].font.color.rgb = RGBColor(0, 128, 0)
        
    doc.add_paragraph(text)
    bio = io.BytesIO()
    doc.save(bio)
    return bio

def create_decision_doc(text):
    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Arial'
    style.font.size = Pt(10)

    # Parser
    def get_tag(tag):
        m = re.search(f"### {tag}(.*?)###", text, re.DOTALL)
        if not m: m = re.search(f"### {tag}(.*)", text, re.DOTALL)
        return m.group(1).strip() if m else "N/A"

    # Header
    h = doc.add_heading("ANÁLISE PRÉVIA E DECISÃO DE SUJEIÇÃO A AIA", 0)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("Regime Jurídico da Avaliação de Impacte Ambiental").alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("")

    # Tabela
    table = doc.add_table(rows=0, cols=2)
    table.style = 'Table Grid'

    def add_merged(txt, bold=False):
        r = table.add_row()
        c = r.cells[0]
        c.merge(r.cells[1])
        run = c.paragraphs[0].add_run(txt)
        if bold: run.bold = True

    def add_row(k, v):
        r = table.add_row()
        r.cells[0].paragraphs[0].add_run(k).bold = True
        r.cells[1].text = v

    add_merged("IDENTIFICAÇÃO", True)
    add_row("Designação", get_tag("CAMPO_DESIGNACAO"))
    add_row("Tipologia", get_tag("CAMPO_TIPOLOGIA"))
    add_row("Localização", get_tag("CAMPO_LOCALIZACAO"))
    add_row("Áreas Sensíveis", get_tag("CAMPO_AREAS_SENSIVEIS"))
    add_row("Proponente", get_tag("CAMPO_PROPONENTE"))

    add_merged("DESCRIÇÃO", True)
    add_merged(get_tag("CAMPO_DESCRICAO"))

    add_merged("FUNDAMENTAÇÃO (ANEXO III)", True)
    add_row("Caraterísticas", get_tag("CAMPO_FUNDAMENTACAO_CARATERISTICAS"))
    add_row("Localização", get_tag("CAMPO_FUNDAMENTACAO_LOCALIZACAO"))
    add_row("Impactes", get_tag("CAMPO_FUNDAMENTACAO_IMPACTES"))

    r = table.add_row()
    c = r.cells[0]
    c.merge(r.cells[1])
    c.text = "DECISÃO"
    c.paragraphs[0].runs[0].bold = True
    
    r = table.add_row()
    c = r.cells[0]
    c.merge(r.cells[1])
    run = c.paragraphs[0].add_run(get_tag("CAMPO_DECISAO"))
    run.bold = True; run.font.size = Pt(12)

    add_merged("CONDICIONANTES", True)
    add_merged(get_tag("CAMPO_CONDICIONANTES"))

    doc.add_paragraph("\n\nO Técnico,\n_______________________").alignment = WD_ALIGN_PARAGRAPH.CENTER

    bio = io.BytesIO()
    doc.save(bio)
    return bio

# ==========================================
# --- EXECUÇÃO ---
# ==========================================
st.markdown("---")
if st.button("🚀 Processar Documentos (Geração Dupla)", type="primary", use_container_width=True):
    
    if not (files_sim and files_form and files_doc):
        st.error("⚠️ Carregue documentos nas 3 caixas.")
    elif not api_key:
        st.error("⚠️ Insira a API Key.")
    else:
        with st.status("⚙️ A trabalhar...", expanded=True) as status:
            # 1. Leitura
            st.write("📖 A ler ficheiros...")
            ts = extract_text(files_sim, "SIM")
            tf = extract_text(files_form, "FORM")
            tp = extract_text(files_doc, "PROJ")
            
            # 2. IA - Validação
            st.write("🕵️ A validar consistência...")
            res_val = analyze_validation(ts, tf, tp)
            
            # 3. IA - Decisão (Corre sempre)
            st.write("⚖️ A redigir minuta de decisão...")
            res_dec = generate_decision_text(ts, tf, tp)
            
            status.update(label="✅ Concluído! Documentos prontos.", state="complete")

        # Apresentação dos resultados
        st.success("Processo terminado. Descarregue os documentos abaixo.")
        
        c1, c2 = st.columns(2)
        
        # Botão 1: Relatório de Validação
        f_val = create_validation_doc(res_val)
        c1.download_button(
            label="📄 1. Relatório de Validação",
            data=f_val.getvalue(),
            file_name="Relatorio_Validacao.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            help="Detalhe das incongruências detetadas (se existirem)."
        )
        
        # Botão 2: Minuta de Decisão
        f_dec = create_decision_doc(res_dec)
        c2.download_button(
            label="📝 2. Minuta de Decisão",
            data=f_dec.getvalue(),
            file_name="Proposta_Decisao.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary",
            help="Proposta final de decisão caso a caso.",
            on_click=reset_app # Limpa a app apenas quando se baixa a decisão final
        )
