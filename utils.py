import os
import pandas as pd
from datetime import datetime
import hashlib
import smtplib
from email.mime.text import MIMEText
import streamlit as st
import random
import string
from sqlalchemy import text

# ==========================================
# 0. FUNÇÃO DE CONEXÃO ROBUSTA (UNIVERSAL)
# ==========================================
def get_db_connection():
    """
    Função inteligente que busca a credencial no Render (Variável de Ambiente)
    ou no Local (secrets.toml), corrigindo bugs do SQLAlchemy.
    """
    # 1. Tenta pegar do Render (Variável de Ambiente)
    db_url = os.environ.get("DATABASE_URL")

    # 2. Se não achou (estamos Local), tenta pegar do secrets.toml
    if not db_url:
        try:
            # Tenta pegar com o nome 'postgres' OU 'postgresql' para garantir
            if "connections" in st.secrets:
                if "postgres" in st.secrets["connections"]:
                    db_url = st.secrets["connections"]["postgres"]["url"]
                elif "postgresql" in st.secrets["connections"]:
                    db_url = st.secrets["connections"]["postgresql"]["url"]
        except:
            # Se der erro ao ler secrets, ignoramos por enquanto
            pass
    
    # 3. Correção do bug do SQLAlchemy (postgres:// -> postgresql://)
    # O Render/Neon costuma mandar postgres://, mas o Python exige postgresql://
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    # 4. Verifica se a URL foi encontrada antes de conectar
    if not db_url:
        # Se chegamos aqui sem URL, o app vai quebrar, então avisamos
        st.error("Erro Crítico: Não foi possível encontrar a URL do Banco de Dados.")
        st.stop()

    # 5. Retorna a conexão configurada
    return st.connection("postgres", type="sql", url=db_url)

# ==========================================
# CONFIGURAÇÃO GLOBAL
# ==========================================

# AQUI ESTAVA O ERRO: Agora usamos a função robusta para definir a conexão global
conn = get_db_connection()

# Constantes
SENHA_ADMIN = "naalli2025" 
DEFAULT_ADMIN_EMAIL = "admin@naalli.com"
DEFAULT_ADMIN_PASS = "mudar123"

# ==========================================
# 1. FUNÇÕES DE SEGURANÇA E USUÁRIOS
# ==========================================

def hash_senha(senha):
    return hashlib.sha256(senha.encode()).hexdigest()

def inicializar_banco():
    """Cria as tabelas no Neon se não existirem."""
    try:
        with conn.session as s:
            # Tabela Usuários
            s.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    email TEXT PRIMARY KEY,
                    nome TEXT,
                    senha TEXT,
                    mudar_senha BOOLEAN,
                    tipo TEXT
                );
            """))
            
            # Tabela Agendamentos
            s.execute(text("""
                CREATE TABLE IF NOT EXISTS agendamentos (
                    id SERIAL PRIMARY KEY,
                    data TEXT,
                    horario TEXT,
                    numero INTEGER,
                    tipo TEXT,
                    nome TEXT,
                    pin TEXT,
                    criado_em TEXT
                );
            """))
            
            # Tabela Avaliações
            s.execute(text("""
                CREATE TABLE IF NOT EXISTS avaliacoes (
                    id SERIAL PRIMARY KEY,
                    id_agendamento INTEGER,
                    nome_aluno TEXT,
                    data_aula TEXT,
                    modalidade TEXT,
                    nota INTEGER,
                    comentario TEXT,
                    data_avaliacao TEXT
                );
            """))
            s.commit()

        # Cria Admin padrão se a tabela estiver vazia
        users = conn.query("SELECT * FROM users", ttl=0)
        if users.empty:
            criar_usuario(DEFAULT_ADMIN_EMAIL, "Administrador", DEFAULT_ADMIN_PASS, "admin")
            
    except Exception as e:
        st.error(f"Erro ao inicializar banco de dados: {e}")

def verificar_login(email, senha_digitada):
    # Usa a conexão global já configurada
    email = email.strip()
    senha_digitada = senha_digitada.strip()
    
    try:
        # Busca segura com parâmetros (evita SQL Injection)
        df = conn.query("SELECT * FROM users WHERE email = :email", params={"email": email}, ttl=0)
        
        if not df.empty:
            user_data = df.iloc[0].to_dict()
            if user_data['senha'] == hash_senha(senha_digitada):
                return user_data
    except Exception as e:
        st.error(f"Erro no login: {e}")
        
    return None

def atualizar_senha(email, nova_senha):
    with conn.session as s:
        s.execute(
            text("UPDATE users SET senha = :s, mudar_senha = :m WHERE email = :e"),
            params={"s": hash_senha(nova_senha), "m": False, "e": email}
        )
        s.commit()
    return True

def recuperar_senha_email(email_destino):
    df = conn.query("SELECT * FROM users WHERE email = :e", params={"e": email_destino}, ttl=0)
    
    if df.empty:
        return False, "E-mail não cadastrado."

    nova_senha_temp = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    with conn.session as s:
        s.execute(
            text("UPDATE users SET senha = :s, mudar_senha = :m WHERE email = :e"),
            params={"s": hash_senha(nova_senha_temp), "m": True, "e": email_destino}
        )
        s.commit()

    try:
        if "email" in st.secrets:
            secrets = st.secrets["email"]
            msg = MIMEText(f"Olá! Para recuperar seu acesso, utilize a senha temporária: {nova_senha_temp}")
            msg['Subject'] = "[Agenda Naalli] Recuperação de Senha"
            msg['From'] = secrets["sender_email"]  
            msg['To'] = email_destino

            with smtplib.SMTP_SSL(secrets["smtp_server"], secrets["smtp_port"]) as server:
                server.login(secrets["sender_email"], secrets["sender_password"])
                server.sendmail(secrets["sender_email"], email_destino, msg.as_string())
            return True, "E-mail enviado!"
        else:
            return True, f"Modo Debug: {nova_senha_temp}"
    except Exception as e:
        return False, f"Erro: {str(e)}"

def criar_usuario(email, nome, senha_inicial, tipo='aluno'):
    # Verifica duplicidade
    df = conn.query("SELECT email FROM users WHERE email = :e", params={"e": email}, ttl=0)
    if not df.empty:
        return False
    
    with conn.session as s:
        s.execute(
            text("INSERT INTO users (email, nome, senha, mudar_senha, tipo) VALUES (:e, :n, :s, :m, :t)"),
            params={
                "e": email, "n": nome, "s": hash_senha(senha_inicial), 
                "m": True, "t": tipo
            }
        )
        s.commit()
    return True

# ==========================================
# 2. FUNÇÕES OPERACIONAIS (AGENDA)
# ==========================================

def carregar_dados_dia(data_str):
    # Retorna com as colunas renomeadas para bater com o Frontend
    query = "SELECT data AS \"Data\", horario AS \"Horario\", numero AS \"Numero\", tipo AS \"Tipo\", nome AS \"Nome\", pin AS \"Pin\", criado_em AS \"CriadoEm\" FROM agendamentos WHERE data = :d"
    df = conn.query(query, params={"d": data_str}, ttl=0)
    
    if df.empty:
        return pd.DataFrame(columns=["Data", "Horario", "Numero", "Tipo", "Nome", "Pin", "CriadoEm"])
    return df

def carregar_tudo_formatado():
    query = "SELECT data AS \"Data\", horario AS \"Horario\", numero AS \"Numero\", tipo AS \"Tipo\", nome AS \"Nome\", pin AS \"Pin\", criado_em AS \"CriadoEm\" FROM agendamentos"
    df = conn.query(query, ttl=0)
    
    if df.empty:
        return pd.DataFrame(columns=["Data", "Horario", "Numero", "Tipo", "Nome", "Pin", "CriadoEm", "Data_dt"])
    
    df['Data_dt'] = pd.to_datetime(df['Data'], format="%d/%m/%Y", errors='coerce')
    return df

def salvar_agendamento(data_str, horario, numero, tipo, nome, pin):
    # Verifica duplicidade
    check = conn.query(
        "SELECT id FROM agendamentos WHERE data = :d AND horario = :h AND numero = :n AND tipo = :t",
        params={"d": data_str, "h": horario, "n": numero, "t": tipo},
        ttl=0
    )
    if not check.empty:
        return False
    
    with conn.session as s:
        s.execute(
            text("INSERT INTO agendamentos (data, horario, numero, tipo, nome, pin, criado_em) VALUES (:d, :h, :n, :t, :nm, :p, :c)"),
            params={
                "d": data_str, "h": horario, "n": numero, "t": tipo, 
                "nm": nome, "p": pin, "c": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        )
        s.commit()
    return True

def remover_agendamento_por_pin(data_str, horario, numero, tipo, pin_usuario, is_admin=False):
    # Busca o ID e o PIN para validar
    df = conn.query(
        "SELECT id, pin FROM agendamentos WHERE data = :d AND horario = :h AND numero = :n AND tipo = :t",
        params={"d": data_str, "h": horario, "n": numero, "t": tipo},
        ttl=0
    )
    
    if df.empty:
        return "Agendamento não encontrado."
    
    agendamento = df.iloc[0]
    
    if is_admin or agendamento['pin'] == pin_usuario:
        with conn.session as s:
            s.execute(text("DELETE FROM agendamentos WHERE id = :id"), params={"id": int(agendamento['id'])})
            s.commit()
        return "Sucesso"
    else:
        return "Permissão negada."

def gerar_estrutura_horario(hora):
    hora_int = int(hora.split(":")[0])
    eh_almoco = 12 <= hora_int <= 14
    estrutura = []
    if eh_almoco:
        for i in range(1, 7): estrutura.append({"Numero": i, "Tipo": "Treino"})
        for i in range(7, 9): estrutura.append({"Numero": i, "Tipo": "Esteira"})
        estrutura.append({"Numero": 9, "Tipo": "Elíptico"})
    else:
        for i in range(1, 11): estrutura.append({"Numero": i, "Tipo": "Treino"})
        for i in range(11, 13): estrutura.append({"Numero": i, "Tipo": "Esteira"})
        estrutura.append({"Numero": 13, "Tipo": "Elíptico"})
    return estrutura

# ==========================================
# 3. FUNÇÕES DE AVALIAÇÃO
# ==========================================

def get_aulas_pendentes_avaliacao(nome_aluno):
    # Pega agendamentos do aluno
    df_agend = conn.query(
        "SELECT id, data AS \"Data\", horario AS \"Horario\", tipo AS \"Tipo\" FROM agendamentos WHERE nome = :n",
        params={"n": nome_aluno}, ttl=0
    )
    
    # Pega avaliações já feitas
    df_aval = conn.query(
        "SELECT id_agendamento FROM avaliacoes WHERE nome_aluno = :n",
        params={"n": nome_aluno}, ttl=0
    )
    ids_avaliados = df_aval['id_agendamento'].tolist() if not df_aval.empty else []
    
    pendentes = []
    agora = datetime.now()
    
    for _, row in df_agend.iterrows():
        if row['id'] in ids_avaliados: continue
        
        try:
            dt_str = f"{row['Data']} {row['Horario']}"
            dt_obj = datetime.strptime(dt_str, "%d/%m/%Y %H:%M")
            if dt_obj < agora:
                row_dict = row.to_dict()
                row_dict['doc_id'] = row['id'] # Adaptando nome para compatibilidade
                pendentes.append(row_dict)
        except: continue
            
    return sorted(pendentes, key=lambda x: datetime.strptime(f"{x['Data']} {x['Horario']}", "%d/%m/%Y %H:%M"), reverse=True)

def salvar_avaliacao_aluno(id_agendamento, nome_aluno, data_aula, modalidade, nota, comentario):
    with conn.session as s:
        s.execute(
            text("""
                INSERT INTO avaliacoes (id_agendamento, nome_aluno, data_aula, modalidade, nota, comentario, data_avaliacao)
                VALUES (:id, :n, :d, :m, :nt, :c, :da)
            """),
            params={
                "id": int(id_agendamento), "n": nome_aluno, "d": data_aula, "m": modalidade,
                "nt": nota, "c": comentario, "da": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        )
        s.commit()
    return True

def carregar_avaliacoes_formatado():
    # 1. Carrega os dados brutos (que vêm como texto)
    df = conn.query("SELECT modalidade AS \"Modalidade\", nota AS \"Nota\", comentario AS \"Comentario\", nome_aluno AS \"NomeAluno\", data_aula AS \"DataAula\", data_avaliacao AS \"DataAvaliacao\" FROM avaliacoes", ttl=0)
    
    if df.empty:
        return pd.DataFrame(columns=["Modalidade", "Nota", "Comentario", "NomeAluno", "DataAula"])
    
    # 2. CONVERSÃO INTELIGENTE
    # Cria uma coluna temporária convertendo o texto DD/MM/YYYY para Data Real
    # 'dayfirst=True' avisa o Python que o dia vem antes do mês (padrão Brasil)
    df['ordem_cronologica'] = pd.to_datetime(df['DataAula'], dayfirst=True, errors='coerce')
    
    # 3. ORDENAÇÃO
    # Ordena pela data real (Ascending=False coloca os mais recentes no topo)
    df = df.sort_values(by='ordem_cronologica', ascending=False)
    
    # 4. LIMPEZA
    # Remove a coluna temporária para não sujar a tabela visual
    return df.drop(columns=['ordem_cronologica'])

# Inicializa tabelas no final, agora seguro com a conexão configurada
inicializar_banco()