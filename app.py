# Adicionar o argumento t_leg
def analyze_validation(t_sim, t_form, t_proj, t_leg):
    legislacao_str = ", ".join(LEGISLATION_DB.keys())
    return get_ai(f"""
    Atua como PERITO AUDITOR AMBIENTAL.
    
    CONTEXTO LEGAL GERAL:
    Utiliza os limiares do RJAIA (Anexos I, II, III, IV, V) e legislação conexa: {legislacao_str}.

    CONTEXTO LEGAL ESPECÍFICO (PRIORITÁRIO PARA LOCALIZAÇÃO):
    {t_leg[:30000]} 

    DADOS DO PROJETO:
    {t_sim[:25000]}
    {t_form[:25000]}
    {t_proj[:80000]}

    TAREFA:
    1. Audita a consistência dos dados.
    2. Verifica o enquadramento legal RJAIA.
    3. CRUZAMENTO: Verifica se o projeto cumpre as regras específicas carregadas em 'CONTEXTO LEGAL ESPECÍFICO' (ex: índices do PDM, interdições de uso do solo, distâncias regulamentares).
    
    OUTPUT (Markdown):
    1. "STATUS: [VALIDADO ou INCONSISTENTE]"
    2. "## 1. Resumo Executivo"
    3. "## 2. Auditoria de Conformidade e Restrições Locais" (Análise explicita sobre a legislação específica se aplicável).
    4. "## 3. Enquadramento Legal e Limiares".
    """)
