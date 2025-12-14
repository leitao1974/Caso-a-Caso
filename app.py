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
    
    SAÍDA (Markdown):
    1. "STATUS: [VALIDADO ou INCONSISTENTE]"
    2. "## 1. Resumo Executivo"
    3. "## 2. Análise de Consistência" (Checklist com ✅ ou ❌)
    4. "## 3. Detalhe" (Se houver erros)
    """)

# --- PROMPT 2: DECISÃO (Atualizado para coincidir com o Modelo) ---
def generate_decision_text(t_sim, t_form, t_proj):
    return get_ai(f"""
    Atua como Entidade Licenciadora. Produz a MINUTA DE ANÁLISE CASO A CASO (DL 151-B/2013).
    Usa os dados do PROJETO e FORMULÁRIO.

    CONTEXTO:
    {t_proj[:120000]}
    {t_form[:30000]}

    Preenche as tags abaixo EXATAMENTE como pedido:

    ### CAMPO_DESIGNACAO
    (Nome do projeto)
    
    ### CAMPO_TIPOLOGIA
    (Apenas a tipologia do projeto, ex: Indústria de...)
    
    ### CAMPO_ENQUADRAMENTO
    (O enquadramento legal: Anexo, Ponto, Alínea do RJAIA e se é sub-limiar)
    
    ### CAMPO_LOCALIZACAO
    (Freguesia e Concelho. Ex: União de Freguesias de X, Concelho de Y)
    
    ### CAMPO_AREAS_SENSIVEIS
    (Sim ou Não. Se Sim, indica qual a alínea a) do artigo 2º do RJAIA afetada)
    
    ### CAMPO_PROPONENTE
    (Nome e NIF)
    
    ### CAMPO_ENTIDADE_LICENCIADORA
    (Identifica a entidade licenciadora se constar nos docs, senão escreve "A preencher")
    
    ### CAMPO_AUTORIDADE_AIA
    (Identifica a autoridade de AIA, ex: CCDR Centro, APA, ou "A preencher")

    ### CAMPO_DESCRICAO
    (Breve descrição do projeto: o que é, objetivos e dimensões principais)

    ### CAMPO_CARATERISTICAS
    (Fundamentação Anexo III: Dimensão, cumulação, recursos, resíduos, poluição)
    
    ### CAMPO_LOCALIZACAO_PROJETO
    (Fundamentação Anexo III: Uso atual do solo, capacidade de carga, áreas protegidas)
    
    ### CAMPO_IMPACTES
    (Fundamentação Anexo III: Extensão, magnitude, probabilidade, duração)

    ### CAMPO_DECISAO
    (Apenas: "SUJEITO A AIA" ou "NÃO SUJEITO A AIA")
    
    ### CAMPO_CONDICIONANTES
    (Lista de medidas a impor no licenciamento)
    """)

# ==========================================
# --- WORD GENERATORS ---
# ==========================================

def create_validation_doc(text):
    doc = Document()
    
    section = doc.sections[0]
    section.header.paragraphs[0].text = "Relatório de Validação Técnica"
    section.header.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT

    doc.add_heading("Relatório de Incongruências e Validação", 0)
    doc.add_paragraph(f"Data: {datetime.now().strftime('%d/%m/%Y')}")

    if "INCONSISTENTE" in text.upper() or "ALERTA" in text.upper():
        p = doc.add_paragraph("⚠️ PARECER: EXISTEM INCONGRUÊNCIAS")
        p.runs[0].font.color.rgb = RGBColor(255, 0, 0)
    else:
        p = doc.add_paragraph("✅ PARECER: PROCESSO CONSISTENTE")
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

    # Função auxiliar para extrair tags
    def get_tag(tag):
        m = re.search(f"### {tag}(.*?)###", text, re.DOTALL)
        if not m: m = re.search(f"### {tag}(.*)", text, re.DOTALL)
        return m.group(1).strip() if m else ""

    # Título do Documento
    # Nota: O modelo original tem logos da CCDR, aqui usamos texto simples
    h = doc.add_heading("Análise prévia e decisão de sujeição a AIA", 0)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("")

    # Tabela Principal
    table = doc.add_table(rows=0, cols=2)
    table.style = 'Table Grid'

    # Funções para adicionar linhas conforme o modelo
    def add_merged_header(txt):
        r = table.add_row()
        c = r.cells[0]
        c.merge(r.cells[1])
        # Fundo cinza ou destaque se necessário, aqui apenas negrito
        p = c.paragraphs[0]
        run = p.add_run(txt)
        run.bold = True
        return r

    def add_row(label, value):
        r = table.add_row()
        r.cells[0].paragraphs[0].add_run(label).bold = True
        r.cells[1].text = value

    # 1. Identificação
    add_merged_header("Identificação")
    add_row("Designação do projeto", get_tag("CAMPO_DESIGNACAO"))
    add_row("Tipologia de Projeto", get_tag("CAMPO_TIPOLOGIA"))
    add_row("Enquadramento no RJAIA", get_tag("CAMPO_ENQUADRAMENTO"))
    add_row("Localização (freguesia e concelho)", get_tag("CAMPO_LOCALIZACAO"))
    add_row("Afetação de áreas sensíveis (alínea a) do artigo 2º do RJAIA)", get_tag("CAMPO_AREAS_SENSIVEIS"))
    add_row("Proponente", get_tag("CAMPO_PROPONENTE"))
    add_row("Entidade Licenciadora", get_tag("CAMPO_ENTIDADE_LICENCIADORA"))
    add_row("Autoridade de AIA", get_tag("CAMPO_AUTORIDADE_AIA"))

    # 2. Breve Descrição
    add_merged_header("Breve descrição do projeto")
    r = table.add_row()
    r.cells[0].merge(r.cells[1])
    r.cells[0].text = get_tag("CAMPO_DESCRICAO")

    # 3. Fundamentação
    add_merged_header("Fundamentação da decisão")
    add_row("Caraterísticas do projeto", get_tag("CAMPO_CARATERISTICAS"))
    add_row("Localização do projeto", get_tag("CAMPO_LOCALIZACAO_PROJETO"))
    add_row("Características do impacte potencial", get_tag("CAMPO_IMPACTES"))

    # 4. Decisão
    add_merged_header("Decisão")
    r = table.add_row()
    c = r.cells[0]
    c.merge(r.cells[1])
    decision_text = get_tag("CAMPO_DECISAO")
    run = c.paragraphs[0].add_run(decision_text)
    run.bold = True
    run.font.size = Pt(12)
    
    # 5. Condicionantes
    add_merged_header("Condicionantes a impor em sede de licenciamento")
    r = table.add_row()
    c = r.cells[0]
    c.merge(r.cells[1])
    c.text = get_tag("CAMPO_CONDICIONANTES")

    # Assinatura
    doc.add_paragraph("\n\n")
    sig_table = doc.add_table(rows=1, cols=2)
    sig_table.rows[0].cells[0].text = "Data: " + datetime.now().strftime('%d/%m/%Y')
    sig_table.rows[0].cells[1].text = "O Técnico,\n_______________________"
    sig_table.rows[0].cells[1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT

    bio = io.BytesIO()
    doc.save(bio)
    return bio

# ==========================================
# --- MOTOR PRINCIPAL ---
# ==========================================
st.markdown("---")

if st.button("🚀 Processar Documentos", type="primary", use_container_width=True):
    if not (files_sim and files_form and files_doc):
        st.error("⚠️ Carregue documentos nas 3 caixas.")
    elif not api_key:
        st.error("⚠️ Insira a API Key.")
    else:
        with st.status("⚙️ A trabalhar...", expanded=True) as status:
            st.write("📖 A ler ficheiros...")
            ts = extract_text(files_sim, "SIM")
            tf = extract_text(files_form, "FORM")
            tp = extract_text(files_doc, "PROJ")
            
            st.write("🕵️ Validação Técnica...")
            st.session_state.validation_result = analyze_validation(ts, tf, tp)
            
            st.write("⚖️ Minuta de Decisão...")
            st.session_state.decision_result = generate_decision_text(ts, tf, tp)
            
            status.update(label="✅ Concluído!", state="complete")

if st.session_state.validation_result and st.session_state.decision_result:
    st.success("Análise concluída.")
    c1, c2 = st.columns(2)
    
    f_val = create_validation_doc(st.session_state.validation_result)
    c1.download_button("📄 1. Relatório de Validação", f_val.getvalue(), "Relatorio_Validacao.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", key="btn_val")
    
    f_dec = create_decision_doc(st.session_state.decision_result)
    c2.download_button("📝 2. Minuta de Decisão", f_dec.getvalue(), "Proposta_Decisao.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", type="primary", key="btn_dec")
