import os
import asyncio
import tempfile
import shutil
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from transcriber import transcribe_audio, write_transcripts

app = FastAPI()

# Mount static files and templates directory
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Maximum allowed file size (400 MB)
MAX_FILE_SIZE = 400 * 1024 * 1024

# Model volumes (shared with the telegram bot container)
MODEL_PATHS = {
    'fa': '/models/fa_model',
    'en': '/models/en_model',
}

async def process_upload(file_path: str, lang: str, file_type: str):
    """
    Process the uploaded file:
    1. Convert to WAV mono 16k using ffmpeg asynchronously.
    2. Transcribe the audio in a thread.
    3. Write transcript and subtitle files (offloaded to a thread).
    4. For audio: return raw text. For video: merge subtitles with video.
    """
    # Convert file to WAV mono 16k using ffmpeg asynchronously
    wav_path = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", file_path,
        "-ac", "1", "-ar", "16000",
        wav_path
    ]
    proc = await asyncio.create_subprocess_exec(*ffmpeg_cmd)
    await proc.communicate()
    
    # Transcribe the audio using the selected model (run in a thread)
    model_path = MODEL_PATHS.get(lang)
    results = await asyncio.to_thread(transcribe_audio, model_path, wav_path)
    
    # Write transcripts (temporary files) in a thread
    txt_file = tempfile.NamedTemporaryFile(suffix=".txt", delete=False).name
    srt_file = tempfile.NamedTemporaryFile(suffix=".srt", delete=False).name
    await asyncio.to_thread(write_transcripts, results, txt_file, srt_file)
    
    if file_type in ['audio', 'voice']:
        # Read raw text and cleanup temporary files
        with open(txt_file, "r", encoding="utf-8") as f:
            raw_text = f.read().strip()
        for fpath in [wav_path, txt_file, srt_file]:
            try:
                os.remove(fpath)
            except Exception:
                pass
        return {"result": "text", "data": raw_text}
    elif file_type == 'video':
        # Merge video with subtitles using ffmpeg asynchronously to create an MKV file
        merged_path = tempfile.NamedTemporaryFile(suffix=".mkv", delete=False).name
        merge_cmd = [
            "ffmpeg", "-y", "-i", file_path, "-vf", f"subtitles={srt_file}",
            merged_path
        ]
        proc = await asyncio.create_subprocess_exec(*merge_cmd)
        await proc.communicate()
        for fpath in [wav_path, txt_file, srt_file]:
            try:
                os.remove(fpath)
            except Exception:
                pass
        return {"result": "file", "file": merged_path}
    else:
        for fpath in [wav_path, txt_file, srt_file]:
            try:
                os.remove(fpath)
            except Exception:
                pass
        raise HTTPException(status_code=400, detail="Unsupported file type.")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """
    Renders the landing page with a gradient background and theme toggle.
    """
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/upload", response_class=JSONResponse)
async def upload(request: Request,
                 language: str = Form(...),
                 file: UploadFile = File(...)):
    """
    Endpoint for handling file uploads.
    - Accepts one file (audio/video) up to 400 MB.
    - Converts, transcribes, and returns raw text for audio or an MKV video with subtitles.
    - Returns a JSON response or a direct file response.
    """
    # Check file size if provided in headers
    if 'content-length' in request.headers:
        content_length = int(request.headers['content-length'])
        if content_length > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File too large. Max size is 400 MB.")

    # Save uploaded file to a temporary directory
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Determine file type (by MIME type)
    file_type = file.content_type.split('/')[0]
    try:
        result = await process_upload(file_path, language, file_type)
    except Exception as e:
        shutil.rmtree(tmp_dir)
        raise HTTPException(status_code=500, detail=str(e))
    
    # Cleanup temporary upload file
    shutil.rmtree(tmp_dir)
    
    if result["result"] == "text":
        return {"result": "text", "data": result["data"]}
    elif result["result"] == "file":
        # Return the processed video file as a FileResponse.
        return FileResponse(result["file"], filename="result.mkv")
    else:
        raise HTTPException(status_code=500, detail="Unknown error.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=5000, reload=False)
