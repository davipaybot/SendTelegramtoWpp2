# Usa uma imagem base Python
FROM python:3.11.9-slim

# Defina o diretório de trabalho dentro do container
WORKDIR /app

# Copie o arquivo de dependências para dentro do container
COPY requirements.txt ./

# Instala as dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Copie o restante do código para dentro do container
COPY . .

# Exponha a porta 5000 (porta do Quart)
EXPOSE 8080

# Comando para rodar o aplicativo Quart
CMD ["python", "sendWppGroups.py"]
