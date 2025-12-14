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
                # O Flash é ideal pela janela de contexto grande (lê muitos PDFs)
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
st.caption("O sistema analisará os documentos com rigor crítico, indicando a fonte (Pág. X) de cada dado relevante.")

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
            # ADICIONAMOS O NOME DO FICHEIRO PARA CITAÇÃO
            text += f"\n\n>>> FONTE: {label} ({f.name}) <<<\n" 
            for i, p in enumerate(r.pages):
                # ADICIONAMOS O NÚMERO DA PÁGINA PARA CITAÇÃO
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
    Atua como um PERITO AUDITOR AMBIENTAL (Rigoroso e Cético).
    
    A tua missão não é apenas "validar", é "AUDITAR". Procura ativamente discrepâncias escondidas.
    
    FONTES DE DADOS:
    1. SIMULAÇÃO SILiAmb (Teórico)
    2. FORMULÁRIO (Declarativo)
    3. PROJETO TÉCNICO (Realidade descrita)
    
    TEXTO DOS DOCUMENTOS:
    {t_sim[:30000]}
    {t_form[:30000]}
    {t_proj[:100000]}

    INSTRUÇÕES DE AUDITORIA:
    1. Compara os valores numéricos exatos (Áreas m2, Toneladas/ano, Capacidades). 
    2. Se encontrares uma diferença, reporta-a indicando a fonte e a página. Ex: "Formulário diz 100t (Pág. 2) mas Memória diz 150t (Pág. 14)".
    3. Verifica se os códigos LER e operações R/D coincidem em todos os documentos.
    
    OUTPUT OBRIGATÓRIO (Markdown):
    1. "STATUS: [VALIDADO ou INCONSISTENTE]"
    2. "## 1. Resumo da Auditoria"
    3. "## 2. Tabela de Incongruências" (Se houver, com CITAÇÃO DE PÁGINAS)
    4. "## 3. Pontos de Atenção Técnica" (Alertas sobre omissões técnicas, mesmo que os números batam certo).
    """)

# --- PROMPT 2: DECISÃO FUNDAMENTADA (COM CITAÇÕES) ---
def generate_decision_text(t_sim, t_form, t_proj):
    return get_ai(f"""
    Atua como Técnico Superior da CCDR com perfil de ANÁLISE CRÍTICA.
    O teu objetivo é produzir a minuta de decisão, mas com uma FUNDAMENTAÇÃO ROBUSTA e baseada em evidências.

    REGRA DE OURO: Sempre que apresentares um dado técnico (áreas, caudais, tipologia, classes de solo, gestão de resíduos), DEVES INDICAR A FONTE E A PÁGINA entre parênteses.
    Exemplo: "...prevê-se a impermeabilização de 2500 m2 (Memória Descritiva, pág. 12), o que contraria o PDM..."

    CONTEXTO:
    {t_proj[:150000]}
    {t_form[:30000]}

    PREENCHE AS TAGS PARA A MINUTA (Sê detalhado e cita as fontes):

    ### CAMPO_DESIGNACAO
    (Nome rigoroso do projeto)
    
    ### CAMPO_TIPOLOGIA
    (Referência legal exata)
    
    ### CAMPO_ENQUADRAMENTO
    (Artigo/Anexo do RJAIA)
    
    ### CAMPO_LOCALIZACAO
    (Freguesia/Concelho)
    
    ### CAMPO_AREAS_SENSIVEIS
    (Verifica se afeta RAN, REN ou Rede Natura. Cita a planta de condicionantes se referida no texto)
    
    ### CAMPO_PROPONENTE
    (Nome/NIF)
    
    ### CAMPO_ENTIDADE_LICENCIADORA
    (Nome da entidade)
    
    ### CAMPO_AUTORIDADE_AIA
    (Nome da autoridade)

    ### CAMPO_DESCRICAO
    (Descrição técnica densa. Não uses linguagem genérica.
     - Indica as áreas exatas de construção/demolição com citação de página.
     - Descreve o processo industrial/operação de resíduos.
     - Menciona licenças anteriores se existirem no texto.)

    ### CAMPO_CARATERISTICAS
    (Esta é a parte mais importante. Sê ousado na análise técnica:
     - Quantifica tudo (Ton/ano, m3/dia) citando as páginas.
     - Analisa a "acumulação com outros projetos" (ex: existem outras indústrias vizinhas referidas?).
     - Analisa a produção de resíduos e efluentes. Os separadores de hidrocarbonetos são adequados? O poço absorvente é legal? Cita onde isso está escrito.)
    
    ### CAMPO_LOCALIZACAO_PROJETO
    (Cruza com o PDM. O uso do solo é compatível? A zona é sensível? Cita a planta de ordenamento se mencionada.)
    
    ### CAMPO_IMPACTES
    (Não digas apenas "pouco significativo". Fundamenta.
     - Avalia ruído, qualidade do ar e solos.
     - Critica a avaliação feita pelo proponente se ela for superficial.
     - Conclui sobre a magnitude e reversibilidade.)

    ### CAMPO_DECISAO
    (SUJEITO ou NÃO SUJEITO)
    
    ### CAMPO_CONDICIONANTES
    (Lista medidas técnicas concretas e exigentes para garantir que o "Não Sujeito" é seguro. Ex: "Apresentar comprovativo de ligação à rede...").
    """)

# ==========================================
# --- WORD GENERATORS ---
# ==========================================

def create_validation_doc(text):
    doc = Document()
    
    section = doc.sections[0]
    section.header.paragraphs[0].text = "Relatório de Auditoria Técnica (Pré-Análise)"
    section.header.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT

    doc.add_heading("Auditoria de Conformidade e Rastreabilidade", 0)
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

    # Título Institucional
    h = doc.add_heading("Análise prévia e decisão de sujeição a AIA", 0)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("")

    # Tabela
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

    # 1. Identificação
    add_section_header("Identificação")
    add_field_row("Designação do projeto", get_tag("CAMPO_DESIGNACAO"))
    add_field_row("Tipologia de Projeto", get_tag("CAMPO_TIPOLOGIA"))
    add_field_row("Enquadramento no RJAIA", get_tag("CAMPO_ENQUADRAMENTO"))
    add_field_row("Localização (freguesia e concelho)", get_tag("CAMPO_LOCALIZACAO"))
    add_field_row("Afetação de áreas sensíveis (alínea a) do artigo 2º do RJAIA)", get_tag("CAMPO_AREAS_SENSIVEIS"))
    add_field_row("Proponente", get_tag("CAMPO_PROPONENTE"))
    add_field_row("Entidade Licenciadora", get_tag("CAMPO_ENTIDADE_LICENCIADORA"))
    add_field_row("Autoridade de AIA", get_tag("CAMPO_AUTORIDADE_AIA"))

    # 2. Descrição
    add_full_text_section("Breve descrição do projeto", get_tag("CAMPO_DESCRICAO"))

    # 3. Fundamentação (Onde a IA deve ser ousada e citar fontes)
    add_section_header("Fundamentação da decisão")
    add_field_row("Caraterísticas do projeto", get_tag("CAMPO_CARATERISTICAS"))
    add_field_row("Localização do projeto", get_tag("CAMPO_LOCALIZACAO_PROJETO"))
    add_field_row("Características do impacte potencial", get_tag("CAMPO_IMPACTES"))

    # 4. Decisão
    add_section_header("Decisão")
    r = table.add_row()
    c = r.cells[0]
    c.merge(r.cells[1])
    run = c.paragraphs[0].add_run(get_tag("CAMPO_DECISAO"))
    run.bold = True; run.font.size = Pt(11)

    # 5. Condicionantes
    add_full_text_section("Condicionantes a impor em sede de licenciamento", get_tag("CAMPO_CONDICIONANTES"))

    # Assinatura
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

if st.button("🚀 Iniciar Auditoria Técnica", type="primary", use_container_width=True):
    if not (files_sim and files_form and files_doc):
        st.error("⚠️ Carregue documentos nas 3 caixas.")
    elif not api_key:
        st.error("⚠️ Insira a API Key.")
    else:
        with st.status("⚙️ A processar com análise crítica...", expanded=True) as status:
            st.write("📖 A indexar páginas e referências...")
            ts = extract_text(files_sim, "SIM")
            tf = extract_text(files_form, "FORM")
            tp = extract_text(files_doc, "PROJ")
            
            st.write("🕵️ A auditar consistência e rastrear fontes...")
            st.session_state.validation_result = analyze_validation(ts, tf, tp)
            
            st.write("⚖️ A fundamentar decisão com referências técnicas...")
            st.session_state.decision_result = generate_decision_text(ts, tf, tp)
            
            status.update(label="✅ Análise Concluída!", state="complete")

if st.session_state.validation_result and st.session_state.decision_result:
    st.success("Resultados gerados.")
    
    c1, c2 = st.columns(2)
    
    f_val = create_validation_doc(st.session_state.validation_result)
    c1.download_button(
        "📄 1. Relatório de Auditoria", 
        f_val.getvalue(), 
        "Relatorio_Auditoria.docx", 
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
        key="btn_val"
    )
    
    f_dec = create_decision_doc(st.session_state.decision_result)
    c2.download_button(
        "📝 2. Minuta de Decisão Fundamentada", 
        f_dec.getvalue(), 
        "Proposta_Decisao_Tecnica.docx", 
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
        type="primary", 
        key="btn_dec"
        )
