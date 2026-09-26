from fastapi import FastAPI
import ingestion.upload as upload

app = FastAPI(title="File Upload API")

# Include the router from upload.py
app.include_router(upload.router)

@app.get("/")
def read_root():
    return {"message": "Welcome to the File Upload API. Go to /docs to test."}
