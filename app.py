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
            else:
                st.error("Chave sem modelos.")
        except Exception as e:
            st.error(f"Erro: {e}")

    st.divider()
    if st.button("🔄 Nova Análise / Limpar Tudo", use_container_width=True):
        reset_app()
        st.rerun()

# ==========================================
# --- INTERFACE ---
# ==========================================
st.title("⚖️ Análise Caso a Caso (RJAIA)")
st.markdown("### Auditoria Técnica e Decisão Fundamentada")
st.caption("Modo: Síntese Rigorosa (Texto Corrido Denso)")

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
            text += f"\n\n>>> FONTE: {label} ({f.name}) <<<\n" 
            for i, p in enumerate(r.pages):
                text += f"[Pág. {i+1}] {p.extract_text()}\n"
        except: pass
    return text

def get_ai(prompt):
    model = genai.GenerativeModel(selected_model)
    return model.generate_content(prompt).text

def markdown_to_word(doc, text):
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if not line: continue
        if line.startswith('##'):
            doc.add_heading(line.replace('#', '').strip(), level=2)
        elif line.startswith('###'):
            doc.add_heading(line.replace('#', '').strip(), level=3)
        elif line.startswith('- ') or line.startswith('* '):
            p = doc.add_paragraph(style='List Bullet')
            parts = re.split(r'(\*\*.*?\*\*)', line[2:])
            for part in parts:
                if part.startswith('**') and part.endswith('**'):
                    p.add_run(part[2:-2]).bold = True
                else:
                    p.add_run(part)
        else:
            p = doc.add_paragraph()
            parts = re.split(r'(\*\*.*?\*\*)', line)
            for part in parts:
                if part.startswith('**') and part.endswith('**'):
                    p.add_run(part[2:-2]).bold = True
                else:
                    p.add_run(part)

# --- PROMPT 1: VALIDAÇÃO CRÍTICA ---
def analyze_validation(t_sim, t_form, t_proj):
    return get_ai(f"""
    Atua como PERITO AUDITOR.
    
    FONTES DE DADOS:
    1. SIMULAÇÃO | 2. FORMULÁRIO | 3. PROJETO
    
    DADOS:
    {t_sim[:30000]}
    {t_form[:30000]}
    {t_proj[:100000]}

    TAREFA:
    Audita a consistência de números (Áreas, Toneladas, Capacidades) e códigos LER/CAE.
    Se encontrares discrepâncias, reporta com a página: "Formulário diz X (Pág. 2) mas Projeto diz Y (Pág. 14)".
    
    OUTPUT (Markdown):
    1. "STATUS: [VALIDADO ou INCONSISTENTE]"
    2. "## 1. Resumo"
    3. "## 2. Incongruências Detetadas" (Se houver)
    4. "## 3. Alertas Técnicos"
    """)

# --- PROMPT 2: DECISÃO (SINTÉTICA, RIGOROSA E CORRIDA) ---
def generate_decision_text(t_sim, t_form, t_proj):
    return get_ai(f"""
    Atua como Técnico Superior da CCDR.
    Redige a minuta de decisão para um processo de Análise Caso a Caso (RJAIA).

    ESTILO DE REDAÇÃO (SÍNTESE RIGOROSA):
    1. **TEXTO CORRIDO DENSO:** Escreve parágrafos que fundem informação. Não uses tópicos/bullets.
    2. **ZERO PALHA:** Elimina conectores vazios ("Relativamente a...", "No que concerne..."). Começa logo pelo sujeito/dado.
    3. **RASTREABILIDADE:** Cita sempre a fonte/página abreviada: `(MD, pág. 4)`.

    EXEMPLO DE ESTILO DESEJADO:
    "A instalação prevê tratar 500 t/ano de VFV (MD, pág. 12), em área totalmente impermeabilizada de 200m2 (Peças Desenhadas, Doc. 3). Os efluentes passam por separador de hidrocarbonetos antes da descarga (Pág. 15), garantindo o cumprimento dos VLE."

    CONTEXTO:
    {t_proj[:150000]}
    {t_form[:30000]}

    PREENCHE AS TAGS ABAIXO:

    ### CAMPO_DESIGNACAO
    (Nome do projeto)
    
    ### CAMPO_TIPOLOGIA
    (Referência legal exata)
    
    ### CAMPO_ENQUADRAMENTO
    (Artigo/Anexo do RJAIA)
    
    ### CAMPO_LOCALIZACAO
    (Freguesia/Concelho)
    
    ### CAMPO_AREAS_SENSIVEIS
    (Frase única sobre a afetação)
    
    ### CAMPO_PROPONENTE
    (Nome/NIF)
    
    ### CAMPO_ENTIDADE_LICENCIADORA
    (Nome da entidade)
    
    ### CAMPO_AUTORIDADE_AIA
    (Nome da autoridade)

    ### CAMPO_DESCRICAO
    (Resumo em 1 parágrafo denso: objetivo, localização exata e operações principais.)

    ### CAMPO_CARATERISTICAS
    (Parágrafos de texto corrido. Funde a informação quantitativa:
     - Une quantidades de resíduos, tipologias e capacidades numa sequência lógica.
     - Une descrição das infraestruturas (áreas, pavimentos) com a gestão de efluentes.
     - Cita sempre as páginas.)
    
    ### CAMPO_LOCALIZACAO_PROJETO
    (1 ou 2 frases sobre compatibilidade com PDM e servidões, citando a planta analisada.)
    
    ### CAMPO_IMPACTES
    (Texto corrido sintético.
     Ex: "Impactes no ar e ruído são pouco significativos dada a envolvente industrial. O risco de contaminação do solo é minimizado pela impermeabilização (MD, pág. 5) e sistema de tratamento proposto.")

    ### CAMPO_DECISAO
    (SUJEITO ou NÃO SUJEITO)
    
    ### CAMPO_CONDICIONANTES
    (Lista numerada compacta das obrigações essenciais.)
    """)

# ==========================================
# --- WORD GENERATORS ---
# ==========================================

def create_validation_doc(text):
    doc = Document()
    section = doc.sections[0]
    section.header.paragraphs[0].text = "Relatório de Auditoria Técnica"
    section.header.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT

    doc.add_heading("Auditoria de Conformidade", 0)
    doc.add_paragraph(f"Data: {datetime.now().strftime('%d/%m/%Y')}")

    if "INCONSISTENTE" in text.upper():
        p = doc.add_paragraph("⚠️ PARECER: INCONGRUÊNCIAS DETETADAS")
        p.runs[0].font.color.rgb = RGBColor(255, 0, 0)
    else:
        p = doc.add_paragraph("✅ PARECER: DADOS CONSISTENTES")
        p.runs[0].font.color.rgb = RGBColor(0, 128, 0)
    p.runs[0].bold = True
    
    doc.add_paragraph("---")
    clean_text = re.sub(r'STATUS:.*', '', text, count=1).strip()
    markdown_to_word(doc, clean_text)
    
    bio = io.BytesIO()
    doc.save(bio)
    return bio

def create_decision_doc(text):
    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Arial'
    style.font.size = Pt(10)
    style.paragraph_format.space_after = Pt(6)

    def get_tag(tag):
        m = re.search(f"### {tag}(.*?)###", text, re.DOTALL)
        if not m: m = re.search(f"### {tag}(.*)", text, re.DOTALL)
        return m.group(1).strip() if m else "A preencher"

    h = doc.add_heading("Análise prévia e decisão de sujeição a AIA", 0)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("")

    table = doc.add_table(rows=0, cols=2)
    table.style = 'Table Grid'

    def add_section_header(txt):
        r = table.add_row()
        c = r.cells[0]
        c.merge(r.cells[1])
        run = c.paragraphs[0].add_run(txt)
        run.bold = True
        return r

    def add_field_row(label, value):
        r = table.add_row()
        r.cells[0].paragraphs[0].add_run(label).bold = True
        r.cells[1].text = value

    def add_full_text_section(header, content):
        add_section_header(header)
        r = table.add_row()
        c = r.cells[0]
        c.merge(r.cells[1])
        c.text = content

    add_section_header("Identificação")
    add_field_row("Designação do projeto", get_tag("CAMPO_DESIGNACAO"))
    add_field_row("Tipologia de Projeto", get_tag("CAMPO_TIPOLOGIA"))
    add_field_row("Enquadramento no RJAIA", get_tag("CAMPO_ENQUADRAMENTO"))
    add_field_row("Localização (freguesia e concelho)", get_tag("CAMPO_LOCALIZACAO"))
    add_field_row("Afetação de áreas sensíveis (alínea a) do artigo 2º do RJAIA)", get_tag("CAMPO_AREAS_SENSIVEIS"))
    add_field_row("Proponente", get_tag("CAMPO_PROPONENTE"))
    add_field_row("Entidade Licenciadora", get_tag("CAMPO_ENTIDADE_LICENCIADORA"))
    add_field_row("Autoridade de AIA", get_tag("CAMPO_AUTORIDADE_AIA"))

    add_full_text_section("Breve descrição do projeto", get_tag("CAMPO_DESCRICAO"))

    add_section_header("Fundamentação da decisão")
    add_field_row("Caraterísticas do projeto", get_tag("CAMPO_CARATERISTICAS"))
    add_field_row("Localização do projeto", get_tag("CAMPO_LOCALIZACAO_PROJETO"))
    add_field_row("Características do impacte potencial", get_tag("CAMPO_IMPACTES"))

    add_section_header("Decisão")
    r = table.add_row()
    c = r.cells[0]
    c.merge(r.cells[1])
    run = c.paragraphs[0].add_run(get_tag("CAMPO_DECISAO"))
    run.bold = True; run.font.size = Pt(11)

    add_full_text_section("Condicionantes a impor em sede de licenciamento", get_tag("CAMPO_CONDICIONANTES"))

    doc.add_paragraph("\n")
    sig_table = doc.add_table(rows=1, cols=2)
    sig_table.allow_autofit = True
    sig_table.rows[0].cells[0].text = "Data: " + datetime.now().strftime('%d/%m/%Y')
    c_sig = sig_table.rows[0].cells[1]
    p_sig = c_sig.paragraphs[0]
    p_sig.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_sig.add_run("O Técnico / A Presidente,\n\n_______________________").bold = True

    bio = io.BytesIO()
    doc.save(bio)
    return bio

# ==========================================
# --- MOTOR PRINCIPAL ---
# ==========================================
st.markdown("---")

if st.button("🚀 Iniciar Análise Sintética", type="primary", use_container_width=True):
    if not (files_sim and files_form and files_doc):
        st.error("⚠️ Carregue documentos nas 3 caixas.")
    elif not api_key:
        st.error("⚠️ Insira a API Key.")
    else:
        with st.status("⚙️ A processar...", expanded=True) as status:
            st.write("📖 A ler e indexar...")
            ts = extract_text(files_sim, "SIM")
            tf = extract_text(files_form, "FORM")
            tp = extract_text(files_doc, "PROJ")
            
            st.write("🕵️ A auditar conformidade...")
            st.session_state.validation_result = analyze_validation(ts, tf, tp)
            
            st.write("⚖️ A redigir decisão (Modo Síntese Rigorosa)...")
            st.session_state.decision_result = generate_decision_text(ts, tf, tp)
            
            status.update(label="✅ Concluído!", state="complete")

if st.session_state.validation_result and st.session_state.decision_result:
    st.success("Documentos prontos.")
    
    c1, c2 = st.columns(2)
    
    f_val = create_validation_doc(st.session_state.validation_result)
    c1.download_button(
        "📄 1. Auditoria Técnica", 
        f_val.getvalue(), 
        "Relatorio_Auditoria.docx", 
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
        key="btn_val"
    )
    
    f_dec = create_decision_doc(st.session_state.decision_result)
    c2.download_button(
        "📝 2. Minuta de Decisão Sintética", 
        f_dec.getvalue(), 
        "Proposta_Decisao_Sintetica.docx", 
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
        type="primary", 
        key="btn_dec"
    )
