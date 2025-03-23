from flask import Flask, render_template, request, jsonify, session
from openai import OpenAI
import os
import uuid
import json
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.urandom(24)

# إعداد OpenAI API
API_KEY = "ddc-5c8kZb236RiHMw0wkEhtDxIFkwV1kM7dlWXeUHPUX104Xibh3R"
BASE_URL = "https://api.sree.shop/v1"
client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

# إعداد قاعدة البيانات
def init_db():
    conn = sqlite3.connect('chat_app.db')
    c = conn.cursor()
    
    # إنشاء جدول المستخدمين إذا لم يكن موجودًا
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE,
        password_hash TEXT,
        theme TEXT DEFAULT 'light'
    )''')
    
    # التحقق من وجود عمود 'language' وإضافته إذا لم يكن موجودًا
    c.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in c.fetchall()]
    if 'language' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'ar'")
    
    c.execute('''CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        title TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER,
        role TEXT,
        content TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (conversation_id) REFERENCES conversations(id)
    )''')
    
    conn.commit()
    conn.close()

init_db()

prompt_templates = {
    "default": "أنت مساعد ذكي مفيد ومهذب.",
    "creative": "أنت مساعد إبداعي يقدم أفكارًا فريدة ومبتكرة.",
    "professional": "أنت مساعد رسمي ومهني يقدم إجابات دقيقة ومختصرة.",
    "friendly": "أنت صديق ودود يتحدث بأسلوب غير رسمي ويستخدم الإيموجي كثيرًا! 😄"
}

@app.route('/')
def home():
    if 'user_id' in session:
        return render_template('chat.html', templates=prompt_templates)
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.json
        username = data.get('username')
        password = data.get('password')
        
        conn = sqlite3.connect('chat_app.db')
        c = conn.cursor()
        
        c.execute("SELECT username FROM users WHERE username = ?", (username,))
        if c.fetchone():
            conn.close()
            return jsonify({"status": "error", "message": "اسم المستخدم موجود بالفعل"})
        
        user_id = str(uuid.uuid4())
        password_hash = generate_password_hash(password)
        
        c.execute("INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
                 (user_id, username, password_hash))
        conn.commit()
        conn.close()
        
        session['user_id'] = user_id
        session['username'] = username
        
        return jsonify({"status": "success", "message": "تم التسجيل بنجاح"})
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.json
        username = data.get('username')
        password = data.get('password')
        
        conn = sqlite3.connect('chat_app.db')
        c = conn.cursor()
        
        c.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()
        
        if not user or not check_password_hash(user[1], password):
            return jsonify({"status": "error", "message": "اسم المستخدم أو كلمة المرور غير صحيحة"})
        
        session['user_id'] = user[0]
        session['username'] = username
        
        return jsonify({"status": "success", "message": "تم تسجيل الدخول بنجاح"})
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    return jsonify({"status": "success", "message": "تم تسجيل الخروج بنجاح"})

@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return render_template('login.html')
    
    conn = sqlite3.connect('chat_app.db')
    c = conn.cursor()
    c.execute("SELECT theme, language FROM users WHERE id = ?", (session['user_id'],))
    user = c.fetchone()
    
    c.execute("SELECT id FROM conversations WHERE user_id = ?", (session['user_id'],))
    if not c.fetchone():
        c.execute("INSERT INTO conversations (user_id, title) VALUES (?, ?)",
                 (session['user_id'], "محادثة افتراضية"))
        conn.commit()
    
    conn.close()
    
    return render_template('chat.html', templates=prompt_templates, theme=user[0], language=user[1], username=session['username'])

@app.route('/api/chat', methods=['POST'])
def api_chat():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "يرجى تسجيل الدخول أولاً"})
    
    data = request.json
    message = data.get('message', '')
    template_key = data.get('template', 'default')
    conversation_id = data.get('conversation_id')
    temperature = float(data.get('temperature', 0.7))
    
    if not conversation_id:
        return jsonify({"status": "error", "message": "معرف المحادثة مطلوب"})
    
    system_prompt = prompt_templates.get(template_key, prompt_templates["default"])
    
    conn = sqlite3.connect('chat_app.db')
    c = conn.cursor()
    
    c.execute("INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
             (conversation_id, "user", message))
    
    c.execute("SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY timestamp DESC LIMIT 10",
             (conversation_id,))
    messages = [{"role": row[0], "content": row[1]} for row in c.fetchall()[::-1]]
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": system_prompt}] + messages,
            temperature=temperature
        )
        
        assistant_response = response.choices[0].message.content
        
        c.execute("INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
                 (conversation_id, "assistant", assistant_response))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            "status": "success",
            "response": assistant_response,
            "template_used": template_key,
            "conversation_id": conversation_id
        })
    
    except Exception as e:
        conn.close()
        return jsonify({"status": "error", "message": f"حدث خطأ: {str(e)}"})

@app.route('/api/new_conversation', methods=['POST'])
def new_conversation():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "يرجى تسجيل الدخول أولاً"})
    
    data = request.json
    title = data.get('title', 'محادثة جديدة')
    
    conn = sqlite3.connect('chat_app.db')
    c = conn.cursor()
    c.execute("INSERT INTO conversations (user_id, title) VALUES (?, ?)",
             (session['user_id'], title))
    conversation_id = c.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({"status": "success", "conversation_id": conversation_id, "title": title})

@app.route('/api/delete_conversation', methods=['POST'])
def delete_conversation():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "يرجى تسجيل الدخول أولاً"})
    
    data = request.json
    conversation_id = data.get('conversation_id')
    
    conn = sqlite3.connect('chat_app.db')
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
    c.execute("DELETE FROM conversations WHERE id = ? AND user_id = ?", (conversation_id, session['user_id']))
    conn.commit()
    conn.close()
    
    return jsonify({"status": "success", "message": "تم حذف المحادثة بنجاح"})

@app.route('/api/conversations')
def get_conversations():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "يرجى تسجيل الدخول أولاً"})
    
    conn = sqlite3.connect('chat_app.db')
    c = conn.cursor()
    c.execute("SELECT id, title, created_at FROM conversations WHERE user_id = ? ORDER BY created_at DESC",
             (session['user_id'],))
    conversations = [{"id": row[0], "title": row[1], "created_at": row[2]} for row in c.fetchall()]
    conn.close()
    
    return jsonify({"status": "success", "conversations": conversations})

@app.route('/api/conversation/<int:conversation_id>')
def get_conversation(conversation_id):
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "يرجى تسجيل الدخول أولاً"})
    
    conn = sqlite3.connect('chat_app.db')
    c = conn.cursor()
    c.execute("SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY timestamp",
             (conversation_id,))
    messages = [{"role": row[0], "content": row[1]} for row in c.fetchall()]
    conn.close()
    
    return jsonify({"status": "success", "messages": messages, "conversation_id": conversation_id})

@app.route('/api/change_theme', methods=['POST'])
def change_theme():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "يرجى تسجيل الدخول أولاً"})
    
    data = request.json
    theme = data.get('theme')
    
    conn = sqlite3.connect('chat_app.db')
    c = conn.cursor()
    c.execute("UPDATE users SET theme = ? WHERE id = ?", (theme, session['user_id']))
    conn.commit()
    conn.close()
    
    return jsonify({"status": "success", "message": "تم تغيير السمة بنجاح"})

@app.route('/api/account_settings', methods=['GET', 'POST'])
def account_settings():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "يرجى تسجيل الدخول أولاً"})
    
    if request.method == 'GET':
        conn = sqlite3.connect('chat_app.db')
        c = conn.cursor()
        c.execute("SELECT username, theme, language FROM users WHERE id = ?", (session['user_id'],))
        user = c.fetchone()
        conn.close()
        return jsonify({"status": "success", "username": user[0], "theme": user[1], "language": user[2]})
    
    if request.method == 'POST':
        data = request.json
        new_username = data.get('username')
        new_password = data.get('password')
        new_language = data.get('language')
        
        conn = sqlite3.connect('chat_app.db')
        c = conn.cursor()
        
        if new_username:
            c.execute("UPDATE users SET username = ? WHERE id = ?", (new_username, session['user_id']))
            session['username'] = new_username
        
        if new_password:
            password_hash = generate_password_hash(new_password)
            c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, session['user_id']))
        
        if new_language:
            c.execute("UPDATE users SET language = ? WHERE id = ?", (new_language, session['user_id']))
        
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "تم تحديث الإعدادات بنجاح"})

@app.route('/api/help')
def help_page():
    help_content = {
        "status": "success",
        "content": "مرحبًا بك في صفحة المساعدة!\n\n"
                   "- لإنشاء محادثة جديدة: اضغط على 'محادثة جديدة' واكتب اسمًا مخصصًا.\n"
                   "- لحذف محادثة: اضغط على أيقونة الحذف بجانب المحادثة في التاريخ.\n"
                   "- لتغيير القالب: اختر قالبًا من القائمة في الشريط الجانبي.\n"
                   "- لتعديل حسابك: اذهب إلى 'إعدادات الحساب'.\n"
                   "- لإخفاء الشريط الجانبي: اضغط على زر الإغلاق في الشريط الجانبي.\n"
                   "- للخروج: اضغط على أيقونة تسجيل الخروج في الأعلى."
    }
    return jsonify(help_content)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))