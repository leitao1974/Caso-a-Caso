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
# --- CONFIGURAÇÃO INICIAL ---
# ==========================================
st.set_page_config(page_title="Análise Caso a Caso RJAIA", page_icon="⚖️", layout="wide")

# Inicialização de estado para re-runs
if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# ==========================================
# --- SIDEBAR & CONFIGURAÇÃO IA ---
# ==========================================
with st.sidebar:
    st.header("🔐 Configuração")
    
    # Tenta ler dos secrets do Streamlit ou pede input manual
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
        st.success("Chave API detetada nos Secrets!")
    else:
        api_key = st.text_input("Google API Key", type="password")
    
    selected_model = "gemini-1.5-flash" # Default fallback
    
    if api_key:
        try:
            genai.configure(api_key=api_key)
            models = genai.list_models()
            # Filtra modelos que geram conteúdo
            valid_models = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
            
            if valid_models:
                # Prioriza o Flash por ser rápido e ter grande contexto
                default_idx = next((i for i, m in enumerate(valid_models) if 'flash' in m), 0)
                selected_model = st.selectbox("Modelo IA:", valid_models, index=default_idx)
                st.info("✅ Ligação IA estabelecida.")
            else:
                st.error("Chave válida, mas sem modelos disponíveis.")
        except Exception as e:
            st.error(f"Erro na Chave API: {e}")

    st.divider()
    st.markdown("""
    **Fluxo de Trabalho:**
    1. **Triangulação:** Cruza dados de 3 fontes.
    2. **Validação:** Se houver erros, gera relatório de incongruências.
    3. **Decisão:** Se validado, gera a minuta de decisão (Anexo III).
    """)

# ==========================================
# --- INTERFACE DE UPLOAD ---
# ==========================================
st.title("⚖️ Análise Caso a Caso (RJAIA)")
st.markdown("### Triangulação de Dados e Decisão Automática")
st.caption("Carregue os documentos nas caixas correspondentes para iniciar a verificação cruzada.")

col1, col2, col3 = st.columns(3)

with col1:
    st.info("📂 1. Simulação SILiAmb")
    files_sim = st.file_uploader("PDF da Simulação", type=['pdf'], accept_multiple_files=True, key="up_sim")

with col2:
    st.warning("📂 2. Formulário Submetido")
    files_form = st.file_uploader("PDF do Formulário", type=['pdf'], accept_multiple_files=True, key="up_form")

with col3:
    st.success("📂 3. Projeto / Memória")
    files_doc = st.file_uploader("Peças Escritas/Desenhadas", type=['pdf'], accept_multiple_files=True, key="up_doc")

# ==========================================
# --- FUNÇÕES DE EXTRAÇÃO E PROCESSAMENTO ---
# ==========================================

def extract_text(files, label):
    """Extrai texto de PDFs carregados."""
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
    """Envia prompt para o Gemini."""
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(prompt)
    return response.text

# --- PROMPT 1: TRIANGULAÇÃO ---
def analyze_consistency(t_sim, t_form, t_proj):
    prompt = f"""
    Atua como Auditor de Licenciamento Ambiental.
    Realiza uma TRIANGULAÇÃO RIGOROSA entre três fontes de dados:
    1. SIMULAÇÃO (Enquadramento teórico)
    2. FORMULÁRIO (Pedido oficial)
    3. PROJETO (Memória Descritiva Técnica)

    DADOS:
    [SIMULAÇÃO]: {t_sim[:30000]}
    [FORMULÁRIO]: {t_form[:30000]}
    [PROJETO]: {t_proj[:100000]}

    TAREFA:
    Verifica a coerência exata de:
    - Identificação do Proponente e NIF.
    - Localização (Freguesia, Artigos).
    - Códigos CAE e Classificação do Projeto.
    - Valores Numéricos (Área Total, Área Implantação, Capacidades).

    SAÍDA OBRIGATÓRIA:
    Se houver divergências de factos ou números (>1% diferença), inicia com "STATUS: INCONSISTENTE".
    Se tudo bater certo, inicia com "STATUS: VALIDADO".
    
    Se INCONSISTENTE, lista as divergências numa tabela.
    Se VALIDADO, lista os dados principais confirmados.
    """
    return get_ai_response(prompt, selected_model)

# --- PROMPT 2: DECISÃO AIA ---
def generate_decision(t_sim, t_form, t_proj):
    prompt = f"""
    Atua como Técnico da Entidade Licenciadora / Autoridade de AIA.
    O projeto foi validado. Produz a MINUTA DE ANÁLISE CASO A CASO (Screening RJAIA DL 151-B/2013).
    
    Usa a informação do PROJETO e FORMULÁRIO para preencher os campos.
    
    CONTEXTO:
    {t_proj[:100000]}
    {t_form[:30000]}

    Gera a resposta usando EXATAMENTE estas tags para eu processar no Word:

    ### CAMPO_DESIGNACAO
    (Nome do projeto)
    ### CAMPO_TIPOLOGIA
    (Enquadramento legal exato: Anexo, Ponto, Alínea)
    ### CAMPO_LOCALIZACAO
    (Freguesia, Concelho)
    ### CAMPO_AREAS_SENSIVEIS
    (Sim/Não e quais: Rede Natura, REN, RAN, Domínio Hídrico)
    ### CAMPO_PROPONENTE
    (Nome da entidade)
    ### CAMPO_DESCRICAO
    (Resumo técnico claro do que vai ser construído e objetivos)
    ### CAMPO_FUNDAMENTACAO_CARATERISTICAS
    (Análise Anexo III: Dimensão, uso de recursos, resíduos, poluição)
    ### CAMPO_FUNDAMENTACAO_LOCALIZACAO
    (Análise Anexo III: Capacidade de carga do ambiente, sensibilidade)
    ### CAMPO_FUNDAMENTACAO_IMPACTES
    (Análise Anexo III: Extensão, magnitude, probabilidade, duração)
    ### CAMPO_DECISAO
    (Apenas: "SUJEITO A AIA" ou "NÃO SUJEITO A AIA" ou "DISPENSADO DE AIA")
    ### CAMPO_CONDICIONANTES
    (Lista de medidas cautelares a impor no licenciamento)
    """
    return get_ai_response(prompt, selected_model)

# ==========================================
# --- GERAÇÃO DE WORD ---
# ==========================================

def create_inconsistency_doc(text):
    doc = Document()
    doc.add_heading("Relatório de Incongruências - RJAIA", 0)
    doc.add_paragraph(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    doc.add_paragraph("Aviso: Documentação Inconsistente", style="Intense Quote")
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

    # 2. Helpers para extrair tags
    def get_tag(tag):
        m = re.search(f"### {tag}(.*?)###", ai_text, re.DOTALL)
        if not m: m = re.search(f"### {tag}(.*)", ai_text, re.DOTALL)
        return m.group(1).strip() if m else "N/A"

    # 3. Tabela Estruturada
    table = doc.add_table(rows=0, cols=2)
    table.style = 'Table Grid'

    def add_section(title, content=None):
        row = table.add_row()
        c = row.cells[0]
        c.merge(row.cells[1])
        c.text = title
        c.paragraphs[0].runs[0].bold = True
        if content:
            r2 = table.add_row()
            c2 = r2.cells[0]
            c2.merge(r2.cells[1])
            c2.text = content

    def add_field(label, value):
        row = table.add_row()
        row.cells[0].text = label
        row.cells[0].paragraphs[0].runs[0].bold = True
        row.cells[1].text = value

    # Construção da Tabela
    add_section("IDENTIFICAÇÃO")
    add_field("Designação", get_tag("CAMPO_DESIGNACAO"))
    add_field("Tipologia", get_tag("CAMPO_TIPOLOGIA"))
    add_field("Localização", get_tag("CAMPO_LOCALIZACAO"))
    add_field("Áreas Sensíveis", get_tag("CAMPO_AREAS_SENSIVEIS"))
    add_field("Proponente", get_tag("CAMPO_PROPONENTE"))

    add_section("BREVE DESCRIÇÃO", get_tag("CAMPO_DESCRICAO"))

    add_section("FUNDAMENTAÇÃO DA DECISÃO (ANEXO III)")
    add_field("Caraterísticas", get_tag("CAMPO_FUNDAMENTACAO_CARATERISTICAS"))
    add_field("Localização", get_tag("CAMPO_FUNDAMENTACAO_LOCALIZACAO"))
    add_field("Impactes Potenciais", get_tag("CAMPO_FUNDAMENTACAO_IMPACTES"))

    # Decisão
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
    run.font.color.rgb = RGBColor(0, 51, 102)

    add_section("CONDICIONANTES", get_tag("CAMPO_CONDICIONANTES"))

    # Assinatura
    doc.add_paragraph("\n\n")
    doc.add_paragraph("O Técnico,\n\n_______________________").alignment = WD_ALIGN_PARAGRAPH.CENTER

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
        st.error("⚠️ Em falta: É necessário carregar documentos nas 3 caixas (Simulação, Formulário e Projeto).")
    elif not api_key:
        st.error("⚠️ Em falta: Chave API Google.")
    else:
        # 1. Leitura
        with st.spinner("📖 A ler documentos..."):
            txt_sim = extract_text(files_sim, "SIMULAÇÃO")
            txt_form = extract_text(files_form, "FORMULÁRIO")
            txt_doc = extract_text(files_doc, "PROJETO")

        # 2. Triangulação
        with st.status("🕵️ A verificar consistência dos dados...") as status:
            st.write("A cruzar Simulação vs Formulário vs Projeto...")
            consistency = analyze_consistency(txt_sim, txt_form, txt_doc)
            
            if "STATUS: INCONSISTENTE" in consistency.upper():
                status.update(label="❌ Inconsistências Detetadas!", state="error")
                st.error("Os documentos não são consistentes. Não é possível gerar decisão segura.")
                st.markdown(consistency)
                
                # Gera Word de Erros
                f_err = create_inconsistency_doc(consistency)
                st.download_button("⬇️ Baixar Relatório de Erros (.docx)", f_err.getvalue(), "Relatorio_Erros.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            
            else:
                status.update(label="✅ Dados Validados! A gerar Decisão...", state="complete")
                
                # 3. Decisão
                with st.spinner("⚖️ A redigir Minuta de Decisão (Anexo III)..."):
                    decision_txt = generate_decision(txt_sim, txt_form, txt_doc)
                
                st.success("Minuta Gerada com Sucesso!")
                
                # Preview e Download
                tab1, tab2 = st.tabs(["📄 Pré-visualização", "💾 Download"])
                with tab1:
                    st.markdown(decision_txt)
                with tab2:
                    f_dec = create_decision_doc(decision_txt)
                    st.download_button(
                        label="⬇️ Baixar DECISÃO FINAL (.docx)",
                        data=f_dec.getvalue(),
                        file_name="Decisao_AIA_Caso_a_Caso.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        type="primary"
                    )