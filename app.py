import os
import numpy as np
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()

app = Flask(__name__)
CORS(app)

def save_to_google_sheet(name, email, phone, requirement):
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = ServiceAccountCredentials.from_json_keyfile_name(
        "credentials.json", scope
    )
    client = gspread.authorize(creds)

    sheet = client.open("Leads").sheet1

    sheet.append_row([
        name,
        email,
        phone,
        requirement,
        str(datetime.now())
    ])

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 🔴 ADD YOUR META DETAILS HERE
ACCESS_TOKEN = "EAArBzCPubZAwBREnLAa5oMhMMK9HNsDZAzQl4X8ZCXvHG2V0S2n2ZCEyIO4rYVCL7jTMoZCoeZB5CT24Fe3yfw1x1ZAbG4XUHqeKuTqO5lWiqKLglK2Gt1SCXqGC1a1uDXRU69rdavwDYo6jIPDtIDuHO05JIsTc6XScwaOXUNqpcGYd273HTxEJbGYeFelLj0cttuI3aAp0EyeHd2LGelnRTe3IUPJ1b10PSZCWb7WgZAJNQh3rSeLQYk1zv70V7WSJS7GzKO7nnAxwFcdSyAnX9rQZDZD"
PHONE_NUMBER_ID = "1040574379142944"
VERIFY_TOKEN = "my_verify_token"

# Load embeddings
embeddings_data = np.load("embeddings.npy", allow_pickle=True)

# 🧠 Memory (per user)
user_memory = defaultdict(list)

# 🔍 Cosine similarity


def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

# 🔍 Get relevant context (Embeddings RAG)


def get_relevant_context(query):
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=query
    )

    query_embedding = response.data[0].embedding

    scored = []

    for item in embeddings_data:
        score = cosine_similarity(query_embedding, item["embedding"])
        scored.append((score, item["text"]))

    scored.sort(reverse=True)

    top_chunks = [text for score, text in scored[:5]]

    return "\n".join(top_chunks)

# 🤖 Chat function


def chat(user_id, user_message):
    context = get_relevant_context(user_message)

    SYSTEM_PROMPT = f"""
You are a chatbot for the website reikigyan.in.

STRICT RULES:
- Answer ONLY about Reiki
- Use the CONTEXT below
- Do NOT make up information
- Do NOT give phone/email/address
- If unrelated question → say:
  "I can only help with Reiki-related queries."
- If answer not found → say:
  "Please check the official website reikigyan.in"

CONTEXT:
{context}
"""

    messages = user_memory[user_id]

    if not messages:
        messages.append({"role": "system", "content": SYSTEM_PROMPT})

    messages.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages[-6:],
        max_tokens=150
    )

    reply = response.choices[0].message.content

    messages.append({"role": "assistant", "content": reply})

    return reply

# 🔥 SEND MESSAGE TO WHATSAPP


def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }

    response = requests.post(url, headers=headers, json=payload)
    print("WhatsApp API Response:", response.text)

# 🔥 WHATSAPP WEBHOOK


@app.route("/webhook", methods=["GET", "POST"])
def webhook():

    # ✅ Verification
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if mode == "subscribe" and token == VERIFY_TOKEN:
            return challenge, 200
        else:
            return "Verification failed", 403

    # ✅ Receive message
    elif request.method == "POST":
        data = request.get_json()

        try:
            value = data["entry"][0]["changes"][0]["value"]

            if "messages" in value:
                msg = value["messages"][0]

                if msg["type"] == "text":
                    user_msg = msg["text"]["body"]
                    phone = msg["from"]

                    print("User:", user_msg)

                    # 🔥 Use phone as user_id (for memory)
                    reply = chat(phone, user_msg)

                    send_whatsapp_message(phone, reply)

        except Exception as e:
            print("Error:", e)

        return "OK", 200

# 🌐 EXISTING API (UNCHANGED)


@app.route("/chat", methods=["POST"])
def chatbot():
    data = request.get_json(silent=True) or {}

    user_message = data.get("message")
    user_id = data.get("user_id", "default_user")

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    try:
        reply = chat(user_id, user_message)
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/save-lead", methods=["POST"])
def save_lead():
    try:
        data = request.json

        save_to_google_sheet(
            data.get("name"),
            data.get("email"),
            data.get("phone"),
            data.get("requirement")
        )

        return jsonify({"status": "success"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
    
# Home
@app.route("/")
def home():
    return "Reiki chatbot with RAG + Memory + WhatsApp is running"


# Run
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)  # for Prod env
#    app.run(host="0.0.0.0", port=5000, debug=True)  #for debudding in Dev env
