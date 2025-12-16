import streamlit as st
from sqlalchemy import text
import random
from datetime import datetime, timedelta
import hashlib

# Conecta usando as configs do secrets.toml
conn = st.connection("postgresql", type="sql")

QTD_DIAS = 60
NOMES = ["Marcelo", "Ana Clara", "João Pedro", "Mariana", "Lucas", "Fernanda", "Ricardo", "Beatriz", "Gabriel", "Juliana", "Roberto", "Camila", "Gustavo", "Larissa", "Felipe", "Patrícia", "Eduardo", "Sofia", "Sr. Antônio", "Dona Maria", "Carlos", "Priscila", "Renato"]
COMENTARIOS = ["Aula excelente!", "Professor atencioso.", "Equipamentos novos.", "Gostei muito.", "Top!", "Ambiente limpo.", "Muito cheio.", "Normal."]
PESOS = {"06:00": 0.95, "07:00": 0.90, "18:00": 1.00, "19:00": 0.95}

def hash_senha(s): return hashlib.sha256(s.encode()).hexdigest()

print("🚀 Iniciando Seed SQL no Neon...")

with conn.session as s:
    # Limpa dados antigos (Opcional, cuidado!)
    # s.execute(text("TRUNCATE TABLE agendamentos, avaliacoes, users RESTART IDENTITY;"))
    
    # 1. Criar Alunos
    print("👤 Criando usuários...")
    for nome in NOMES:
        email = f"{nome.lower().split()[0]}@email.com"
        # Verifica se já existe
        res = s.execute(text("SELECT email FROM users WHERE email = :e"), {"e": email}).fetchone()
        if not res:
            s.execute(
                text("INSERT INTO users (email, nome, senha, mudar_senha, tipo) VALUES (:e, :n, :s, :m, :t)"),
                {"e": email, "n": nome, "s": hash_senha("123"), "m": False, "t": "aluno"}
            )

    # 2. Criar Agendamentos e Avaliações
    print("📅 Gerando histórico...")
    data_hoje = datetime.now()
    
    for d in range(QTD_DIAS):
        data_atual = data_hoje - timedelta(days=(QTD_DIAS - d))
        data_str = data_atual.strftime("%d/%m/%Y")
        if data_atual.weekday() == 6: continue # Pula domingo

        horarios = ["06:00", "07:00", "08:00", "18:00", "19:00", "20:00"]
        
        for h in horarios:
            chance = PESOS.get(h, 0.3)
            for n in range(1, 5):
                if random.random() < chance:
                    nome = random.choice(NOMES)
                    tipo = random.choice(["Treino", "Esteira"])
                    
                    # Insere Agendamento
                    result = s.execute(
                        text("INSERT INTO agendamentos (data, horario, numero, tipo, nome, pin, criado_em) VALUES (:d, :h, :n, :t, :nm, :p, :c) RETURNING id"),
                        {"d": data_str, "h": h, "n": n, "t": tipo, "nm": nome, "p": "SEED", "c": datetime.now().strftime("%Y-%m-%d")}
                    )
                    id_agend = result.fetchone()[0]
                    
                    # Gera Avaliação (30% de chance)
                    if data_atual < data_hoje and random.random() < 0.3:
                        s.execute(
                            text("INSERT INTO avaliacoes (id_agendamento, nome_aluno, data_aula, modalidade, nota, comentario, data_avaliacao) VALUES (:id, :n, :d, :m, :nt, :c, :da)"),
                            {"id": id_agend, "n": nome, "d": data_str, "m": tipo, "nt": random.randint(3,5), "c": random.choice(COMENTARIOS), "da": datetime.now().strftime("%Y-%m-%d")}
                        )
    
    s.commit()

print("✅ Sucesso! Dados inseridos no Neon.")