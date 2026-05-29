import os
import json
import pandas as pd
import datetime
import glob
import requests
import unicodedata
import gspread
from google.oauth2 import service_account
from dotenv import load_dotenv
from pathlib import Path
try:
    from psycopg2.extras import execute_values
except ImportError:
    def execute_values(cursor, query, argslist, page_size=5000):
        if not argslist:
            return
        placeholder = "(" + ",".join(["%s"] * len(argslist[0])) + ")"
        query = query.replace("%s", placeholder)
        cursor.executemany(query, argslist)

try:
    from core.db import get_db_connection
except ImportError:
    get_db_connection = None

load_dotenv()


def normalizar_nome_coluna(nome):
    if not isinstance(nome, str):
        return nome

    texto = nome.replace('="', '').replace('"', '').strip()

    substituicoes = {
        "Custo#MĂŠdio": "Custo#Médio",
        "Custo#MÃ©dio": "Custo#Médio",
        "NÃºmero": "Número",
        "SĂ‰RIE": "SÉRIE",
    }
    texto = substituicoes.get(texto, texto)

    return texto


def limpar_valores_dataframe(df):
    limpar = lambda x: str(x).replace('="', '').replace('"', '')
    if hasattr(df, "map"):
        return df.map(limpar)
    return df.applymap(limpar)


def ultimo_arquivo():

    # Caminho para a pasta "Downloads"
    caminho_downloads = os.path.expanduser("~") + "/Downloads"

    # Lista de todos os arquivos na pasta "Downloads", ordenados por data de modificação (o mais recente primeiro)
    lista_arquivos = glob.glob(caminho_downloads + "/*", recursive=False)
    lista_arquivos.sort(key=lambda x: os.path.getmtime(x), reverse=True)

    # Pegue o caminho do último arquivo baixado (o arquivo mais recente)
    ultimo_arquivo_baixado = lista_arquivos[0]

    print("Caminho do último arquivo baixado:", ultimo_arquivo_baixado)

    ultimo_erro = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            df = pd.read_csv(ultimo_arquivo_baixado, sep=';', encoding=encoding)
            print(f"CSV carregado com encoding: {encoding}")
            break
        except UnicodeDecodeError as exc:
            ultimo_erro = exc
    else:
        raise ultimo_erro

    df['data'] = datetime.datetime.today()
    df['data'] = df['data'].dt.strftime('%d/%m/%Y %H:%M:%S')

    df.rename(columns=normalizar_nome_coluna, inplace=True)

    # df = df.drop(columns={'=" "'})
    # df.columns
    df["1o. Agrupamento"] = df["1o. Agrupamento"].apply(lambda x: str(x).replace("=", "").replace('"', ''))
    df["2o. Agrupamento"] = df["2o. Agrupamento"].apply(lambda x: str(x).replace("=", "").replace('"', ''))

    print("Colunas do dataframe:", df.columns.tolist())
    
    return df

def inserir_postgres_saldo_central_mp(df=None, tabela='ConsultaSaldoInnovaro'):
    """
    Insere ou atualiza os dados do dataframe na tabela PostgreSQL especificada
    utilizando UPSERT, evitando locks globais.
    """
    try:
        if get_db_connection is None:
            print("Modulo core.db nao disponivel. Insercao no PostgreSQL foi ignorada.")
            return "skipped: core.db unavailable"

        if df is None:
            df = ultimo_arquivo()

        # Limpeza de colunas
        df.rename(columns=lambda x: x.replace('="', '').replace('"', ''), inplace=True)
        df = limpar_valores_dataframe(df)

        # Conversões numéricas
        df['Saldo'] = df['Saldo'].apply(lambda x: float(x.replace('.', '').replace(',', '.')))
        df['Custo#Total'] = df['Custo#Total'].apply(lambda x: float(x.replace('.', '').replace(',', '.')))
        df['Custo#Médio'] = df['Custo#Médio'].apply(lambda x: float(x.replace('.', '').replace(',', '.')))

        # Extração de código e descrição
        df['codigo'] = df['3o. Agrupamento'].apply(lambda x: x.split()[0])
        df['descricao'] = df['3o. Agrupamento'].apply(lambda x: x.split('-')[1].strip())

        # Seleção final
        df_final = df[
            ['1o. Agrupamento', 'codigo', 'descricao',
             'Saldo', 'Custo#Total', 'Custo#Médio', 'data']
        ].copy()

        df_final.columns = [
            'agrupamento',
            'codigo',
            'descricao',
            'saldo',
            'custo_total',
            'custo_medio',
            'data_registro'
        ]

        if df_final.empty:
            return 'No data to insert'

        registros = [tuple(row) for row in df_final.itertuples(index=False, name=None)]

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SET search_path TO apontamento_v2")

        # Limpa a tabela antes de inserir (evita TRUNCATE para não gerar lock exclusivo)
        cursor.execute(f"DELETE FROM apontamento_v2.core_{tabela}")

        insert_query = f"""
            INSERT INTO apontamento_v2.core_{tabela} (
                agrupamento, codigo, descricao, saldo, custo_total, custo_medio, data_ultimo_saldo
            ) VALUES %s
        """

        execute_values(cursor, insert_query, registros, page_size=5000)

        conn.commit()
        cursor.close()
        conn.close()

        print(f"✓ {len(registros)} registros inseridos na tabela '{tabela}' com sucesso!")
        return 'success'

    except Exception as e:
        print(f"Erro ao inserir dados no PostgreSQL: {e}")
        try:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
        except Exception:
            pass
        return f'error: {str(e)}'

def inserir_gspread_saldo_central_mp():

    pasta_do_script = os.path.dirname(os.path.abspath(__file__))
    caminho_env = os.path.join(pasta_do_script, '.env')
    load_dotenv(caminho_env, override=True)

    private_key = os.getenv("GOOGLE_PRIVATE_KEY")
    
    if private_key:
        # --- LIMPEZA CRÍTICA ---
        
        # Passo A: Remove aspas extras se elas vieram do .env (strip remove do começo e fim)
        private_key = private_key.strip('"').strip("'")
        
        # Passo B: Converte os caracteres literais "\n" em quebras de linha reais
        private_key = private_key.replace('\\n', '\n')

    credentials_dict = {
        "type": os.getenv("GOOGLE_TYPE"),
        "project_id": os.getenv("GOOGLE_PROJECT_ID"),
        "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
        "private_key": private_key,
        "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
        "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
        "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_CERT_URL"),
        "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_CERT_URL")
    }

    try:
        gc = gspread.service_account_from_dict(credentials_dict)
        print("Autenticação realizada com sucesso!")
    except Exception as e:
        print(f"Erro na autenticação: {e}")
        return f"error: gspread auth failed - {e}"

    df = ultimo_arquivo()

    # Autentique-se com a API do Google Sheets (configure o caminho para suas credenciais)
    # gc = gspread.service_account(filename=r'C:\Users\Engine\automacao_saldo_almoc\service_account_cemag.json')
    # gc = gspread.service_account(filename='service_account.json')

    # Abra a planilha com base no ID
    planilha = gc.open_by_key("1u2Iza-ocp6ROUBXG9GpfHvEJwLHuW7F2uiO583qqLIE")

    # Acessar a aba "BD_saldo_diario"
    aba = planilha.worksheet("saldo central")

    # Defina o intervalo (range) que você deseja apagar (por exemplo, A2:H5)
    range_to_clear = "A2:Z"
    
    df.rename(columns=lambda x: x.replace('="', '').replace('"', ''), inplace=True)
    
    df = limpar_valores_dataframe(df)

    df['Saldo'] = df['Saldo'].apply(lambda x: float(x.replace(".","").replace(",",".")))
    df['Custo#Total'] = df['Custo#Total'].apply(lambda x: float(x.replace(".","").replace(",",".")))
    df['Custo#Médio'] = df['Custo#Médio'].apply(lambda x: float(x.replace(".","").replace(",",".")))
    
    df['codigo'] = df['3o. Agrupamento'].apply(lambda x: x.split()[0])
    df['descricao'] = df['3o. Agrupamento'].apply(lambda x: x.split('-')[1])

    df = df[['1o. Agrupamento', 'codigo', 'descricao', 'Saldo','Custo#Total', 'Custo#Médio','data']]

    df_values = df.values.tolist()

    if len(df_values) > 0:
        
        # Obtém a lista de células no intervalo especificado
        cell_list = aba.range(range_to_clear)
        
        # Define o valor de todas as células no intervalo como uma string vazia ('')
        for cell in cell_list:
            cell.value = ""
        
        # Atualiza as células no intervalo com os valores vazios
        aba.update_cells(cell_list)
        
        planilha.values_append("saldo central", {'valueInputOption': 'RAW'}, {'values': df_values})

    return 'sucess'

def apagar_ultimo_download():
    """
    Busca o arquivo mais recente na pasta Downloads do usuário e o apaga.
    """
    try:
        # Define o caminho
        caminho_downloads = os.path.join(os.path.expanduser("~"), "Downloads")

        # Pega a lista de caminhos (strings)
        lista_arquivos = glob.glob(os.path.join(caminho_downloads, "*"))
        
        # FILTRO IMPORTANTE: Remove pastas da lista, mantém só arquivos
        # Se não filtrar, o script pode tentar apagar uma pasta e dar erro
        arquivos_apenas = [f for f in lista_arquivos if os.path.isfile(f)]

        if not arquivos_apenas:
            print("A pasta está vazia.")
            return

        # Busca o mais recente usando os.path.getmtime
        arquivo_mais_recente = max(arquivos_apenas, key=os.path.getmtime)

        # Para pegar o nome visual (ex: arquivo.pdf)
        nome_arquivo = os.path.basename(arquivo_mais_recente)
        
        # Apaga o arquivo usando os.remove (que aceita string)
        os.remove(arquivo_mais_recente)
        
        print(f"Arquivo deletado com sucesso: {nome_arquivo}")

    except PermissionError:
        print(f"Erro: O arquivo parece estar aberto ou em uso.")
    except Exception as e:
        print(f"Ocorreu um erro inesperado: {e}")

def inserir_gspread_saldo_levantamento():

    pasta_do_script = os.path.dirname(os.path.abspath(__file__))
    caminho_env = os.path.join(pasta_do_script, '.env')
    load_dotenv(caminho_env, override=True)

    private_key = os.getenv("GOOGLE_PRIVATE_KEY")
    
    if private_key:
        # --- LIMPEZA CRÍTICA ---
        
        # Passo A: Remove aspas extras se elas vieram do .env (strip remove do começo e fim)
        private_key = private_key.strip('"').strip("'")
        
        # Passo B: Converte os caracteres literais "\n" em quebras de linha reais
        private_key = private_key.replace('\\n', '\n')

    credentials_dict = {
        "type": os.getenv("GOOGLE_TYPE"),
        "project_id": os.getenv("GOOGLE_PROJECT_ID"),
        "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
        "private_key": private_key,
        "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
        "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
        "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_CERT_URL"),
        "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_CERT_URL")
    }

    try:
        gc = gspread.service_account_from_dict(credentials_dict)
        print("Autenticação realizada com sucesso!")
    except Exception as e:
        print(f"Erro na autenticação: {e}")
        return f"error: gspread auth failed - {e}"

    df = ultimo_arquivo()

    # Autentique-se com a API do Google Sheets (configure o caminho para suas credenciais)
    # gc = gspread.service_account(filename=r'C:\Users\Engine\automacao_saldo_almoc\service_account_cemag.json')
    # gc = gspread.service_account(filename='service_account.json')

    # Abra a planilha com base no ID
    planilha = gc.open_by_key("1u2Iza-ocp6ROUBXG9GpfHvEJwLHuW7F2uiO583qqLIE")

    # Acessar a aba "BD_saldo_diario"
    aba = planilha.worksheet("saldo de recurso")

    # Defina o intervalo (range) que você deseja apagar (por exemplo, A2:H5)
    range_to_clear = "A2:Z"
    
    df.rename(columns=lambda x: x.replace('="', '').replace('"', ''), inplace=True)
    
    df = limpar_valores_dataframe(df)

    df['Saldo'] = df['Saldo'].apply(lambda x: float(x.replace(".","").replace(",",".")))
    df['Custo#Total'] = df['Custo#Total'].apply(lambda x: float(x.replace(".","").replace(",",".")))
    df['Custo#Médio'] = df['Custo#Médio'].apply(lambda x: float(x.replace(".","").replace(",",".")))
    
    df = df[df['2o. Agrupamento'] == 'nan']

    df['codigo'] = df['3o. Agrupamento'].apply(lambda x: x.split()[0])
    df['descricao'] = df['3o. Agrupamento'].apply(lambda x: x.split('-')[1])
    
    df = df[['1o. Agrupamento','codigo','descricao','3o. Agrupamento','Saldo','Custo#Total','Custo#Médio','data']]
    df_values = df.values.tolist()

    if len(df_values) > 0:
    
        # Obtém a lista de células no intervalo especificado
        cell_list = aba.range(range_to_clear)
        
        # Define o valor de todas as células no intervalo como uma string vazia ('')
        for cell in cell_list:
            cell.value = ""
        
        # Atualiza as células no intervalo com os valores vazios
        aba.update_cells(cell_list)

        planilha.values_append("saldo de recurso", {'valueInputOption': 'RAW'}, {'values': df_values})

    return 'sucess'

def inserir_gspread_saldo_levantamento_incluindo_em_processo():
   
    pasta_do_script = os.path.dirname(os.path.abspath(__file__))
    caminho_env = os.path.join(pasta_do_script, '.env')
    load_dotenv(caminho_env, override=True)

    private_key = os.getenv("GOOGLE_PRIVATE_KEY")
    
    if private_key:
        # --- LIMPEZA CRÍTICA ---
        
        # Passo A: Remove aspas extras se elas vieram do .env (strip remove do começo e fim)
        private_key = private_key.strip('"').strip("'")
        
        # Passo B: Converte os caracteres literais "\n" em quebras de linha reais
        private_key = private_key.replace('\\n', '\n')

    credentials_dict = {
        "type": os.getenv("GOOGLE_TYPE"),
        "project_id": os.getenv("GOOGLE_PROJECT_ID"),
        "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
        "private_key": private_key,
        "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
        "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
        "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_CERT_URL"),
        "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_CERT_URL")
    }

    try:
        gc = gspread.service_account_from_dict(credentials_dict)
        print("Autenticação realizada com sucesso!")
    except Exception as e:
        print(f"Erro na autenticação: {e}")
        return f"error: gspread auth failed - {e}"

    df = ultimo_arquivo()

    # Autentique-se com a API do Google Sheets (configure o caminho para suas credenciais)
    # gc = gspread.service_account(filename=r'C:\Users\Engine\automacao_saldo_almoc\service_account_cemag.json')
    # gc = gspread.service_account(filename='service_account.json')

    # Abra a planilha com base no ID
    planilha = gc.open_by_key("1u2Iza-ocp6ROUBXG9GpfHvEJwLHuW7F2uiO583qqLIE")

    # Acessar a aba "BD_saldo_diario"
    aba = planilha.worksheet("saldo de recurso (incluindo em processo)")

    # Defina o intervalo (range) que você deseja apagar (por exemplo, A2:H5)
    range_to_clear = "A2:Z"
    
    df.rename(columns=lambda x: x.replace('="', '').replace('"', ''), inplace=True)
    
    df = limpar_valores_dataframe(df)

    df['Saldo'] = df['Saldo'].apply(lambda x: float(x.replace(".","").replace(",",".")))
    df['Custo#Total'] = df['Custo#Total'].apply(lambda x: float(x.replace(".","").replace(",",".")))
    df['Custo#Médio'] = df['Custo#Médio'].apply(lambda x: float(x.replace(".","").replace(",",".")))
    
    df['2o. Agrupamento'] = df['2o. Agrupamento'].apply(lambda x: str(x).replace('nan', ''))

    df['codigo'] = df['3o. Agrupamento'].apply(lambda x: x.split()[0])
    # df['descricao'] = df['3o. Agrupamento'].apply(lambda x: x.split('-')[1])
    # df['descricao'] = df['3o. Agrupamento'].str.split('-', n=1).str[1].str.strip()
    df['descricao'] = df['3o. Agrupamento'].apply(
        lambda x: x.split('-', 1)[1].strip() if '-' in x else x
    )
    
    df = df[['1o. Agrupamento', '2o. Agrupamento','codigo','descricao','3o. Agrupamento', 'Recurso#Unid. Medida','Saldo','Custo#Total','Custo#Médio','data']]
    df_values = df.values.tolist()

    if len(df_values) > 0:
    
        # Obtém a lista de células no intervalo especificado
        cell_list = aba.range(range_to_clear)
        
        # Define o valor de todas as células no intervalo como uma string vazia ('')
        for cell in cell_list:
            cell.value = ""
        
        # Atualiza as células no intervalo com os valores vazios
        aba.update_cells(cell_list)

        planilha.values_append("saldo de recurso (incluindo em processo)", {'valueInputOption': 'RAW'}, {'values': df_values})

    return 'sucess'
