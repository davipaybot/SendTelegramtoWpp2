from telethon import TelegramClient
from dotenv import load_dotenv
import os
import logging
import requests
from quart import Quart, request, jsonify  # Quart no lugar de Flask
from collections import deque
import asyncio
import threading

# Carregar as variáveis de ambiente
load_dotenv(".env")

# Configurações do cliente do Telegram
API_ID = int(os.getenv("API_ID", "").strip())
API_HASH = os.getenv("API_HASH", "").strip()
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "").strip())  # Canal Telegram a ser monitorado
GROUP_IDS = os.getenv("GROUP_IDS", "").split(",")  # Grupos do WhatsApp para envio

# Fila para processar mensagens
message_queue = deque()

# Conjunto para armazenar IDs das mensagens enviadas
sent_message_ids = set()

# Inicializa o cliente do Telethon
client = TelegramClient('session_name', API_ID, API_HASH)

# Diretório para salvar as imagens
download_folder = "downloads/"

# Quart para receber a nova requisição
app = Quart(__name__)

# URL da API para o WhatsApp
api_url = "https://sendtelegramtowpp-production.up.railway.app/send"

# Função para enviar a mensagem ao WhatsApp
async def send_whatsapp_message(phone=None, group_id=None, message="", image=None):
    """
    Envia mensagens para grupos do WhatsApp via API local.
    """
    if not message and not image:
        return {"error": "Você deve fornecer uma mensagem ou uma imagem."}

    if not phone and not group_id:
        return {"error": "Você deve fornecer um número de telefone ou um ID de grupo."}

    data = {}
    if phone:
        data["phone"] = phone
    if group_id:
        data["group"] = group_id
    if message:
        data["message"] = message

    files = None
    if image:
        files = {"image": open(image, "rb")}

    try:
        if files:
            response = await asyncio.to_thread(requests.post, api_url, data=data, files=files)
        else:
            response = await asyncio.to_thread(requests.post, api_url, json=data)

        if response.status_code == 200:
            logging.info(f"Mensagem enviada para {group_id} com sucesso.")
        else:
            logging.error(f"Falha ao enviar mensagem para {group_id}: {response.text}")

        return response.json() if response.status_code == 200 else {"error": response.text}
    except requests.exceptions.RequestException as e:
        logging.error(f"Erro ao enviar mensagem para {group_id}: {str(e)}")
        return {"error": str(e)}
    finally:
        if files:
            files["image"].close()


# Função para processar uma mensagem recebida no Telegram
async def process_message(message):
    """
    Processa uma única mensagem do Telegram para envio ao WhatsApp.
    """
    try:
        if message.id in sent_message_ids:
            logging.info(f"Mensagem {message.id} já processada. Ignorando.")
            return

        # Salva o ID da mensagem para evitar duplicatas
        sent_message_ids.add(message.id)

        image_path = None

        # Verifica se a mensagem contém uma imagem
        if message.photo:
            image_path = await client.download_media(
                message.photo,
                file=os.path.join(download_folder, f"photo_{message.id}.png")
            )
            logging.info(f"Imagem salva em: {image_path}")

        # Captura o texto da mensagem
        message_text = message.text or ""
        logging.info(f"Texto da mensagem:\n {message_text}")

        # Envia a mensagem para cada grupo do WhatsApp
        for group_id in GROUP_IDS:
            response = await send_whatsapp_message(
                group_id=group_id.strip(),
                message=message_text,
                image=image_path
            )
            logging.info(f"Enviado para {group_id.strip()}: {response}")

        # Remove a imagem baixada após o envio
        if image_path and os.path.exists(image_path):
            os.remove(image_path)
            logging.info(f"Imagem removida: {image_path}")

    except Exception as e:
        print(f"Erro ao processar mensagem\n {message.id}: {e}")


# Quart API para receber novas mensagens e enviá-las ao WhatsApp
@app.route('/send_message', methods=['POST'])
async def handle_new_message():
    """
    Endpoint para enviar uma mensagem ao WhatsApp via a API
    """
    try:
        data = await request.json
        message = data.get("message")
        group_id = data.get("group_id")
        image = data.get("image")  # Caminho da imagem

        if not message and not image:
            return jsonify({"error": "Mensagem ou imagem não fornecida."}), 400

        if group_id:
            logging.info(f"Enviando mensagem para o grupo {group_id}")
            # Enviar a mensagem para o grupo
            response = await send_whatsapp_message(group_id=group_id, message=message, image=image)
            return jsonify(response)

        else:
            return jsonify({"error": "Grupo não especificado."}), 400

    except Exception as e:
        logging.error(f"Erro ao processar a requisição: {str(e)}")
        return jsonify({"error": "Erro ao processar a requisição"}), 500


# Função para iniciar o cliente do Telegram
async def start_telegram():
    await client.start()
    logging.info("Cliente Telegram iniciado.")
    await monitor_channel()


# Função de monitoramento do canal
async def monitor_channel():
    """
    Monitora o canal do Telegram e envia as mensagens para o WhatsApp.
    """
    logging.info(f"Iniciando monitoramento do canal {CHANNEL_ID}...")

    while True:
        try:
            messages = await client.get_messages(CHANNEL_ID, limit=1)

            for message in messages:
                if message.id not in sent_message_ids:
                    message_queue.append(message)

            while message_queue:
                msg = message_queue.popleft()
                await process_message(msg)

            await asyncio.sleep(5)  # Aguarda antes de buscar novas mensagens
        except Exception as e:
            logging.error(f"Erro no monitoramento: {e}")
            await asyncio.sleep(5)


# Função principal para iniciar a aplicação
async def main():
    await client.start()
    logging.info("Cliente conectado ao Telegram.")
    await monitor_channel()


if __name__ == '__main__':
    t = threading.Thread(target=lambda: asyncio.run(start_telegram()))
    t.start()

    port = int(os.environ.get("PORT", 8080))
    # Iniciar o Quart para ouvir as requisições
    app.run(host="0.0.0.0", port=port)  # Rodar o Quart, não Flask, agora
