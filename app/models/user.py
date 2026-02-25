from sqlmodel import Field, SQLModel


class UserBase(SQLModel):
    email: str = Field(unique=True, index=True)
    full_name: str | None = None
    is_google_account: bool = False


class User(UserBase, table=True):
    __tablename__ = "users"
    id: int | None = Field(default=None, primary_key=True)
    hashed_password: str | None = None  # None for Google-only users


class UserCreate(SQLModel):
    email: str
    password: str
    full_name: str | None = None


class UserUpdate(SQLModel):
    full_name: str | None = None


class UserPublic(SQLModel):
    id: int
    email: str
    full_name: str | None = None
    is_google_account: bool
