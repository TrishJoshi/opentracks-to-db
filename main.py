from fastapi import FastAPI, File, UploadFile, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import timedelta
import models, database, parser, auth

# Initialize Database (or rely on Alembic)
# models.Base.metadata.create_all(bind=database.engine) # We use Alembic now

app = FastAPI(title="OpenTracks Importer")

# Setup Templates
templates = Jinja2Templates(directory="templates")


# --- HTML ROUTES ---
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})


@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    # Default to upload page (which will redirect to login if no token)
    return templates.TemplateResponse("upload.html", {"request": request})


# --- AUTH ROUTES ---
@app.post("/register", status_code=status.HTTP_201_CREATED)
async def register(user: auth.UserCreate, db: Session = Depends(database.get_db)):
    # Check if user exists
    existing_user = db.query(models.User).filter(models.User.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")

    # Create User
    hashed_pw = auth.get_password_hash(user.password)
    new_user = models.User(username=user.username, hashed_password=hashed_pw)
    db.add(new_user)
    db.commit()
    return {"message": "User created successfully"}


@app.post("/token", response_model=auth.Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(),
                                 db: Session = Depends(database.get_db)):
    # 1. Fetch user
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    # 2. Verify password
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # 3. Create Token
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/reset-password")
async def reset_password(
        pw_data: auth.PasswordReset,
        current_user: models.User = Depends(auth.get_current_user),
        db: Session = Depends(database.get_db)
):
    # Verify old password
    if not auth.verify_password(pw_data.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect old password")

    # Update with new hash
    current_user.hashed_password = auth.get_password_hash(pw_data.new_password)
    db.commit()
    return {"message": "Password updated successfully"}

@app.post("/generate-api-key")
async def generate_api_key_endpoint(
        current_user: models.User = Depends(auth.get_current_user),
        db: Session = Depends(database.get_db)
):
    """
    Generates a new API key for the user, invalidating the old one.
    Returns the raw key ONCE. The server only stores the hash.
    """
    new_key = auth.generate_api_key()
    new_hash = auth.hash_api_key(new_key)

    current_user.api_key_hash = new_hash
    db.commit()

    return {"api_key": new_key, "message": "Save this key! It won't be shown again."}

@app.post("/upload")
async def upload_kmz_file(
        file: UploadFile = File(...),
        current_user: models.User = Depends(auth.get_current_user_or_api_key),
        db: Session = Depends(database.get_db)
):
    if not file.filename.endswith('.kmz'):
        raise HTTPException(status_code=400, detail="Invalid file type. Only .kmz files are accepted.")

    try:
        file_content = await file.read()
        # Pass the user.id to the parser so it's associated with the track
        new_track = parser.parse_kmz_file(file_content, db, current_user.id)

        return JSONResponse(status_code=201, content={
            "message": "File processed successfully",
            "track_id": new_track.id,
            "track_name": new_track.name,
            "owner": current_user.username
        })

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error.")


@app.get("/tracks")
async def get_tracks(
        current_user: models.User = Depends(auth.get_current_user),
        db: Session = Depends(database.get_db)
):
    """
    Returns a list of tracks.
    - Admins see ALL tracks.
    - Regular users see only THEIR tracks.
    """
    if current_user.is_admin:
        tracks = db.query(models.Track).order_by(models.Track.start_time.desc()).all()
    else:
        tracks = db.query(models.Track).filter(models.Track.user_id == current_user.id).order_by(
            models.Track.start_time.desc()).all()

    # Return a simplified list suitable for JSON
    return [
        {
            "id": t.id,
            "name": t.name,
            "date": t.start_time.strftime('%Y-%m-%d %H:%M') if t.start_time else "Unknown",
            "distance": f"{float(t.total_distance_m) / 1000:.2f} km" if t.total_distance_m else "0 km",
            "owner_id": t.user_id
        }
        for t in tracks
    ]


@app.delete("/tracks/{track_id}")
async def delete_track(
        track_id: int,
        current_user: models.User = Depends(auth.get_current_user),
        db: Session = Depends(database.get_db)
):
    """
    Deletes a track.
    - Admins can delete ANY track.
    - Users can only delete THEIR own tracks.
    """
    track = db.query(models.Track).filter(models.Track.id == track_id).first()
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")

    # Permission Check
    if not current_user.is_admin and track.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this track")

    # SQLAlchemy handles the cascade delete of points because of 'cascade="all, delete-orphan"' in models.py
    db.delete(track)
    db.commit()

    return {"message": f"Track {track_id} deleted successfully"}