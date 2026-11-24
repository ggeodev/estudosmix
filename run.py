from app import create_app
from app.config import Config

app = create_app()

if __name__ == "__main__":
    print(f"\n  Estudos rodando em http://{Config.HOST}:{Config.PORT}\n  Banco: {app.config['DATABASE_PATH']}\n")
    app.run(host=Config.HOST, port=Config.PORT, debug=False)
