
from langchain.agents.middleware import SummarizationMiddleware
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import InMemorySaver
from dateutil.relativedelta import relativedelta
from langchain.tools import tool, ToolRuntime
from langchain.agents import create_agent
from datetime import datetime
from dotenv import load_dotenv
from dataclasses import dataclass
from datetime import date
import psycopg2
import psycopg2.extras
import time
import os

from agent.prompts import SYSTEM_PROMPT

load_dotenv()
start = time.perf_counter()

DATABASE_URL = os.environ['SUPABASE_URL']

def get_conn():
    return psycopg2.connect(DATABASE_URL)

@dataclass # gera automaticamente o __init__ 
class UserInfos:
    name: str
    age: int 
    city: str

api_key_google = os.environ['GOOGLE_API_KEY']
llm = ChatGoogleGenerativeAI(
    model="models/gemini-2.5-flash-lite",
    api_key=api_key_google,
)

@tool
def get_info_user(runtime: ToolRuntime) -> str:
    """
    Retorna as informações do usuário atual (nome e idade e cidade).
    Use esta ferramenta sempre que precisar saber o nome, idade ou/e cidade do usuário,
    ou quando for necessário personalizar a resposta com os dados do usuário.
    """
    return f"O nome do usuário é {runtime.context.name}, a idade é {runtime.context.age} e ele mora em {runtime.context.city}."

@tool
def create_transaction_unique(data: str, descr: str, destinatario: str, valor: float, categoria: str, modalidade: str = "", observacoes: str = "") -> str:
    """
    Insere uma conta paga no banco de dados local.
    Use esta ferramenta quando o usuário informar uma conta paga com data de lançamento,
    descrição, destinatário, valor, modalidade e observações. Retorna confirmação da inserção.

    Args:
        data: Data de lançamento no formato YYYY-MM-DD (ex: '2026-04-05')
        descr: Descrição da conta (ex: 'Aluguel', 'Conta de luz')
        destinatario: Nome do destinatário ou empresa (ex: 'Imobiliária XYZ')
        valor: Valor da conta em reais (ex: 1500.00)
        categoria: Categoria da despesa
        modalidade: Modalidade de pagamento (ex: 'À vista', 'Parcelado')
        observacoes: Observações adicionais (opcional)
    """

    # valida se nenhum campo veio vazio
    if not all([data, descr, destinatario, valor, categoria, modalidade]):
        return "Erro: todos os campos são obrigatórios."

    if valor <= 0:
        return "Erro: valor deve ser maior que zero."

    with get_conn() as conn:
        with conn.cursor() as cursor:
            data_base = datetime.strptime(data, "%Y-%m-%d")

            cursor.execute("""
                INSERT INTO contas_pagas (data_lancamento, descricao, destinatario, valor, categoria, modalidade, observacoes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (data_base.strftime("%Y-%m-%d"), descr.capitalize(), destinatario.capitalize(), valor, categoria.capitalize(), modalidade.strip(), observacoes.strip()))
        
        conn.commit()

    return "Conta paga inserida com sucesso."

@tool
def get_paid_bills(dias: int) -> list | str:
    """Retorna contas pagas nos últimos X dias."""
    if dias < 0:
        return "O parâmetro dias precisa ser maior ou igual a 0."

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("""
                SELECT * FROM contas_pagas
                WHERE data_lancamento <= CURRENT_DATE
                AND data_lancamento >= CURRENT_DATE - INTERVAL '1 day' * %s
            """, (dias,))

            rows = cursor.fetchall()
            if not rows:
                return f'Nenhuma conta paga encontrada nos últimos {dias} dias.'

            return [dict(row) for row in rows]

@tool
def get_paid_bills_today() -> list | str:
    """Retorna as contas pagas na data de hoje."""

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("""
                SELECT * FROM contas_pagas
                WHERE data_lancamento = CURRENT_DATE
            """)

            rows = cursor.fetchall()
            if not rows:
                return 'Nenhuma conta paga encontrada para hoje.'

            return [dict(row) for row in rows]

@tool
def get_bills_today() -> list | str:
    """Retorna as contas pagas da data de hoje. (Alias para get_paid_bills_today)"""
    return get_paid_bills_today()

@tool
def update_description_by_id(id: int, descr: str) -> str:
    """Atualiza a descrição de uma conta paga dado seu ID."""
    with get_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE contas_pagas
                SET descricao = %s
                WHERE id = %s
            """, (descr, id))
            rowcount = cursor.rowcount

        conn.commit()

    if rowcount == 0:
        return "Nenhuma conta encontrada."

    return f"{rowcount} conta(s) atualizada(s)."

@tool
def update_recipient_by_id(id: int, dest: str) -> str:
    """Atualiza o destinatário de uma conta paga dado seu ID."""
    with get_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE contas_pagas
                SET destinatario = %s
                WHERE id = %s
            """, (dest, id))
            rowcount = cursor.rowcount

        conn.commit()

    if rowcount == 0:
        return "Nenhuma conta encontrada."

    return f"{rowcount} conta(s) atualizada(s)."

@tool
def update_value_by_id(id: int, value: float) -> str:
    """Atualiza o valor de uma conta paga dado seu ID."""
    with get_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE contas_pagas
                SET valor = %s
                WHERE id = %s
            """, (value, id))
            rowcount = cursor.rowcount

        conn.commit()

    if rowcount == 0:
        return "Nenhuma conta encontrada."

    return f"{rowcount} conta(s) atualizada(s)."
    
@tool
def update_category_by_id(id: int, categ: str) -> str:
    """Atualiza a categoria de uma conta paga dado seu ID."""
    with get_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE contas_pagas
                SET categoria = %s
                WHERE id = %s
            """, (categ, id))
            rowcount = cursor.rowcount

        conn.commit()

    if rowcount == 0:
        return "Nenhuma conta encontrada."

    return f"{rowcount} conta(s) atualizada(s)."
        
@tool
def update_date_by_id(id: int, data: str) -> str:
    """Atualiza a data de lançamento de uma conta paga dado seu ID."""
    new_data = datetime.strptime(data, "%Y-%m-%d")
    with get_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE contas_pagas
                SET data_lancamento = %s
                WHERE id = %s
            """, (new_data.strftime("%Y-%m-%d"), id))
            rowcount = cursor.rowcount

        conn.commit()

    if rowcount == 0:
        return "Nenhuma conta encontrada."

    return f"{rowcount} conta(s) atualizada(s)."

@tool
def update_modalidade_by_id(id: int, modalidade: str) -> str:
    """Atualiza a modalidade de pagamento de uma conta paga dado seu ID."""
    with get_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE contas_pagas
                SET modalidade = %s
                WHERE id = %s
            """, (modalidade, id))
            rowcount = cursor.rowcount

        conn.commit()

    if rowcount == 0:
        return "Nenhuma conta encontrada."

    return f"{rowcount} conta(s) atualizada(s)."

@tool
def update_observacoes_by_id(id: int, observacoes: str) -> str:
    """Atualiza as observações de uma conta paga dado seu ID."""
    with get_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE contas_pagas
                SET observacoes = %s
                WHERE id = %s
            """, (observacoes, id))
            rowcount = cursor.rowcount

        conn.commit()

    if rowcount == 0:
        return "Nenhuma conta encontrada."

    return f"{rowcount} conta(s) atualizada(s)."

@tool
def delete_by_id(id: int) -> str:
    """Deleta um lançamento de conta paga dado seu ID."""
    with get_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                DELETE FROM contas_pagas
                WHERE id = %s
            """, (id,))
            rowcount = cursor.rowcount

        conn.commit()

    if rowcount == 0:
        return "Nenhuma conta encontrada."

    return f"{rowcount} conta(s) deletada(s)."

@tool
def value_total_by_category() -> list[dict]:
    """
    Retorna o valor total pago por categoria a partir do banco de dados.
    Use esta tool quando o usuário perguntar sobre despesas/gastos por categoria,
    quanto foi pago em cada categoria, ou quiser um resumo financeiro por categoria.
    O retorno é uma lista de dicionários com os campos 'categoria' e 'total'.
    """

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("""
                SELECT
                    categoria,
                    SUM(valor) AS total
                FROM contas_pagas
                GROUP BY categoria
                ORDER BY total DESC
            """)

            rows = cursor.fetchall()
            if not rows:
                return []

            return [{'categoria': row['categoria'], 'total': f"{row['total']:.2f}"} for row in rows]

@tool
def get_transactions_by_date(date: str) -> list | dict:
    """Retorna todas as contas pagas de uma data específica.
    O argumento date deve estar no formato YYYY-MM-DD.
    Use quando o usuário quiser ver as contas pagas em um dia específico."""

    try:
        parsed_date = datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return f"Data inválida: '{date}'. Use o formato YYYY-MM-DD (ex: 2025-04-10)."

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("""
                SELECT * FROM contas_pagas
                WHERE data_lancamento = %s
            """, (parsed_date,))

            rows = cursor.fetchall()
            if not rows:
                return f"Nenhuma conta encontrada para {parsed_date}."

            return [dict(row) for row in rows]

tools_agent = [
    get_info_user,
    create_transaction_unique, 
    get_paid_bills, get_paid_bills_today, get_bills_today, 
    update_description_by_id, update_recipient_by_id, 
    update_value_by_id, update_category_by_id, 
    update_date_by_id, update_modalidade_by_id, update_observacoes_by_id, delete_by_id, 
    value_total_by_category, get_transactions_by_date
]

summarization = SummarizationMiddleware(
        model=llm, 
        trigger=('fraction', 0.7), 
        keep=('messages', 8), 
        summary_prompt="Resuma a conversa até agora em poucas palavras, mantendo as informações mais importantes. A resposta deve ser breve e direta ao ponto."
    )

agent = create_agent(
    model=llm,
    tools=tools_agent,
    system_prompt=SYSTEM_PROMPT,
    checkpointer=InMemorySaver(),
    middleware=[summarization],
    context_schema=UserInfos,
)