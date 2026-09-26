# upload.py
from fastapi import APIRouter, File, UploadFile, HTTPException
from pathlib import Path
import shutil

# Use an APIRouter to modularize the code
router = APIRouter()

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
}

@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    Endpoint accepting PDF, TXT, and MD files.
    """
    file_ext = Path(file.filename).suffix.lower()

    if file_ext not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{file_ext}'. Only .pdf, .txt, and .md files are allowed."
        )

    dest_path = UPLOAD_DIR / file.filename

    try:
        with dest_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not save file: {str(e)}")
    finally:
        file.file.close()

    return {
        "filename": file.filename,
        "content_type": file.content_type,
        "size_bytes": dest_path.stat().st_size,
        "message": "File uploaded successfully"
    }
