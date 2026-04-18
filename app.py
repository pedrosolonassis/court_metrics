import sqlite3
import csv
import io
import os
import re
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, Response, session, flash
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "chave_super_secreta_court_metrics" # Necessário para segurança da sessão

# --- CONFIGURAÇÃO DA PASTA DE UPLOADS (FOTOS DE PERFIL E FEEDBACK) ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'profiles')
FEEDBACK_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'feedback')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['FEEDBACK_FOLDER'] = FEEDBACK_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(FEEDBACK_FOLDER, exist_ok=True)

def create_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    
    # 1. CRIA A TABELA DE USUÁRIOS
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        first_name TEXT,
        last_name TEXT,
        email TEXT,
        birth_date TEXT
    )
    """)

    # 2. TABELA DE PARTIDAS
    c.execute("""
    CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        opponent TEXT,
        categoria TEXT,
        match_type TEXT, 
        surface TEXT,
        result TEXT,
        score TEXT,
        match_format TEXT,
        partner TEXT,
        opp_partner TEXT,
        forehand INTEGER,
        backhand INTEGER,
        serve INTEGER,
        first_serve INTEGER,
        second_serve INTEGER,
        double_faults INTEGER,
        return_serve INTEGER,
        slice INTEGER,
        volley INTEGER,
        smash INTEGER,
        dropshot INTEGER,
        footwork INTEGER,
        strategy INTEGER,
        winners INTEGER,
        unforced_errors INTEGER,
        performance_rating REAL,
        notes TEXT,
        match_date TEXT,
        game_format TEXT,
        user_id INTEGER,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """)

    # TABELA DE NOTIFICAÇÕES
    c.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        message TEXT,
        link TEXT,
        is_read INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """)

    # 3. TABELA DE FEEDBACKS
    c.execute("""
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        feedback_type TEXT,
        subject TEXT,
        description TEXT,
        priority TEXT,
        image_path TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """)
    
    # ATUALIZAÇÕES SILENCIOSAS: Adiciona as colunas novas em bancos antigos sem apagar dados
    try:
        c.execute("ALTER TABLE matches ADD COLUMN game_format TEXT DEFAULT 'Padrão'")
    except sqlite3.OperationalError:
        pass
        
    try:
        c.execute("ALTER TABLE matches ADD COLUMN user_id INTEGER")
    except sqlite3.OperationalError:
        pass

    novos_campos_partida = {
        'mental_focus': 'INTEGER DEFAULT 0',
        'mental_resilience': 'INTEGER DEFAULT 0',
        'mental_confidence': 'INTEGER DEFAULT 0',
        'mental_pressure': 'INTEGER DEFAULT 0',
        'clutch_bp_saved': 'INTEGER DEFAULT 0',
        'clutch_bp_won': 'INTEGER DEFAULT 0',
        'momentum_lost_streak': 'INTEGER DEFAULT 0',
        'mental_tags': 'TEXT DEFAULT ""'
    }
    
    for campo, tipo in novos_campos_partida.items():
        try:
            c.execute(f"ALTER TABLE matches ADD COLUMN {campo} {tipo}")
        except sqlite3.OperationalError:
            pass

    # Migração silenciosa para os novos campos de usuário
    novos_campos_usuario = {
        'first_name': 'TEXT', 'last_name': 'TEXT', 'email': 'TEXT', 'birth_date': 'TEXT',
        'gender': 'TEXT', 'phone': 'TEXT', 'playing_since': 'TEXT', 
        'forehand_hand': 'TEXT', 'backhand_type': 'TEXT', 
        'height': 'REAL', 'weight': 'REAL', 'profile_pic': 'TEXT'
    }
    
    for campo, tipo in novos_campos_usuario.items():
        try: 
            c.execute(f"ALTER TABLE users ADD COLUMN {campo} {tipo}")
        except sqlite3.OperationalError: 
            pass

    conn.commit()
    conn.close()

create_db()

# --- DECORADOR DE SEGURANÇA (O PORTEIRO) ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_notifications():
    if "user_id" not in session:
        return dict(notifications=[])
        
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # Busca apenas as notificações não lidas
    c.execute("SELECT * FROM notifications WHERE user_id = ? AND is_read = 0 ORDER BY created_at DESC", (session["user_id"],))
    notifs = c.fetchall()
    conn.close()
    
    return dict(notifications=notifs)

# Rotas de Ação das Notificações
@app.route("/read_notif/<int:notif_id>")
@login_required
def read_notif(notif_id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT link FROM notifications WHERE id = ? AND user_id = ?", (notif_id, session["user_id"]))
    notif = c.fetchone()
    if notif:
        c.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notif_id,))
        conn.commit()
        conn.close()
        return redirect(notif[0]) # Vai para o link da notificação
    conn.close()
    return redirect("/")

@app.route("/read_all_notifs")
@login_required
def read_all_notifs():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (session["user_id"],))
    conn.commit()
    conn.close()
    return redirect(request.referrer or "/") # Recarrega a página atual


# --- ROTAS DE AUTENTICAÇÃO (LOGIN / REGISTRO) ---
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        first_name = request.form["first_name"]
        last_name = request.form["last_name"]
        email = request.form["email"]
        birth_date = request.form["birth_date"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]
        
        if password != confirm_password:
            return render_template("register.html", error="As senhas não coincidem.")
        if len(password) < 6:
            return render_template("register.html", error="A senha deve ter no mínimo 6 caracteres.")
        
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        
        c.execute("SELECT * FROM users WHERE username = ? OR email = ?", (username, email))
        if c.fetchone():
            conn.close()
            return render_template("register.html", error="Este Nome de Usuário ou E-mail já está em uso.")
        
        hashed_password = generate_password_hash(password)
        c.execute("""
            INSERT INTO users (username, password, first_name, last_name, email, birth_date) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (username, hashed_password, first_name, last_name, email, birth_date))
        new_user_id = c.lastrowid
        
        c.execute("UPDATE matches SET user_id = ? WHERE user_id IS NULL", (new_user_id,))
        
        conn.commit()
        conn.close()
        
        session["user_id"] = new_user_id
        session["username"] = username
        session["first_name"] = first_name
        session["last_name"] = last_name
        return redirect("/")
        
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        
        conn = sqlite3.connect("database.db")
        conn.row_factory = sqlite3.Row 
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session["user_id"] = user['id']
            session["username"] = user['username']
            session["first_name"] = user['first_name']
            session["last_name"] = user['last_name']
            session["profile_pic"] = user['profile_pic'] 
            return redirect("/")
        else:
            return render_template("login.html", error="Usuário ou senha incorretos.")
            
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ==============================================================================
# --- ROTAS DO SISTEMA PROTEGIDAS ---
# ==============================================================================

@app.route("/")
@login_required
def home():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM matches WHERE user_id = ? ORDER BY match_date DESC, id DESC", (session["user_id"],))
    matches = c.fetchall()
    
    c.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],))
    user_row = c.fetchone()
    col_names = [description[0] for description in c.description]
    user_data = dict(zip(col_names, user_row)) if user_row else {}
    conn.close()

    ultima_partida = "Sem registros"
    if matches:
        last_date_str = matches[0][27] 
        try:
            last_date = datetime.strptime(last_date_str, '%Y-%m-%d').date()
            hoje = datetime.today().date()
            delta = (hoje - last_date).days
            if delta == 0: ultima_partida = "Hoje"
            elif delta == 1: ultima_partida = "Ontem"
            else: ultima_partida = f"há {delta} dias"
        except:
            pass

    tempo_joga = "Não informado"
    if user_data.get('playing_since'):
        try:
            start_date = datetime.strptime(user_data['playing_since'], '%Y-%m-%d').date()
            anos = datetime.today().year - start_date.year
            if anos == 0: tempo_joga = "Menos de 1 ano"
            elif anos == 1: tempo_joga = "há 1 ano"
            else: tempo_joga = f"há mais de {anos} anos"
        except:
            pass

    return render_template("index.html", matches=matches, user_data=user_data, tempo_joga=tempo_joga, ultima_partida=ultima_partida)

@app.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    if request.method == "POST":
        foto_filename = None
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file and file.filename != '':
                filename = secure_filename(f"user_{session['user_id']}_profile.png")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                foto_filename = f"uploads/profiles/{filename}"

        update_query = """
            UPDATE users SET 
            first_name=?, last_name=?, email=?, gender=?, birth_date=?, phone=?,
            playing_since=?, forehand_hand=?, backhand_type=?, height=?, weight=?
        """
        params = [
            request.form.get("first_name"), request.form.get("last_name"), request.form.get("email"),
            request.form.get("gender"), request.form.get("birth_date"), request.form.get("phone"),
            request.form.get("playing_since"), request.form.get("forehand_hand"), request.form.get("backhand_type"),
            request.form.get("height"), request.form.get("weight")
        ]

        if foto_filename:
            update_query += ", profile_pic=?"
            params.append(foto_filename)
            session["profile_pic"] = foto_filename 

        update_query += " WHERE id=?"
        params.append(session["user_id"])

        c.execute(update_query, tuple(params))
        
        session["first_name"] = request.form.get("first_name")
        session["last_name"] = request.form.get("last_name")
        
        conn.commit()
        conn.close()
        return redirect("/perfil")

    c.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],))
    user_row = c.fetchone()
    user_data = dict(user_row) if user_row else {}
    
    if 'profile_pic' not in session and user_data.get('profile_pic'):
        session['profile_pic'] = user_data['profile_pic']

    conn.close()
    return render_template("perfil.html", user=user_data)

@app.route("/feedback", methods=["GET", "POST"])
@login_required
def feedback():
    if request.method == "POST":
        feedback_type = request.form.get("feedback_type")
        subject = request.form.get("subject")
        description = request.form.get("description")
        priority = request.form.get("priority")
        
        foto_filename = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '':
                filename = secure_filename(f"fb_{session['user_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
                filepath = os.path.join(app.config['FEEDBACK_FOLDER'], filename)
                file.save(filepath)
                foto_filename = f"uploads/feedback/{filename}"

        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("""
            INSERT INTO feedback (user_id, feedback_type, subject, description, priority, image_path)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session["user_id"], feedback_type, subject, description, priority, foto_filename))
        conn.commit()
        conn.close()
        
        return render_template("feedback.html", success=True)
        
    return render_template("feedback.html")

@app.route("/history")
@login_required
def history():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    
    f_surface = request.args.get("surface", "")
    f_type = request.args.get("match_type", "")
    f_format = request.args.get("match_format", "")
    
    query = "SELECT * FROM matches WHERE user_id = ?"
    params = [session["user_id"]]
    
    if f_surface:
        query += " AND surface = ?"
        params.append(f_surface)
    if f_type:
        query += " AND match_type = ?"
        params.append(f_type)
    if f_format:
        query += " AND match_format = ?"
        params.append(f_format)
        
    query += " ORDER BY match_date DESC, id DESC"
    
    c.execute(query, params)
    matches = c.fetchall()
    conn.close()
    
    filters = {"surface": f_surface, "match_type": f_type, "match_format": f_format}
    return render_template("history.html", matches=matches, filters=filters)

@app.route("/fundamento/<nome>")
@login_required
def fundamento(nome):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM matches WHERE user_id = ? ORDER BY match_date ASC", (session["user_id"],)) 
    matches = c.fetchall()
    conn.close()
    return render_template("fundamento.html", matches=matches, nome=nome)

@app.route("/new_match", methods=["GET", "POST"])
@login_required
def new_match():
    if request.method == "POST":
        # CORREÇÃO: usar .get() com fallback em todos os campos — evita HTTP 400 (KeyError)
        # quando o browser mobile envia formulário com campo vazio ou ausente
        opponent = request.form.get("opponent", "").strip()
        categoria = request.form.get("categoria", "Não informado").strip() or "Não informado"
        match_type = request.form.get("match_type", "Amistoso").strip() or "Amistoso"
        surface = request.form.get("surface", "Não informado").strip() or "Não informado"
        result = request.form.get("result", "Derrota")
        match_format = request.form.get("match_format", "1 Set")
        game_format = request.form.get("game_format", "6")
        partner = request.form.get("partner", "")
        opp_partner = request.form.get("opp_partner", "")
        match_date = request.form.get("match_date", datetime.today().strftime('%Y-%m-%d'))
        score = request.form.get("final_score", "")

        f_names = ["forehand", "backhand", "serve", "first_serve", "second_serve", "double_faults", "return_serve", "slice", "volley", "smash", "dropshot", "footwork", "strategy"]
        notes = {f: int(request.form.get(f, 0)) for f in f_names}
        notes_list = [notes[f] for f in f_names]

        winners = int(request.form.get("winners", 0) or 0)
        unforced_errors = int(request.form.get("unforced_errors", 0) or 0)

        primarios = [notes['forehand'], notes['backhand'], notes['serve']]
        v_prim = [n for n in primarios if n > 0]
        m_prim = sum(v_prim)/len(v_prim) if v_prim else 0

        secundarios = [notes['return_serve'], notes['footwork'], notes['strategy']]
        v_sec = [n for n in secundarios if n > 0]
        m_sec = sum(v_sec)/len(v_sec) if v_sec else 0

        especificos = [notes['slice'], notes['volley'], notes['smash'], notes['dropshot']]
        v_esp = [n for n in especificos if n > 0]
        m_esp = sum(v_esp)/len(v_esp) if v_esp else 0

        perf = round((m_prim * 0.5) + (m_sec * 0.3) + (m_esp * 0.2), 1)

        mental_focus = int(request.form.get("mental_focus", 0) or 0)
        mental_resilience = int(request.form.get("mental_resilience", 0) or 0)
        clutch_bp_saved = int(request.form.get("clutch_bp_saved", "") if request.form.get("clutch_bp_saved", "").isdigit() else 0)
        clutch_bp_won = int(request.form.get("clutch_bp_won", "") if request.form.get("clutch_bp_won", "").isdigit() else 0)
        momentum_lost_streak = int(request.form.get("momentum_lost_streak", "") if request.form.get("momentum_lost_streak", "").isdigit() else 0)
        mental_tags = request.form.get("mental_tags", "")

        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("""
        INSERT INTO matches (
            opponent, categoria, match_type, surface, result, score, match_format, partner, opp_partner, 
            forehand, backhand, serve, first_serve, second_serve, double_faults, return_serve, slice, volley, smash, dropshot, footwork, strategy, 
            winners, unforced_errors, performance_rating, notes, match_date, game_format, user_id,
            mental_focus, mental_resilience, clutch_bp_saved, clutch_bp_won, momentum_lost_streak, mental_tags
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            opponent, categoria, match_type, surface, result, score, match_format, partner, opp_partner, 
            *notes_list, winners, unforced_errors, perf, request.form.get("notes", ""), match_date, game_format, session["user_id"],
            mental_focus, mental_resilience, clutch_bp_saved, clutch_bp_won, momentum_lost_streak, mental_tags
        ))
        
        conn.commit(); conn.close()
        return redirect("/")
    
    return render_template("new_match.html")

@app.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_match(id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    if request.method == "POST":
        # CORREÇÃO: usar .get() com fallback — evita HTTP 400 no mobile
        opponent = request.form.get("opponent", "").strip()
        categoria = request.form.get("categoria", "Não informado").strip() or "Não informado"
        match_type = request.form.get("match_type", "Amistoso").strip() or "Amistoso"
        surface = request.form.get("surface", "Não informado").strip() or "Não informado"
        result = request.form["result"]
        match_format = request.form.get("match_format", "1 Set")
        game_format = request.form.get("game_format", "6")
        partner = request.form.get("partner", "")
        opp_partner = request.form.get("opp_partner", "")
        match_date = request.form.get("match_date", datetime.today().strftime('%Y-%m-%d'))
        score = request.form.get("final_score", request.form.get("score", ""))

        f_names = ["forehand", "backhand", "serve", "first_serve", "second_serve", "double_faults", "return_serve", "slice", "volley", "smash", "dropshot", "footwork", "strategy"]
        notes = {f: int(request.form.get(f, 0)) for f in f_names}
        notes_list = [notes[f] for f in f_names]

        winners = int(request.form.get("winners", 0) or 0)
        unforced_errors = int(request.form.get("unforced_errors", 0) or 0)

        primarios = [notes['forehand'], notes['backhand'], notes['serve']]
        v_prim = [n for n in primarios if n > 0]
        m_prim = sum(v_prim)/len(v_prim) if v_prim else 0

        secundarios = [notes['return_serve'], notes['footwork'], notes['strategy']]
        v_sec = [n for n in secundarios if n > 0]
        m_sec = sum(v_sec)/len(v_sec) if v_sec else 0

        especificos = [notes['slice'], notes['volley'], notes['smash'], notes['dropshot']]
        v_esp = [n for n in especificos if n > 0]
        m_esp = sum(v_esp)/len(v_esp) if v_esp else 0

        perf = round((m_prim * 0.5) + (m_sec * 0.3) + (m_esp * 0.2), 1)

        mental_focus = int(request.form.get("mental_focus", 0) or 0)
        mental_resilience = int(request.form.get("mental_resilience", 0) or 0)
        clutch_bp_saved = int(request.form.get("clutch_bp_saved", "") if request.form.get("clutch_bp_saved", "").isdigit() else 0)
        clutch_bp_won = int(request.form.get("clutch_bp_won", "") if request.form.get("clutch_bp_won", "").isdigit() else 0)
        momentum_lost_streak = int(request.form.get("momentum_lost_streak", "") if request.form.get("momentum_lost_streak", "").isdigit() else 0)
        mental_tags = request.form.get("mental_tags", "")

        c.execute("""
        UPDATE matches SET 
        opponent=?, categoria=?, match_type=?, surface=?, result=?, score=?, match_format=?, partner=?, opp_partner=?, 
        forehand=?, backhand=?, serve=?, first_serve=?, second_serve=?, double_faults=?, return_serve=?, slice=?, volley=?, smash=?, dropshot=?, footwork=?, strategy=?, 
        winners=?, unforced_errors=?, performance_rating=?, notes=?, match_date=?, game_format=?,
        mental_focus=?, mental_resilience=?, clutch_bp_saved=?, clutch_bp_won=?, momentum_lost_streak=?, mental_tags=?
        WHERE id=? AND user_id=?
        """, (
            opponent, categoria, match_type, surface, result, score, match_format, partner, opp_partner, 
            *notes_list, winners, unforced_errors, perf, request.form.get("notes", ""), match_date, game_format,
            mental_focus, mental_resilience, clutch_bp_saved, clutch_bp_won, momentum_lost_streak, mental_tags,
            id, session["user_id"]
        ))
        
        conn.commit(); conn.close()
        return redirect("/")
    else:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM matches WHERE id = ? AND user_id = ?", (id, session["user_id"]))
        match = c.fetchone()
        conn.close()
        if match: 
            return render_template("edit_match.html", match=dict(match))
        return redirect("/")

@app.route("/delete/<int:id>", methods=["POST"])
@login_required
def delete_match(id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("DELETE FROM matches WHERE id = ? AND user_id = ?", (id, session["user_id"]))
    conn.commit()
    conn.close()
    return redirect("/")

@app.route("/match/<int:id>")
@login_required
def match_details(id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM matches WHERE id = ? AND user_id = ?", (id, session["user_id"]))
    match = c.fetchone()
    conn.close()
    
    if match:
        return render_template("match_details.html", match=match)
    return redirect("/")

@app.route("/export")
@login_required
def export_csv():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    # Selecionamos apenas as colunas úteis para análise de dados
    c.execute("""
        SELECT match_date, opponent, categoria, match_type, surface, result, score, 
               match_format, game_format, partner, opp_partner,
               forehand, backhand, serve, first_serve, second_serve, double_faults, return_serve,
               slice, volley, smash, dropshot, footwork, strategy, winners, unforced_errors,
               performance_rating, mental_focus, mental_resilience, clutch_bp_saved, clutch_bp_won,
               momentum_lost_streak, mental_tags
        FROM matches WHERE user_id = ? ORDER BY match_date DESC
    """, (session["user_id"],))
    matches = c.fetchall()
    conn.close()

    # Cabeçalhos limpos e formatados
    headers = [
        "Data da Partida", "Adversario", "Categoria", "Tipo de Partida", "Superficie", "Resultado", "Placar",
        "Formato Partida", "Formato Game", "Parceiro", "Parceiro Adversario",
        "Nota Forehand", "Nota Backhand", "Nota Saque", "Nota 1o Saque", "Nota 2o Saque", "Duplas Faltas", "Nota Devolucao",
        "Nota Slice", "Nota Voleio", "Nota Smash", "Nota Dropshot", "Nota Movimentacao", "Nota Estrategia", 
        "Winners", "Erros Nao Forcados", "Rating de Performance",
        "Foco Mental", "Resiliencia Mental", "BP Salvos", "BP Ganhos", "Momentum Perdido (Streak)", "Tags Mentais"
    ]

    output = io.StringIO()
    
    # ---------------------------------------------------------
    # A LINHA MÁGICA: Força o Excel a reconhecer os acentos
    output.write('\ufeff')
    # ---------------------------------------------------------

    # Usando vírgula como delimitador
    writer = csv.writer(output, delimiter=',')
    writer.writerow(headers)
    writer.writerows(matches)

    # Gera o nome do arquivo dinâmico baseado no usuário logado
    username = session.get("username", "usuario").lower().replace(" ", "_")
    filename = f"{username}_courtmetrics.csv"

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )

@app.route("/select_compare/<int:id>")
@login_required
def select_compare(id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM matches WHERE id = ? AND user_id = ?", (id, session["user_id"]))
    base_match = c.fetchone()
    c.execute("SELECT * FROM matches WHERE id != ? AND user_id = ? ORDER BY match_date DESC", (id, session["user_id"]))
    other_matches = c.fetchall()
    conn.close()
    
    if base_match:
        return render_template("select_compare.html", base_match=base_match, matches=other_matches)
    return redirect("/")

@app.route("/compare/<int:id1>/<int:id2>")
@login_required
def compare(id1, id2):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM matches WHERE id = ? AND user_id = ?", (id1, session["user_id"]))
    match1 = c.fetchone()
    c.execute("SELECT * FROM matches WHERE id = ? AND user_id = ?", (id2, session["user_id"]))
    match2 = c.fetchone()
    conn.close()
    
    if match1 and match2:
        return render_template("compare.html", m1=match1, m2=match2)
    return redirect("/")

@app.route("/adversarios")
@login_required
def adversarios():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("""
        SELECT 
            CASE WHEN match_format LIKE '%Duplas%' THEN opponent || ' & ' || opp_partner ELSE opponent END as rival, 
            COUNT(id) as total_jogos,
            SUM(CASE WHEN result = 'Vitória' THEN 1 ELSE 0 END) as vitorias
        FROM matches 
        WHERE user_id = ?
        GROUP BY rival 
        ORDER BY total_jogos DESC
    """, (session["user_id"],))
    opponents_data = c.fetchall()
    conn.close()
    return render_template("adversarios.html", opponents=opponents_data)

@app.route("/h2h/<path:opponent>")
@login_required
def h2h(opponent):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    
    c.execute("""
        SELECT * FROM matches 
        WHERE user_id = ? AND CASE WHEN match_format LIKE '%Duplas%' THEN opponent || ' & ' || opp_partner ELSE opponent END = ? 
        ORDER BY match_date DESC
    """, (session["user_id"], opponent))
    matches = c.fetchall()
    
    c.execute("SELECT AVG(performance_rating), AVG(winners), AVG(unforced_errors) FROM matches WHERE user_id = ?", (session["user_id"],))
    career_avg = c.fetchone()
    conn.close()
    
    if not matches:
        return redirect("/adversarios")
        
    return render_template("h2h_detail.html", matches=matches, opponent=opponent, career_avg=career_avg)

@app.route("/insights")
@login_required
def insights():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM matches WHERE user_id = ? ORDER BY match_date DESC, id DESC", (session["user_id"],))
    matches = c.fetchall()
    conn.close()

    if not matches: return redirect("/")

    streak_type = matches[0][5] if matches[0][5] else "Sem Dados"
    streak_count = 0
    for m in matches:
        if m[5] == streak_type: streak_count += 1
        else: break

    stats = {
        'streak_type': streak_type, 'streak_count': streak_count,
        'surface': {'Quadra Dura': {'v': 0, 'd': 0}, 'Saibro': {'v': 0, 'd': 0}},
        'format': {'Simples': {'v': 0, 'd': 0}, 'Duplas': {'v': 0, 'd': 0}},
        'type': {'Ranking': {'v': 0, 'd': 0}, 'Torneio': {'v': 0, 'd': 0}, 'Amistoso': {'v': 0, 'd': 0}},
        # ESTATÍSTICAS DE 1º SET
        'first_set': {
            'Ranking': {'won_match_won': 0, 'won_match_lost': 0, 'lost_match_won': 0, 'lost_match_lost': 0},
            'Torneio': {'won_match_won': 0, 'won_match_lost': 0, 'lost_match_won': 0, 'lost_match_lost': 0},
            'Amistoso': {'won_match_won': 0, 'won_match_lost': 0, 'lost_match_won': 0, 'lost_match_lost': 0}
        },
        'category': {}, 'tb_won': 0, 'tb_lost': 0, 'decisive_won': 0, 'decisive_lost': 0,
        'perf_wins': 0, 'perf_losses': 0, 'count_wins': 0, 'count_losses': 0,
        'winners_total': 0, 'ue_total': 0,
        'focus_win_tot': 0, 'focus_win_cnt': 0, 'focus_loss_tot': 0, 'focus_loss_cnt': 0,
        'res_win_tot': 0, 'res_win_cnt': 0, 'res_loss_tot': 0, 'res_loss_cnt': 0
    }

    for m in matches:
        is_win = m[5] == 'Vitória'
        m_type = m[3] if m[3] in stats['first_set'] else 'Amistoso'
        
        if is_win:
            stats['count_wins'] += 1; stats['perf_wins'] += m[25]
            if m[30] and m[30] > 0: stats['focus_win_tot'] += m[30]; stats['focus_win_cnt'] += 1
            if m[31] and m[31] > 0: stats['res_win_tot'] += m[31]; stats['res_win_cnt'] += 1
        else:
            stats['count_losses'] += 1; stats['perf_losses'] += m[25]
            if m[30] and m[30] > 0: stats['focus_loss_tot'] += m[30]; stats['focus_loss_cnt'] += 1
            if m[31] and m[31] > 0: stats['res_loss_tot'] += m[31]; stats['res_loss_cnt'] += 1
            
        stats['winners_total'] += m[23]; stats['ue_total'] += m[24]
        if m[4] and m[4] in stats['surface']: stats['surface'][m[4]]['v' if is_win else 'd'] += 1
        if m[3] and m[3] in stats['type']: stats['type'][m[3]]['v' if is_win else 'd'] += 1
        
        cat = m[2] if m[2] else 'Sem Classe'
        if cat not in stats['category']: stats['category'][cat] = {'v': 0, 'd': 0}
        stats['category'][cat]['v' if is_win else 'd'] += 1
        
        fmt_cat = 'Duplas' if m[7] and 'Duplas' in str(m[7]) else 'Simples'
        stats['format'][fmt_cat]['v' if is_win else 'd'] += 1

        if m[6]: 
            sets = [s for s in m[6].split() if '/' in s and s.strip() != '/' and s.strip() != '0/0']
            
            # --- LÓGICA DO 1º SET (Ignora partidas de apenas 1 set) ---
            if len(sets) >= 1 and (m[7] and '1 Set' not in m[7]):
                # Limpa parênteses/colchetes do 1º set
                s1_clean = re.sub(r'\(.*?\)', '', sets[0].replace('[', '').replace(']', ''))
                parts1 = s1_clean.split('/')
                if len(parts1) == 2:
                    try:
                        g1, g2 = int(parts1[0]), int(parts1[1])
                        if g1 > g2:
                            if is_win: stats['first_set'][m_type]['won_match_won'] += 1
                            else: stats['first_set'][m_type]['won_match_lost'] += 1
                        elif g2 > g1:
                            if is_win: stats['first_set'][m_type]['lost_match_won'] += 1
                            else: stats['first_set'][m_type]['lost_match_lost'] += 1
                    except ValueError: pass

            # --- LÓGICA DE TIE-BREAK E SET DECISIVO ---
            for s in sets:
                # O regex .sub(r'\(.*?\)', '', s) arranca tudo que tá entre parênteses para olhar só pros games
                s_clean = re.sub(r'\(.*?\)', '', s.replace('[', '').replace(']', ''))
                parts = s_clean.split('/')
                if len(parts) == 2:
                    try:
                        p1 = int(parts[0])
                        p2 = int(parts[1])
                        
                        # Tiebreak acontece se: Jogaram 7x6 / 6x7, ou se é SuperTB (>=10), ou se existe o "(" na string
                        if (p1 == 7 and p2 == 6) or (p1 >= 10 and p1 - p2 >= 2) or ('(' in s and p1 > p2):
                            stats['tb_won'] += 1
                        elif (p1 == 6 and p2 == 7) or (p2 >= 10 and p2 - p1 >= 2) or ('(' in s and p2 > p1):
                            stats['tb_lost'] += 1
                    except ValueError: pass
            
            try:
                if (len(sets) == 3 and m[7] and '5 Sets' not in m[7]) or len(sets) == 5:
                    if is_win: stats['decisive_won'] += 1
                    else: stats['decisive_lost'] += 1
            except Exception: pass 

    total_jogos = len(matches)
    stats['avg_perf_win'] = round(stats['perf_wins'] / stats['count_wins'], 1) if stats['count_wins'] > 0 else 0.0
    stats['avg_perf_loss'] = round(stats['perf_losses'] / stats['count_losses'], 1) if stats['count_losses'] > 0 else 0.0
    stats['avg_winners'] = round(stats['winners_total'] / total_jogos, 1) if total_jogos > 0 else 0.0
    stats['avg_ue'] = round(stats['ue_total'] / total_jogos, 1) if total_jogos > 0 else 0.0
    
    stats['avg_focus_win'] = round(stats['focus_win_tot'] / stats['focus_win_cnt'], 1) if stats['focus_win_cnt'] > 0 else 0.0
    stats['avg_focus_loss'] = round(stats['focus_loss_tot'] / stats['focus_loss_cnt'], 1) if stats['focus_loss_cnt'] > 0 else 0.0
    stats['avg_res_win'] = round(stats['res_win_tot'] / stats['res_win_cnt'], 1) if stats['res_win_cnt'] > 0 else 0.0
    stats['avg_res_loss'] = round(stats['res_loss_tot'] / stats['res_loss_cnt'], 1) if stats['res_loss_cnt'] > 0 else 0.0

    return render_template("insights.html", stats=stats, matches=matches)

@app.route("/simulador", methods=["GET", "POST"])
@login_required
def simulador():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT surface, performance_rating, winners, unforced_errors, mental_focus, mental_resilience, categoria, result FROM matches WHERE user_id = ?", (session["user_id"],))
    matches = c.fetchall()
    conn.close()

    if len(matches) < 5: return render_template("simulador.html", erro_dados="Jogue mais! O Oráculo precisa de pelo menos 5 partidas registradas para aprender seus padrões.")

    if request.method == "POST":
        sim_surface = request.form["surface"]
        sim_rating = float(request.form["rating"])
        sim_agressividade = float(request.form["winners"]) / (float(request.form["erros"]) + 1)
        sim_focus = int(request.form.get("focus", 3)) 
        sim_resilience = int(request.form.get("resilience", 3)) 
        sim_classe = request.form.get("classe", "4ª Classe") 

        # Escala matemática de classes para calcular o abismo técnico
        hierarquia_classes = {'Iniciante': 1, '5ª Classe': 2, '4ª Classe': 3, '3ª Classe': 4, '2ª Classe': 5, '1ª Classe': 6}

        try:
            from sklearn.linear_model import LogisticRegression
            from sklearn.preprocessing import StandardScaler
            import numpy as np

            X, y = [], []
            niveis_jogados = []
            
            for m in matches:
                is_saibro = 1 if m[0] == 'Saibro' else 0
                rating = m[1]
                agr = m[2] / (m[3] + 1)
                foc = m[4] if (m[4] and m[4] > 0) else 3
                res = m[5] if (m[5] and m[5] > 0) else 3
                
                # Descobre quem o usuário costuma enfrentar para achar o "Nível Verdadeiro" dele
                cat_banco = m[6] if m[6] else '4ª Classe'
                nivel = hierarquia_classes.get(cat_banco, 3)
                niveis_jogados.append(nivel)
                
                X.append([is_saibro, rating, agr, foc, res])
                y.append(1 if m[7] == 'Vitória' else 0)

            # Média dos níveis enfrentados (Ex: se joga muito com 4ª Classe, a média é 3.0)
            nivel_usuario = sum(niveis_jogados) / len(niveis_jogados) if niveis_jogados else 3

            if len(set(y)) < 2: return render_template("simulador.html", erro_dados="O Oráculo precisa de exemplos tanto de Vitórias quanto de Derrotas no seu histórico para aprender a diferença.")

            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)

            model = LogisticRegression(class_weight='balanced')
            model.fit(X_scaled, y)

            is_saibro_sim = 1 if sim_surface == 'Saibro' else 0
            cenario = np.array([[is_saibro_sim, sim_rating, sim_agressividade, sim_focus, sim_resilience]])
            cenario_scaled = scaler.transform(cenario)
            
            # 1. Pega a Probabilidade Técnica Pura da IA
            prob_tecnica = model.predict_proba(cenario_scaled)[0][1] * 100

            # 2. O GRANDE AJUSTE: Handicap de Discrepância de Classe
            nivel_simulado = hierarquia_classes.get(sim_classe, 3)
            diferenca_nivel = nivel_usuario - nivel_simulado
            
            # Cada classe de diferença aplica um peso absurdo de 35% na probabilidade final
            handicap = diferenca_nivel * 35.0 
            
            probabilidade_final = prob_tecnica + handicap

            # 3. Trava a matemática entre 1% (Derrota iminente) e 99% (Passeio na quadra)
            if probabilidade_final > 99.0: probabilidade_final = 99.0
            elif probabilidade_final < 1.0: probabilidade_final = 1.0

            # Gera texto de explicação (XAI) baseado no Handicap
            gap_text = ""
            if diferenca_nivel > 0: gap_text = f"+{round(handicap)}% de vantagem por superioridade técnica de classe"
            elif diferenca_nivel < 0: gap_text = f"{round(handicap)}% de penalidade por inferioridade técnica de classe"
            else: gap_text = "Nivelamento equilibrado com o seu histórico"

            return render_template("simulador.html", probabilidade=round(probabilidade_final, 1), surface=sim_surface, rating=sim_rating, focus=sim_focus, resilience=sim_resilience, classe=sim_classe, gap_text=gap_text)

        except Exception as e:
            return render_template("simulador.html", erro_dados=f"Erro no Motor de IA: {str(e)}")

    return render_template("simulador.html")

@app.route("/treinador", methods=["GET", "POST"])
@login_required
def treinador():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM matches WHERE user_id = ? ORDER BY match_date DESC, id DESC", (session["user_id"],))
    all_matches = c.fetchall()
    conn.close()

    if len(all_matches) < 3:
        return render_template("treinador.html", erro="Calibração em andamento: Você precisa registrar pelo menos 3 partidas para a IA entender seu padrão global.")

    # --- EXTRAÇÃO DE ADVERSÁRIOS ÚNICOS ---
    opponents_set = set()
    for m in all_matches:
        op_name = f"{m['opponent']} & {m['opp_partner']}" if m['match_format'] and 'Duplas' in str(m['match_format']) else str(m['opponent'])
        opponents_set.add(op_name)
    unique_opponents = sorted(list(opponents_set))

    # --- LEITURA DOS FILTROS ---
    selected_opponent = request.args.get("opponent", "")
    limit = int(request.args.get("limit", 3))

    # --- FILTRAGEM DO CONFRONTO DIRETO ---
    if selected_opponent:
        filtered_matches = []
        for m in all_matches:
            op_name = f"{m['opponent']} & {m['opp_partner']}" if m['match_format'] and 'Duplas' in str(m['match_format']) else str(m['opponent'])
            if op_name == selected_opponent:
                filtered_matches.append(m)
        
        if len(filtered_matches) == 0:
            return render_template("treinador.html", erro=f"Nenhum jogo encontrado contra {selected_opponent}.", unique_opponents=unique_opponents, selected_opponent=selected_opponent)
        
        matches = filtered_matches[:limit]
        total_base = len(filtered_matches)
    else:
        matches = all_matches[:limit]
        total_base = len(all_matches)

    # --- FUNÇÕES DE CÁLCULO ---
    def calc_avg(field, data_set=matches):
        vals = [m[field] for m in data_set if m[field] is not None and m[field] > 0]
        return sum(vals) / len(vals) if vals else 0.0

    def calc_raw_avg(field, data_set=matches):
        vals = [m[field] for m in data_set if m[field] is not None]
        return sum(vals) / len(vals) if vals else 0.0

    # --- MÉTRICAS DO JOGADOR ---
    avg_fh = calc_avg("forehand")
    avg_bh = calc_avg("backhand")
    avg_serve = calc_avg("serve")
    avg_return = calc_avg("return_serve")
    avg_volley = calc_avg("volley")
    avg_footwork = calc_avg("footwork")
    avg_df = calc_raw_avg("double_faults")
    avg_winners = calc_raw_avg("winners")
    avg_ue = calc_raw_avg("unforced_errors")
    
    # --- ANÁLISE DE DIFICULDADE ---
    hard_matches = sum(1 for m in matches if any(x in str(m["categoria"]).lower() for x in ["1", "2", "3", "a", "pro", "primeira", "segunda", "terceira", "aberta", "especial"]))
    dificuldade_fator = hard_matches / len(matches) if matches else 0
    nivel_adversarios = "Avançado (Classes Superiores)" if dificuldade_fator > 0.5 else "Intermediário / Equilibrado" if dificuldade_fator > 0 else "Padrão (Mesma Classe)"

    # --- DEFINIÇÃO DO ESTILO DE JOGO ---
    estilo_jogo = "All-Court (Jogador Completo)"
    desc_estilo = "Você é um jogador versátil, que busca se adaptar a diferentes situações na quadra e domina transições."
    icone_estilo = "bx-layer"

    if avg_volley >= 7.5 and avg_serve >= 7.5:
        estilo_jogo, desc_estilo, icone_estilo = "Saque e Voleio (Serve & Volley)", "Seu jogo é vertical e sufocante. Você usa o saque para abrir a quadra e sobe à rede para matar os pontos rápido.", "bx-navigation"
    elif avg_winners >= (avg_ue * 0.7) and avg_fh >= 7.0:
        estilo_jogo, desc_estilo, icone_estilo = "Fundo de Quadra Agressivo (Aggressive Baseliner)", "Você dita o ritmo do jogo. Sua principal arma são os golpes de fundo potentes, buscando dominar o centro.", "bx-target-lock"
    elif avg_ue <= 3.5 and avg_footwork >= 7.5 and avg_return >= 7.0:
        estilo_jogo, desc_estilo, icone_estilo = "Contra-Atacador (Counterpuncher)", "Sua defesa é um muro. Você vence pela consistência técnica, movimentação de elite e forçando o colapso adversário.", "bx-shield-alt-2"
    elif avg_fh >= 6.0 and avg_bh >= 6.0 and avg_winners < avg_ue:
        estilo_jogo, desc_estilo, icone_estilo = "Fundo de Quadra Tático", "Você constrói os pontos com paciência do fundo da quadra, usando altura, variação e profundidade.", "bx-cog"
    # --- O DOCK TÁTICO PRINCIPAL ---
    relatorio = {
        "estilo": estilo_jogo, "desc_estilo": desc_estilo, "icone": icone_estilo, "nivel_adversarios": nivel_adversarios,
        "analise": [], "fortes": [], "evitar": [], "estrategias": [], "super_modulos": []
    }

    # Ajuste de Narrativa se for um Nêmesis (Adversário Específico)
    if selected_opponent:
        relatorio["analise"].append(f"Dossiê Tático Isolado: Esta análise foi gerada cruzando apenas os dados dos seus confrontos diretos contra {selected_opponent}.")
    else:
        if dificuldade_fator > 0.5: relatorio["analise"].append(f"Enfrentando classes altas. O aumento de Erros Não Forçados ({round(avg_ue, 1)}/jogo) é um reflexo natural do peso de bola destes adversários.")
        else: relatorio["analise"].append(f"Volume estabilizado. Sua média agressiva está em {round(avg_winners, 1)} winners por jogo neste recorte.")
        
    if avg_fh > (avg_bh + 1.5): relatorio["analise"].append("Assimetria: seu forehand dita a regra, enquanto o backhand atua apenas na manutenção.")
    elif abs(avg_fh - avg_bh) <= 1.0 and avg_fh > 6.5: relatorio["analise"].append("Fundo de quadra blindado, sem lados vulneráveis óbvios para o adversário atacar.")

    if avg_fh >= 7.0: relatorio["fortes"].append("Forehand Dominante: Sua direita está empurrando o adversário para trás da linha.")
    if avg_serve >= 7.0: relatorio["fortes"].append("Serviço Bélico: O saque está garantindo pontos rápidos e ditando o controle.")
    if avg_footwork >= 7.5: relatorio["fortes"].append("Movimentação de Elite: Suas pernas compensam os dias ruins. Chegar bem posicionado garante devoluções limpas.")
    if len(relatorio["fortes"]) == 0: relatorio["fortes"].append("Equilíbrio Sólido: Padrão extremamente imprevisível de ser lido.")

    if avg_df >= 3.0: relatorio["evitar"].append(f"Entregar Games no Saque: Com {round(avg_df, 1)} duplas faltas, você dá quase um game de graça. Aumente o spin do 2º saque.")
    if avg_ue > (avg_winners * 1.5) and avg_ue > 5: relatorio["evitar"].append("Apressar a Definição: Pare de buscar as linhas muito cedo. Construa o ponto pelo centro.")
    if avg_volley > 0 and avg_volley <= 5.5: relatorio["evitar"].append("Transições no Susto: Subir à rede sem uma boa bola de aproximação está te deixando vulnerável a passadas.")

    if "Aggressive" in estilo_jogo: relatorio["estrategias"].append("Explore o backhand do adversário. Quando ele devolver curto, gire o corpo para bater o inside-out no lado vazio.")
    elif "Counterpuncher" in estilo_jogo: relatorio["estrategias"].append("Levante a bola (moonballs) com muito topspin no lado esquerdo deles. Obrigue-os a gerar a própria força.")
    elif "Serve & Volley" in estilo_jogo: relatorio["estrategias"].append("Use mais saques no corpo. Essa direção 'trava' o braço do oponente, garantindo devoluções lentas.")
    else: relatorio["estrategias"].append("Padrão Seguro: Nos pontos cruciais, use a cruzada. Só puxe a paralela com os pés dentro da quadra.")
    
    if dificuldade_fator > 0.5 and not selected_opponent: relatorio["estrategias"].append("Adversários de níveis altos adoram ritmo. Use slices curtos para quebrar as pernas deles e tirar o peso.")

    # ==========================================
    # 🧠 SUPER CÉREBRO: OS 4 MÓDULOS AVANÇADOS
    # ==========================================
    import re

    avg_bp_saved = calc_avg("clutch_bp_saved")
    avg_bp_won = calc_avg("clutch_bp_won")

    if avg_bp_saved >= 3.5 or avg_bp_won >= 3.5:
        relatorio["super_modulos"].append({
            "nome": "Termômetro Clutch", "icone": "bx-pulse", "cor": "#f43f5e",
            "texto": f"O seu instinto assassino está afiado! Sua nota média sob pressão é excelente (Salvos: {round(avg_bp_saved, 1)}/5 | Convertidos: {round(avg_bp_won, 1)}/5). Você cresce na hora H."
        })
    elif (avg_bp_saved > 0 and avg_bp_saved <= 2.5) or (avg_bp_won > 0 and avg_bp_won <= 2.5) or avg_ue > 8:
        salvos_txt = round(avg_bp_saved, 1) if avg_bp_saved > 0 else "N/A"
        ganhos_txt = round(avg_bp_won, 1) if avg_bp_won > 0 else "N/A"
        relatorio["super_modulos"].append({
            "nome": "Termômetro Clutch", "icone": "bx-pulse", "cor": "#f43f5e",
            "texto": f"Síndrome de Fechamento. O baixo desempenho nos break points (Notas: Salvos {salvos_txt}/5 | Convertidos {ganhos_txt}/5) indica que o braço está 'encurtando'. Jogue com mais topspin na hora da pressão."
        })

    notas_tecnicas = {"Forehand": avg_fh, "Backhand": avg_bh, "Saque": avg_serve, "Devolução": avg_return, "Voleio": avg_volley}
    notas_validas = {k: v for k, v in notas_tecnicas.items() if v > 0}
    if notas_validas:
        pior_golpe = min(notas_validas, key=notas_validas.get)
        nota_pior = round(notas_validas[pior_golpe], 1)
        drill_txt = ""
        if pior_golpe == "Backhand": drill_txt = "Treino: Peça para cruzarem bolas altas no seu lado esquerdo. Foque apenas em bater na subida, pegando a bola cedo para cortar o tempo."
        elif pior_golpe == "Forehand": drill_txt = "Treino: Faça o drill 'Para-brisa'. Bata um forehand cruzado e o próximo na paralela, forçando a transferência de peso correta do corpo."
        elif pior_golpe == "Saque": drill_txt = "Treino: Coloque dois cones a 1 metro das linhas de saque. Saque 20 bolas usando apenas o movimento do 2º saque (foco em kick e margem)."
        elif pior_golpe == "Devolução": drill_txt = "Treino: Bloqueio de saque. Dê apenas MEIO passo para frente quando o adversário sacar, sem armar a raquete para trás."
        elif pior_golpe == "Voleio": drill_txt = "Treino: Jogo de mini-tênis (só dentro dos quadrados de saque) sem deixar a bola pingar, para melhorar o reflexo e a mão."
        
        relatorio["super_modulos"].append({
            "nome": "Prescrição de Treino", "icone": "bx-dumbbell", "cor": "#10b981",
            "texto": f"Fundamento Crítico: {pior_golpe} (Nota {nota_pior}). {drill_txt}"
        })

    # Inteligência de Superfície (No confronto direto, só compara os jogos contra a pessoa)
    base_superficie = matches if selected_opponent else all_matches
    vitorias_dura = sum(1 for m in base_superficie if m["surface"] == "Quadra Dura" and m["result"] == "Vitória")
    jogos_dura = sum(1 for m in base_superficie if m["surface"] == "Quadra Dura")
    vitorias_saibro = sum(1 for m in base_superficie if m["surface"] == "Saibro" and m["result"] == "Vitória")
    jogos_saibro = sum(1 for m in base_superficie if m["surface"] == "Saibro")
    taxa_dura = (vitorias_dura / jogos_dura) * 100 if jogos_dura > 0 else 0
    taxa_saibro = (vitorias_saibro / jogos_saibro) * 100 if jogos_saibro > 0 else 0

    if abs(taxa_dura - taxa_saibro) > 20 and jogos_dura >= 2 and jogos_saibro >= 2:
        melhor = "Quadra Dura" if taxa_dura > taxa_saibro else "Saibro"
        pior = "Saibro" if melhor == "Quadra Dura" else "Quadra Dura"
        txt_op = f"contra {selected_opponent}" if selected_opponent else ""
        relatorio["super_modulos"].append({
            "nome": "Radar de Superfície", "icone": "bx-map", "cor": "#f59e0b",
            "texto": f"Atenção: Seu rendimento {txt_op} é drasticamente superior na {melhor}. Na {pior}, você perde sua efetividade. Se for jogar na {pior}, adapte sua movimentação para ralis mais longos."
        })

    tie_breaks = 0
    decisivos = 0
    for m in matches:
        if not m["score"]: continue
        sets = [s for s in m["score"].split() if '/' in s]
        if (len(sets) == 3 and m["match_format"] and '5 Sets' not in m["match_format"]) or len(sets) == 5:
            decisivos += 1
        for s in sets:
            s_clean = re.sub(r'\(.*?\)', '', s.replace('[', '').replace(']', ''))
            parts = s_clean.split('/')
            if len(parts) == 2:
                try:
                    p1, p2 = int(parts[0]), int(parts[1])
                    if (p1 == 7 and p2 == 6) or (p1 == 6 and p2 == 7) or (p1 >= 10 and abs(p1-p2)>=2) or (p2 >= 10 and abs(p1-p2)>=2):
                        tie_breaks += 1
                except ValueError: pass
    
    if decisivos >= 1 or tie_breaks >= 1:
        txt_op = f"O jogo de {selected_opponent} te arrasta" if selected_opponent else "Você está sendo arrastado"
        relatorio["super_modulos"].append({
            "nome": "Raio-X de Resistência", "icone": "bx-stopwatch", "cor": "#8b5cf6",
            "texto": f"O algoritmo detectou {tie_breaks} Tie-breaks e {decisivos} Sets Decisivos recentes. {txt_op} para maratonas. Economize energia nos games de devolução e foque 100% nos seus saques."
        })

    # Módulo E: TERMÔMETRO DE CIRCUITO (Transição de Classes) - Ideia 3
    if not selected_opponent: 
        cat_stats = {}
        for m in all_matches:
            cat_name = m["categoria"].strip() if m["categoria"] else "Sem Categoria"
            if cat_name not in cat_stats: cat_stats[cat_name] = {'v': 0, 'total': 0}
            cat_stats[cat_name]['total'] += 1
            if m["result"] == "Vitória": cat_stats[cat_name]['v'] += 1

        # A IA agora entende a hierarquia: Quanto maior o peso, mais difícil a classe
        def peso_classe(cat_str):
            c = cat_str.lower()
            if "1" in c or "primeira" in c or "pro" in c or "especial" in c: return 6
            if "2" in c or "segunda" in c: return 5
            if "3" in c or "terceira" in c: return 4
            if "4" in c or "quarta" in c: return 3
            if "5" in c or "quinta" in c: return 2
            if "iniciante" in c or "principiante" in c: return 1
            return 0 # Torneios sem classe definida

        valid_cats = []
        for cat, data in cat_stats.items():
            if data['total'] >= 1 and cat != "Sem Categoria":
                valid_cats.append({
                    "nome": cat,
                    "win_rate": round((data['v'] / data['total']) * 100),
                    "peso": peso_classe(cat)
                })

        # Organiza as classes da mais fácil para a mais difícil
        valid_cats.sort(key=lambda x: x["peso"])

        if len(valid_cats) >= 2:
            txt_stats = " | ".join([f"{c['nome']}: {c['win_rate']}%" for c in valid_cats])
            
            # Pega as duas classes mais difíceis que você jogou para comparar
            c_alta = valid_cats[-1] 
            c_baixa = valid_cats[-2] 

            if c_alta["peso"] == 0 or c_baixa["peso"] == 0:
                analise = " Observe os saltos entre as categorias para entender seu teto competitivo atual."
            elif c_alta["win_rate"] < (c_baixa["win_rate"] - 15):
                # Caso Normal: Bate nos mais fracos, sofre nos mais fortes
                analise = f" Choque de Realidade: A queda de rendimento ao subir da {c_baixa['nome']} para a {c_alta['nome']} mostra que o peso de bola adversário está cobrando o preço. Foque em profundidade antes de tentar a definição final."
            elif c_baixa["win_rate"] < (c_alta["win_rate"] - 15):
                # O Seu Caso Especial: A Anomalia Tática (Sofre nos mais fracos)
                analise = f" Anomalia Tática: Você vence {c_alta['win_rate']}% na {c_alta['nome']}, mas sofre na {c_baixa['nome']} ({c_baixa['win_rate']}%). Diagnóstico: Você joga melhor quando o adversário te dá RITMO. Em classes menores, as bolas vêm lentas e sem peso, forçando você a gerar a própria força e cometer erros. Treine atacar bolas flutuantes!"
            else:
                # Caso de Equilíbrio
                analise = f" Consistência: Seu nível está sólido e estabilizado entre a {c_baixa['nome']} e a {c_alta['nome']}."

            relatorio["super_modulos"].append({
                "nome": "Termômetro de Circuito", "icone": "bx-bar-chart-alt-2", "cor": "#0ea5e9",
                "texto": f"{txt_stats}.{analise}"
            })

    return render_template("treinador.html", relatorio=relatorio, limit=limit, total=total_base, unique_opponents=unique_opponents, selected_opponent=selected_opponent)
@app.route("/sobre")
@login_required
def sobre():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],))
    user_row = c.fetchone()
    col_names = [description[0] for description in c.description]
    user_data = dict(zip(col_names, user_row)) if user_row else {}
    conn.close()
    return render_template("sobre.html", user=user_data)

@app.route("/privacidade")
@login_required
def privacidade():
    return render_template("privacidade.html")

if __name__ == "__main__":
    app.run(debug=True)