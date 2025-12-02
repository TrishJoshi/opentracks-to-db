from fastapi import FastAPI, File, UploadFile, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
import models, database, parser

# NOTE: We removed the `models.Base.metadata.create_all(bind=database.engine)` line.
# Table creation is now handled entirely by Alembic migrations.

app = FastAPI(title="OpenTracks Importer")

@app.get("/", response_class=HTMLResponse)
async def get_upload_page():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Upload OpenTracks KMZ</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                   display: grid; place-items: center; min-height: 100vh; margin: 0; background-color: #f0f2f5; color: #1c1e21; }
            .container { background: #ffffff; padding: 2rem 2.5rem; border-radius: 12px;
                         box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1), 0 8px 16px rgba(0, 0, 0, 0.1);
                         width: 100%; max-width: 480px; text-align: center; }
            h1 { margin-bottom: 1.5rem; color: #1c1e21; font-weight: 600; }
            .upload-area { border: 2px dashed #ced0d4; border-radius: 8px; padding: 2rem;
                           margin-bottom: 1.5rem; transition: border-color 0.2s; cursor: pointer; }
            .upload-area:hover { border-color: #1877f2; }
            input[type="file"] { display: none; }
            .file-label { display: block; cursor: pointer; font-size: 1.1rem; color: #65676b; }
            .file-icon { font-size: 3rem; color: #1877f2; margin-bottom: 1rem; }
            #fileName { margin-top: 1rem; font-weight: 500; color: #1877f2; word-break: break-all; }
            button { background-color: #1877f2; color: white; border: none; padding: 0.875rem 2rem;
                     border-radius: 6px; font-size: 1rem; font-weight: 600; cursor: pointer;
                     transition: background-color 0.2s; width: 100%; }
            button:hover { background-color: #166fe5; }
            button:disabled { background-color: #e4e6eb; color: #bcc0c4; cursor: not-allowed; }
            #message { margin-top: 1.5rem; padding: 1rem; border-radius: 6px; font-weight: 500; display: none; text-align: left; }
            .success { background-color: #e7f3ff; color: #1877f2; border: 1px solid #1877f2; }
            .error { background-color: #ffebe8; color: #dc3545; border: 1px solid #dc3545; }
            .loading { opacity: 0.7; cursor: not-allowed; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Upload OpenTracks KMZ</h1>
            <form id="uploadForm">
                <label for="fileInput" class="upload-area">
                    <div class="file-icon">📁</div>
                    <span class="file-label">Choose a .kmz file or drag it here</span>
                    <div id="fileName"></div>
                </label>
                <input type="file" name="file" id="fileInput" accept=".kmz" required>
                <button type="submit" id="submitBtn" disabled>Upload Activity</button>
            </form>
            <div id="message"></div>
        </div>
        <script>
            const form = document.getElementById('uploadForm');
            const fileInput = document.getElementById('fileInput');
            const fileNameDisplay = document.getElementById('fileName');
            const submitBtn = document.getElementById('submitBtn');
            const messageEl = document.getElementById('message');

            fileInput.addEventListener('change', (e) => {
                if (fileInput.files.length > 0) {
                    fileNameDisplay.textContent = fileInput.files[0].name;
                    submitBtn.disabled = false;
                } else {
                    fileNameDisplay.textContent = '';
                    submitBtn.disabled = true;
                }
            });

            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                submitBtn.textContent = 'Uploading...';
                submitBtn.classList.add('loading');
                submitBtn.disabled = true;
                messageEl.style.display = 'none';

                const formData = new FormData();
                formData.append('file', fileInput.files[0]);

                try {
                    const response = await fetch('/upload', { method: 'POST', body: formData });
                    const result = await response.json();

                    messageEl.style.display = 'block';
                    if (response.ok) {
                        messageEl.className = 'success';
                        messageEl.innerHTML = `✅ <strong>Success!</strong><br>Track: ${result.track_name}<br>ID: ${result.track_id}`;
                        form.reset();
                        fileNameDisplay.textContent = '';
                    } else {
                        messageEl.className = 'error';
                        messageEl.innerHTML = `❌ <strong>Error:</strong><br>${result.detail}`;
                    }
                } catch (err) {
                    messageEl.style.display = 'block';
                    messageEl.className = 'error';
                    messageEl.textContent = `Network Error: ${err.message}`;
                } finally {
                    submitBtn.textContent = 'Upload Activity';
                    submitBtn.classList.remove('loading');
                    // Only re-enable if there is still a file selected (mostly for retries if needed, though form reset clears it)
                     if (fileInput.files.length > 0) submitBtn.disabled = false;
                }
            });
        </script>
    </body>
    </html>
    """

@app.post("/upload")
async def upload_kmz_file(file: UploadFile = File(...), db: Session = Depends(database.get_db)):
    if not file.filename.endswith('.kmz'):
        raise HTTPException(status_code=400, detail="Invalid file type. Only .kmz files are accepted.")

    try:
        file_content = await file.read()
        new_track = parser.parse_kmz_file(file_content, db)
        return JSONResponse(status_code=201, content={
            "message": "File processed successfully",
            "track_id": new_track.id,
            "track_name": new_track.name
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")
