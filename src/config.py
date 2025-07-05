from dotenv import load_dotenv
import os

load_dotenv()


class Config:
    QUESTDB_HOST = os.getenv("QUESTDB_HOST")
    QUESTDB_PORT = os.getenv("QUESTDB_PORT")
    QUESTDB_USER = os.getenv("QUESTDB_USER")
    QUESTDB_PASSWORD = os.getenv("QUESTDB_PASSWORD")
    QUESTDB_DATABASE = os.getenv("QUESTDB_DATABASE")
