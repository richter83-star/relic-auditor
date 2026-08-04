from fastapi import FastAPI
from service import create_analysis

app = FastAPI()

@app.post("/api/login")
def login():
    return {"token": "demo"}

@app.post("/api/documents")
def upload_document(document):
    return create_analysis(document)
