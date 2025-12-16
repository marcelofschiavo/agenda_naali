# Importa a conexão (conn) inteligente que já criamos no utils.py
from utils import conn
from sqlalchemy import text

def rodar_seed():
    dados = [
        # Data, Hora, Numero, Tipo, Nome
        ('15/12/2025', '07:00', 1, 'Treino', 'Ana Clara'),
        ('15/12/2025', '07:00', 2, 'Esteira', 'Ricardo'),
        ('15/12/2025', '08:00', 1, 'Treino', 'Sr. Antônio'),
        ('15/12/2025', '18:00', 1, 'Treino', 'Felipe'),
        ('15/12/2025', '18:00', 2, 'Treino', 'Beatriz'),
        ('15/12/2025', '19:00', 3, 'Elíptico', 'Larissa'),
        
        # TERÇA (HOJE)
        ('16/12/2025', '06:00', 1, 'Esteira', 'Juliana'),
        ('16/12/2025', '07:00', 1, 'Treino', 'Fernanda'),
        ('16/12/2025', '07:00', 2, 'Esteira', 'Ana Clara'),
        ('16/12/2025', '18:00', 1, 'Treino', 'Gustavo'),
        ('16/12/2025', '19:00', 1, 'Treino', 'Priscila'),
        ('16/12/2025', '20:00', 1, 'Esteira', 'Gabriel')
    ]
    
    print("⏳ Inserindo dados no banco...")
    
    try:
        with conn.session as s:
            for d in dados:
                s.execute(text("""
                    INSERT INTO agendamentos (data, horario, numero, tipo, nome, pin, criado_em)
                    VALUES (:data, :hora, :num, :tipo, :nome, 'SEED', '2025-12-16 00:00:00')
                """), params={"data": d[0], "hora": d[1], "num": d[2], "tipo": d[3], "nome": d[4]})
            s.commit()
        print("✅ Dados inseridos com sucesso! Pode abrir o painel.")
    except Exception as e:
        print(f"❌ Erro ao inserir: {e}")

if __name__ == "__main__":
    rodar_seed()