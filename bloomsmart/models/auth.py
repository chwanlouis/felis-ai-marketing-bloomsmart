from pydantic import BaseModel, Field


class EmailLoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1)


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(min_length=1)


class SetPasswordRequest(BaseModel):
    user_id: str
    password: str = Field(min_length=8)
