import streamlit as st
from pypdf import PdfReader
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
import io
import time
from datetime import datetime
import re

# ==========================================
# --- 1. BASE DE DADOS JURÍDICA ---
# ==========================================
LEGISLATION_DB = {
    "RJAIA (DL 151-B/2013)": "https://diariodarepublica.pt/dr/legislacao-consolidada/decreto-lei/2013-116043164",
    "Alteração RJAIA (DL 152-B/2017)": "https://diariodarepublica.pt/dr/detalhe/decreto-lei/152-b-2017-114337069",
    "RGGR (DL 102-D/2020)": "https://diariodarepublica.pt/dr/legislacao-consolidada/decreto-lei/2020-150917243",
    "LUA (DL 75/2015)": "https://diariodarepublica.pt/dr/legislacao-consolidada/decreto-lei/2015-106562356",
    "Rede Natura 2000 (DL 140/99)": "https://diariodarepublica.pt/dr/legislacao-consolidada/decreto-lei/1999-34460975",
    "Regulamento Geral do Ruído (DL 9/2007)": "https://diariodarepublica.pt/dr/legislacao-consolidada/decreto-lei/2007-34526556",
    "Lei da Água (Lei 58/2005)": "https://diariodarepublica.pt/dr/legislacao-consolidada/lei/2005-34563267",
    "Emissões Industriais (DL 127/2013)": "https://diariodarepublica.pt/dr/legislacao-consolidada/decreto-lei/2013-34789569"
}

# ==========================================
# --- CONFIGURAÇÃO INICIAL E ESTADO ---
# ==========================================
st.set_page_config(page_title="Análise Caso a Caso RJAIA", page_icon="⚖️", layout="wide")

if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0
if 'validation_result' not in st.session_state:
    st.session_state.validation_result = None
if 'decision_result' not in st.session_state:
    st.session_state.decision_result = None

def reset_app():
    st.session_state.uploader_key += 1
    st.session_state.validation_result = None
    st.session_state.decision_result = None

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
        except Exception as e:
            st.error(f"Erro: {e}")
    
    st.divider()
    if st.button("🔄 Nova Análise / Limpar Tudo", use_container_width=True):
        reset_app()
        st.rerun()

# ==========================================
# --- FUNÇÕES AUXILIARES (WORD) ---
# ==========================================

def add_hyperlink(paragraph, text, url):
    """
    Adiciona um hiperlink clicável num parágrafo do Word.
    """
    part = paragraph.part
    r_id = part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)

    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    new_run = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")

    # Estilo do Link (Azul sublinhado)
    c = OxmlElement("w:color")
    c.set(qn("w:val"), "0000FF")
    rPr.append(c)
    u = OxmlElement("w:u")
    u.set(qn("w:val"), "single")
    rPr.append(u)

    new_run.append(rPr)
    new_run.text = text
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)
    return hyperlink

def markdown_to_word(doc, text):
    """Converte Markdown para Word com Justificação."""
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if not line: continue
        
        p = None
        if line.startswith('##'):
            p = doc.add_heading(line.replace('#', '').strip(), level=2)
        elif line.startswith('###'):
            p = doc.add_heading(line.replace('#', '').strip(), level=3)
        elif line.startswith('- ') or line.startswith('* '):
            p = doc.add_paragraph(style='List Bullet')
            clean_line = line[2:]
            process_bold(p, clean_line)
        else:
            p = doc.add_paragraph()
            process_bold(p, line)
        
        # JUSTIFICAR TEXTO (exceto títulos)
        if p and not line.startswith('#'):
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

def process_bold(paragraph, text):
    """Processa negrito (**texto**) dentro do parágrafo."""
    parts = re.split(r'(\*\*.*?\*\*)', text)
    for part in parts:
        if part.startswith('**') and part.endswith('**'):
            paragraph.add_run(part[2:-2]).bold = True
        else:
            paragraph.add_run(part)

def append_legislation_section(doc):
    """Adiciona a lista de legislação com hiperlinks no final."""
    doc.add_page_break()
    doc.add_heading("Legislação Consultada e Referências", level=1)
    
    p_intro = doc.add_paragraph("A presente análise teve por base os seguintes diplomas legais:")
    p_intro.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    
    for name, url in LEGISLATION_DB.items():
        p = doc.add_paragraph(style='List Bullet')
        add_hyperlink(p, name, url)

# ==========================================
# --- EXTRAÇÃO E IA ---
# ==========================================

def extract_text(files, label):
    text = ""
    if not files: return ""
    for f in files:
        try:
            r = PdfReader(f)
            text += f"\n\n>>> FONTE: {label} ({f.name}) <<<\n" 
            for i, p in enumerate(r.pages):
                text += f"[Pág. {i+1}] {p.extract_text()}\n"
        except: pass
    return text

def get_ai(prompt):
    model = genai.GenerativeModel(selected_model)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return model.generate_content(prompt).text
        except ResourceExhausted:
            time.sleep(5 * (attempt + 1))
        except Exception as e:
            return f"Erro IA: {str(e)}"
    return "Erro: Sistema sobrecarregado."

# --- PROMPTS ---

def analyze_validation(t_sim, t_form, t_proj):
    legislacao_str = ", ".join(LEGISLATION_DB.keys())
    return get_ai(f"""
    Atua como PERITO AUDITOR AMBIENTAL.
    
    CONTEXTO LEGAL:
    Utiliza os limiares do RJAIA (Anexos I, II, III, IV, V) e legislação conexa: {legislacao_str}.
    
    DADOS:
    {t_sim[:25000]}
    {t_form[:25000]}
    {t_proj[:80000]}

    TAREFA:
    1. Audita a consistência dos dados (Áreas, Toneladas, LER).
    2. Verifica o enquadramento legal: O projeto ultrapassa algum limiar do RJAIA? Cita o Anexo e o Ponto específico.
    3. Identifica a legislação setorial aplicável (Resíduos, Indústria, etc.).
    
    OUTPUT (Markdown):
    1. "STATUS: [VALIDADO ou INCONSISTENTE]"
    2. "## 1. Resumo Executivo"
    3. "## 2. Auditoria de Conformidade" (Com citações de página)
    4. "## 3. Enquadramento Legal e Limiares" (Análise detalhada face ao RJAIA e legislação setorial).
    """)

def generate_decision_text(t_sim, t_form, t_proj):
    return get_ai(f"""
    Atua como Técnico Superior da CCDR. Redige a MINUTA DE DECISÃO.
    
    REGRAS DE FORMATAÇÃO:
    - Texto corrido, JUSTIFICADO, linguagem formal e culta.
    - Cita sempre a fonte: (MD, pág. X).
    
    CONTEXTO:
    {t_proj[:120000]}
    {t_form[:25000]}

    PREENCHE AS TAGS:
    ### CAMPO_DESIGNACAO
    (Nome rigoroso)
    ### CAMPO_TIPOLOGIA
    (Ex: "Ponto 11.b do Anexo II do DL 151-B/2013")
    ### CAMPO_ENQUADRAMENTO
    (Ex: "Artigo 1.º, n.º 3, alínea b)...")
    ### CAMPO_LOCALIZACAO
    (Freguesia/Concelho)
    ### CAMPO_AREAS_SENSIVEIS
    (Análise art. 2.º RJAIA)
    ### CAMPO_PROPONENTE
    ### CAMPO_ENTIDADE_LICENCIADORA
    ### CAMPO_AUTORIDADE_AIA
    
    ### CAMPO_DESCRICAO
    (Resumo técnico denso do projeto.)
    
    ### CAMPO_CARATERISTICAS
    (Fundamentação técnica. Quantifica resíduos/efluentes. Compara explicitamente com os limiares do RJAIA (ex: "A capacidade de X t/ano é inferior ao limiar de 100 t/ano previsto no Anexo II...").)
    
    ### CAMPO_LOCALIZACAO_PROJETO
    (Compatibilidade com PDM/REN/RAN.)
    
    ### CAMPO_IMPACTES
    (Avaliação dos descritores ambientais.)
    
    ### CAMPO_DECISAO
    (SUJEITO / NÃO SUJEITO)
    
    ### CAMPO_CONDICIONANTES
    (Obrigações essenciais.)
    """)

# ==========================================
# --- GERADORES DE DOCS (ATUALIZADOS) ---
# ==========================================

def create_validation_doc(text):
    doc = Document()
    
    # Cabeçalho
    sec = doc.sections[0]
    sec.header.paragraphs[0].text = "Relatório de Auditoria Técnica"
    sec.header.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT

    # Título
    h = doc.add_heading("Auditoria de Conformidade Legal e Técnica", 0)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f"Data: {datetime.now().strftime('%d/%m/%Y')}\n").alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Status
    p_status = doc.add_paragraph()
    p_status.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if "INCONSISTENTE" in text.upper():
        r = p_status.add_run("⚠️ PARECER: INCONGRUÊNCIAS DETETADAS")
        r.font.color.rgb = RGBColor(255, 0, 0)
    else:
        r = p_status.add_run("✅ PARECER: DADOS CONSISTENTES")
        r.font.color.rgb = RGBColor(0, 128, 0)
    r.bold = True
    r.font.size = Pt(14)
    
    doc.add_paragraph("---")
    
    # Corpo do Texto Justificado
    clean_text = re.sub(r'STATUS:.*', '', text, count=1).strip()
    markdown_to_word(doc, clean_text)
    
    # Adicionar Legislação e Hiperlinks
    append_legislation_section(doc)
    
    bio = io.BytesIO()
    doc.save(bio)
    return bio

def create_decision_doc(text):
    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Arial'
    style.font.size = Pt(10)
    
    def get_tag(tag):
        m = re.search(f"### {tag}(.*?)###", text, re.DOTALL)
        if not m: m = re.search(f"### {tag}(.*)", text, re.DOTALL)
        return m.group(1).strip() if m else "A preencher"

    h = doc.add_heading("Análise prévia e decisão de sujeição a AIA", 0)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("")

    table = doc.add_table(rows=0, cols=2)
    table.style = 'Table Grid'

    def add_merged_header(txt):
        r = table.add_row()
        c = r.cells[0]
        c.merge(r.cells[1])
        p = c.paragraphs[0]
        run = p.add_run(txt)
        run.bold = True
        return r

    def add_row(label, val):
        r = table.add_row()
        p_lbl = r.cells[0].paragraphs[0]
        p_lbl.add_run(label).bold = True
        p_lbl.alignment = WD_ALIGN_PARAGRAPH.LEFT # Label à esquerda
        
        p_val = r.cells[1].paragraphs[0]
        p_val.text = val
        p_val.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY # Valor justificado
        return r

    def add_full_text(header, content):
        add_merged_header(header)
        r = table.add_row()
        c = r.cells[0]
        c.merge(r.cells[1])
        p = c.paragraphs[0]
        p.text = content
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY # Justificado

    # Tabela
    add_merged_header("Identificação")
    add_row("Designação do projeto", get_tag("CAMPO_DESIGNACAO"))
    add_row("Tipologia de Projeto", get_tag("CAMPO_TIPOLOGIA"))
    add_row("Enquadramento no RJAIA", get_tag("CAMPO_ENQUADRAMENTO"))
    add_row("Localização", get_tag("CAMPO_LOCALIZACAO"))
    add_row("Áreas Sensíveis", get_tag("CAMPO_AREAS_SENSIVEIS"))
    add_row("Proponente", get_tag("CAMPO_PROPONENTE"))
    add_row("Entidade Licenciadora", get_tag("CAMPO_ENTIDADE_LICENCIADORA"))
    add_row("Autoridade de AIA", get_tag("CAMPO_AUTORIDADE_AIA"))

    add_full_text("Breve descrição do projeto", get_tag("CAMPO_DESCRICAO"))

    add_merged_header("Fundamentação da decisão")
    add_row("Caraterísticas do projeto", get_tag("CAMPO_CARATERISTICAS"))
    add_row("Localização do projeto", get_tag("CAMPO_LOCALIZACAO_PROJETO"))
    add_row("Impactes Potenciais", get_tag("CAMPO_IMPACTES"))

    add_merged_header("Decisão")
    r = table.add_row()
    c = r.cells[0]
    c.merge(r.cells[1])
    p = c.paragraphs[0]
    run = p.add_run(get_tag("CAMPO_DECISAO"))
    run.bold = True
    run.font.size = Pt(11)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    add_full_text("Condicionantes", get_tag("CAMPO_CONDICIONANTES"))

    # Assinatura
    doc.add_paragraph("\n")
    t_sig = doc.add_table(rows=1, cols=2)
    t_sig.rows[0].cells[0].text = "Data: " + datetime.now().strftime('%d/%m/%Y')
    
    p_sig = t_sig.rows[0].cells[1].paragraphs[0]
    p_sig.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_sig.add_run("O Técnico,\n\n_______________________").bold = True

    bio = io.BytesIO()
    doc.save(bio)
    return bio

# ==========================================
# --- UI PRINCIPAL ---
# ==========================================
st.title("⚖️ Análise Caso a Caso (RJAIA)")
st.markdown("### Auditoria Técnica e Decisão Fundamentada")
col1, col2, col3 = st.columns(3)

with col1:
    files_sim = st.file_uploader("📂 Simulação SILiAmb", type=['pdf'], accept_multiple_files=True, key=f"s_{st.session_state.uploader_key}")
with col2:
    files_form = st.file_uploader("📂 Formulário", type=['pdf'], accept_multiple_files=True, key=f"f_{st.session_state.uploader_key}")
with col3:
    files_doc = st.file_uploader("📂 Projeto/Memória", type=['pdf'], accept_multiple_files=True, key=f"p_{st.session_state.uploader_key}")

st.markdown("---")

if st.button("🚀 Processar com Rigor Jurídico", type="primary", use_container_width=True):
    if not (files_sim and files_form and files_doc):
        st.error("Carregue todos os documentos.")
    elif not st.secrets.get("GOOGLE_API_KEY") and not api_key: # Verifica ambas as fontes
        st.error("Chave API em falta.")
    else:
        with st.status("⚙️ A processar...", expanded=True) as status:
            ts = extract_text(files_sim, "SIM")
            tf = extract_text(files_form, "FORM")
            tp = extract_text(files_doc, "PROJ")
            
            st.write("🕵️ Auditoria e Legislação...")
            st.session_state.validation_result = analyze_validation(ts, tf, tp)
            
            st.write("⚖️ Decisão e Formatação...")
            st.session_state.decision_result = generate_decision_text(ts, tf, tp)
            status.update(label="Concluído!", state="complete")

if st.session_state.validation_result and st.session_state.decision_result:
    c1, c2 = st.columns(2)
    f_val = create_validation_doc(st.session_state.validation_result)
    c1.download_button("📄 Relatório Auditoria (Justificado + Links)", f_val.getvalue(), "Relatorio_Auditoria.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    f_dec = create_decision_doc(st.session_state.decision_result)
    c2.download_button("📝 Minuta Decisão (Justificado)", f_dec.getvalue(), "Proposta_Decisao.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", type="primary")
