import os
import re
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document
import openai
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Установка API ключа OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Создаем экземпляр FastAPI
app = FastAPI()

# Модель для приема данных
class Question(BaseModel):
    query: str

# Переменная для хранения количества обращений
total_requests = 0

# Функция для загрузки текста с Google Docs
def load_document_text(url: str) -> str:
    match_ = re.search('/document/d/([a-zA-Z0-9-_]+)', url)
    if match_ is None:
        raise ValueError('Invalid Google Docs URL')
    doc_id = match_.group(1)
    response = requests.get(f'https://docs.google.com/document/d/{doc_id}/export?format=txt')
    response.raise_for_status()
    return response.text

# Загрузка базы знаний с Google Docs
data_from_url = load_document_text('https://docs.google.com/document/d/11MU3SnVbwL_rM-5fIC14Lc3XnbAV4rY1Zd_kpcMuH4Y')

# Разделение текста на чанки
source_chunks = []
splitter = RecursiveCharacterTextSplitter(chunk_size=1024, chunk_overlap=50)
for chunk in splitter.split_text(data_from_url):
    source_chunks.append(Document(page_content=chunk, metadata={}))

# Инициализация эмбеддингов и FAISS
embeddings = OpenAIEmbeddings()
db = FAISS.from_documents(source_chunks, embeddings)

# Функция для форматирования ответа
def insert_newlines(text: str, max_len: int = 170) -> str:
    words = text.split()
    lines = []
    current_line = ""
    for word in words:
        if len(current_line + " " + word) > max_len:
            lines.append(current_line)
            current_line = ""
        current_line += " " + word
    lines.append(current_line)
    return "\n".join(lines)

# Основная функция для обработки вопросов
def get_answer(query: str):
    global total_requests
    total_requests += 1

    # Поиск релевантных отрезков из базы знаний
    docs = db.similarity_search(query, k=5)
    message_content = '\n'.join([f'{doc.page_content}' for doc in docs])

    messages = [
        {"role": "system", "content": "Ты нейро-консультант по страхованию. Отвечай на вопросы клиентов четко и по теме, не упоминая документ."},
        {"role": "user", "content": f"Ответь на вопрос клиента, используя информацию: {message_content}. Вопрос: {query}"}
    ]

    completion = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=messages,
        temperature=0
    )
    return insert_newlines(completion.choices[0].message.content)

# Маршрут для ответа на вопросы
@app.post("/api/get_answer")
def get_answer_endpoint(question: Question):
    try:
        answer = get_answer(question.query)
        return {"query": question.query, "answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Маршрут для получения количества обращений
@app.get("/api/requests_count")
def get_requests_count():
    return {"total_requests": total_requests}
