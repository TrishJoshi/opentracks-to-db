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


# --- PROTECTED UPLOAD ROUTE ---
@app.post("/upload")
async def upload_kmz_file(
        file: UploadFile = File(...),
        current_user: models.User = Depends(auth.get_current_user),  # <--- PROTECTED
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