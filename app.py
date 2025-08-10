import os
import threading
import webbrowser
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, make_response, jsonify
from werkzeug.utils import secure_filename
import pandas as pd
import datetime
import io

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "supersecretkey")

INVENTORY_FILE = "inventory.xlsx"
HISTORY_FILE = "history.csv"
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "backgrounds")
ALLOWED_EXTENSIONS_IMAGE = {"png", "jpg", "jpeg", "gif"}
ALLOWED_EXTENSIONS_VIDEO = {"mp4"}
ALLOWED_EXTENSIONS = ALLOWED_EXTENSIONS_IMAGE | ALLOWED_EXTENSIONS_VIDEO
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_video(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS_VIDEO

def allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS_IMAGE

def ensure_inventory_file():
    if not os.path.exists(INVENTORY_FILE):
        df = pd.DataFrame(columns=[
            "Category", "Subcategory", "Item", "Brand/Type", "Length/Capacity", "Quantity", "Notes"
        ])
        df.to_excel(INVENTORY_FILE, index=False)

def load_inventory():
    ensure_inventory_file()
    return pd.read_excel(INVENTORY_FILE)

def save_inventory(df):
    df.to_excel(INVENTORY_FILE, index=False)

def get_background_url():
    video_path = os.path.join(app.config["UPLOAD_FOLDER"], "background.mp4")
    if os.path.exists(video_path):
        return url_for('static', filename='backgrounds/background.mp4'), 'video'
    for ext in ALLOWED_EXTENSIONS_IMAGE:
        img_path = os.path.join(app.config["UPLOAD_FOLDER"], f"background.{ext}")
        if os.path.exists(img_path):
            return url_for('static', filename=f'backgrounds/background.{ext}'), 'image'
    return None, None

def log_history(action, details, restore_data=None):
    dt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_exists = os.path.exists(HISTORY_FILE)
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        if not log_exists:
            f.write("Timestamp,Action,Details,RestoreData\n")
        safe_details = str(details).replace('"', '""')
        safe_restore = str(restore_data) if restore_data else ""
        safe_restore = safe_restore.replace('"', '""')
        f.write(f'"{dt}","{action}","{safe_details}","{safe_restore}"\n')

@app.route("/", methods=["GET", "POST"])
def index():
    df = load_inventory()
    search_query = request.form.get("search", "")
    if not search_query:
        search_query = request.args.get("search", "")
    if search_query:
        filtered = df.apply(lambda row: search_query.lower() in str(row).lower(), axis=1)
        df = df[filtered]
    items = df.to_dict(orient="records")
    background_url, bg_type = get_background_url()
    theme_color = request.cookies.get('theme_color', '#f8f9fa')
    return render_template("index.html", items=items, search=search_query, background_url=background_url, bg_type=bg_type, theme_color=theme_color)

@app.route("/search")
def live_search():
    query = request.args.get("search", "")
    df = load_inventory()
    if query:
        filtered = df.apply(lambda row: query.lower() in str(row).lower(), axis=1)
        df = df[filtered]
    items = df.to_dict(orient="records")
    return jsonify({"items": items})

@app.route("/add", methods=["GET", "POST"])
def add():
    background_url, bg_type = get_background_url()
    theme_color = request.cookies.get('theme_color', '#f8f9fa')
    if request.method == "POST":
        df = load_inventory()
        new_item = {
            "Category": request.form.get("category", ""),
            "Subcategory": request.form.get("subcategory", ""),
            "Item": request.form.get("item", ""),
            "Brand/Type": request.form.get("brand_type", ""),
            "Length/Capacity": request.form.get("length_capacity", ""),
            "Quantity": int(request.form.get("quantity", "0")),
            "Notes": request.form.get("notes", "")
        }
        df = pd.concat([df, pd.DataFrame([new_item])], ignore_index=True)
        save_inventory(df)
        log_history("Add", f"Added item: {new_item}")
        flash("Product added successfully.", "success")
        return redirect(url_for("index"))
    return render_template("add.html", background_url=background_url, bg_type=bg_type, theme_color=theme_color)

@app.route("/remove/<int:row>", methods=["POST"])
def remove(row):
    df = load_inventory()
    if 0 <= row < len(df):
        removed_item = df.iloc[row].to_dict()
        df = df.drop(df.index[row])
        df = df.reset_index(drop=True)
        save_inventory(df)
        log_history("Remove", f"Removed item: {removed_item}", restore_data=removed_item)
        flash("Product removed successfully.", "success")
    else:
        flash("Invalid item selected.", "danger")
    return redirect(url_for("index"))

@app.route("/undo/<timestamp>", methods=["POST"])
def undo(timestamp):
    import csv
    restored = False
    history_rows = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, newline='', encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                history_rows.append(row)
    to_restore = None
    for row in history_rows:
        if row['Timestamp'] == timestamp and row['Action'] == "Remove":
            to_restore = row
            break
    if to_restore and to_restore.get('RestoreData'):
        try:
            restore_data = eval(to_restore['RestoreData'])
            df = load_inventory()
            df = pd.concat([df, pd.DataFrame([restore_data])], ignore_index=True)
            save_inventory(df)
            log_history("Undo Remove", f"Restored item: {restore_data}")
            flash("Item restored successfully.", "success")
            restored = True
        except Exception as e:
            flash("Failed to restore item.", "danger")
    else:
        flash("Nothing to restore.", "danger")
    return redirect(url_for("history"))

@app.route("/update/<int:row>", methods=["GET", "POST"])
def update(row):
    df = load_inventory()
    background_url, bg_type = get_background_url()
    theme_color = request.cookies.get('theme_color', '#f8f9fa')
    if row >= len(df):
        flash("Invalid item selected!", "danger")
        return redirect(url_for("index"))
    if request.method == "POST":
        old_row = df.iloc[row].to_dict()
        df.at[row, "Quantity"] = request.form["quantity"]
        df.at[row, "Notes"] = request.form["notes"]
        save_inventory(df)
        log_history("Update", f"Before: {old_row}, After: {df.iloc[row].to_dict()}")
        flash("Item updated successfully.", "success")
        return redirect(url_for("index"))
    item = df.iloc[row].to_dict()
    return render_template("update.html", item=item, row=row, background_url=background_url, bg_type=bg_type, theme_color=theme_color)

@app.route("/analyze")
def analyze():
    df = load_inventory()
    total_items = len(df)
    total_quantity = df["Quantity"].sum() if "Quantity" in df else 0
    low_stock = df[df["Quantity"] <= 5] if "Quantity" in df else pd.DataFrame()

    pie_data = df["Category"].value_counts().to_dict()
    bar_data = df.groupby("Category")["Quantity"].sum().to_dict()

    background_url, bg_type = get_background_url()
    theme_color = request.cookies.get('theme_color', '#f8f9fa')
    return render_template(
        "analyze.html",
        total_items=total_items,
        total_quantity=total_quantity,
        low_stock=low_stock.to_dict(orient="records"),
        pie_data=pie_data,
        bar_data=bar_data,
        background_url=background_url,
        bg_type=bg_type,
        theme_color=theme_color
    )

@app.route("/export")
def export_excel():
    return send_file(INVENTORY_FILE, as_attachment=True)

@app.route("/export_csv")
def export_csv():
    df = load_inventory()
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return send_file(
        io.BytesIO(buf.getvalue().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name='inventory.csv'
    )

@app.route("/customise", methods=["GET", "POST"])
def customise():
    background_url, bg_type = get_background_url()
    theme_color = request.cookies.get('theme_color', '#f8f9fa')

    if request.method == "POST":
        # Handle background removal
        if "remove_background" in request.form:
            for e in ALLOWED_EXTENSIONS:
                try:
                    os.remove(os.path.join(app.config["UPLOAD_FOLDER"], f"background.{e}"))
                except FileNotFoundError:
                    pass
            flash("Background removed!", "success")
            return redirect(url_for("customise"))

        # Handle color selection
        color = request.form.get("theme_color", "#f8f9fa")
        resp = make_response(redirect(url_for("customise")))
        resp.set_cookie("theme_color", color, max_age=60*60*24*365)

        # Handle background upload
        file = request.files.get("background")
        if file and allowed_file(file.filename):
            filename = "background"
            ext = file.filename.rsplit('.', 1)[1].lower()

            # Remove any existing backgrounds
            for e in ALLOWED_EXTENSIONS:
                try:
                    os.remove(os.path.join(app.config["UPLOAD_FOLDER"], f"background.{e}"))
                except Exception:
                    pass

            # Save new file
            path = os.path.join(app.config["UPLOAD_FOLDER"], f"{filename}.{ext}")
            file.save(path)
            flash("Background updated!", "success")

        elif file and not allowed_file(file.filename):
            flash("Invalid file type. Please upload an image or MP4 video.", "danger")

        return resp

    return render_template("customise.html", background_url=background_url, bg_type=bg_type, theme_color=theme_color)

@app.route("/history")
def history():
    history_data = []
    if os.path.exists(HISTORY_FILE):
        import csv
        with open(HISTORY_FILE, newline='', encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            history_data = list(reader)
    background_url, bg_type = get_background_url()
    theme_color = request.cookies.get('theme_color', '#f8f9fa')
    return render_template("history.html", history_data=history_data, background_url=background_url, bg_type=bg_type, theme_color=theme_color)

def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000/")

if __name__ == "__main__":
    ensure_inventory_file()
    app.run(host="0.0.0.0", port=5000, debug=True)
