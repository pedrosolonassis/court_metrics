import sqlite3
from flask import Flask, render_template, request, redirect

app = Flask(__name__)

def create_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    # Tabela robusta com todos os campos necessários
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
        performance_rating REAL,
        notes TEXT
    )
    """)
    conn.commit()
    conn.close()

# Inicializa o banco ao rodar o app
create_db()

@app.route("/")
def home():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    # Puxa as partidas mais recentes primeiro
    c.execute("SELECT * FROM matches ORDER BY id DESC")
    matches = c.fetchall()
    conn.close()
    return render_template("index.html", matches=matches)

@app.route("/new_match", methods=["GET", "POST"])
def new_match():
    if request.method == "POST":
        # 1. Dados Básicos do Formulário
        opponent = request.form["opponent"]
        categoria = request.form["categoria"]
        match_type = request.form["match_type"]
        surface = request.form["surface"]
        result = request.form["result"]
        match_format = request.form.get("match_format", "Simples")
        partner = request.form.get("partner", "")
        opp_partner = request.form.get("opp_partner", "")
        
        # 2. Formatação do Placar (Ex: 6/4 6/2)
        s1_p, s1_o = request.form.get("set1_player", "0"), request.form.get("set1_opp", "0")
        s2_p, s2_o = request.form.get("set2_player", "0"), request.form.get("set2_opp", "0")
        s3_p, s3_o = request.form.get("set3_player", ""), request.form.get("set3_opp", "")
        
        score = f"{s1_p}/{s1_o} {s2_p}/{s2_o}"
        if s3_p and s3_o:
            score += f" {s3_p}/{s3_o}"

        # 3. Coleta das Notas
        # Ordem exata para o banco: forehand[0], backhand[1], serve[2], first[3], second[4], 
        # double[5], return[6], slice[7], volley[8], smash[9], drop[10], foot[11], strat[12]
        f_names = ["forehand", "backhand", "serve", "first_serve", "second_serve", 
                   "double_faults", "return_serve", "slice", "volley", "smash", 
                   "dropshot", "footwork", "strategy"]
        
        notes = {f: int(request.form.get(f, 0)) for f in f_names}
        notes_list = [notes[f] for f in f_names]

        # --- FASE 4: NOVO SISTEMA DE PERFORMANCE (PESOS PONDERADOS) ---
        
        # Grupo 1: Primários (Peso 50%) - O coração do seu jogo
        primarios = [notes['forehand'], notes['backhand'], notes['serve']]
        v_prim = [n for n in primarios if n > 0]
        m_prim = sum(v_prim)/len(v_prim) if v_prim else 0

        # Grupo 2: Secundários (Peso 30%) - Fundamentos de base
        secundarios = [notes['return_serve'], notes['footwork'], notes['strategy']]
        v_sec = [n for n in secundarios if n > 0]
        m_sec = sum(v_sec)/len(v_sec) if v_sec else 0

        # Grupo 3: Específicos (Peso 20%) - Finalização e variação
        especificos = [notes['slice'], notes['volley'], notes['smash'], notes['dropshot']]
        v_esp = [n for n in especificos if n > 0]
        m_esp = sum(v_esp)/len(v_esp) if v_esp else 0

        # Cálculo Final Ponderado
        # Se um grupo estiver zerado, redistribuímos o peso para os outros
        perf = (m_prim * 0.5) + (m_sec * 0.3) + (m_esp * 0.2)
        perf = round(perf, 1)

        # 4. Inserção no Banco de Dados
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("""
        INSERT INTO matches (opponent, categoria, match_type, surface, result, score, 
        match_format, partner, opp_partner, forehand, backhand, serve, first_serve, 
        second_serve, double_faults, return_serve, slice, volley, smash, dropshot, 
        footwork, strategy, performance_rating, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (opponent, categoria, match_type, surface, result, score, match_format, 
              partner, opp_partner, *notes_list, perf, request.form.get("notes", "")))
        
        conn.commit()
        conn.close()
        return redirect("/")
    
    return render_template("new_match.html")

if __name__ == "__main__":
    app.run(debug=True)