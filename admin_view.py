import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import plotly.express as px
from langchain_google_genai import ChatGoogleGenerativeAI
from utils import carregar_tudo_formatado, carregar_avaliacoes_formatado, SENHA_ADMIN

def render_admin_page():
    if st.button("⬅️ Voltar à Agenda"):
        st.session_state.page = "main"
        st.rerun()

    st.title("📊 Gestão e Inteligência")
    
    # --- AUTO-UNLOCK (SOLICITAÇÃO 4: Acesso sem senha se já for Admin) ---
    if st.session_state.user and st.session_state.user.get('tipo') == 'admin':
        st.session_state.admin_unlocked = True
    
    # Fallback para acesso direto (Login manual no painel)
    if "admin_unlocked" not in st.session_state:
        st.session_state.admin_unlocked = False

    if not st.session_state.admin_unlocked:
        senha = st.text_input("Senha de acesso", type="password")
        if st.button("Entrar no Painel"):
            if senha == SENHA_ADMIN:
                st.session_state.admin_unlocked = True
                st.rerun()
            else:
                st.error("Acesso negado.")
        return

    # --- DADOS ---
    df_full = carregar_tudo_formatado()
    df_aval = carregar_avaliacoes_formatado() # Carrega avaliações para a aba nova
    
    # --- SIDEBAR DE FILTROS ---
    with st.sidebar:
        st.header("🔍 Filtros Avançados")
        
        periodo = st.radio("Período (Gráficos Gerais):", ["Esta Semana", "Este Mês", "Últimos 3 Meses", "Todo o Histórico", "Personalizado"])
        hoje = date.today()
        
        if periodo == "Esta Semana":
            inicio = hoje - timedelta(days=hoje.weekday())
            fim = hoje + timedelta(days=6)
        elif periodo == "Este Mês":
            inicio = hoje.replace(day=1)
            prox_mes = inicio.replace(day=28) + timedelta(days=4)
            fim = prox_mes - timedelta(days=prox_mes.day)
        elif periodo == "Últimos 3 Meses":
            fim = hoje
            inicio = hoje - timedelta(days=90)
        elif periodo == "Personalizado":
            c1, c2 = st.columns(2)
            inicio = c1.date_input("Início", hoje - timedelta(days=7), format="DD/MM/YYYY")
            fim = c2.date_input("Fim", hoje, format="DD/MM/YYYY")
        else:
            if not df_full.empty:
                inicio = df_full['Data_dt'].min().date()
                fim = df_full['Data_dt'].max().date()
            else:
                inicio, fim = hoje, hoje
        
        st.divider()
        todos_tipos = df_full['Tipo'].unique().tolist() if not df_full.empty else []
        tipos_sel = st.multiselect("Filtrar Modalidades:", todos_tipos, default=todos_tipos)

        st.divider()
        if "GOOGLE_API_KEY" in st.secrets:
            gemini_key = st.secrets["GOOGLE_API_KEY"]
            st.success("✨ IA Conectada (v2.5)")
        else:
            gemini_key = st.text_input("Chave da API Google (IA)", type="password")
        
        # Botão sair do painel
        if st.button("🔒 Bloquear Painel"):
            st.session_state.admin_unlocked = False
            st.session_state.page = "main"
            st.rerun()

    # --- PROCESSAMENTO DOS FILTROS ---
    inicio_ts = pd.to_datetime(inicio)
    fim_ts = pd.to_datetime(fim) + timedelta(days=1) - timedelta(seconds=1)
    
    DIAS_PT = {0: "Segunda", 1: "Terça", 2: "Quarta", 3: "Quinta", 4: "Sexta", 5: "Sábado", 6: "Domingo"}
    DIAS_CURTOS = {0: "Seg", 1: "Ter", 2: "Qua", 3: "Qui", 4: "Sex", 5: "Sáb", 6: "Dom"}
    
    ordem_cronologica_dias = []
    
    if not df_full.empty:
        mask = (df_full['Data_dt'] >= inicio_ts) & (df_full['Data_dt'] <= fim_ts) & (df_full['Tipo'].isin(tipos_sel))
        df_filtered = df_full.loc[mask].copy()
        
        df_filtered['Dia_Semana_Int'] = df_filtered['Data_dt'].dt.dayofweek
        df_filtered['Dia_Visual'] = df_filtered['Dia_Semana_Int'].map(DIAS_CURTOS) + ", " + df_filtered['Data_dt'].dt.strftime('%d/%m')
        df_filtered['Nome_Dia_Semana'] = df_filtered['Dia_Semana_Int'].map(DIAS_PT)
        
        ordem_cronologica_dias = df_filtered.sort_values('Data_dt')['Dia_Visual'].unique().tolist()
        df_filtered = df_filtered.sort_values('Data_dt')
    else:
        df_filtered = pd.DataFrame(columns=df_full.columns)

    # =========================================================
    # ORGANIZAÇÃO EM ABAS (NOVO RECURSO)
    # =========================================================
    tab_dashboard, tab_qualidade = st.tabs(["📈 Dashboard & IA", "⭐ Qualidade & Feedback"])

    # ---------------------------------------------------------
    # ABA 1: DASHBOARD GERAL (O código original preservado aqui)
    # ---------------------------------------------------------
    with tab_dashboard:
        st.subheader(f"Visão Geral ({inicio.strftime('%d/%m')} a {fim.strftime('%d/%m')})")
        
        k1, k2, k3 = st.columns(3)
        total_agendamentos = len(df_filtered)
        if not df_filtered.empty:
            alunos_unicos = df_filtered['Nome'].nunique()
            horario_pico = df_filtered['Horario'].mode()[0]
        else:
            alunos_unicos = 0; horario_pico = "-"

        k1.metric("Total de Agendamentos", total_agendamentos)
        k2.metric("Alunos Ativos", alunos_unicos)
        k3.metric("Horário de Pico", horario_pico)

        st.divider()

        # GRÁFICOS
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.markdown("##### 📈 Evolução (Dia a Dia)")
            if not df_filtered.empty:
                df_line = df_filtered.groupby('Dia_Visual', sort=False).size().reset_index(name='Qtd')
                fig_line = px.line(df_line, x='Dia_Visual', y='Qtd', markers=True, labels={'Dia_Visual': 'Data', 'Qtd': 'Treinos'})
                fig_line.update_xaxes(categoryorder='array', categoryarray=ordem_cronologica_dias)
                st.plotly_chart(fig_line, use_container_width=True)
            else:
                st.info("Sem dados.")

        with col_g2:
            st.markdown("##### 📅 Volume por Dia da Semana")
            if not df_filtered.empty:
                df_semana = df_filtered.groupby(['Dia_Semana_Int', 'Nome_Dia_Semana']).size().reset_index(name='Qtd')
                df_semana = df_semana.sort_values('Dia_Semana_Int')
                fig_bar_sem = px.bar(df_semana, x='Nome_Dia_Semana', y='Qtd', text='Qtd', title="")
                st.plotly_chart(fig_bar_sem, use_container_width=True)
            else:
                st.info("Sem dados.")

        col_g3, col_g4 = st.columns(2)
        with col_g3:
            st.markdown("##### 🕒 Horários vs Modalidade")
            if not df_filtered.empty:
                df_stack = df_filtered.groupby(['Horario', 'Tipo']).size().reset_index(name='Qtd')
                fig_stack = px.bar(df_stack, x='Horario', y='Qtd', color='Tipo', barmode='stack')
                fig_stack.update_xaxes(categoryorder='category ascending')
                st.plotly_chart(fig_stack, use_container_width=True)
            else:
                st.info("Sem dados.")

        with col_g4:
            st.markdown("##### 🔥 Mapa de Calor")
            if not df_filtered.empty:
                df_heat = df_filtered.groupby(['Dia_Visual', 'Horario']).size().reset_index(name='Ocupacao')
                fig_heat = px.density_heatmap(df_heat, x='Horario', y='Dia_Visual', z='Ocupacao', color_continuous_scale='Viridis')
                fig_heat.update_yaxes(categoryorder='array', categoryarray=ordem_cronologica_dias)
                fig_heat.update_xaxes(categoryorder='category ascending')
                st.plotly_chart(fig_heat, use_container_width=True)
            else:
                st.info("Sem dados.")

        st.divider()

        # RANKING E RAIO-X
        st.subheader("🏆 Desempenho e Ficha do Aluno")
        c_rank, c_busca = st.columns([1, 2])
        
        with c_rank:
            st.markdown("##### Ranking (Top 10)")
            if not df_filtered.empty:
                df_alunos = df_filtered['Nome'].value_counts().head(10).reset_index()
                df_alunos.columns = ['Nome', 'Agendamentos']
                fig_top = px.bar(df_alunos, x='Agendamentos', y='Nome', orientation='h', text='Agendamentos')
                fig_top.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=False, height=400)
                st.plotly_chart(fig_top, use_container_width=True)
            else:
                st.info("Sem dados.")

        with c_busca:
            st.markdown("##### 🔎 Raio-X Completo")
            if not df_full.empty:
                lista_alunos = sorted(df_full['Nome'].unique().tolist())
                aluno_sel = st.selectbox("Selecione o Aluno para ver a ficha:", ["Selecione..."] + lista_alunos)
                
                if aluno_sel != "Selecione...":
                    df_aluno = df_full[df_full['Nome'] == aluno_sel].sort_values('Data_dt', ascending=False)
                    if not df_aluno.empty:
                        total_vida = len(df_aluno)
                        primeira_vez = df_aluno['Data_dt'].min().strftime('%d/%m/%Y')
                        ultima_vez_dt = df_aluno['Data_dt'].max()
                        ultima_vez = ultima_vez_dt.strftime('%d/%m/%Y')
                        
                        dias_sem_vir = (datetime.now() - ultima_vez_dt).days
                        if dias_sem_vir <= 7: status, cor = "🟢 Ativo", "green"
                        elif dias_sem_vir <= 30: status, cor = "🟡 Atenção", "orange"
                        else: status, cor = "🔴 Inativo", "red"

                        with st.container(border=True):
                            c_h1, c_h2 = st.columns([3, 1])
                            c_h1.markdown(f"## 👤 {aluno_sel}")
                            c_h2.markdown(f"### :{cor}[{status}]")
                            st.divider()
                            m1, m2, m3, m4 = st.columns(4)
                            m1.metric("Total", total_vida)
                            m2.metric("Último", ultima_vez)
                            m3.metric("Início", primeira_vez)
                            semanas = ((df_aluno['Data_dt'].max() - df_aluno['Data_dt'].min()).days / 7) or 1
                            m4.metric("Média/Semana", round(total_vida/semanas, 1))
                            st.divider()
                            c_pizza, c_hist = st.columns([1, 1])
                            with c_pizza:
                                st.caption("Preferência")
                                fig_pizza = px.pie(df_aluno, names='Tipo', hole=0.4, height=250)
                                fig_pizza.update_layout(margin=dict(t=0, b=0, l=0, r=0), showlegend=False)
                                st.plotly_chart(fig_pizza, use_container_width=True)
                            with c_hist:
                                st.caption("Histórico Recente")
                                st.dataframe(df_aluno[['Data', 'Horario', 'Tipo']].head(5), hide_index=True, use_container_width=True)

        st.divider()

        # IA ASSISTANT (EXPANDIDA)
        st.subheader("✨ Naalli AI Assistant (Gemini 2.5)")
        
        if df_filtered.empty:
            st.warning("Sem dados.")
        elif not gemini_key:
            st.warning("⚠️ Insira a API Key.")
        else:
            sugestoes = [
                "Quem são os alunos com risco de evasão (não vêm há 10 dias)?",
                "Qual o horário mais crítico que precisamos abrir mais vagas urgente?",
                "Faça um comparativo detalhado: Manhã (6-9h) vs Noite (18-21h).",
                "Liste os alunos que SÓ fazem esteira e nunca musculação.",
                "Qual dia da semana tem o pior movimento? Sugira uma ação para melhorar.",
                "Identifique padrões: Existe algum horário que sempre lota na segunda-feira?",
                "Quais são os 5 alunos mais fiéis (assíduos) do último mês?",
                "O uso do Elíptico está baixo? Vale a pena trocar por outra Esteira?",
                "Analise a tendência: Estamos crescendo ou diminuindo em relação à semana anterior?",
                "Crie um resumo executivo do desempenho da academia nesta semana."
            ]
            
            selection = st.pills("Análises Sugeridas:", sugestoes)
            prompt_input = st.chat_input("Pergunte sobre os dados...", key="chat_input")
            
            texto_final = prompt_input if prompt_input else selection
            
            if texto_final:
                with st.spinner(f"Analisando: '{texto_final}'..."):
                    try:
                        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=gemini_key, temperature=0.3)
                        cols_to_send = ['Data', 'Horario', 'Tipo', 'Nome']
                        csv_data = df_filtered[cols_to_send].to_csv(index=False)
                        
                        full_prompt = f"""
                        Atue como um consultor de negócios de academia (que não é franquia e é mais voltada para ginástica). Analise os dados (CSV):
                        {csv_data}
                        PERGUNTA: {texto_final}
                        Diretrizes: 1. Use dados concretos (cite números). 2. Seja propositivo. 3. PT-BR.
                        """
                        response = llm.invoke(full_prompt)
                        with st.chat_message("assistant", avatar="🤖"):
                            st.markdown(response.content)
                    except Exception as e:
                        st.error(f"Erro IA: {e}")

    # ---------------------------------------------------------
    # ABA 2: QUALIDADE & FEEDBACK (NOVO DASHBOARD DE AVALIAÇÕES)
    # ---------------------------------------------------------
    with tab_qualidade:
        st.subheader("⭐ Satisfação e Feedback dos Alunos")
        
        if not df_aval.empty:
            # Métricas de Qualidade (NPS Simulado)
            media_nota = df_aval['Nota'].mean()
            total_reviews = len(df_aval)
            promotores = len(df_aval[df_aval['Nota'] == 5])
            
            ka1, ka2, ka3 = st.columns(3)
            ka1.metric("Nota Média Geral (1-5)", f"{media_nota:.1f}")
            ka2.metric("Total de Avaliações", total_reviews)
            ka3.metric("Fãs (Nota 5)", promotores)
            
            st.divider()
            
            c_bar, c_com = st.columns([1, 2])
            
            with c_bar:
                st.markdown("##### Distribuição das Notas")
                count_notas = df_aval['Nota'].value_counts().reset_index()
                count_notas.columns = ['Nota', 'Qtd']
                # Ordena notas de 5 a 1
                count_notas = count_notas.sort_values('Nota', ascending=False)
                fig_notas = px.bar(count_notas, x='Nota', y='Qtd', color='Nota', color_discrete_sequence=px.colors.qualitative.Prism)
                fig_notas.update_layout(xaxis=dict(tickmode='linear', tick0=1, dtick=1))
                st.plotly_chart(fig_notas, use_container_width=True)
                
            with c_com:
                st.markdown("##### Últimos Comentários")
                # Filtra apenas quem deixou comentário
                df_coments = df_aval[df_aval['Comentario'] != ""].sort_values('DataAvaliacao', ascending=False)
                
                if not df_coments.empty:
                    # Tabela interativa
                    st.dataframe(
                        df_coments[['DataAula', 'NomeAluno', 'Nota', 'Comentario', 'Modalidade']], 
                        hide_index=True, 
                        use_container_width=True,
                        column_config={
                            "Nota": st.column_config.NumberColumn("Nota", format="%d ⭐")
                        }
                    )
                else:
                    st.info("Nenhum comentário de texto registrado, apenas notas.")
        else:
            st.info("Ainda não há avaliações registradas no sistema. Incentive seus alunos a avaliar os treinos!")
        st.divider()
        st.subheader("🔍 Análise Profunda de Qualidade")

        # Prepara dados de data para gráficos temporais
        # Converte a string 'DataAvaliacao' para objeto datetime real
        df_aval['Data_dt'] = pd.to_datetime(df_aval['DataAvaliacao'], errors='coerce')
        df_aval['Dia'] = df_aval['Data_dt'].dt.strftime('%d/%m') # Formato visual 13/12

        col_q1, col_q2 = st.columns(2)

        # GRÁFICO 1: TENDÊNCIA TEMPORAL
        with col_q1:
            st.markdown("##### 📈 Evolução da Nota Média (Dia a Dia)")
            if not df_aval.empty:
                # Agrupa por dia e tira a média da nota
                df_evolucao = df_aval.groupby('Dia')['Nota'].mean().reset_index()
                
                fig_evol = px.line(df_evolucao, x='Dia', y='Nota', markers=True, 
                                    range_y=[0, 5.5], # Fixa o eixo Y de 0 a 5.5 para visualização real
                                    title="A qualidade está subindo ou descendo?")
                
                # Adiciona uma linha de meta (Ex: nota 4.5 é a meta)
                fig_evol.add_hline(y=4.5, line_dash="dot", line_color="green", 
                                    annotation_text="Meta de Excelência (4.5)")
                
                st.plotly_chart(fig_evol, use_container_width=True)
            else:
                st.info("Dados insuficientes para gerar tendência.")

        # GRÁFICO 2: RANKING POR MODALIDADE
        with col_q2:
            st.markdown("##### 🏆 Satisfação por Equipamento")
            if not df_aval.empty:
                # Agrupa por modalidade e calcula média e quantidade
                df_mod = df_aval.groupby('Modalidade')['Nota'].agg(['mean', 'count']).reset_index()
                df_mod.columns = ['Modalidade', 'Nota Média', 'Qtd Avaliações']
                
                # Gráfico de barras colorido pela nota (Vermelho=Ruim, Verde=Bom)
                fig_mod = px.bar(df_mod, x='Modalidade', y='Nota Média', 
                                    color='Nota Média',
                                    range_y=[0, 5.5],
                                    text_auto='.1f', # Mostra o valor em cima da barra com 1 casa decimal
                                    color_continuous_scale='RdYlGn', # Escala Red-Yellow-Green
                                    hover_data=['Qtd Avaliações']) # Mostra quantos votaram ao passar o mouse
                
                fig_mod.update_layout(coloraxis_showscale=False) # Esconde a barra de cores lateral
                st.plotly_chart(fig_mod, use_container_width=True)
            else:
                st.info("Sem dados de modalidade.")