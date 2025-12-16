import os
import streamlit as st
import pandas as pd
from datetime import date, datetime
import plotly.express as px
from utils import (
    carregar_dados_dia, salvar_agendamento, remover_agendamento_por_pin, 
    gerar_estrutura_horario, verificar_login, atualizar_senha, 
    recuperar_senha_email, criar_usuario, 
    get_aulas_pendentes_avaliacao, salvar_avaliacao_aluno, 
    carregar_tudo_formatado
)
from utils import conn, hash_senha, atualizar_senha
from admin_view import render_admin_page
from sqlalchemy import text

# ==========================================
# CONFIGURAÇÃO DE CONEXÃO (ROBUSTA)
# ==========================================

# 1. Tenta pegar do Render
db_url = os.environ.get("DATABASE_URL")

# 2. Se não achou, tenta pegar do secrets.toml (Local)
if not db_url:
    if "connections" in st.secrets and "postgres" in st.secrets["connections"]:
        db_url = st.secrets["connections"]["postgres"]["url"]
    else:
        st.error("⚠️ ERRO CRÍTICO: Não encontrei a URL do banco.")
        st.info("Verifique se o arquivo `.streamlit/secrets.toml` existe e tem a seção `[connections.postgres]`.")
        st.stop()

# 3. Correção do bug postgres://
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# 4. Conecta
conn = st.connection("postgres", type="sql", url=db_url)

st.set_page_config(page_title="Agenda Naalli", page_icon="🏋️‍♀️", layout="wide")

# --- GERENCIAMENTO DE SESSÃO ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.view = "login"

# --- HELPER: FORMATAR NOME ---
def formatar_nome_curto(nome_completo):
    if not nome_completo: return ""
    partes = nome_completo.strip().split()
    if len(partes) >= 2:
        return f"{partes[0]} {partes[1]}"
    return partes[0]

# --- TELA DE LOGIN ---
def login_screen():
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.header("🔐 Agenda Naalli")
        st.write("Faça login para agendar.")
        
        email = st.text_input("E-mail")
        senha = st.text_input("Senha", type="password")
        
        col_entrar, col_esqueceu = st.columns([1,1])
        
        if col_entrar.button("Entrar", type="primary", use_container_width=True):
            user = verificar_login(email, senha)
            if user:
                st.session_state.user = user
                st.session_state.logged_in = True
                if user.get('mudar_senha', False):
                    st.session_state.view = "force_change"
                else:
                    st.session_state.view = "main"
                st.rerun()
            else:
                st.error("E-mail ou senha inválidos.")
        
        if col_esqueceu.button("Esqueci a senha"):
            st.session_state.view = "recovery"
            st.rerun()
            
        st.markdown("---")
        st.caption("Primeiro acesso? Use o login fornecido pela recepção.")

# --- TELA DE RECUPERAÇÃO ---
def recovery_screen():
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.header("🔑 Recuperar Senha")
        st.write("Digite seu e-mail. Enviaremos uma senha temporária.")
        email = st.text_input("Seu E-mail Cadastrado")
        
        if st.button("Enviar E-mail de Recuperação", type="primary"):
            sucesso, msg = recuperar_senha_email(email)
            if sucesso:
                st.success(msg)
                st.info("Verifique seu e-mail e use a senha temporária para logar.")
            else:
                st.error(msg)
        
        if st.button("Voltar ao Login"):
            st.session_state.view = "login"
            st.rerun()

# --- TELA DE TROCA OBRIGATÓRIA DE SENHA ---
def force_change_screen():
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.warning("⚠️ Segurança: Você precisa alterar sua senha no primeiro acesso.")
        nova_senha = st.text_input("Nova Senha", type="password")
        confirma_senha = st.text_input("Confirme a Nova Senha", type="password")
        
        if st.button("Atualizar Senha", type="primary"):
            if nova_senha == confirma_senha and len(nova_senha) > 3:
                atualizar_senha(st.session_state.user['email'], nova_senha)
                st.success("Senha atualizada! Redirecionando...")
                st.session_state.user['mudar_senha'] = False
                st.session_state.view = "main"
                st.rerun()
            else:
                st.error("As senhas não conferem ou são muito curtas.")

# --- APLICAÇÃO PRINCIPAL ---
def main_app():
    # --- HEADER & LOGOUT ---
    col_t, col_l = st.columns([8, 1]) 
    with col_t:
        col1, col2 = st.columns([1, 5], vertical_alignment="center")
        with col1:
            try:
                st.image("logonaalli.jpg", width=80) 
            except:
                st.write("🏋️‍♀️") 
        with col2:
            st.title(f"Olá, {formatar_nome_curto(st.session_state.user['nome'])}! 👋")
    with col_l:
        st.write("") 
        if st.button("Sair", type="secondary", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user = None
            st.session_state.view = "login"
            st.rerun()

    # =========================================================
    # LÓGICA DE ABAS DINÂMICAS (Admin vê 4 abas, Aluno vê 3)
    # =========================================================
    lista_abas = ["📅 Agendamento", "⭐ Avaliação", "📊 Meu Painel"]
    
    # Adiciona a aba extra apenas se for admin
    if st.session_state.user['tipo'] == 'admin':
        lista_abas.append("🔐 Admin")
    
    tabs = st.tabs(lista_abas)

    # Distribui as abas em variáveis
    tab_agenda = tabs[0]
    tab_avaliacao = tabs[1]
    tab_painel = tabs[2]
    
    # Se tiver a 4ª aba, pega ela, senão define como None
    tab_admin = tabs[3] if len(tabs) > 3 else None

    # ---------------------------------------------------------
    # ABA 1: AGENDAMENTO
    # ---------------------------------------------------------
    with tab_agenda:
        c1, c2 = st.columns(2)
        with c1:
            data_sel = st.date_input("Data:", date.today(), format="DD/MM/YYYY")
            data_str = data_sel.strftime("%d/%m/%Y")
        
        dia_semana = data_sel.weekday() # 5 = Sábado, 6 = Domingo
        
        if dia_semana == 6:
            st.error("🚫 A academia não abre aos Domingos.")
        else:
            if dia_semana == 5:
                horarios = [f"{h:02d}:00" for h in range(8, 13)] 
                aviso_sabado = " (Sábado: 08h às 12h)"
            else:
                horarios = [f"{h:02d}:00" for h in range(6, 21)]
                aviso_sabado = ""

            with c2:
                hora_sel = st.selectbox(f"Horário{aviso_sabado}:", horarios)

            DIAS_PT = {0: "Segunda-feira", 1: "Terça-feira", 2: "Quarta-feira", 3: "Quinta-feira", 4: "Sexta-feira", 5: "Sábado", 6: "Domingo"}
            nome_dia = DIAS_PT[dia_semana]
            
            st.markdown(f"""
                <div style="background-color: #e8f4f8; padding: 15px; border-radius: 10px; text-align: center; margin: 20px 0; border: 1px solid #b8daff; color: #004085;">
                    <span style="font-size: 20px;">📅 <b>{nome_dia}, {data_str}</b></span>
                    &nbsp;|&nbsp;
                    <span style="font-size: 20px;">⏰ <b>{hora_sel}</b></span>
                </div>
            """, unsafe_allow_html=True)

            df_dia = carregar_dados_dia(data_str)
            agendamentos_horario = df_dia[df_dia['Horario'] == hora_sel] if not df_dia.empty else pd.DataFrame()

            st.divider()
            todas_vagas = gerar_estrutura_horario(hora_sel)
            
            grupos = {
                "🏋️‍♂️ Musculação": [v for v in todas_vagas if v['Tipo'] == 'Treino'],
                "🏃 Esteiras": [v for v in todas_vagas if v['Tipo'] == 'Esteira'],
                "🚴 Elípticos": [v for v in todas_vagas if v['Tipo'] == 'Elíptico']
            }

            for titulo, vagas in grupos.items():
                if vagas:
                    st.markdown(f"### {titulo}")
                    cols = st.columns(4)
                    for idx, vaga in enumerate(vagas):
                        num, tipo = vaga['Numero'], vaga['Tipo']
                        ocupante_nome_full = None
                        
                        if not agendamentos_horario.empty:
                            filtro = agendamentos_horario[(agendamentos_horario['Numero'] == num) & (agendamentos_horario['Tipo'] == tipo)]
                            if not filtro.empty: 
                                ocupante_nome_full = filtro.iloc[0]['Nome']
                        
                        with cols[idx % 4]:
                            if ocupante_nome_full:
                                nome_exibicao = formatar_nome_curto(ocupante_nome_full)
                                st.warning(f"🔒 {num} - {nome_exibicao}")
                                
                                if ocupante_nome_full == st.session_state.user['nome']:
                                    if st.button("Liberar", key=f"lib_{tipo}_{num}"):
                                        remover_agendamento_por_pin(data_str, hora_sel, num, tipo, "", is_admin=True)
                                        st.rerun()
                            else:
                                st.success(f"✅ {num} - Livre")
                                if st.button("Reservar", key=f"res_{tipo}_{num}", type="primary", use_container_width=True):
                                    salvar_agendamento(data_str, hora_sel, num, tipo, st.session_state.user['nome'], "LOGGED_USER")
                                    st.success("Agendado!")
                                    st.rerun()
                    st.markdown("---")

    # ---------------------------------------------------------
    # ABA 2: AVALIAÇÃO
    # ---------------------------------------------------------
    with tab_avaliacao:
        if st.session_state.user['tipo'] == 'admin':
            st.info("Administradores não realizam avaliações de treino.")
        else:
            st.subheader("⭐ Avalie seu Treino")
            st.caption("Ajude a Naalli a melhorar. Avalie as aulas que você já concluiu.")
            
            aulas_pendentes = get_aulas_pendentes_avaliacao(st.session_state.user['nome'])
            
            if aulas_pendentes:
                opcoes = {f"{a['Data']} - {a['Horario']} | {a['Tipo']}": a for a in aulas_pendentes}
                escolha = st.selectbox("Selecione a aula para avaliar:", list(opcoes.keys()), key="sel_aval")
                dados_aula = opcoes[escolha]
                
                with st.form("form_avaliacao"):
                    c_stars, c_text = st.columns([1, 2])
                    with c_stars:
                        st.write("Sua nota:")
                        stars = st.feedback("stars")
                    with c_text:
                        comentario = st.text_area("Comentário (Opcional):", placeholder="O que achou do treino?")
                    
                    submit_aval = st.form_submit_button("Enviar Avaliação", type="primary")
                    
                    if submit_aval:
                        if stars is not None:
                            salvar_avaliacao_aluno(dados_aula['doc_id'], st.session_state.user['nome'], dados_aula['Data'], dados_aula['Tipo'], stars+1, comentario)
                            st.success("Obrigado pelo feedback!")
                            st.rerun()
                        else:
                            st.warning("Por favor, selecione as estrelas.")
            else:
                st.info("🎉 Você não tem avaliações pendentes no momento.")

    # ---------------------------------------------------------
    # ABA 3: MEU PAINEL
    # ---------------------------------------------------------
    with tab_painel:
        if st.session_state.user['tipo'] == 'admin':
            st.info("👉 Use a aba 'Admin' para ver os dados gerais da academia.")
        else:
            st.subheader("📊 Seu Painel de Atleta")
            
            df_full = carregar_tudo_formatado()
            nome_user = st.session_state.user['nome']
            
            if not df_full.empty:
                df_aluno = df_full[df_full['Nome'] == nome_user].sort_values('Data_dt', ascending=False)
                
                if not df_aluno.empty:
                    total_vida = len(df_aluno)
                    primeira_vez = df_aluno['Data_dt'].min().strftime('%d/%m/%Y')
                    ultima_vez_dt = df_aluno['Data_dt'].max()
                    ultima_vez = ultima_vez_dt.strftime('%d/%m/%Y')
                    
                    dias_sem_vir = (datetime.now() - ultima_vez_dt).days
                    if dias_sem_vir <= 7:
                        status_txt = "🟢 Ativo"
                        status_msg = "Você está mandando bem!"
                    elif dias_sem_vir <= 30:
                        status_txt = "🟡 Atenção"
                        status_msg = f"Faz {dias_sem_vir} dias que não te vemos."
                    else:
                        status_txt = "🔴 Inativo"
                        status_msg = "Vamos voltar a treinar?"

                    with st.container(border=True):
                        c_head1, c_head2 = st.columns([3, 1])
                        c_head1.markdown(f"### Status: {status_txt}")
                        c_head1.caption(status_msg)
                        
                        m1, m2, m3, m4 = st.columns(4)
                        m1.metric("Total Check-ins", total_vida)
                        m2.metric("Último Treino", ultima_vez)
                        m3.metric("Primeiro Treino", primeira_vez)
                        
                        semanas_ativo = ((df_aluno['Data_dt'].max() - df_aluno['Data_dt'].min()).days / 7) or 1
                        media_semanal = round(total_vida / semanas_ativo, 1)
                        m4.metric("Média / Semana", media_semanal)
                        
                        st.divider()
                        
                        col_chart1, col_chart2 = st.columns(2)
                        with col_chart1:
                            st.markdown("**Sua Modalidade Favorita**")
                            if not df_aluno.empty:
                                fig_pizza = px.pie(df_aluno, names='Tipo', hole=0.5, height=250)
                                fig_pizza.update_layout(margin=dict(t=0, b=0, l=0, r=0), showlegend=False)
                                st.plotly_chart(fig_pizza, use_container_width=True)
                                
                        with col_chart2:
                            st.markdown("**Seus Últimos Treinos**")
                            st.dataframe(
                                df_aluno[['Data', 'Horario', 'Tipo']].head(5), 
                                hide_index=True, 
                                use_container_width=True
                            )
                else:
                    st.info("Agende seu primeiro treino para ver suas estatísticas aqui!")
            else:
                st.info("Nenhum dado encontrado.")

# ---------------------------------------------------------
    # ABA 4: ADMIN (Layout Vertical Melhorado)
    # ---------------------------------------------------------
    if tab_admin:
        with tab_admin:
            st.subheader("🔐 Área de Gestão")
            st.caption("Selecione uma ação administrativa abaixo.")
            st.write("<br>", unsafe_allow_html=True) # Um pouco de espaço

            # --- BLOCO 1: DASHBOARD GERAL ---
            with st.container(border=True):
                # Cria colunas dentro do container para alinhar texto e botão
                c_txt, c_btn = st.columns([3, 1])
                with c_txt:
                    st.markdown("### 📊 Dashboard e KPIs")
                    st.write("Visualize gráficos de frequência, horários de pico e métricas gerais da academia.")
                with c_btn:
                    # Centraliza o botão verticalmente usando espaços em branco
                    st.write("") 
                    st.write("") 
                    if st.button("Acessar Painel ➡️", type="primary", use_container_width=True):
                        st.session_state.view = "admin"
                        st.rerun()

            st.write("<br>", unsafe_allow_html=True) # Espaço entre os blocos

            # --- BLOCO 2: CADASTRO RÁPIDO ---
            with st.container(border=True):
                st.markdown("### 👤 Cadastro Rápido de Aluno")
                st.caption("Cria um novo usuário com a senha padrão: **mudar123**")
                
                with st.form("form_cadastro_rapido", border=False):
                    # Coloca os campos lado a lado para economizar altura
                    c_email, c_nome = st.columns(2)
                    with c_email:
                        new_email = st.text_input("E-mail do Aluno")
                    with c_nome:
                        new_nome = st.text_input("Nome Completo")
                    
                    st.write("") # Espacinho antes do botão
                    submit_cad = st.form_submit_button("Concluir Cadastro", use_container_width=True)
                    
                    if submit_cad:
                        # Verifica se os campos foram preenchidos
                        if new_email and new_nome:
                            if criar_usuario(new_email, new_nome, "mudar123"):
                                # st.toast é uma notificação mais elegante que some sozinha
                                st.toast(f"✅ Usuário **{new_nome}** criado com sucesso!", icon="🎉") 
                            else:
                                st.error("Erro: Este e-mail já está cadastrado no sistema.")
                        else:
                            st.warning("Preencha o e-mail e o nome.")

# --- ROTEADOR ---
if st.session_state.view == "login":
    login_screen()
elif st.session_state.view == "recovery":
    recovery_screen()
elif st.session_state.view == "force_change":
    force_change_screen()
elif st.session_state.view == "admin":
    # Validação de segurança extra
    if st.session_state.user and st.session_state.user['tipo'] == 'admin':
        render_admin_page()
    else:
        st.session_state.view = "main"
        st.rerun()
elif st.session_state.view == "main":
    if st.session_state.logged_in:
        main_app()
    else:
        st.session_state.view = "login"
        st.rerun()