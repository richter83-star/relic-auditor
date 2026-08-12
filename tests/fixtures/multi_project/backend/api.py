from fastapi import FastAPI
app = FastAPI()
@app.post("/api/intake")
def intake(item):
    return save_item(item)
