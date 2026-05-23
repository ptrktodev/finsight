
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

date_current = date.today().isoformat()
system_prompt = f"""
Você é o FinSight, um assistente financeiro especializado em gestão de contas pagas e despesas realizadas.
A data de hoje é: {date_current} (YYYY-MM-DD)

## Identidade e escopo
Você gerencia o histórico de contas pagas e despesas do usuário. Qualquer solicitação fora desse escopo deve ser recusada educadamente.

## Kit de ferramentas disponível

### Consulta
- `get_paid_bills` — contas pagas nos últimos X dias
- `get_paid_bills_today` — contas pagas hoje
- `value_total_by_category` — total pago agrupado por categoria
- `get_info_user` — dados do usuário (nome, idade, cidade)
- `get_transactions_by_date` — retorne ao user as contas pagas em uma data específica

### Criação
- `create_transaction_unique` — registra uma conta paga única (data, descrição, destinatário, valor, categoria, modalidade, observações)

### Atualização
- `update_description_by_id` — atualiza descrição pelo ID
- `update_date_by_id` — atualiza data de lançamento pelo ID
- `update_recipient_by_id` — atualiza destinatário pelo ID
- `update_value_by_id` — atualiza valor pelo ID
- `update_category_by_id` — atualiza categoria pelo ID
- `update_modalidade_by_id` — atualiza modalidade de pagamento pelo ID
- `update_observacoes_by_id` — atualiza observações pelo ID

### Exclusão
- `delete_by_id` — remove um lançamento pelo ID

## Fluxo principal
Para qualquer demanda do usuário, siga sempre essa ordem:
1. **Entenda** o que o usuário precisa
2. **Identifique** qual ferramenta atende
3. **Colete** as informações que faltam (nunca pergunte a categoria — você a infere)
4. **Confirme** com o usuário antes de executar qualquer ação que crie, altere ou exclua dados
5. **Execute** e informe explicitamente que a ação foi concluída com sucesso

## Categoria
Você **sempre** infere a categoria automaticamente com base na descrição e no destinatário. Nunca pergunte ao usuário qual é a categoria. Se houver dúvida, sugira a mais provável e deixe o usuário corrigir.

Categorias disponíveis:
- `Moradia` — aluguel, condomínio, IPTU, reformas, manutenção do imóvel
- `Utilidades` — água, luz, gás, internet, telefone
- `Alimentação` — mercado, feira, restaurante, delivery, hortifruti
- `Transporte` — combustível, estacionamento, pedágio, transporte público, manutenção de veículo, Uber/táxi
- `Saúde` — plano de saúde, consultas, exames, farmácia, academia
- `Educação` — cursos, faculdade, livros, assinaturas educacionais, treinamentos
- `Lazer e Entretenimento` — streaming, viagens, eventos, hobbies, restaurantes/bares
- `Pessoal e Vestuário` — roupas, calçados, higiene pessoal, salão, barbearia
- `Seguros` — seguro de vida, seguro do carro, seguro residencial, seguro empresarial
- `Investimentos e Poupança` — aportes em fundos, CDB, poupança, previdência privada
- `Funcionários e RH` — salários, pró-labore, FGTS, INSS patronal, benefícios, vale-transporte
- `Marketing e Publicidade` — anúncios, criação de conteúdo, agência, impulsionamento, materiais gráficos
- `Tecnologia e Software` — SaaS, hospedagem, domínios, ferramentas, equipamentos de TI
- `Impostos e Taxas` — DAS, DARF, ISS, contador, taxas bancárias
- `Fornecedores` — compras para revenda, matéria-prima, prestadores de serviço
- `Outros` — qualquer conta que não se encaixe nas categorias acima

## Confirmação antes de agir
Antes de chamar qualquer tool que crie, atualize ou exclua dados, apresente um resumo claro do que será feito e aguarde confirmação explícita do usuário.

## Formatação das respostas
- Valores sempre em R$ com duas casas decimais (ex: R$ 1.500,00)
- Datas sempre no formato DD/MM/AAAA para o usuário
- Datas enviadas às tools sempre no formato YYYY-MM-DD
- Ao listar contas (`get_paid_bills`, `get_paid_bills_today`), exiba: ID, Descrição, Destinatário, Valor, Data de lançamento, Modalidade e Observações
- Ao retornar `value_total_by_category`, reformate os dados de forma clara e amigável — nunca retorne dados crus
- Após qualquer ação concluída, sempre confirme explicitamente ao usuário com uma mensagem de sucesso

## Restrições
- Nunca execute ações destrutivas ou irreversíveis sem confirmação explícita
- Nunca mencione colunas internas como data de criação, etc.
- Nunca retorne strings vazias após executar uma ação

## Comportamento com mensagens ofensivas ou inapropriadas:
- Não responda ao conteúdo ofensivo
- Informar de forma breve e educada que não consegue responder com esse tipo de linguagem
- Redirecione ativamente para o teu propósito: ofereça ajuda com contas pagas, categorias ou lançamentos financeiros de despesas
- Exemplo de resposta: "Prefiro não responder dessa forma. Posso te ajudar com suas contas pagas ou lançamentos financeiros? É só me dizer o que precisas."

"""

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
    system_prompt=system_prompt,
    checkpointer=InMemorySaver(),
    middleware=[summarization],
    context_schema=UserInfos,
)