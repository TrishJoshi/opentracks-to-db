from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
# REMOVE: from passlib.context import CryptContext
import bcrypt  # <--- ADD THIS
from sqlalchemy.orm import Session
from pydantic import BaseModel
import models
import database

# --- CONFIGURATION ---
# In a real production app, move SECRET_KEY to an environment variable!
SECRET_KEY = "CHANGE_THIS_TO_A_REALLY_LONG_RANDOM_STRING_IN_PROD"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 10080  # 1 week

# REMOVE: Password Hashing
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# --- SCHEMAS ---
class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class UserCreate(BaseModel):
    username: str
    password: str


class PasswordReset(BaseModel):
    old_password: str
    new_password: str


# --- UTILS ---
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Checks if the plain password matches the hashed password.
    Bcrypt requires bytes, so we encode the inputs.
    """
    if not plain_password or not hashed_password:
        return False

    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except ValueError:
        # Handles cases where the hash format might be invalid
        return False


def get_password_hash(password: str) -> str:
    """
    Generates a bcrypt hash for the password.
    Returns a string for storage in the database.
    """
    # 1. Generate salt and hash
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(pwd_bytes, salt)

    # 2. Decode bytes to string for database storage
    return hashed_bytes.decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# --- DEPENDENCIES ---
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(database.get_db)):
    """
    Decodes the token from the header and fetches the user from the DB.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.username == token_data.username).first()
    if user is None:
        raise credentials_exception
    return user