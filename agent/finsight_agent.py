
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import InMemorySaver
from dateutil.relativedelta import relativedelta
from langchain.tools import tool, ToolRuntime
from langchain.agents import create_agent
from datetime import datetime
from dotenv import load_dotenv
from dataclasses import dataclass
from datetime import date
import sqlite3
import time
import os

load_dotenv()
start = time.perf_counter()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # pasta agent/
DB_PATH = os.path.join(BASE_DIR, "..", "meu_banco.db")  # sobe um nível

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
Você é o FinSight, um assistente financeiro especializado em gestão de contas a pagar.
A data de hoje é: {date_current} (YYYY-MM-DD)

## Identidade e escopo
Você gerencia contas a pagar do usuário. Qualquer solicitação fora desse escopo deve ser recusada educadamente.

## Kit de ferramentas disponível

### Consulta
- `get_due_bills` — contas que vencem nos próximos X dias
- `get_due_bills_today` — contas que vencem hoje
- `get_bills_today` — contas pagas hoje
- `value_total_by_category` — total a pagar agrupado por categoria
- `get_info_user` — dados do usuário (nome, idade, cidade)
- `get_transactions_by_date` — retorne ao user as contas de uma data específica

### Criação
- `create_transaction_unique` — registra uma conta única
- `create_transaction_recurrence` — registra contas recorrentes

### Atualização
- `update_status_bills_by_today` — marca todas as contas de hoje como pagas
- `update_status_by_id` — altera status de uma conta pelo ID
- `update_description_by_id` — atualiza descrição pelo ID
- `update_date_by_id` — atualiza data de vencimento pelo ID
- `update_recipient_by_id` — atualiza destinatário pelo ID
- `update_value_by_id` — atualiza valor pelo ID
- `update_category_by_id` — atualiza categoria pelo ID

### Exclusão
- `deletar_conta` — remove um lançamento pelo ID

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
- Ao listar contas (`get_due_bills`, `get_due_bills_today`), exiba apenas: ID, Descrição, Destinatário, Valor e Data de vencimento
- Ao retornar `value_total_by_category`, reformate os dados de forma clara e amigável — nunca retorne dados crus
- Após qualquer ação concluída, sempre confirme explicitamente ao usuário com uma mensagem de sucesso

## Restrições
- Nunca execute ações destrutivas ou irreversíveis sem confirmação explícita
- Nunca mencione colunas internas como status, data de criação, etc.
- Nunca retorne strings vazias após executar uma ação
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
def create_transaction_unique(data: str, descr: str, destinatario: str, valor: float, categoria: str) -> str:
    """
    Insere uma conta a pagar no banco de dados local.
    Use esta ferramenta quando o usuário informar uma conta a pagar com data de vencimento,
    descrição, destinatário e valor. Retorna confirmação da inserção.

    Args:
        data: Data de vencimento no formato YYYY-MM-DD (ex: '2026-04-05')
        descr: Descrição da conta (ex: 'Aluguel', 'Conta de luz')
        destinatario: Nome do destinatário ou empresa (ex: 'Imobiliária XYZ')
        valor: Valor da conta em reais (ex: 1500.00)
    """

    # valida se nenhum campo veio vazio
    if not all([data, descr, destinatario, valor, categoria]):
        return "Erro: todos os campos são obrigatórios."

    if valor <= 0:
        return "Erro: valor deve ser maior que zero."

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor() # cria o ponteiro para executar comandos, é a caneta que escreve
        data_base = datetime.strptime(data, "%Y-%m-%d")  # converte string → datetime

        cursor.execute("""
            INSERT INTO contas_a_pagar (data_vencimento, descricao, destinatario, valor, categoria, recorrencia, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (data_base.strftime("%Y-%m-%d"), descr.capitalize(), destinatario.capitalize(), valor, categoria.capitalize(), 'Não', 'A pagar'))
        conn.commit() # confirma/salva as operações

    conn.close() # fecha conexão com bd
    return "Conta inserida com sucesso."

@tool
def create_transaction_recurrence(data: str, descr: str, destinat: str, valor: float, categoria: str, recurrence: int) -> str:
    """
    Insere contas a pagar recorrentes no banco de dados local.
    Use esta ferramenta quando o usuário informar uma conta a pagar que tenha parcelas/mensalidades com data de vencimento,
    descrição, destinatário e valor. Retorna confirmação da inserção.

    Args:
        data: Data de vencimento no formato YYYY-MM-DD
        descr: Descrição da conta
        destinat: Nome do destinatário
        valor: Valor da conta total
        categoria: Categoria da despesa
        recorr: Quantidade total de parcelas/mensalidades
    """

    # valida se nenhum campo veio vazio
    if not all([data, descr, destinat, valor, categoria, recurrence]):
        return "Erro: todos os campos são obrigatórios."

    if valor <= 0:
        return "Erro: valor deve ser maior que zero."
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor() # cria o ponteiro para executar comandos, é a caneta que escreve
        data_base = datetime.strptime(data, "%Y-%m-%d")  # converte string → datetime
        valor_parcelado = round(valor / recurrence, 2)

        for i in range(1, recurrence + 1):
            descr_parcela = descr.capitalize() + f' {i}/{recurrence}'
            data_parcela = data_base + relativedelta(months=i - 1)

            cursor.execute("""
                INSERT INTO contas_a_pagar (data_vencimento, descricao, destinatario, valor, categoria, recorrencia, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (data_parcela.strftime("%Y-%m-%d"), descr_parcela, destinat.capitalize(), valor_parcelado, categoria.capitalize(), 'Sim', 'A pagar'))
            
        conn.commit() # confirma/salva as operações

    conn.close() # fecha conexão com bd
    return "Conta inserida com sucesso."

@tool
def get_due_bills(dias: int) -> list | str:
    """Retorna contas a pagar com vencimento nos próximos X dias."""
    if dias < 0:
        return "O parâmetro dias precisa ser maior que 0."
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM contas_a_pagar
            WHERE data_vencimento >= date('now', 'localtime')
            AND data_vencimento <= date('now', 'localtime', ? || ' days')
            AND status = 'A pagar'
        """, (f"+{dias}",))

        rows = cursor.fetchall()
        if not rows:
            return 'Nenhuma conta a pagar encontrada para hoje.'
        
        return [dict(row) for row in rows]

@tool
def get_due_bills_today() -> list | str:
    """Retorna as contas a pagar com o vencimento de hoje."""
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM contas_a_pagar
            WHERE data_vencimento >= date('now', 'localtime')
            AND data_vencimento <= date('now', 'localtime', ? || ' days')
            AND status = 'A pagar'
        """, (f"+{1}",))

        rows = cursor.fetchall()
        if not rows:
            return 'Nenhuma conta a pagar encontrada para hoje.'
        
        return [dict(row) for row in rows]

@tool
def get_bills_today() -> list | str:
    """Retorna as contas pagas da data de hoje."""
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM contas_a_pagar
            WHERE data_vencimento >= date('now', 'localtime')
            AND data_vencimento <= date('now', 'localtime', ? || ' days')
            AND status = 'Paga'
        """, (f"+{1}",))

        rows = cursor.fetchall()
        if not rows:
            return 'Nenhuma conta paga encontrada com data de hoje.'
        
        return [dict(row) for row in rows]

@tool
def update_today_status() -> str:
    """Marca todas as contas a pagar de hoje como 'Pagas'. Use esta tool quando o usuário quiser quitar todas as contas do dia de uma vez, sem especificar uma conta individual."""
    today_date = date.today().strftime("%Y-%m-%d")
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            UPDATE contas_a_pagar
            SET status = ?
            WHERE data_vencimento = ?
        """, ('Paga', today_date))
        conn.commit()
        
        if cursor.rowcount == 0:
            return f"Nenhuma conta encontrada para a data de hoje."
        
        return f"{cursor.rowcount} conta(s) atualizada(s) para a data de hoje."

@tool
def update_status_by_id(id: int, status: str) -> str:
    """Marca uma conta como 'A pagar' ou 'Paga' dado seu ID. Use quando o usuário quiser alterar o status de uma conta específica."""
    status_validos = ["A Pagar", "Paga"]
    if status not in status_validos:
        return f"Status inválido: '{status}'. Use 'A Pagar' ou 'Paga'."
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            UPDATE contas_a_pagar
            SET status = ?
            WHERE id = ?
        """, (status, id))
        conn.commit()
        
        if cursor.rowcount == 0:
            return f"Nenhuma conta encontrada."
        
        return f"{cursor.rowcount} conta(s) atualizada(s)."

@tool
def update_description_by_id(id: int, descr: str) -> str:
    """Atualiza a descrição de uma conta a pagar dado seu ID. Use quando o usuário quiser editar ou corrigir a descrição de uma conta específica."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            UPDATE contas_a_pagar
            SET descricao = ?
            WHERE id = ?
        """, (descr, id))
        conn.commit()
        
        if cursor.rowcount == 0:
            return f"Nenhuma conta encontrada."
        
        return f"{cursor.rowcount} conta(s) atualizada(s)."

@tool
def update_recipient_by_id(id: int, dest: str) -> str:
    """Atualiza a coluna de destinatário de uma conta a pagar dado seu ID. Use quando o usuário quiser editar ou corrigir a coluna de destinatário de uma conta específica."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            UPDATE contas_a_pagar
            SET destinatario = ?
            WHERE id = ?
        """, (dest, id))
        conn.commit()
        
        if cursor.rowcount == 0:
            return f"Nenhuma conta encontrada."
        
        return f"{cursor.rowcount} conta(s) atualizada(s)."

@tool
def update_value_by_id(id: int, value: float) -> str:
    """Atualiza a coluna de valor de uma conta a pagar dado seu ID. Use quando o usuário quiser editar ou corrigir a coluna de valor de uma conta específica."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            UPDATE contas_a_pagar
            SET valor = ?
            WHERE id = ?
        """, (value, id))
        conn.commit()
        
        if cursor.rowcount == 0:
            return f"Nenhuma conta encontrada."
        
        return f"{cursor.rowcount} conta(s) atualizada(s)."
    
@tool
def update_category_by_id(id: int, categ: str) -> str:
    """Atualiza a coluna de categoria de uma conta a pagar dado seu ID. Use quando o usuário quiser editar ou corrigir a coluna de categoria de uma conta específica."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            UPDATE contas_a_pagar
            SET categoria = ?
            WHERE id = ?
        """, (categ, id))
        conn.commit()
        
        if cursor.rowcount == 0:
            return f"Nenhuma conta encontrada."
        
        return f"{cursor.rowcount} conta(s) atualizada(s)."
        
@tool
def update_date_by_id(id: int, data: str) -> str:
    """Atualiza a coluna de data de uma conta a pagar dado seu ID. Use quando o usuário quiser editar ou corrigir a coluna de data de uma conta específica."""
    new_data = datetime.strptime(data, "%Y-%m-%d")  # converte string → datetime
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            UPDATE contas_a_pagar
            SET data_vencimento = ?
            WHERE id = ?
        """, (new_data.strftime("%Y-%m-%d"), id))
        conn.commit()
        
        if cursor.rowcount == 0:
            return f"Nenhuma conta encontrada."
        
        return f"{cursor.rowcount} conta(s) atualizada(s)."

@tool
def delete_by_id(id: int) -> str:
    """Deleta uma linha dado seu ID. Use quando o usuário quiser deletar ou excluir a linha um registro específico."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            DELETE FROM contas_a_pagar
            WHERE id = ?
        """, (id,))
        conn.commit()
        
        if cursor.rowcount == 0:
            return f"Nenhuma conta encontrada."
        
        return f"{cursor.rowcount} conta(s) deletada(s)."

@tool
def value_total_by_category() -> list[dict]:
    """
    Retorna o valor total gasto por categoria a partir do banco de dados.
    Use esta tool quando o usuário perguntar sobre gastos por categoria,
    quanto foi gasto em cada categoria, ou quiser um resumo financeiro por categoria.
    O retorno é uma lista de dicionários com os campos 'categoria' e 'total'.
    """
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                categoria,
                SUM(valor) AS total
            FROM contas_a_pagar
            GROUP BY categoria
            ORDER BY total DESC
        """)

        rows = cursor.fetchall()
        if not rows:
            return 'Nenhuma conta paga encontrada com data de hoje.'
        
        return [{'categoria': row['categoria'], 'total': f'{row['total']:.2f}'} for row in rows]

@tool
def get_transactions_by_date(date: str) -> list | dict:
    """Retorna todas as contas a pagar de uma data específica.
    O argumento date deve estar no formato YYYY-MM-DD.
    Use quando o usuário quiser ver as contas de um dia específico."""
    
    try:
        parsed_date = datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return f"Data inválida: '{date}'. Use o formato YYYY-MM-DD (ex: 2025-04-10)."
    
    print(parsed_date)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM contas_a_pagar
            WHERE data_vencimento = ?
        """, (parsed_date,))

        rows = cursor.fetchall()
        print(rows)
        if not rows:
            return f"Nenhuma conta encontrada para {parsed_date}."
        
        return [dict(row) for row in rows]

tools_agent = [update_recipient_by_id, update_description_by_id, get_info_user, create_transaction_unique, 
               create_transaction_recurrence, get_due_bills, get_due_bills_today, 
               update_today_status, update_status_by_id, get_bills_today, update_value_by_id, update_category_by_id,
               update_date_by_id, delete_by_id, value_total_by_category, get_transactions_by_date]

agent = create_agent(
    model=llm,
    tools=tools_agent,
    system_prompt=system_prompt,
    checkpointer=InMemorySaver(),
    context_schema=UserInfos,
)