import sqlite3
import csv
import io
from flask import Flask, render_template, request, redirect, Response

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
        winners INTEGER,         /* CORRIGIDO: Retornou para winners */
        unforced_errors INTEGER, /* CORRIGIDO: Retornou para erros não forçados */
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
    
    # Capturando os filtros da URL
    f_surface = request.args.get("surface", "")
    f_type = request.args.get("match_type", "")
    f_format = request.args.get("match_format", "")
    
    # Montando a consulta SQL dinamicamente
    query = "SELECT * FROM matches WHERE 1=1"
    params = []
    
    if f_surface:
        query += " AND surface = ?"
        params.append(f_surface)
    if f_type:
        query += " AND match_type = ?"
        params.append(f_type)
    if f_format:
        query += " AND match_format = ?"
        params.append(f_format)
        
    query += " ORDER BY id DESC"
    
    c.execute(query, params)
    matches = c.fetchall()
    conn.close()
    
    # Passando os filtros atuais de volta para o HTML
    filters = {
        "surface": f_surface,
        "match_type": f_type,
        "match_format": f_format
    }
    
    return render_template("index.html", matches=matches, filters=filters)

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

        # CORRIGIDO: Voltando a coletar Winners e Erros
        winners = int(request.form.get("winners", 0))
        unforced_errors = int(request.form.get("unforced_errors", 0))

        # Cálculo Final Ponderado
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

# --- ROTA DE EXPORTAÇÃO CSV ---
@app.route("/export")
def export_csv():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM matches ORDER BY id DESC")
    matches = c.fetchall()
    
    # Pegando os nomes das colunas
    column_names = [description[0] for description in c.description]
    conn.close()

    # Criando o arquivo CSV na memória
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';') # Ponto e vírgula evita problemas no Excel pt-BR
    
    writer.writerow(column_names)
    writer.writerows(matches)
    
    # Preparando a resposta para forçar o download
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=meus_dados_tenis.csv"}
    )

# --- ROTA DE EXCLUSÃO ---
@app.route("/delete/<int:id>", methods=["POST"])
def delete_match(id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("DELETE FROM matches WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect("/")

# --- ROTA DE EDIÇÃO ---
@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_match(id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    
    if request.method == "POST":
        # Copiamos exatamente a mesma lógica do new_match para calcular tudo de novo
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

        # A diferença aqui é o UPDATE em vez de INSERT
        c.execute("""
        UPDATE matches SET 
        opponent=?, categoria=?, match_type=?, surface=?, result=?, score=?, 
        match_format=?, partner=?, opp_partner=?, forehand=?, backhand=?, serve=?, first_serve=?, 
        second_serve=?, double_faults=?, return_serve=?, slice=?, volley=?, smash=?, dropshot=?, 
        footwork=?, strategy=?, winners=?, unforced_errors=?, performance_rating=?, notes=?
        WHERE id=?
        """, (opponent, categoria, match_type, surface, result, score, match_format, 
              partner, opp_partner, *notes_list, winners, unforced_errors, perf, request.form.get("notes", ""), id))
        
        conn.commit()
        conn.close()
        return redirect("/")
    
    else:
        # Se for GET, busca os dados da partida para preencher a tela de edição
        c.execute("SELECT * FROM matches WHERE id = ?", (id,))
        match = c.fetchone()
        conn.close()
        return render_template("edit_match.html", match=match)

if __name__ == "__main__":
    app.run(debug=True)