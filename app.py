import sqlite3
import csv
import io
import os
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, Response, session, flash
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "chave_super_secreta_court_metrics" # Necessário para segurança da sessão

# --- CONFIGURAÇÃO DA PASTA DE UPLOADS (FOTOS DE PERFIL E FEEDBACK) ---
UPLOAD_FOLDER = 'static/uploads/profiles'
FEEDBACK_FOLDER = 'static/uploads/feedback'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['FEEDBACK_FOLDER'] = FEEDBACK_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(FEEDBACK_FOLDER, exist_ok=True)

def create_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    
    # 1. CRIA A TABELA DE USUÁRIOS (Atualizada com novos campos)
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

    # 3. TABELA DE FEEDBACKS (NOVA)
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
        
        # VALIDAÇÕES DE SENHA
        if password != confirm_password:
            return render_template("register.html", error="As senhas não coincidem.")
        if len(password) < 6:
            return render_template("register.html", error="A senha deve ter no mínimo 6 caracteres.")
        
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        
        # Verifica se o usuário ou e-mail já existe
        c.execute("SELECT * FROM users WHERE username = ? OR email = ?", (username, email))
        if c.fetchone():
            conn.close()
            return render_template("register.html", error="Este Nome de Usuário ou E-mail já está em uso.")
        
        # Cria o usuário com senha criptografada e novos campos
        hashed_password = generate_password_hash(password)
        c.execute("""
            INSERT INTO users (username, password, first_name, last_name, email, birth_date) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (username, hashed_password, first_name, last_name, email, birth_date))
        new_user_id = c.lastrowid
        
        # MIGRAÇÃO INTELIGENTE: A primeira conta herda os jogos antigos que estavam sem dono
        c.execute("UPDATE matches SET user_id = ? WHERE user_id IS NULL", (new_user_id,))
        
        conn.commit()
        conn.close()
        
        # Loga automaticamente após o registro e salva os dados na sessão
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
        conn.row_factory = sqlite3.Row # Usa dicionário para evitar erros de índice
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session["user_id"] = user['id']
            session["username"] = user['username']
            session["first_name"] = user['first_name']
            session["last_name"] = user['last_name']
            session["profile_pic"] = user['profile_pic'] # Adiciona a foto à sessão
            return redirect("/")
        else:
            return render_template("login.html", error="Usuário ou senha incorretos.")
            
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ==============================================================================
# --- ROTAS DO SISTEMA (AGORA PROTEGIDAS PELO @login_required) ---
# ==============================================================================

@app.route("/")
@login_required
def home():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    # Busca apenas os jogos do usuário logado
    c.execute("SELECT * FROM matches WHERE user_id = ? ORDER BY match_date DESC, id DESC", (session["user_id"],))
    matches = c.fetchall()
    
    # Busca as informações de perfil e transforma em dicionário para não quebrar o HTML antigo
    c.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],))
    user_row = c.fetchone()
    col_names = [description[0] for description in c.description]
    user_data = dict(zip(col_names, user_row)) if user_row else {}
    conn.close()

    # Lógica: Última vez que jogou
    ultima_partida = "Sem registros"
    if matches:
        last_date_str = matches[0][27] # match_date é o índice 27
        try:
            last_date = datetime.strptime(last_date_str, '%Y-%m-%d').date()
            hoje = datetime.today().date()
            delta = (hoje - last_date).days
            if delta == 0: ultima_partida = "Hoje"
            elif delta == 1: ultima_partida = "Ontem"
            else: ultima_partida = f"há {delta} dias"
        except:
            pass

    # Lógica: Há quanto tempo joga
    tempo_joga = "Não informado"
    if user_data.get('playing_since'):
        try:
            start_date = datetime.strptime(user_data['playing_since'], '%Y-%m-%d').date()
            anos = datetime.today().year - start_date.year
            if anos == 0:
                tempo_joga = "Menos de 1 ano"
            elif anos == 1:
                tempo_joga = "há 1 ano"
            else:
                tempo_joga = f"há mais de {anos} anos"
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
        # 1. Tratar o upload da foto de perfil recortada (se houver)
        foto_filename = None
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file and file.filename != '':
                # Cria um nome de arquivo seguro vinculado ao ID do usuário
                filename = secure_filename(f"user_{session['user_id']}_profile.png")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                # Salva apenas o caminho relativo no banco de dados
                foto_filename = f"uploads/profiles/{filename}"

        # 2. Atualizar os outros dados do usuário
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

        # Só atualiza o banco com a foto se uma nova foi enviada
        if foto_filename:
            update_query += ", profile_pic=?"
            params.append(foto_filename)
            session["profile_pic"] = foto_filename # Atualiza a sessão instantaneamente

        update_query += " WHERE id=?"
        params.append(session["user_id"])

        c.execute(update_query, tuple(params))
        
        session["first_name"] = request.form.get("first_name")
        session["last_name"] = request.form.get("last_name")
        
        conn.commit()
        conn.close()
        return redirect("/perfil")

    # Resgata os dados para preencher o formulário no GET
    c.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],))
    user_row = c.fetchone()
    user_data = dict(user_row) if user_row else {}
    
    # Previne que a foto suma da tela caso a sessão tenha sido perdida mas o banco não
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
    
    filters = {
        "surface": f_surface,
        "match_type": f_type,
        "match_format": f_format
    }
    
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
        opponent = request.form["opponent"]
        categoria = request.form["categoria"]
        match_type = request.form["match_type"]
        surface = request.form["surface"]
        result = request.form["result"]
        
        match_format = request.form.get("match_format", "1 Set")
        game_format = request.form.get("game_format", "6")
        partner = request.form.get("partner", "")
        opp_partner = request.form.get("opp_partner", "")
        match_date = request.form.get("match_date", datetime.today().strftime('%Y-%m-%d'))
        
        score = request.form.get("final_score", "")

        f_names = ["forehand", "backhand", "serve", "first_serve", "second_serve", 
                   "double_faults", "return_serve", "slice", "volley", "smash", 
                   "dropshot", "footwork", "strategy"]
        
        notes = {f: int(request.form.get(f, 0)) for f in f_names}
        notes_list = [notes[f] for f in f_names]

        winners = int(request.form.get("winners", 0))
        unforced_errors = int(request.form.get("unforced_errors", 0))

        primarios = [notes['forehand'], notes['backhand'], notes['serve']]
        v_prim = [n for n in primarios if n > 0]
        m_prim = sum(v_prim)/len(v_prim) if v_prim else 0

        secundarios = [notes['return_serve'], notes['footwork'], notes['strategy']]
        v_sec = [n for n in secundarios if n > 0]
        m_sec = sum(v_sec)/len(v_sec) if v_sec else 0

        especificos = [notes['slice'], notes['volley'], notes['smash'], notes['dropshot']]
        v_esp = [n for n in especificos if n > 0]
        m_esp = sum(v_esp)/len(v_esp) if v_esp else 0

        perf = (m_prim * 0.5) + (m_sec * 0.3) + (m_esp * 0.2)
        perf = round(perf, 1)

        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("""
        INSERT INTO matches (opponent, categoria, match_type, surface, result, score, 
        match_format, partner, opp_partner, forehand, backhand, serve, first_serve, 
        second_serve, double_faults, return_serve, slice, volley, smash, dropshot, 
        footwork, strategy, winners, unforced_errors, performance_rating, notes, match_date, game_format, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (opponent, categoria, match_type, surface, result, score, match_format, 
              partner, opp_partner, *notes_list, winners, unforced_errors, perf, request.form.get("notes", ""), match_date, game_format, session["user_id"]))
        
        conn.commit()
        conn.close()
        return redirect("/")
    
    return render_template("new_match.html")

@app.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_match(id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    
    if request.method == "POST":
        opponent = request.form["opponent"]
        categoria = request.form["categoria"]
        match_type = request.form["match_type"]
        surface = request.form["surface"]
        result = request.form["result"]
        
        match_format = request.form.get("match_format", "1 Set")
        game_format = request.form.get("game_format", "6")
        partner = request.form.get("partner", "")
        opp_partner = request.form.get("opp_partner", "")
        match_date = request.form.get("match_date", datetime.today().strftime('%Y-%m-%d'))
        
        score = request.form.get("final_score", request.form.get("score", ""))

        f_names = ["forehand", "backhand", "serve", "first_serve", "second_serve", 
                   "double_faults", "return_serve", "slice", "volley", "smash", 
                   "dropshot", "footwork", "strategy"]
        
        notes = {f: int(request.form.get(f, 0)) for f in f_names}
        notes_list = [notes[f] for f in f_names]

        winners = int(request.form.get("winners", 0))
        unforced_errors = int(request.form.get("unforced_errors", 0))

        primarios = [notes['forehand'], notes['backhand'], notes['serve']]
        v_prim = [n for n in primarios if n > 0]
        m_prim = sum(v_prim)/len(v_prim) if v_prim else 0

        secundarios = [notes['return_serve'], notes['footwork'], notes['strategy']]
        v_sec = [n for n in secundarios if n > 0]
        m_sec = sum(v_sec)/len(v_sec) if v_sec else 0

        especificos = [notes['slice'], notes['volley'], notes['smash'], notes['dropshot']]
        v_esp = [n for n in especificos if n > 0]
        m_esp = sum(v_esp)/len(v_esp) if v_esp else 0

        perf = (m_prim * 0.5) + (m_sec * 0.3) + (m_esp * 0.2)
        perf = round(perf, 1)

        c.execute("""
        UPDATE matches SET 
        opponent=?, categoria=?, match_type=?, surface=?, result=?, score=?, 
        match_format=?, partner=?, opp_partner=?, forehand=?, backhand=?, serve=?, first_serve=?, 
        second_serve=?, double_faults=?, return_serve=?, slice=?, volley=?, smash=?, dropshot=?, 
        footwork=?, strategy=?, winners=?, unforced_errors=?, performance_rating=?, notes=?, match_date=?, game_format=?
        WHERE id=? AND user_id=?
        """, (opponent, categoria, match_type, surface, result, score, match_format, 
              partner, opp_partner, *notes_list, winners, unforced_errors, perf, request.form.get("notes", ""), match_date, game_format, id, session["user_id"]))
        
        conn.commit()
        conn.close()
        return redirect("/")
    
    else:
        # Garante que só pode editar a própria partida
        c.execute("SELECT * FROM matches WHERE id = ? AND user_id = ?", (id, session["user_id"]))
        match = c.fetchone()
        conn.close()
        if match:
            return render_template("edit_match.html", match=match)
        return redirect("/")

@app.route("/delete/<int:id>", methods=["POST"])
@login_required
def delete_match(id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    # Garante que só pode deletar a própria partida
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
    c.execute("SELECT * FROM matches WHERE user_id = ? ORDER BY match_date DESC", (session["user_id"],))
    matches = c.fetchall()
    column_names = [description[0] for description in c.description]
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(column_names)
    writer.writerows(matches)
    
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=meus_dados_tenis.csv"}
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

    if not matches:
        return redirect("/")

    streak_type = matches[0][5] if matches[0][5] else "Sem Dados"
    streak_count = 0
    for m in matches:
        if m[5] == streak_type:
            streak_count += 1
        else:
            break

    stats = {
        'streak_type': streak_type,
        'streak_count': streak_count,
        'surface': {'Quadra Dura': {'v': 0, 'd': 0}, 'Saibro': {'v': 0, 'd': 0}},
        'format': {'Simples': {'v': 0, 'd': 0}, 'Duplas': {'v': 0, 'd': 0}},
        'type': {'Ranking': {'v': 0, 'd': 0}, 'Torneio': {'v': 0, 'd': 0}, 'Amistoso': {'v': 0, 'd': 0}},
        'category': {}, 
        'tb_won': 0, 'tb_lost': 0,
        'decisive_won': 0, 'decisive_lost': 0,
        'perf_wins': 0, 'perf_losses': 0, 
        'count_wins': 0, 'count_losses': 0,
        'winners_total': 0, 'ue_total': 0
    }

    for m in matches:
        is_win = m[5] == 'Vitória'
        
        if is_win:
            stats['count_wins'] += 1
            stats['perf_wins'] += m[25]
        else:
            stats['count_losses'] += 1
            stats['perf_losses'] += m[25]
            
        stats['winners_total'] += m[23]
        stats['ue_total'] += m[24]

        if m[4] and m[4] in stats['surface']: stats['surface'][m[4]]['v' if is_win else 'd'] += 1
        if m[3] and m[3] in stats['type']: stats['type'][m[3]]['v' if is_win else 'd'] += 1
        
        cat = m[2] if m[2] else 'Sem Classe'
        if cat not in stats['category']: stats['category'][cat] = {'v': 0, 'd': 0}
        stats['category'][cat]['v' if is_win else 'd'] += 1
        
        fmt_cat = 'Duplas' if m[7] and 'Duplas' in str(m[7]) else 'Simples'
        stats['format'][fmt_cat]['v' if is_win else 'd'] += 1

        if m[6]: 
            sets = [s for s in m[6].split() if '/' in s and s.strip() != '/' and s.strip() != '0/0']
            for s in sets:
                parts = s.split('/')
                if len(parts) == 2:
                    try:
                        p1 = int(parts[0].replace('[', ''))
                        p2 = int(parts[1].split(' ')[0].replace(']', '').replace('(', '').replace(')', ''))
                        if (p1 == 7 and p2 == 6) or (p1 >= 10 and p1 - p2 >= 2):
                            stats['tb_won'] += 1
                        elif (p1 == 6 and p2 == 7) or (p2 >= 10 and p2 - p1 >= 2):
                            stats['tb_lost'] += 1
                    except ValueError:
                        pass
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

    return render_template("insights.html", stats=stats, matches=matches)

@app.route("/simulador", methods=["GET", "POST"])
@login_required
def simulador():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    # Puxa o histórico do usuário para treinar a IA
    c.execute("SELECT surface, performance_rating, winners, unforced_errors, result FROM matches WHERE user_id = ?", (session["user_id"],))
    matches = c.fetchall()
    conn.close()

    # Regra 1: Precisa de dados suficientes
    if len(matches) < 5:
        return render_template("simulador.html", erro_dados="Jogue mais! O Oráculo precisa de pelo menos 5 partidas registradas para aprender seus padrões.")

    if request.method == "POST":
        sim_surface = request.form["surface"]
        sim_rating = float(request.form["rating"])
        # Fator de agressividade: Winners dividido por Erros (soma 1 para evitar divisão por zero)
        sim_agressividade = float(request.form["winners"]) / (float(request.form["erros"]) + 1)

        try:
            from sklearn.linear_model import LogisticRegression
            import numpy as np

            X = []
            y = []
            for m in matches:
                is_saibro = 1 if m[0] == 'Saibro' else 0
                rating = m[1]
                agr = m[2] / (m[3] + 1)
                target = 1 if m[4] == 'Vitória' else 0
                
                X.append([is_saibro, rating, agr])
                y.append(target)

            # Regra 2: A IA precisa conhecer os dois lados da moeda
            if len(set(y)) < 2:
                return render_template("simulador.html", erro_dados="O Oráculo precisa de exemplos tanto de Vitórias quanto de Derrotas no seu histórico para aprender a diferença.")

            # Treinando o cérebro da IA
            model = LogisticRegression()
            model.fit(X, y)

            # Fazendo a Previsão
            is_saibro_sim = 1 if sim_surface == 'Saibro' else 0
            cenario = np.array([[is_saibro_sim, sim_rating, sim_agressividade]])
            
            # Pega a probabilidade de vitória (classe 1)
            probabilidade = model.predict_proba(cenario)[0][1] * 100

            return render_template("simulador.html", 
                                   probabilidade=round(probabilidade, 1),
                                   surface=sim_surface, 
                                   rating=sim_rating)

        except Exception as e:
            return render_template("simulador.html", erro_dados=f"Erro no Motor de IA: {str(e)}")

    return render_template("simulador.html")

@app.route("/sobre")
@login_required
def sobre():
    # Passamos os dados do usuário para o cabeçalho funcionar corretamente
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