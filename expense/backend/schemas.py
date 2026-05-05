from pydantic import BaseModel
from typing import List, Optional

# --- Account Schemas ---
class AccountBase(BaseModel):
    name: str
    balance: float = 0.0

class AccountCreate(AccountBase):
    pass

class Account(AccountBase):
    id: int

    class Config:
        orm_mode = True

# --- Category Schemas ---
class CategoryBase(BaseModel):
    name: str

class CategoryCreate(CategoryBase):
    pass

class Category(CategoryBase):
    id: int

    class Config:
        orm_mode = True

# --- Record Schemas ---
class RecordBase(BaseModel):
    date: str
    description: str
    amount: float
    type: str
    account_id: int
    category_id: int

class RecordCreate(RecordBase):
    pass

class Record(RecordBase):
    id: int
    account: Account
    category: Category

    class Config:
        orm_mode = True
