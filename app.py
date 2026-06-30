import os
import sqlite3
from flask import Flask, render_template_string, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.urandom(24)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tiles.db")

# Setup Image Upload Folder
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER): 
    os.makedirs(UPLOAD_FOLDER)

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, username TEXT UNIQUE NOT NULL, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, category TEXT, size TEXT, description TEXT, price REAL, stock INTEGER, image_url TEXT)''')
    conn.commit()
    conn.close()

init_db()

def read_html_template(filename):
    with open(os.path.join(BASE_DIR, filename), "r", encoding="utf-8") as file:
        return file.read()

# ==========================================
# --- CUSTOMER & SHOWROOM ROUTES ---
# ==========================================
@app.route("/")
def home():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM inventory")
    tiles = cursor.fetchall()
    conn.close()
    return render_template_string(read_html_template("index.html"), tiles=tiles)

@app.route("/about")
def about():
    return render_template_string(read_html_template("about.html"))
@app.route("/privacy")
def privacy():
    return render_template_string(read_html_template("privacy.html"))
@app.route("/tile/<int:tile_id>")
def tile_detail(tile_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM inventory WHERE id = ?", (tile_id,))
    tile = cursor.fetchone()
    
    # Get 4 related tiles from the same category
    if tile:
        cursor.execute("SELECT * FROM inventory WHERE category = ? AND id != ? LIMIT 4", (tile['category'], tile_id))
        related_tiles = cursor.fetchall()
    else:
        related_tiles = []
    conn.close()
    
    if not tile: return redirect(url_for("home"))
    return render_template_string(read_html_template("tile_detail.html"), tile=tile, related_tiles=related_tiles)

@app.route("/checkout/<int:tile_id>")
def checkout(tile_id):
    # Ensure customer is logged in to buy
    if "customer" not in session:
        return redirect(url_for("customer_auth"))

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM inventory WHERE id = ?", (tile_id,))
    tile = cursor.fetchone()
    conn.close()
    
    if not tile: return redirect(url_for("home"))
    return render_template_string(read_html_template("checkout.html"), tile=tile)

@app.route("/order/<int:tile_id>", methods=["POST"])
def process_order(tile_id):
    if "customer" not in session: return redirect(url_for("customer_auth"))
    

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT stock FROM inventory WHERE id = ?", (tile_id,))
    row = cursor.fetchone()
    
    if row and row[0] >= 1:
        cursor.execute("UPDATE inventory SET stock = ? WHERE id = ?", (row[0] - 1, tile_id))
        conn.commit()
    conn.close()
    
    # Send them back to showroom after successful purchase
    return redirect(url_for("home"))

@app.route("/support")
def support():
    return render_template_string(read_html_template("support.html"))

@app.route("/customer/auth", methods=["GET"])
@app.route("/login", methods=["GET"])
def customer_auth():
    if "customer" in session: return redirect(url_for("home"))
    return render_template_string(read_html_template("customer_auth.html"), msg=None, show_register=False)

@app.route("/customer/register", methods=["POST"])
def customer_register():
    name = request.form.get("name", "").strip()
    username = request.form.get("username", "").strip().lower()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    hashed_password = generate_password_hash(password)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (name, username, email, password) VALUES (?, ?, ?, ?)", (name, username, email, hashed_password))
        conn.commit()
        return render_template_string(read_html_template("customer_auth.html"), msg="Registration successful! Please sign in.", show_register=False)
    except sqlite3.IntegrityError:
        return render_template_string(read_html_template("customer_auth.html"), msg="Username or Email exists.", show_register=True)
    finally:
        conn.close()

@app.route("/customer/login", methods=["POST"])
def customer_login():
    identity = request.form.get("identity", request.form.get("username", "")).strip().lower()
    password = request.form.get("password", "")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, password FROM users WHERE username = ? OR email = ?", (identity, identity))
    user_record = cursor.fetchone()
    conn.close()

    if user_record and check_password_hash(user_record[1], password):
        session["customer"] = identity
        session["customer_name"] = user_record[0]
        return redirect(url_for("home"))

    return render_template_string(read_html_template("customer_auth.html"), msg="Invalid credentials.", show_register=False)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ==========================================
# --- ADMIN / STAFF PORTAL ROUTES ---
# ==========================================
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if "admin" in session: return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        if request.form.get("username") == "admin" and request.form.get("password") == "ggtiles123":
            session["admin"] = "admin"
            return redirect(url_for("admin_dashboard"))
        return render_template_string(read_html_template("login.html"), error="Invalid credentials.")
    return render_template_string(read_html_template("login.html"), error=None)

@app.route("/admin")
def admin_dashboard():
    if "admin" not in session: return redirect(url_for("admin_login"))
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM inventory")
    inventory = cursor.fetchall()
    cursor.execute("SELECT SUM(stock) FROM inventory")
    total_stock = cursor.fetchone()[0] or 0
    conn.close()
    return render_template_string(read_html_template("admin.html"), inventory=inventory, total_stock=total_stock)

@app.route("/admin/add_tile", methods=["POST"])
def add_tile():
    if "admin" not in session: return redirect(url_for("admin_login"))
    
    file = request.files.get('image_file')
    filename = ""
    if file and file.filename:
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    
    # Save the relative path for static serving
    db_img_path = f"uploads/{filename}" if filename else ""

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO inventory (name, category, size, description, price, stock, image_url) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                   (request.form['name'], request.form['category'], request.form['size'], request.form['description'], float(request.form['price']), int(request.form['stock']), db_img_path))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/edit_tile/<int:tile_id>", methods=["POST"])
def edit_tile(tile_id):
    if "admin" not in session: return redirect(url_for("admin_login"))
    
    file = request.files.get('image_file')
    new_price = request.form.get("price", "0")
    new_stock = request.form.get("stock", "0")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if file and file.filename:
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        db_img_path = f"uploads/{filename}"
        cursor.execute("UPDATE inventory SET price = ?, stock = ?, image_url = ? WHERE id = ?", (float(new_price), int(new_stock), db_img_path, tile_id))
    else:
        # If no new file uploaded, just update price and stock
        cursor.execute("UPDATE inventory SET price = ?, stock = ? WHERE id = ?", (float(new_price), int(new_stock), tile_id))
        
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))

if __name__ == "__main__":
    app.run(debug=True, port=5000)