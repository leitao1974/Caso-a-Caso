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
                # Flash é melhor para documentos longos e extração
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
            # Negrito simples
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
    Atua como Auditor Técnico Sénior em Licenciamento Ambiental.
    Realiza uma TRIANGULAÇÃO DE DADOS rigorosa entre:
    1. SIMULAÇÃO SILiAmb | 2. FORMULÁRIO | 3. PROJETO (Memória Descritiva)
    
    DADOS:
    [SIMULAÇÃO]: {t_sim[:30000]}
    [FORMULÁRIO]: {t_form[:30000]}
    [PROJETO]: {t_proj[:100000]}

    TAREFA:
    Verifica a consistência EXATA de: 
    - Designação e Identificação do Proponente (NIF).
    - Localização administrativa (Freguesia, Artigos Matriciais).
    - Enquadramento (CAEs, Tipologia RJAIA).
    - Números: Áreas (Implantação, Impermeabilização), Capacidades (ton/ano), Gestão de Resíduos.
    
    OUTPUT (Markdown):
    1. "STATUS: [VALIDADO ou INCONSISTENTE]"
    2. "## 1. Resumo Executivo" (2 linhas).
    3. "## 2. Análise de Consistência" (Checklist detalhada com ✅ ou ❌ e valores comparados).
    4. "## 3. Detalhe e Recomendações" (Se houver erros).
    """)

# --- PROMPT 2: DECISÃO (REFINADO PARA O MODELO UACNB) ---
def generate_decision_text(t_sim, t_form, t_proj):
    return get_ai(f"""
    Atua como Técnico Superior da CCDR. O teu objetivo é redigir a "Análise prévia e decisão de sujeição a AIA" com elevado rigor técnico e jurídico.
    
    Usa a informação do PROJETO e FORMULÁRIO.

    CONTEXTO:
    {t_proj[:150000]}
    {t_form[:30000]}

    INSTRUÇÕES DE PREENCHIMENTO (Segue o estilo formal):
    - Não inventes dados. Se não existir, escreve "Não aplicável" ou "A preencher".
    - Na "Fundamentação", sê exaustivo: cita toneladas, metros quadrados, códigos LER e PDM.
    - Usa a terminologia jurídica correta para as tipologias (Ex: "Subalínea ii) da alínea b)...").

    PREENCHE AS SEGUINTES TAGS:

    ### CAMPO_DESIGNACAO
    (Nome do Proponente ou Designação do Estabelecimento)
    
    ### CAMPO_TIPOLOGIA
    (Apenas a referência legal da atividade no Anexo do RJAIA. Ex: "Subalínea ii) da alínea b) do ponto 11 do Anexo II do RJAIA")
    
    ### CAMPO_ENQUADRAMENTO
    (A referência legal da sujeição a análise caso a caso. Ex: "Subalínea ii) da alínea b) do n.º 3 do art.º 1º do RJAIA")
    
    ### CAMPO_LOCALIZACAO
    (Freguesia e Concelho exatos. Ex: "União das freguesias de Monte Redondo e Carreira, concelho de Leiria")
    
    ### CAMPO_AREAS_SENSIVEIS
    (Frase completa. Ex: "O projeto não se localiza em áreas sensíveis identificadas na alínea a) do Artigo 2º do Decreto-Lei nº 152-B/2017.")
    
    ### CAMPO_PROPONENTE
    (Nome da empresa)
    
    ### CAMPO_ENTIDADE_LICENCIADORA
    (Normalmente "CCDRC, I.P." para resíduos, ou a Câmara Municipal se for urbano. Verifica os docs.)
    
    ### CAMPO_AUTORIDADE_AIA
    ("CCDRC, I.P.")

    ### CAMPO_DESCRICAO
    (Texto corrido e detalhado, dividido em parágrafos. Deve incluir:
    1. Localização exata (Estrada, nº, artigo matricial).
    2. Objetivo do pedido (Licenciamento de operações R12, regularização, ampliação?).
    3. Referência a licenças de obras anteriores (nº da licença).
    4. Áreas exatas (área total, coberta, impermeabilizada).
    5. Justificação de não haver alternativas.)

    ### CAMPO_CARATERISTICAS
    (Texto técnico detalhado. Deve incluir:
    1. Quantidades totais de resíduos geridos (ton/ano) discriminado por operação (R12F, R12C).
    2. Discriminação de VFV e Resíduos Perigosos vs Não Perigosos.
    3. Capacidade Instalada vs Capacidade Instantânea de Armazenamento (CIA).
    4. Comparação explicita com os limiares do RJAIA (Ex: "A capacidade é inferior ao limiar de 50t...").
    5. Gestão de efluentes e águas pluviais (separadores de hidrocarbonetos, poço absorvente).)
    
    ### CAMPO_LOCALIZACAO_PROJETO
    (Análise do PDM. Identifica a classe de espaço (Ex: Espaços Urbanos de Baixa Densidade, Área de Estrada). Confirma a compatibilidade com o uso do solo.)
    
    ### CAMPO_IMPACTES
    (Metodologia de avaliação. Identifica fatores avaliados (Socioeconomia, Ar, Ruído, Solo). Conclui sobre a significância (Ex: "impactes pouco significativos", "efeitos cumulativos desprezáveis").)

    ### CAMPO_DECISAO
    (Texto completo da decisão. Ex: "Da análise efetuada, verifica-se que o projeto em análise não é suscetível de provocar impactes significativos no ambiente, pelo que se emite decisão de NÃO SUJEIÇÃO do projeto a procedimento de AIA.")
    
    ### CAMPO_CONDICIONANTES
    (Lista de medidas técnicas. Ex: Monitorização de efluentes, Manutenção de separadores, Impermeabilização de solos, etc.)
    """)

# ==========================================
# --- WORD GENERATORS ---
# ==========================================

def create_validation_doc(text):
    doc = Document()
    
    # Cabeçalho
    section = doc.sections[0]
    header = section.header
    p = header.paragraphs[0]
    p.text = "Relatório de Validação da Instrução"
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    doc.add_heading("Relatório de Validação e Incongruências", 0)
    doc.add_paragraph(f"Data: {datetime.now().strftime('%d/%m/%Y')}")

    if "INCONSISTENTE" in text.upper():
        p = doc.add_paragraph("⚠️ PARECER: EXISTEM INCONGRUÊNCIAS")
        p.runs[0].font.color.rgb = RGBColor(255, 0, 0)
    else:
        p = doc.add_paragraph("✅ PARECER: PROCESSO CONSISTENTE")
        p.runs[0].font.color.rgb = RGBColor(0, 128, 0)
    p.runs[0].bold = True
    
    doc.add_paragraph("---")
    # Remove a primeira linha de status para limpar o texto
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

    # Parser de Tags
    def get_tag(tag):
        m = re.search(f"### {tag}(.*?)###", text, re.DOTALL)
        if not m: m = re.search(f"### {tag}(.*)", text, re.DOTALL)
        return m.group(1).strip() if m else ""

    # Título Institucional
    h = doc.add_heading("Análise prévia e decisão de sujeição a AIA", 0)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("")

    # --- CRIAÇÃO DA TABELA ---
    table = doc.add_table(rows=0, cols=2)
    table.style = 'Table Grid'

    # Função para Cabeçalhos Fundidos (Fundo Cinza/Negrito)
    def add_section_header(txt):
        r = table.add_row()
        c = r.cells[0]
        c.merge(r.cells[1])
        # Podes adicionar shading aqui se quiseres, por agora fica Bold
        run = c.paragraphs[0].add_run(txt)
        run.bold = True
        return r

    # Função para Linhas Identificação (Label | Valor)
    def add_field_row(label, value):
        r = table.add_row()
        r.cells[0].paragraphs[0].add_run(label).bold = True
        r.cells[1].text = value

    # Função para Linhas de Texto Longo (Header Fundido -> Texto Fundido)
    def add_full_text_section(header, content):
        # 1. Cabeçalho da Secção
        add_section_header(header)
        # 2. Conteúdo em baixo (Fundido)
        r = table.add_row()
        c = r.cells[0]
        c.merge(r.cells[1])
        c.text = content

    # --- 1. IDENTIFICAÇÃO ---
    add_section_header("Identificação")
    add_field_row("Designação do projeto", get_tag("CAMPO_DESIGNACAO"))
    add_field_row("Tipologia de Projeto", get_tag("CAMPO_TIPOLOGIA"))
    add_field_row("Enquadramento no RJAIA", get_tag("CAMPO_ENQUADRAMENTO"))
    add_field_row("Localização (freguesia e concelho)", get_tag("CAMPO_LOCALIZACAO"))
    add_field_row("Afetação de áreas sensíveis (alínea a) do artigo 2º do RJAIA)", get_tag("CAMPO_AREAS_SENSIVEIS"))
    add_field_row("Proponente", get_tag("CAMPO_PROPONENTE"))
    add_field_row("Entidade Licenciadora", get_tag("CAMPO_ENTIDADE_LICENCIADORA"))
    add_field_row("Autoridade de AIA", get_tag("CAMPO_AUTORIDADE_AIA"))

    # --- 2. BREVE DESCRIÇÃO (Layout: Cabeçalho -> Texto Full) ---
    add_full_text_section("Breve descrição do projeto", get_tag("CAMPO_DESCRICAO"))

    # --- 3. FUNDAMENTAÇÃO (Layout: Cabeçalho Geral -> Label | Valor Longo) ---
    add_section_header("Fundamentação da decisão")
    add_field_row("Caraterísticas do projeto", get_tag("CAMPO_CARATERISTICAS"))
    add_field_row("Localização do projeto", get_tag("CAMPO_LOCALIZACAO_PROJETO"))
    add_field_row("Características do impacte potencial", get_tag("CAMPO_IMPACTES"))

    # --- 4. DECISÃO (Layout: Cabeçalho -> Texto Full Destaque) ---
    add_section_header("Decisão")
    r = table.add_row()
    c = r.cells[0]
    c.merge(r.cells[1])
    run = c.paragraphs[0].add_run(get_tag("CAMPO_DECISAO"))
    run.bold = True
    run.font.size = Pt(11)

    # --- 5. CONDICIONANTES (Layout: Cabeçalho -> Texto Full) ---
    add_full_text_section("Condicionantes a impor em sede de licenciamento", get_tag("CAMPO_CONDICIONANTES"))

    # --- ASSINATURA ---
    doc.add_paragraph("\n")
    sig_table = doc.add_table(rows=1, cols=2)
    sig_table.allow_autofit = True
    
    # Data à esquerda
    sig_table.rows[0].cells[0].text = "Data: " + datetime.now().strftime('%d/%m/%Y')
    
    # Assinatura à direita
    c_sig = sig_table.rows[0].cells[1]
    p_sig = c_sig.paragraphs[0]
    p_sig.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_sig.add_run("A Presidente da CCDRC,\n\n_______________________").bold = True

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
            
            st.write("🕵️ A analisar (Triangulação)...")
            st.session_state.validation_result = analyze_validation(ts, tf, tp)
            
            st.write("⚖️ A redigir minuta técnica...")
            st.session_state.decision_result = generate_decision_text(ts, tf, tp)
            
            status.update(label="✅ Concluído!", state="complete")

if st.session_state.validation_result and st.session_state.decision_result:
    st.success("Resultados prontos.")
    
    c1, c2 = st.columns(2)
    
    f_val = create_validation_doc(st.session_state.validation_result)
    c1.download_button(
        label="📄 1. Relatório de Validação", 
        data=f_val.getvalue(), 
        file_name="Relatorio_Validacao.docx", 
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        key="btn_val"
    )
    
    f_dec = create_decision_doc(st.session_state.decision_result)
    c2.download_button(
        label="📝 2. Minuta de Decisão", 
        data=f_dec.getvalue(), 
        file_name="Proposta_Decisao.docx", 
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
        type="primary",
        key="btn_dec"
                 )
