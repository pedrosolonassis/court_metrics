import sqlite3
from flask import Flask, render_template, request, redirect

app = Flask(__name__)

def create_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
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
        winners INTEGER,         /* NOVA COLUNA */
        unforced_errors INTEGER, /* NOVA COLUNA */
        performance_rating REAL,
        notes TEXT
    )
    """)
    conn.commit()
    conn.close()

create_db()

@app.route("/")
def home():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM matches ORDER BY id DESC")
    matches = c.fetchall()
    conn.close()
    return render_template("index.html", matches=matches)

@app.route("/new_match", methods=["GET", "POST"])
def new_match():
    if request.method == "POST":
        opponent = request.form["opponent"]
        categoria = request.form["categoria"]
        match_type = request.form["match_type"]
        surface = request.form["surface"]
        result = request.form["result"]
        match_format = request.form.get("match_format", "Simples")
        partner = request.form.get("partner", "")
        opp_partner = request.form.get("opp_partner", "")
        
        s1_p, s1_o = request.form.get("set1_player", "0"), request.form.get("set1_opp", "0")
        s2_p, s2_o = request.form.get("set2_player", "0"), request.form.get("set2_opp", "0")
        s3_p, s3_o = request.form.get("set3_player", ""), request.form.get("set3_opp", "")
        
        score = f"{s1_p}/{s1_o} {s2_p}/{s2_o}"
        if s3_p and s3_o:
            score += f" {s3_p}/{s3_o}"

        f_names = ["forehand", "backhand", "serve", "first_serve", "second_serve", 
                   "double_faults", "return_serve", "slice", "volley", "smash", 
                   "dropshot", "footwork", "strategy"]
        
        notes = {f: int(request.form.get(f, 0)) for f in f_names}
        notes_list = [notes[f] for f in f_names]

        # COLETANDO OS DADOS TÁTICOS
        winners = int(request.form.get("winners", 0))
        unforced_errors = int(request.form.get("unforced_errors", 0))

        # CÁLCULO PONDERADO INTACTO (0 a 10)
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
        footwork, strategy, winners, unforced_errors, performance_rating, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (opponent, categoria, match_type, surface, result, score, match_format, 
              partner, opp_partner, *notes_list, winners, unforced_errors, perf, request.form.get("notes", "")))
        
        conn.commit()
        conn.close()
        return redirect("/")
    
    return render_template("new_match.html")

if __name__ == "__main__":
    app.run(debug=True)