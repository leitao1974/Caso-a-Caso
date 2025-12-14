import streamlit as st
from pypdf import PdfReader
from docx import Document
from docx.shared import Pt, RGBColor, Inches
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

# Inicialização de variáveis de estado
if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0
if 'validation_result' not in st.session_state:
    st.session_state.validation_result = None
if 'decision_result' not in st.session_state:
    st.session_state.decision_result = None

def reset_app():
    """Limpa os resultados e reinicia os uploaders."""
    st.session_state.uploader_key += 1
    st.session_state.validation_result = None
    st.session_state.decision_result = None

# ==========================================
# --- SIDEBAR & SETUP ---
# ==========================================
with st.sidebar:
    st.header("🔐 Configuração")
    
    # Tenta ler dos secrets ou pede input
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

# Chaves dinâmicas para permitir limpeza
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
# --- FUNÇÕES DE AUXÍLIO ---
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

# --- FORMATADOR INTELIGENTE (MARKDOWN -> WORD) ---
def markdown_to_word(doc, text):
    """
    Converte texto Markdown simples (Headers ##, Bullets -, Bold **) em estilos Word.
    Torna o relatório muito mais legível.
    """
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        # 1. Títulos (##)
        if line.startswith('##'):
            clean_text = line.replace('#', '').strip()
            doc.add_heading(clean_text, level=2)
        
        # 2. Títulos Menores (###)
        elif line.startswith('###'):
            clean_text = line.replace('#', '').strip()
            doc.add_heading(clean_text, level=3)
            
        # 3. Listas (Bullets)
        elif line.startswith('- ') or line.startswith('* '):
            clean_text = line[2:].strip()
            p = doc.add_paragraph(style='List Bullet')
            # Aplica negrito se houver **texto**
            parts = re.split(r'(\*\*.*?\*\*)', clean_text)
            for part in parts:
                if part.startswith('**') and part.endswith('**'):
                    run = p.add_run(part[2:-2])
                    run.bold = True
                else:
                    p.add_run(part)
                    
        # 4. Texto Normal
        else:
            p = doc.add_paragraph()
            # Aplica negrito se houver **texto**
            parts = re.split(r'(\*\*.*?\*\*)', line)
            for part in parts:
                if part.startswith('**') and part.endswith('**'):
                    run = p.add_run(part[2:-2])
                    run.bold = True
                else:
                    p.add_run(part)

# ==========================================
# --- PROMPTS DA IA ---
# ==========================================

def analyze_validation(t_sim, t_form, t_proj):
    return get_ai(f"""
    Atua como Auditor Técnico Sénior. A tua tarefa é criar um RELATÓRIO DE INCONGRUÊNCIAS legível e estruturado.
    
    Realiza uma TRIANGULAÇÃO DE DADOS rigorosa entre:
    1. SIMULAÇÃO | 2. FORMULÁRIO | 3. PROJETO
    
    DADOS:
    [SIMULAÇÃO]: {t_sim[:30000]}
    [FORMULÁRIO]: {t_form[:30000]}
    [PROJETO]: {t_proj[:100000]}

    TAREFA:
    Verifica: Identificação, Localização, CAEs, Áreas (Implantação/Total), Capacidades.
    
    ESTRUTURA OBRIGATÓRIA DA RESPOSTA (Usa Markdown):
    
    1. Começa com uma linha contendo apenas: "STATUS: [VALIDADO ou INCONSISTENTE]"
    
    2. Cria uma secção: "## 1. Resumo Executivo"
       - Resume em 2 linhas se o processo está apto ou tem falhas graves.
    
    3. Cria uma secção: "## 2. Análise de Consistência"
       - Usa uma lista (bullet points) para cada parâmetro analisado.
       - Se houver erro, escreve: "- **[PARÂMETRO]**: ❌ Inconsistente. (Simulação: X | Projeto: Y)"
       - Se estiver correto, escreve: "- **[PARÂMETRO]**: ✅ Validado."
    
    4. Cria uma secção: "## 3. Detalhe das Incongruências" (Apenas se existirem)
       - Explica porque é que a diferença é relevante ou se pode ser erro de arredondamento.
    
    Nota: Sê direto e claro. Usa formatação Markdown (negrito **texto**, listas - item, titulos ##).
    """)

def generate_decision_text(t_sim, t_form, t_proj):
    return get_ai(f"""
    Atua como Entidade Licenciadora. Produz a MINUTA DE ANÁLISE CASO A CASO (DL 151-B/2013).
    Usa o texto do PROJETO como fonte principal.

    CONTEXTO:
    {t_proj[:120000]}
    {t_form[:30000]}

    Preenche as tags abaixo (não mudes os nomes das tags):
    ### CAMPO_DESIGNACAO
    ### CAMPO_TIPOLOGIA (Anexo, Ponto, Alínea)
    ### CAMPO_LOCALIZACAO
    ### CAMPO_AREAS_SENSIVEIS
    ### CAMPO_PROPONENTE
    ### CAMPO_DESCRICAO (Resumo claro)
    ### CAMPO_FUNDAMENTACAO_CARATERISTICAS (Anexo III)
    ### CAMPO_FUNDAMENTACAO_LOCALIZACAO (Anexo III)
    ### CAMPO_FUNDAMENTACAO_IMPACTES (Anexo III)
    ### CAMPO_DECISAO ("SUJEITO A AIA" ou "NÃO SUJEITO A AIA")
    ### CAMPO_CONDICIONANTES (Lista bullet points)
    """)

# ==========================================
# --- GERADORES DE WORD ---
# ==========================================

def create_validation_doc(text):
    doc = Document()
    
    # Cabeçalho Institucional Simples
    section = doc.sections[0]
    header = section.header
    p_head = header.paragraphs[0]
    p_head.text = "Relatório de Validação Técnica - RJAIA"
    p_head.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    # Título Principal
    title = doc.add_heading("Relatório de Incongruências e Validação", 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f"Data da Análise: {datetime.now().strftime('%d/%m/%Y')}\n").alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Caixa de Status Colorida
    status_paragraph = doc.add_paragraph()
    if "STATUS: INCONSISTENTE" in text.upper() or "STATUS: ALERTA" in text.upper():
        runner = status_paragraph.add_run("⚠️ PARECER: EXISTEM INCONGRUÊNCIAS A VERIFICAR")
        runner.bold = True
        runner.font.color.rgb = RGBColor(255, 0, 0) # Vermelho
        runner.font.size = Pt(14)
    else:
        runner = status_paragraph.add_run("✅ PARECER: PROCESSO CONSISTENTE")
        runner.bold = True
        runner.font.color.rgb = RGBColor(0, 150, 0) # Verde
        runner.font.size = Pt(14)
    status_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    doc.add_paragraph("---") # Linha separadora

    # Usa o parser inteligente para formatar o corpo do texto
    # Remove a primeira linha de status do corpo para não duplicar
    clean_body = re.sub(r'STATUS:.*', '', text, count=1).strip()
    markdown_to_word(doc, clean_body)

    # Rodapé
    footer = section.footer
    p_foot = footer.paragraphs[0]
    p_foot.text = "Documento gerado automaticamente por IA. A validação final cabe ao técnico responsável."
    
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
        return m.group(1).strip() if m else "N/A"

    h = doc.add_heading("ANÁLISE PRÉVIA E DECISÃO DE SUJEIÇÃO A AIA", 0)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("Regime Jurídico da Avaliação de Impacte Ambiental").alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("")

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
            
            st.write("🕵️ A analisar consistência (Triangulação)...")
            st.session_state.validation_result = analyze_validation(ts, tf, tp)
            
            st.write("⚖️ A redigir minuta de decisão...")
            st.session_state.decision_result = generate_decision_text(ts, tf, tp)
            
            status.update(label="✅ Concluído!", state="complete")

# ==========================================
# --- ÁREA DE DOWNLOADS ---
# ==========================================
if st.session_state.validation_result and st.session_state.decision_result:
    
    st.success("Análise concluída com sucesso.")
    st.markdown("### 📥 Descarregar Resultados")
    
    c1, c2 = st.columns(2)
    
    # Documento 1: Relatório de Validação (Melhorado)
    f_val = create_validation_doc(st.session_state.validation_result)
    c1.download_button(
        label="📄 1. Relatório de Validação",
        data=f_val.getvalue(),
        file_name="Relatorio_Incongruencias.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        key="btn_val",
        help="Relatório detalhado com lista de conformidades e disparidades."
    )
    
    # Documento 2: Minuta de Decisão
    f_dec = create_decision_doc(st.session_state.decision_result)
    c2.download_button(
        label="📝 2. Minuta de Decisão",
        data=f_dec.getvalue(),
        file_name="Proposta_Decisao.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        type="primary",
        key="btn_dec",
        help="Minuta preenchida pronta a editar."
    )
