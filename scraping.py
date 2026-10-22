import json
from datetime import datetime
from dotenv import load_dotenv
import os, sys
import psycopg2
import requests

load_dotenv()

BASE_URL = os.getenv("GITLAB_URL")

created_after='2026-06-30T23:59:59Z'
created_before='2026-10-31T23:59:59Z'

conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    database=os.getenv("DB_NAME", "gitlab_data"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD"),
)


def criaTabelas(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS projetos (
            id BIGINT PRIMARY KEY,
            name TEXT,
            url TEXT
        );
        CREATE TABLE IF NOT EXISTS pipelines (
            id BIGINT PRIMARY KEY,
            project_id BIGINT REFERENCES projetos(id),
            ref TEXT,
            status TEXT,
            queue_seconds REAL,
            duration_seconds REAL,
            total_duration_seconds REAL,
            created_at TIMESTAMP,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            url TEXT,
            user_username TEXT
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id BIGINT PRIMARY KEY,
            pipeline_id BIGINT REFERENCES pipelines(id),
            project_id BIGINT REFERENCES projetos(id),
            name TEXT,
            duration_seconds REAL,
            queue_seconds REAL,
            total_duration_seconds REAL,
            created_at TIMESTAMP,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            ref TEXT,
            status TEXT,
            url TEXT,
            author_name TEXT

        );
    """)
    conn.commit()


def realizaRequest(path):
    url = f"{BASE_URL}{path}"
    headers = {
        "PRIVATE-TOKEN": os.getenv("PRIVATE_TOKEN"),
        "Content-Type": "application/json",
    }
    print(url)
    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        print(f"Erro no servidor: {res.text}")
        exit(1)
    return res


def getProjectById(id):
    res = realizaRequest(f"/projects/{id}")
    projeto = res.json()
    return {
        "id": projeto["id"],
        "name": projeto["name"],
        "url": projeto["web_url"],
    }


def calcular_segundos(string_inicio, string_fim):
    if not string_inicio or not string_fim:
        return 0
    # O replace('Z', '+00:00') trata o fuso horário UTC
    # O Python identifica os milissegundos automaticamente
    dt_inicio = datetime.fromisoformat(string_inicio.replace("Z", "+00:00"))
    dt_fim = datetime.fromisoformat(string_fim.replace("Z", "+00:00"))

    diferenca = dt_fim - dt_inicio
    return diferenca.total_seconds()


def getJobsByPipelineId(projectId, pipelineId, cur):
    vazio = False
    page = 1
    while not vazio:
        res = realizaRequest(
            f"/projects/{projectId}/pipelines/{pipelineId}/jobs?page={page}&per_page=100&created_after={created_after}&created_before={created_before}"
        )
        jobs = res.json()
        vazio = len(jobs) < 100
        page += 1
        for job in jobs:
            try:
                segundos = calcular_segundos(job["started_at"], job["finished_at"])
                cur.execute(
                    """
                            INSERT INTO jobs (id, pipeline_id, project_id, name, duration_seconds, queue_seconds, total_duration_seconds, created_at, started_at, finished_at, ref, status, url, author_name)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                    (
                        job["id"],
                        pipelineId,
                        projectId,
                        job["name"],
                        job["duration"],
                        job["queued_duration"],
                        segundos,
                        job["created_at"],
                        job["started_at"],
                        job["finished_at"],
                        job["ref"],
                        job["status"],
                        job["web_url"],
                        job["user"]["username"] if job["user"] else None,
                    ),
                )
                conn.commit()
            except Exception as e:
                print(e)
                conn.rollback()


def getPipelinesByProjectId(projectId, cur):
    vazio = False
    page = 1
    while not vazio:
        res = realizaRequest(
            f"/projects/{projectId}/pipelines?page={page}&per_page=100&created_after={created_after}&created_before={created_before}"
        )
        pipelines = res.json()
        vazio = len(pipelines) < 100
        page += 1
        for p in pipelines:
            res = realizaRequest(f"/projects/{projectId}/pipelines/{p['id']}")
            pipeline = res.json()
            try:
                segundos = calcular_segundos(
                    pipeline["started_at"], pipeline["finished_at"]
                )
                cur.execute(
                    """
                INSERT INTO pipelines (id, project_id, ref, queue_seconds, status, duration_seconds, total_duration_seconds, created_at, started_at, finished_at, url, user_username)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
                    (
                        pipeline["id"],
                        projectId,
                        pipeline["ref"],
                        pipeline["queued_duration"],
                        pipeline["status"],
                        pipeline["duration"],
                        segundos,
                        pipeline["created_at"],
                        pipeline["started_at"],
                        pipeline["finished_at"],
                        pipeline["web_url"],
                        pipeline["user"]["username"] if pipeline["user"] else None,
                    ),
                )
                conn.commit()
                getJobsByPipelineId(projectId, pipeline["id"], cur)
            except Exception as e:
                conn.rollback()
                print(e)


caminho_arquivo = 'projetos.json'

with conn.cursor() as cur:
    criaTabelas(cur)
    with open(caminho_arquivo, "r", encoding="utf-8") as arquivo:
        dados = json.load(arquivo)
        for item in dados:
            projectId = item['id']
            projeto = getProjectById(projectId)
            try:
                cur.execute(
                    """
                                    INSERT INTO projetos (id, name, url)
                                    VALUES (%s, %s, %s)
                                """,
                    (projeto["id"], projeto["name"], projeto["url"]),
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                print(e)    
            getPipelinesByProjectId(projeto["id"], cur)
conn.commit()
conn.close()
